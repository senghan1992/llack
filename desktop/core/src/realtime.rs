//! WebSocket client: reconnect with backoff, heartbeats, and gap detection.
//!
//! The gateway stamps every frame with a monotonic `seq`. If the client sees a
//! jump, it missed events, and the only safe response is to re-fetch the
//! affected channels rather than render a transcript with holes in it. That is
//! surfaced as [`RealtimeEvent::GapDetected`].

use std::sync::Arc;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message as WsMessage;

use crate::api::ApiConfig;
use crate::error::{Error, Result};
use crate::session::Session;

const MIN_BACKOFF: Duration = Duration::from_millis(500);
const MAX_BACKOFF: Duration = Duration::from_secs(30);

/// A frame from the server.
///
/// `Serialize` as well as `Deserialize`, because the shell forwards frames
/// verbatim across the Tauri IPC boundary to the UI.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerFrame {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(default)]
    pub seq: Option<u64>,
    #[serde(default)]
    pub ts: Option<String>,
    #[serde(default)]
    pub workspace_id: Option<String>,
    #[serde(default)]
    pub data: serde_json::Value,
}

#[derive(Debug, Clone, Serialize)]
struct ClientFrame<'a> {
    #[serde(rename = "type")]
    kind: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<String>,
    data: serde_json::Value,
}

/// What the UI layer observes.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RealtimeEvent {
    /// The socket is up and `hello` was received.
    Connected {
        session_id: String,
        workspace_ids: Vec<String>,
    },
    /// The socket dropped. `will_retry_in_ms` is None when giving up.
    Disconnected {
        reason: String,
        will_retry_in_ms: Option<u64>,
    },
    /// A sequence gap: events were missed and state must be re-fetched.
    GapDetected { expected: u64, received: u64 },
    /// Any other server frame, passed through for the UI to route.
    Frame(ServerFrame),
    /// Credentials are dead; the user must sign in again.
    AuthenticationLost { message: String },
}

/// Commands the UI sends up the socket.
#[derive(Debug, Clone)]
pub enum RealtimeCommand {
    Subscribe {
        channel_ids: Vec<String>,
    },
    Unsubscribe {
        channel_ids: Vec<String>,
    },
    Typing {
        channel_id: String,
        parent_id: Option<String>,
    },
    Presence {
        state: String,
    },
    MarkRead {
        channel_id: String,
        message_id: Option<String>,
    },
    /// Drop the current socket and reconnect immediately — used when the app
    /// window regains focus after a long sleep.
    Reconnect,
    Shutdown,
}

pub struct RealtimeClient {
    config: ApiConfig,
    session: Arc<Session>,
    commands: mpsc::UnboundedSender<RealtimeCommand>,
    command_rx: Option<mpsc::UnboundedReceiver<RealtimeCommand>>,
}

impl RealtimeClient {
    pub fn new(config: ApiConfig, session: Arc<Session>) -> Self {
        let (commands, command_rx) = mpsc::unbounded_channel();
        Self {
            config,
            session,
            commands,
            command_rx: Some(command_rx),
        }
    }

    /// Handle for sending commands, cloneable and usable from anywhere.
    pub fn handle(&self) -> RealtimeHandle {
        RealtimeHandle {
            commands: self.commands.clone(),
        }
    }

    /// Run the connect/read/reconnect loop until told to shut down.
    ///
    /// Emits every event into `events`. Intended to be spawned as a task.
    pub async fn run(
        mut self,
        workspace_id: Option<String>,
        events: mpsc::UnboundedSender<RealtimeEvent>,
    ) {
        let mut command_rx = match self.command_rx.take() {
            Some(rx) => rx,
            None => return,
        };
        let mut backoff = MIN_BACKOFF;
        let mut last_seq: Option<u64> = None;

        loop {
            match self
                .connect_and_pump(
                    workspace_id.as_deref(),
                    &events,
                    &mut command_rx,
                    &mut last_seq,
                )
                .await
            {
                Ok(Disposition::Shutdown) => return,
                Ok(Disposition::Reconnect) => {
                    // Explicit reconnect: no penalty delay.
                    backoff = MIN_BACKOFF;
                    last_seq = None;
                }
                Err(err) if err.requires_reauth() => {
                    let _ = events.send(RealtimeEvent::AuthenticationLost {
                        message: err.to_string(),
                    });
                    return;
                }
                Err(err) => {
                    let _ = events.send(RealtimeEvent::Disconnected {
                        reason: err.to_string(),
                        will_retry_in_ms: Some(backoff.as_millis() as u64),
                    });
                    // Jitter avoids a thundering herd when a server restarts
                    // and every client reconnects on the same schedule.
                    let jitter =
                        Duration::from_millis(rand_u64() % (backoff.as_millis() as u64 / 2 + 1));
                    tokio::time::sleep(backoff + jitter).await;
                    backoff = (backoff * 2).min(MAX_BACKOFF);
                    // The socket may have dropped because the token expired.
                    last_seq = None;
                }
            }
        }
    }

