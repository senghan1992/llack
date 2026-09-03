//! Ties the pieces together: applies realtime frames to the cache, computes
//! badge counts, and drains the outbox.
//!
//! Kept separate from both the API client and the cache so the rules for
//! "what does a `message.created` frame actually change locally" live in one
//! reviewable place, and can be unit-tested without a server or a webview.

use std::sync::Arc;

use crate::api::ApiClient;
use crate::cache::{Cache, OutboxState};
use crate::error::Result;
use crate::models::{Channel, Message};
use crate::realtime::ServerFrame;

/// What the UI should do in response to an applied frame.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SyncEffect {
    /// A message arrived or changed in this channel.
    ChannelChanged { channel_id: String },
    /// A thread gained a reply.
    ThreadChanged {
        channel_id: String,
        parent_id: String,
    },
    /// The sidebar needs re-rendering (new channel, membership change).
    SidebarChanged,
    /// The dock needs re-rendering (an app was installed, removed or renamed).
    AppsChanged,
    /// Someone's name or avatar changed: the directory should reload.
    DirectoryChanged { user_id: Option<String> },
    /// Show an OS notification.
    Notify {
        title: String,
        body: String,
        channel_id: Option<String>,
        message_id: Option<String>,
        /// "reminder" | "quarantine" | "review" — absent for ordinary messages.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        notice_kind: Option<String>,
    },
    /// Someone is typing.
    Typing { channel_id: String, user_id: String },
    /// A user's presence changed.
    Presence { user_id: String, presence: String },
    /// The frame was understood but needs nothing from the UI.
    Ignored,
}

pub struct SyncEngine {
    cache: Arc<Cache>,
    api: Arc<ApiClient>,
    /// The signed-in user, so self-authored events can be filtered.
    user_id: String,
}

impl SyncEngine {
    pub fn new(cache: Arc<Cache>, api: Arc<ApiClient>, user_id: impl Into<String>) -> Self {
        Self {
            cache,
            api,
            user_id: user_id.into(),
        }
    }

    /// Apply one realtime frame to the local cache.
    pub fn apply(&self, frame: &ServerFrame) -> Result<SyncEffect> {
        match frame.kind.as_str() {
            "message.created" | "message.updated" => {
                let Some(message) = decode::<Message>(&frame.data, "message") else {
                    return Ok(SyncEffect::Ignored);
                };
                self.cache.put_messages(std::slice::from_ref(&message))?;

                // An echo of our own message: the optimistic bubble is already
                // on screen, and its outbox entry can be retired.
                if let Some(client_msg_id) = &message.client_msg_id {
                    if message.author.as_ref().map(|a| a.id.as_str()) == Some(&self.user_id) {
                        self.retire_outbox_entry(client_msg_id)?;
                    }
                }

                Ok(match &message.parent_id {
                    Some(parent_id) => SyncEffect::ThreadChanged {
                        channel_id: message.channel_id.clone(),
                        parent_id: parent_id.clone(),
                    },
                    None => SyncEffect::ChannelChanged {
                        channel_id: message.channel_id,
                    },
                })
            }

            "message.deleted" => {
                let message_id = frame.data.get("message_id").and_then(|v| v.as_str());
                let channel_id = frame.data.get("channel_id").and_then(|v| v.as_str());
                if let Some(message_id) = message_id {
                    self.cache.remove_message(message_id)?;
                }
                Ok(channel_id
                    .map(|id| SyncEffect::ChannelChanged {
                        channel_id: id.to_string(),
                    })
                    .unwrap_or(SyncEffect::Ignored))
            }

            // Reactions change a message's rendering, but the frame carries
            // only the delta. Re-fetching one message is cheaper and less
            // error-prone than merging counts locally.
            "reaction.added" | "reaction.removed" => Ok(frame
                .data
                .get("channel_id")
                .and_then(|v| v.as_str())
                .map(|id| SyncEffect::ChannelChanged {
                    channel_id: id.to_string(),
                })
                .unwrap_or(SyncEffect::Ignored)),

            "channel.created" | "channel.updated" => {
                if let Some(channel) = decode::<Channel>(&frame.data, "channel") {
                    self.cache.put_channels(&[channel])?;
                }
                Ok(SyncEffect::SidebarChanged)
            }

            "channel.archived" => {
                if let Some(channel) = decode::<Channel>(&frame.data, "channel") {
                    self.cache.remove_channel(&channel.id)?;
                }
                Ok(SyncEffect::SidebarChanged)
            }

            "channel.member_joined" | "channel.member_left" | "channel.read" => {
                Ok(SyncEffect::SidebarChanged)
            }

            "notification" => Ok(SyncEffect::Notify {
                title: string_field(&frame.data, "title").unwrap_or_else(|| "Llack".into()),
                body: string_field(&frame.data, "body").unwrap_or_default(),
                channel_id: string_field(&frame.data, "channel_id"),
                message_id: string_field(&frame.data, "message_id"),
                notice_kind: string_field(&frame.data, "kind"),
            }),

            "typing" => {
                let channel_id = string_field(&frame.data, "channel_id");
                let user_id = string_field(&frame.data, "user_id");
                match (channel_id, user_id) {
                    // Never render a typing indicator for ourselves.
                    (Some(channel_id), Some(user_id)) if user_id != self.user_id => {
                        Ok(SyncEffect::Typing {
                            channel_id,
                            user_id,
                        })
                    }
                    _ => Ok(SyncEffect::Ignored),
                }
            }

            "presence.updated" => {
                let user_id = string_field(&frame.data, "user_id");
                let presence = string_field(&frame.data, "presence");
                match (user_id, presence) {
                    (Some(user_id), Some(presence)) => {
                        Ok(SyncEffect::Presence { user_id, presence })
                    }
                    _ => Ok(SyncEffect::Ignored),
                }
            }

            "app.installed" | "app.uninstalled" | "app.updated" => Ok(SyncEffect::AppsChanged),

            "user.updated" => Ok(SyncEffect::DirectoryChanged {
                user_id: string_field(&frame.data, "user_id"),
            }),

            _ => Ok(SyncEffect::Ignored),
        }
    }

