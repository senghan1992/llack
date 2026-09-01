//! Runs the realtime client as a background task and turns its events into
//! Tauri events, OS notifications and badge updates.

use std::sync::Arc;

use llack_core::{RealtimeClient, RealtimeEvent, SyncEffect};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_notification::NotificationExt;

use crate::state::AppState;

/// Event names the UI subscribes to. Prefixed so they cannot collide with
/// Tauri's own or a plugin's events.
pub const EVENT_CONNECTION: &str = "llack://connection";
pub const EVENT_SYNC: &str = "llack://sync";
pub const EVENT_FRAME: &str = "llack://frame";
pub const EVENT_AUTH_LOST: &str = "llack://auth-lost";
pub const EVENT_BADGE: &str = "llack://badge";

/// Start (or restart) the realtime task for the current session.
pub fn start(app: AppHandle, state: Arc<AppState>, workspace_id: Option<String>) {
    // Replace any previous socket so signing in twice does not leave two.
    if let Some(previous) = state.take_realtime() {
        let _ = previous.shutdown();
    }

    let Ok(api) = state.api() else { return };
    let session = api.session().clone();
    let client = RealtimeClient::new(api.config().clone(), session);
    state.set_realtime(client.handle());

    let (events_tx, mut events_rx) = tokio::sync::mpsc::unbounded_channel();
    let workspace_for_socket = workspace_id.or_else(|| state.active_workspace());

    tauri::async_runtime::spawn(async move {
        client.run(workspace_for_socket, events_tx).await;
    });

    let handler_app = app.clone();
    let handler_state = state.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events_rx.recv().await {
            handle_event(&handler_app, &handler_state, event).await;
        }
    });

    // Anything composed while offline goes out as soon as the socket is up.
    let drain_state = state;
    tauri::async_runtime::spawn(async move {
        if let Ok(sync) = drain_state.sync() {
            if let Ok(report) = sync.drain_outbox().await {
                if report.sent > 0 {
                    tracing::info!(sent = report.sent, "outbox drained on connect");
                }
            }
        }
    });
}

async fn handle_event(app: &AppHandle, state: &Arc<AppState>, event: RealtimeEvent) {
    match event {
        RealtimeEvent::Connected { ref session_id, ref workspace_ids } => {
            tracing::info!(session_id, "realtime connected");
            let _ = app.emit(
                EVENT_CONNECTION,
                serde_json::json!({
                    "status": "connected",
                    "session_id": session_id,
                    "workspace_ids": workspace_ids,
                }),
            );

            // Resubscribe to the cached channel list: after a reconnect the
            // server only knows about the channels the handshake derived.
            if let Some(workspace_id) = state.active_workspace() {
                if let (Ok(realtime), Ok(channels)) =
                    (state.realtime(), state.cache.channels(&workspace_id))
                {
                    let _ = realtime.subscribe(channels.iter().map(|c| c.id.clone()).collect());
                }
            }

            // Send anything that piled up while disconnected.
            if let Ok(sync) = state.sync() {
                let _ = sync.drain_outbox().await;
            }
        }

        RealtimeEvent::Disconnected { ref reason, will_retry_in_ms } => {
            tracing::warn!(reason, ?will_retry_in_ms, "realtime disconnected");
            let _ = app.emit(
                EVENT_CONNECTION,
                serde_json::json!({
                    "status": "disconnected",
                    "reason": reason,
                    "will_retry_in_ms": will_retry_in_ms,
                }),
            );
        }

        RealtimeEvent::GapDetected { expected, received } => {
            // Events were missed, so cached state is incomplete. Re-fetch
            // rather than render a transcript with holes.
            tracing::warn!(expected, received, "realtime sequence gap; resyncing");
            let _ = app.emit(
                EVENT_CONNECTION,
                serde_json::json!({
                    "status": "resyncing",
                    "expected": expected,
                    "received": received,
                }),
            );
            if let (Some(workspace_id), Ok(sync)) = (state.active_workspace(), state.sync()) {
                if let Ok(channels) = sync.refresh_channels(&workspace_id).await {
                    let _ = app.emit(
                        EVENT_SYNC,
                        serde_json::json!({ "kind": "sidebar_changed" }),
                    );
                    // Refresh the channels the user is most likely looking at.
                    for channel in channels.iter().take(10) {
                        let _ = sync.refresh_history(&channel.id, 80).await;
                        let _ = app.emit(
                            EVENT_SYNC,
                            serde_json::json!({
                                "kind": "channel_changed",
                                "channel_id": channel.id,
                            }),
                        );
                    }
                }
            }
        }

        RealtimeEvent::AuthenticationLost { ref message } => {
            tracing::warn!(message, "realtime authentication lost");
            let _ = state.reset();
            let _ = app.emit(EVENT_AUTH_LOST, serde_json::json!({ "message": message }));
        }

        RealtimeEvent::Frame(frame) => {
            // Hand the raw frame to the UI as well: it may want to apply a
            // change optimistically before the cache round-trip completes.
            let _ = app.emit(EVENT_FRAME, &frame);

            let Ok(sync) = state.sync() else { return };
            match sync.apply(&frame) {
                Ok(SyncEffect::Ignored) => {}
                Ok(SyncEffect::Notify { title, body, channel_id, message_id }) => {
                    show_notification(app, &title, &body);
                    let _ = app.emit(
                        EVENT_SYNC,
                        serde_json::json!({
                            "kind": "notify",
                            "title": title,
                            "body": body,
                            "channel_id": channel_id,
                            "message_id": message_id,
                        }),
                    );
                }
                Ok(effect) => {
                    let _ = app.emit(EVENT_SYNC, &effect);
                    // Unread counters may have moved; refresh the badge.
                    if let Some(workspace_id) = state.active_workspace() {
                        if let Ok(total) = sync.badge_count(&workspace_id) {
                            let _ =
                                app.emit(EVENT_BADGE, serde_json::json!({ "count": total }));
                        }
                    }
                }
                Err(err) => tracing::warn!(error = %err, "could not apply a realtime frame"),
            }
        }
    }
}

/// Show an OS notification, unless the window is focused — in which case the
/// user is already looking at the message.
fn show_notification(app: &AppHandle, title: &str, body: &str) {
    let focused = app
        .get_webview_window("main")
        .and_then(|w| w.is_focused().ok())
        .unwrap_or(false);
    if focused {
        return;
    }
    if let Err(err) = app
        .notification()
        .builder()
        .title(title)
        .body(body)
        .show()
    {
        tracing::warn!(error = %err, "could not show a notification");
    }
}