    async fn connect_and_pump(
        &self,
        workspace_id: Option<&str>,
        events: &mpsc::UnboundedSender<RealtimeEvent>,
        commands: &mut mpsc::UnboundedReceiver<RealtimeCommand>,
        last_seq: &mut Option<u64>,
    ) -> Result<Disposition> {
        let token = self
            .session
            .access_token()
            .ok_or_else(|| Error::Unauthenticated("no access token for the gateway".into()))?;
        let url = self.config.websocket_url(&token, workspace_id);

        let (stream, _) = tokio_tungstenite::connect_async(&url)
            .await
            .map_err(|e| classify_handshake_error(&e))?;
        let (mut writer, mut reader) = stream.split();

        // Default until `hello` tells us the server's interval.
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));
        heartbeat.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        // The first tick fires immediately; skip it so we do not ping before
        // the handshake completes.
        heartbeat.tick().await;

        loop {
            tokio::select! {
                incoming = reader.next() => {
                    let Some(message) = incoming else {
                        return Err(Error::Realtime("socket closed by server".into()));
                    };
                    match message {
                        Ok(WsMessage::Text(text)) => {
                            self.handle_text(&text, events, last_seq, &mut heartbeat);
                        }
                        Ok(WsMessage::Close(frame)) => {
                            let reason = frame
                                .map(|f| format!("{} {}", f.code, f.reason))
                                .unwrap_or_else(|| "closed".into());
                            // 4001 is the gateway's "unauthorized".
                            if reason.starts_with("4001") {
                                return Err(Error::Unauthenticated(reason));
                            }
                            return Err(Error::Realtime(reason));
                        }
                        Ok(WsMessage::Ping(payload)) => {
                            let _ = writer.send(WsMessage::Pong(payload)).await;
                        }
                        Ok(_) => {}
                        Err(err) => return Err(Error::Realtime(err.to_string())),
                    }
                }

                _ = heartbeat.tick() => {
                    let frame = ClientFrame {
                        kind: "ping",
                        id: None,
                        data: serde_json::json!({}),
                    };
                    if writer
                        .send(WsMessage::Text(serde_json::to_string(&frame).unwrap_or_default()))
                        .await
                        .is_err()
                    {
                        return Err(Error::Realtime("heartbeat write failed".into()));
                    }
                }

                command = commands.recv() => {
                    let Some(command) = command else {
                        return Ok(Disposition::Shutdown);
                    };
                    match command {
                        RealtimeCommand::Shutdown => {
                            let _ = writer.send(WsMessage::Close(None)).await;
                            return Ok(Disposition::Shutdown);
                        }
                        RealtimeCommand::Reconnect => {
                            let _ = writer.send(WsMessage::Close(None)).await;
                            return Ok(Disposition::Reconnect);
                        }
                        other => {
                            let frame = command_to_frame(&other);
                            if writer
                                .send(WsMessage::Text(
                                    serde_json::to_string(&frame).unwrap_or_default(),
                                ))
                                .await
                                .is_err()
                            {
                                return Err(Error::Realtime("command write failed".into()));
                            }
                        }
                    }
                }
            }
        }
    }

    fn handle_text(
        &self,
        text: &str,
        events: &mpsc::UnboundedSender<RealtimeEvent>,
        last_seq: &mut Option<u64>,
        heartbeat: &mut tokio::time::Interval,
    ) {
        let Ok(frame) = serde_json::from_str::<ServerFrame>(text) else {
            tracing::warn!("realtime: undecodable frame");
            return;
        };

        // Gap detection before anything else: the UI needs to know its state
        // is incomplete even if this particular frame is applied.
        if let Some(seq) = frame.seq {
            if let Some(previous) = *last_seq {
                if seq > previous + 1 {
                    let _ = events.send(RealtimeEvent::GapDetected {
                        expected: previous + 1,
                        received: seq,
                    });
                }
            }
            *last_seq = Some(seq);
        }

        if frame.kind == "hello" {
            if let Some(seconds) = frame.data.get("heartbeat_seconds").and_then(|v| v.as_u64()) {
                let mut refreshed =
                    tokio::time::interval(Duration::from_secs(seconds.clamp(5, 300)));
                refreshed.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
                refreshed.reset();
                *heartbeat = refreshed;
            }
            let _ = events.send(RealtimeEvent::Connected {
                session_id: frame
                    .data
                    .get("session_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default()
                    .to_string(),
                workspace_ids: frame
                    .data
                    .get("workspace_ids")
                    .and_then(|v| v.as_array())
                    .map(|items| {
                        items
                            .iter()
                            .filter_map(|v| v.as_str().map(str::to_string))
                            .collect()
                    })
                    .unwrap_or_default(),
            });
            return;
        }

        // `pong` only keeps the connection alive; the UI has no use for it.
        if frame.kind == "pong" {
            return;
        }

        let _ = events.send(RealtimeEvent::Frame(frame));
    }
}