    /// Remove the outbox entry whose `client_msg_id` matches a confirmed send.
    fn retire_outbox_entry(&self, client_msg_id: &str) -> Result<()> {
        for entry in self.cache.pending(200)? {
            if entry.client_msg_id == client_msg_id {
                self.cache.dequeue(&entry.id)?;
                break;
            }
        }
        Ok(())
    }

    /// Pull the authoritative channel list and mirror it locally.
    pub async fn refresh_channels(&self, workspace_id: &str) -> Result<Vec<Channel>> {
        let channels = self.api.list_channels(workspace_id).await?;
        self.cache.put_channels(&channels)?;
        Ok(channels)
    }

    /// Pull recent history for one channel. Used on open, and after a gap.
    pub async fn refresh_history(&self, channel_id: &str, limit: u32) -> Result<Vec<Message>> {
        let page = self.api.history(channel_id, limit, None).await?;
        self.cache.put_messages(&page.items)?;
        // The API returns newest-first; the UI wants oldest-first.
        let mut items = page.items;
        items.reverse();
        Ok(items)
    }

    /// Try to send everything queued. Returns (sent, still_pending, failed).
    ///
    /// A retryable failure stops the drain: messages in a channel must keep
    /// their order, and pushing on past a failure would reorder them.
    pub async fn drain_outbox(&self) -> Result<DrainReport> {
        let mut report = DrainReport::default();

        for entry in self.cache.pending(100)? {
            self.cache.mark_sending(&entry.id)?;
            match self
                .api
                .post_message(&entry.channel_id, &entry.payload)
                .await
            {
                Ok(message) => {
                    self.cache.put_messages(&[message])?;
                    self.cache.dequeue(&entry.id)?;
                    report.sent += 1;
                }
                Err(err) if err.is_retryable() => {
                    self.cache.mark_result(&entry.id, &err.to_string(), true)?;
                    report.still_pending += 1;
                    // Stop, so later messages do not overtake this one.
                    break;
                }
                Err(err) => {
                    self.cache.mark_result(&entry.id, &err.to_string(), false)?;
                    report.failed += 1;
                }
            }
        }
        Ok(report)
    }

    /// Total badge count across a workspace, from the cached channel list.
    pub fn badge_count(&self, workspace_id: &str) -> Result<i64> {
        Ok(self
            .cache
            .channels(workspace_id)?
            .iter()
            .map(Channel::badge_count)
            .sum())
    }

    /// Whether anything is waiting to be sent, for the "offline" indicator.
    pub fn has_unsent(&self) -> Result<bool> {
        Ok(!self.cache.pending(1)?.is_empty())
    }

    pub fn failed_entries(&self, channel_id: &str) -> Result<Vec<crate::cache::OutboxEntry>> {
        Ok(self
            .cache
            .outbox_for_channel(channel_id)?
            .into_iter()
            .filter(|e| e.state == OutboxState::Failed)
            .collect())
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, serde::Serialize)]
pub struct DrainReport {
    pub sent: usize,
    pub still_pending: usize,
    pub failed: usize,
}

fn decode<T: serde::de::DeserializeOwned>(data: &serde_json::Value, key: &str) -> Option<T> {
    serde_json::from_value(data.get(key)?.clone()).ok()
}