enum Disposition {
    Shutdown,
    Reconnect,
}

#[derive(Clone)]
pub struct RealtimeHandle {
    commands: mpsc::UnboundedSender<RealtimeCommand>,
}

impl RealtimeHandle {
    pub fn send(&self, command: RealtimeCommand) -> Result<()> {
        self.commands
            .send(command)
            .map_err(|_| Error::Realtime("realtime task is not running".into()))
    }

    pub fn subscribe(&self, channel_ids: Vec<String>) -> Result<()> {
        self.send(RealtimeCommand::Subscribe { channel_ids })
    }

    pub fn typing(&self, channel_id: impl Into<String>, parent_id: Option<String>) -> Result<()> {
        self.send(RealtimeCommand::Typing {
            channel_id: channel_id.into(),
            parent_id,
        })
    }

    pub fn set_presence(&self, state: impl Into<String>) -> Result<()> {
        self.send(RealtimeCommand::Presence {
            state: state.into(),
        })
    }

    pub fn reconnect(&self) -> Result<()> {
        self.send(RealtimeCommand::Reconnect)
    }

    pub fn shutdown(&self) -> Result<()> {
        self.send(RealtimeCommand::Shutdown)
    }
}

fn command_to_frame(command: &RealtimeCommand) -> ClientFrame<'static> {
    match command {
        RealtimeCommand::Subscribe { channel_ids } => ClientFrame {
            kind: "subscribe",
            id: None,
            data: serde_json::json!({ "channel_ids": channel_ids }),
        },
        RealtimeCommand::Unsubscribe { channel_ids } => ClientFrame {
            kind: "unsubscribe",
            id: None,
            data: serde_json::json!({ "channel_ids": channel_ids }),
        },
        RealtimeCommand::Typing {
            channel_id,
            parent_id,
        } => ClientFrame {
            kind: "typing",
            id: None,
            data: serde_json::json!({ "channel_id": channel_id, "parent_id": parent_id }),
        },
        RealtimeCommand::Presence { state } => ClientFrame {
            kind: "presence",
            id: None,
            data: serde_json::json!({ "presence": state }),
        },
        RealtimeCommand::MarkRead {
            channel_id,
            message_id,
        } => ClientFrame {
            kind: "mark_read",
            id: None,
            data: serde_json::json!({ "channel_id": channel_id, "message_id": message_id }),
        },
        // Handled before reaching here.
        RealtimeCommand::Reconnect | RealtimeCommand::Shutdown => ClientFrame {
            kind: "ping",
            id: None,
            data: serde_json::json!({}),
        },
    }
}

fn classify_handshake_error(err: &tokio_tungstenite::tungstenite::Error) -> Error {
    use tokio_tungstenite::tungstenite::Error as WsError;
    match err {
        // The gateway closes with 4001 before the upgrade completes when the
        // token is bad, which surfaces as an HTTP error here.
        WsError::Http(response) if response.status().as_u16() == 401 => {
            Error::Unauthenticated("gateway rejected the token".into())
        }
        other => Error::Realtime(other.to_string()),
    }
}