fn string_field(data: &serde_json::Value, key: &str) -> Option<String> {
    data.get(key)?.as_str().map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::ApiConfig;
    use crate::models::{ChannelKind, ChannelMembership, MessageKind, UserBrief};
    use crate::session::{MemoryTokenStore, Session};

    const ME: &str = "01USERME";

    fn engine() -> (SyncEngine, Arc<Cache>) {
        let cache = Arc::new(Cache::open_in_memory().unwrap());
        let session = Arc::new(Session::new(Arc::new(MemoryTokenStore::new()), "test"));
        let api =
            Arc::new(ApiClient::new(ApiConfig::new("http://localhost:8000"), session).unwrap());
        (SyncEngine::new(cache.clone(), api, ME), cache)
    }

    fn frame(kind: &str, data: serde_json::Value) -> ServerFrame {
        ServerFrame {
            kind: kind.into(),
            seq: Some(1),
            ts: None,
            workspace_id: Some("01WS".into()),
            data,
        }
    }

    fn message_json(id: &str, channel_id: &str, author_id: Option<&str>) -> serde_json::Value {
        serde_json::json!({
            "message": {
                "id": id,
                "channel_id": channel_id,
                "kind": "user",
                "body": "안녕하세요",
                "created_at": "2026-01-01T00:00:00Z",
                "author": author_id.map(|id| serde_json::json!({
                    "id": id, "handle": "someone", "display_name": "누군가"
                })),
            }
        })
    }

    #[test]
    fn message_created_is_cached_and_reports_the_channel() {
        let (engine, cache) = engine();
        let effect = engine
            .apply(&frame(
                "message.created",
                message_json("01M1", "01CH", Some("01OTHER")),
            ))
            .unwrap();

        assert_eq!(
            effect,
            SyncEffect::ChannelChanged {
                channel_id: "01CH".into()
            }
        );
        let history = cache.channel_history("01CH", 10).unwrap();
        assert_eq!(history.len(), 1);
        assert_eq!(history[0].body, "안녕하세요");
    }

    #[test]
    fn a_threaded_message_reports_the_thread_not_the_channel() {
        let (engine, _cache) = engine();
        let mut data = message_json("01M2", "01CH", Some("01OTHER"));
        data["message"]["parent_id"] = serde_json::json!("01ROOT");

        let effect = engine.apply(&frame("message.created", data)).unwrap();
        assert_eq!(
            effect,
            SyncEffect::ThreadChanged {
                channel_id: "01CH".into(),
                parent_id: "01ROOT".into(),
            }
        );
    }

    #[test]
    fn the_echo_of_our_own_send_retires_its_outbox_entry() {
        let (engine, cache) = engine();
        let queued = cache
            .enqueue(
                "01CH",
                crate::models::NewMessage {
                    body: "내 메시지".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        assert_eq!(cache.pending(10).unwrap().len(), 1);

        // The server echoes it back, authored by us, carrying our key.
        let mut data = message_json("01M1", "01CH", Some(ME));
        data["message"]["client_msg_id"] = serde_json::json!(queued.client_msg_id);
        engine.apply(&frame("message.created", data)).unwrap();

        assert!(
            cache.pending(10).unwrap().is_empty(),
            "a confirmed send must leave the outbox"
        );
    }

    #[test]
    fn someone_elses_message_leaves_our_outbox_alone() {
        let (engine, cache) = engine();
        let queued = cache
            .enqueue(
                "01CH",
                crate::models::NewMessage {
                    body: "내 메시지".into(),
                    ..Default::default()
                },
            )
            .unwrap();

        // Same client_msg_id but a different author would be a server bug;
        // the guard is that authorship, not just the key, must match.
        let mut data = message_json("01M1", "01CH", Some("01SOMEONEELSE"));
        data["message"]["client_msg_id"] = serde_json::json!(queued.client_msg_id);
        engine.apply(&frame("message.created", data)).unwrap();

        assert_eq!(cache.pending(10).unwrap().len(), 1);
    }

    #[test]
    fn deletion_removes_the_message_from_the_cache() {
        let (engine, cache) = engine();
        engine
            .apply(&frame(
                "message.created",
                message_json("01M1", "01CH", Some("01O")),
            ))
            .unwrap();

        let effect = engine
            .apply(&frame(
                "message.deleted",
                serde_json::json!({ "message_id": "01M1", "channel_id": "01CH" }),
            ))
            .unwrap();

        assert_eq!(
            effect,
            SyncEffect::ChannelChanged {
                channel_id: "01CH".into()
            }
        );
        assert!(cache.channel_history("01CH", 10).unwrap().is_empty());
    }

    #[test]
    fn our_own_typing_indicator_is_suppressed() {
        let (engine, _cache) = engine();

        let mine = engine
            .apply(&frame(
                "typing",
                serde_json::json!({ "channel_id": "01CH", "user_id": ME }),
            ))
            .unwrap();
        assert_eq!(mine, SyncEffect::Ignored);

        let theirs = engine
            .apply(&frame(
                "typing",
                serde_json::json!({ "channel_id": "01CH", "user_id": "01OTHER" }),
            ))
            .unwrap();
        assert_eq!(
            theirs,
            SyncEffect::Typing {
                channel_id: "01CH".into(),
                user_id: "01OTHER".into()
            }
        );
    }

    #[test]
    fn a_notification_frame_becomes_a_notify_effect() {
        let (engine, _cache) = engine();
        let effect = engine
            .apply(&frame(
                "notification",
                serde_json::json!({
                    "title": "#일반 · 김앨리스",
                    "body": "확인 부탁드립니다",
                    "channel_id": "01CH",
                    "message_id": "01M1",
                }),
            ))
            .unwrap();

        assert_eq!(
            effect,
            SyncEffect::Notify {
                title: "#일반 · 김앨리스".into(),
                body: "확인 부탁드립니다".into(),
                channel_id: Some("01CH".into()),
                message_id: Some("01M1".into()),
                notice_kind: None,
            }
        );
    }

    #[test]
    fn archiving_a_channel_drops_it_from_the_cache() {
        let (engine, cache) = engine();
        let channel = serde_json::json!({
            "channel": {
                "id": "01CH", "workspace_id": "01WS", "kind": "public",
                "name": "공지", "created_at": "2026-01-01T00:00:00Z"
            }
        });
        engine
            .apply(&frame("channel.created", channel.clone()))
            .unwrap();
        assert_eq!(cache.channels("01WS").unwrap().len(), 1);

        let effect = engine.apply(&frame("channel.archived", channel)).unwrap();
        assert_eq!(effect, SyncEffect::SidebarChanged);
        assert!(cache.channels("01WS").unwrap().is_empty());
    }

    #[test]
    fn unknown_frames_are_ignored_rather_than_erroring() {
        let (engine, _cache) = engine();
        // A newer server may send frames this client has never heard of.
        let effect = engine
            .apply(&frame("something.invented.later", serde_json::json!({})))
            .unwrap();
        assert_eq!(effect, SyncEffect::Ignored);
    }

    #[test]
    fn malformed_payloads_are_ignored_rather_than_erroring() {
        let (engine, _cache) = engine();
        let effect = engine
            .apply(&frame(
                "message.created",
                serde_json::json!({ "message": 42 }),
            ))
            .unwrap();
        assert_eq!(effect, SyncEffect::Ignored);
    }

    #[test]
    fn badge_count_sums_unread_but_a_muted_channel_only_contributes_mentions() {
        let (engine, cache) = engine();

        let make = |id: &str, unread: i64, mentions: i64, muted: bool| Channel {
            id: id.into(),
            workspace_id: "01WS".into(),
            kind: ChannelKind::Public,
            slug: None,
            name: Some(id.into()),
            topic: None,
            purpose: None,
            is_archived: false,
            last_message_at: None,
            message_count: 0,
            member_count: 1,
            peers: vec![],
            membership: Some(ChannelMembership {
                role: None,
                last_read_message_id: None,
                unread_count: unread,
                mention_count: mentions,
                notification_level: None,
                is_muted: muted,
                is_starred: false,
                section: None,
                sort_order: 0,
            }),
        };

        cache
            .put_channels(&[make("01LOUD", 5, 1, false), make("01MUTED", 100, 2, true)])
            .unwrap();

        // 5 from the normal channel + 2 mentions from the muted one.
        assert_eq!(engine.badge_count("01WS").unwrap(), 7);
    }

    #[test]
    fn has_unsent_reflects_the_outbox() {
        let (engine, cache) = engine();
        assert!(!engine.has_unsent().unwrap());

        cache
            .enqueue(
                "01CH",
                crate::models::NewMessage {
                    body: "x".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        assert!(engine.has_unsent().unwrap());
    }

    #[test]
    fn message_kind_survives_the_round_trip() {
        let (engine, cache) = engine();
        let mut data = message_json("01M1", "01CH", Some("01BOT"));
        data["message"]["kind"] = serde_json::json!("app");
        engine.apply(&frame("message.created", data)).unwrap();

        let history = cache.channel_history("01CH", 10).unwrap();
        assert_eq!(history[0].kind, MessageKind::App);
    }

    #[test]
    fn author_is_preserved_through_the_cache() {
        let (engine, cache) = engine();
        engine
            .apply(&frame(
                "message.created",
                message_json("01M1", "01CH", Some("01OTHER")),
            ))
            .unwrap();
        let history = cache.channel_history("01CH", 10).unwrap();
        let author: &UserBrief = history[0].author.as_ref().unwrap();
        assert_eq!(author.id, "01OTHER");
        assert_eq!(author.display_name, "누군가");
    }
}