fn rand_u64() -> u64 {
    use rand::Rng;
    rand::thread_rng().gen()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(seq: u64) -> String {
        serde_json::json!({ "type": "message.created", "seq": seq, "data": {} }).to_string()
    }

    fn client() -> RealtimeClient {
        RealtimeClient::new(
            ApiConfig::new("http://localhost:8000"),
            Arc::new(Session::new(
                Arc::new(crate::session::MemoryTokenStore::new()),
                "test",
            )),
        )
    }

    #[tokio::test]
    async fn contiguous_sequences_produce_no_gap() {
        let client = client();
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut last = None;
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));

        for seq in 1..=3 {
            client.handle_text(&frame(seq), &tx, &mut last, &mut heartbeat);
        }
        assert_eq!(last, Some(3));

        let mut events = Vec::new();
        while let Ok(event) = rx.try_recv() {
            events.push(event);
        }
        assert_eq!(events.len(), 3, "three frames, no gap events");
        assert!(events.iter().all(|e| matches!(e, RealtimeEvent::Frame(_))));
    }

    #[tokio::test]
    async fn a_missing_sequence_reports_a_gap() {
        let client = client();
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut last = None;
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));

        client.handle_text(&frame(1), &tx, &mut last, &mut heartbeat);
        // seq 2 and 3 were dropped.
        client.handle_text(&frame(4), &tx, &mut last, &mut heartbeat);

        let mut saw_gap = false;
        while let Ok(event) = rx.try_recv() {
            if let RealtimeEvent::GapDetected { expected, received } = event {
                assert_eq!((expected, received), (2, 4));
                saw_gap = true;
            }
        }
        assert!(saw_gap, "a sequence jump must be reported");
    }

    #[tokio::test]
    async fn hello_emits_connected_and_adopts_the_heartbeat() {
        let client = client();
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut last = None;
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));

        let hello = serde_json::json!({
            "type": "hello",
            "seq": 1,
            "data": {
                "session_id": "01CONN",
                "user_id": "01USER",
                "workspace_ids": ["01WS"],
                "heartbeat_seconds": 10,
            }
        })
        .to_string();
        client.handle_text(&hello, &tx, &mut last, &mut heartbeat);

        match rx.try_recv().expect("an event") {
            RealtimeEvent::Connected {
                session_id,
                workspace_ids,
            } => {
                assert_eq!(session_id, "01CONN");
                assert_eq!(workspace_ids, vec!["01WS".to_string()]);
            }
            other => panic!("expected Connected, got {other:?}"),
        }
        assert_eq!(heartbeat.period(), Duration::from_secs(10));
    }

    #[tokio::test]
    async fn pong_frames_are_not_forwarded_to_the_ui() {
        let client = client();
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut last = None;
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));

        client.handle_text(
            &serde_json::json!({ "type": "pong", "seq": 2, "data": {} }).to_string(),
            &tx,
            &mut last,
            &mut heartbeat,
        );
        assert!(rx.try_recv().is_err(), "pong is internal bookkeeping");
        // It still advances the sequence, so it cannot cause a false gap.
        assert_eq!(last, Some(2));
    }

    #[tokio::test]
    async fn an_absurd_heartbeat_is_clamped() {
        let client = client();
        let (tx, _rx) = mpsc::unbounded_channel();
        let mut last = None;
        let mut heartbeat = tokio::time::interval(Duration::from_secs(25));

        let hello = serde_json::json!({
            "type": "hello",
            "data": { "session_id": "x", "heartbeat_seconds": 0 }
        })
        .to_string();
        client.handle_text(&hello, &tx, &mut last, &mut heartbeat);
        // A zero-second interval would spin; clamp keeps it sane.
        assert_eq!(heartbeat.period(), Duration::from_secs(5));
    }

    #[test]
    fn commands_serialise_to_the_gateway_protocol() {
        let frame = command_to_frame(&RealtimeCommand::Typing {
            channel_id: "01CH".into(),
            parent_id: Some("01MSG".into()),
        });
        let json = serde_json::to_value(&frame).unwrap();
        assert_eq!(json["type"], "typing");
        assert_eq!(json["data"]["channel_id"], "01CH");
        assert_eq!(json["data"]["parent_id"], "01MSG");
    }
}
