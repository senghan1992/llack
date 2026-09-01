//! Local SQLite cache and offline send queue.
//!
//! Two jobs:
//!
//! 1. **Read cache.** Channels and recent messages are mirrored locally so the
//!    app renders a full transcript at launch before any network round-trip,
//!    and keeps working on a train.
//! 2. **Outbox.** A message composed offline is stored with the ULID and
//!    `client_msg_id` already assigned, then replayed when connectivity
//!    returns. Because the server treats `client_msg_id` as an idempotency
//!    key, replaying a message that actually did reach the server is a no-op
//!    rather than a duplicate.

use std::path::Path;

use r2d2::Pool;
use r2d2_sqlite::SqliteConnectionManager;
use rusqlite::{params, OptionalExtension};

use crate::error::{Error, Result};
use crate::ids::new_ulid;
use crate::models::{Channel, Message, NewMessage};

/// Bumped whenever the local schema changes. The cache is disposable — on a
/// version mismatch it is dropped and rebuilt rather than migrated, since
/// everything in it can be re-fetched.
const SCHEMA_VERSION: i32 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OutboxState {
    Pending,
    Sending,
    Failed,
}

impl OutboxState {
    fn as_str(self) -> &'static str {
        match self {
            OutboxState::Pending => "pending",
            OutboxState::Sending => "sending",
            OutboxState::Failed => "failed",
        }
    }

    fn parse(value: &str) -> Self {
        match value {
            "sending" => OutboxState::Sending,
            "failed" => OutboxState::Failed,
            _ => OutboxState::Pending,
        }
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct OutboxEntry {
    pub id: String,
    pub channel_id: String,
    pub client_msg_id: String,
    pub payload: NewMessage,
    pub state: OutboxState,
    pub attempts: i64,
    pub last_error: Option<String>,
    pub created_at_ms: i64,
}

pub struct Cache {
    pool: Pool<SqliteConnectionManager>,
}

impl Cache {
    /// Open (or create) the cache at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let manager = SqliteConnectionManager::file(path.as_ref()).with_init(|conn| {
            // WAL so a background sync write never blocks the UI's reads.
            conn.execute_batch(
                "PRAGMA journal_mode=WAL;
                 PRAGMA synchronous=NORMAL;
                 PRAGMA foreign_keys=ON;
                 PRAGMA busy_timeout=5000;",
            )
        });
        let pool = Pool::builder()
            .max_size(4)
            .build(manager)
            .map_err(|e| Error::Cache(e.to_string()))?;
        let cache = Self { pool };
        cache.migrate()?;
        Ok(cache)
    }

    pub fn open_in_memory() -> Result<Self> {
        let manager = SqliteConnectionManager::memory();
        // A single connection: each new connection to `:memory:` would
        // otherwise get its own empty database.
        let pool = Pool::builder()
            .max_size(1)
            .build(manager)
            .map_err(|e| Error::Cache(e.to_string()))?;
        let cache = Self { pool };
        cache.migrate()?;
        Ok(cache)
    }

    fn conn(&self) -> Result<r2d2::PooledConnection<SqliteConnectionManager>> {
        self.pool.get().map_err(Error::from)
    }

    fn migrate(&self) -> Result<()> {
        let conn = self.conn()?;
        let version: i32 = conn.query_row("PRAGMA user_version", [], |row| row.get(0))?;

        if version != 0 && version != SCHEMA_VERSION {
            // Disposable cache: rebuild rather than migrate.
            conn.execute_batch(
                "DROP TABLE IF EXISTS messages;
                 DROP TABLE IF EXISTS channels;
                 DROP TABLE IF EXISTS outbox;
                 DROP TABLE IF EXISTS sync_state;",
            )?;
        }

        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS channels (
                 id            TEXT PRIMARY KEY,
                 workspace_id  TEXT NOT NULL,
                 payload       TEXT NOT NULL,
                 sort_key      TEXT,
                 updated_at_ms INTEGER NOT NULL
             );
             CREATE INDEX IF NOT EXISTS idx_channels_workspace
                 ON channels (workspace_id, sort_key DESC);

             CREATE TABLE IF NOT EXISTS messages (
                 id            TEXT PRIMARY KEY,
                 channel_id    TEXT NOT NULL,
                 parent_id     TEXT,
                 payload       TEXT NOT NULL,
                 updated_at_ms INTEGER NOT NULL
             );
             -- The channel-history read path: newest N for a channel.
             CREATE INDEX IF NOT EXISTS idx_messages_channel
                 ON messages (channel_id, id DESC);
             CREATE INDEX IF NOT EXISTS idx_messages_thread
                 ON messages (parent_id, id ASC);

             CREATE TABLE IF NOT EXISTS outbox (
                 id            TEXT PRIMARY KEY,
                 channel_id    TEXT NOT NULL,
                 client_msg_id TEXT NOT NULL UNIQUE,
                 payload       TEXT NOT NULL,
                 state         TEXT NOT NULL DEFAULT 'pending',
                 attempts      INTEGER NOT NULL DEFAULT 0,
                 last_error    TEXT,
                 created_at_ms INTEGER NOT NULL
             );
             CREATE INDEX IF NOT EXISTS idx_outbox_ready
                 ON outbox (state, created_at_ms);

             CREATE TABLE IF NOT EXISTS sync_state (
                 key   TEXT PRIMARY KEY,
                 value TEXT NOT NULL
             );",
        )?;
        conn.execute_batch(&format!("PRAGMA user_version = {SCHEMA_VERSION}"))?;
        Ok(())
    }

    // ── Channels ────────────────────────────────────────────────────────

    pub fn put_channels(&self, channels: &[Channel]) -> Result<()> {
        let mut conn = self.conn()?;
        let tx = conn.transaction()?;
        {
            let mut stmt = tx.prepare(
                "INSERT INTO channels (id, workspace_id, payload, sort_key, updated_at_ms)
                 VALUES (?1, ?2, ?3, ?4, ?5)
                 ON CONFLICT(id) DO UPDATE SET
                     workspace_id = excluded.workspace_id,
                     payload      = excluded.payload,
                     sort_key     = excluded.sort_key,
                     updated_at_ms = excluded.updated_at_ms",
            )?;
            let now = crate::session::now_ms();
            for channel in channels {
                let payload =
                    serde_json::to_string(channel).map_err(|e| Error::Cache(e.to_string()))?;
                stmt.execute(params![
                    channel.id,
                    channel.workspace_id,
                    payload,
                    channel.last_message_at.clone().unwrap_or_default(),
                    now,
                ])?;
            }
        }
        tx.commit()?;
        Ok(())
    }

    pub fn channels(&self, workspace_id: &str) -> Result<Vec<Channel>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT payload FROM channels
             WHERE workspace_id = ?1
             ORDER BY sort_key DESC",
        )?;
        let rows = stmt.query_map([workspace_id], |row| row.get::<_, String>(0))?;
        let mut out = Vec::new();
        for row in rows {
            if let Ok(channel) = serde_json::from_str(&row?) {
                out.push(channel);
            }
        }
        Ok(out)
    }

    pub fn remove_channel(&self, channel_id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute("DELETE FROM channels WHERE id = ?1", [channel_id])?;
        conn.execute("DELETE FROM messages WHERE channel_id = ?1", [channel_id])?;
        Ok(())
    }

    // ── Messages ────────────────────────────────────────────────────────

    pub fn put_messages(&self, messages: &[Message]) -> Result<()> {
        let mut conn = self.conn()?;
        let tx = conn.transaction()?;
        {
            let mut stmt = tx.prepare(
                "INSERT INTO messages (id, channel_id, parent_id, payload, updated_at_ms)
                 VALUES (?1, ?2, ?3, ?4, ?5)
                 ON CONFLICT(id) DO UPDATE SET
                     payload       = excluded.payload,
                     parent_id     = excluded.parent_id,
                     updated_at_ms = excluded.updated_at_ms",
            )?;
            let now = crate::session::now_ms();
            for message in messages {
                let payload =
                    serde_json::to_string(message).map_err(|e| Error::Cache(e.to_string()))?;
                stmt.execute(params![
                    message.id,
                    message.channel_id,
                    message.parent_id,
                    payload,
                    now,
                ])?;
            }
        }
        tx.commit()?;
        Ok(())
    }

    /// Newest `limit` channel messages, returned oldest-first so the UI can
    /// render them straight into a transcript.
    pub fn channel_history(&self, channel_id: &str, limit: u32) -> Result<Vec<Message>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT payload FROM (
                 SELECT id, payload FROM messages
                 WHERE channel_id = ?1 AND (parent_id IS NULL OR parent_id = '')
                 ORDER BY id DESC
                 LIMIT ?2
             ) ORDER BY id ASC",
        )?;
        let rows = stmt.query_map(params![channel_id, limit], |row| row.get::<_, String>(0))?;
        let mut out = Vec::new();
        for row in rows {
            if let Ok(message) = serde_json::from_str(&row?) {
                out.push(message);
            }
        }
        Ok(out)
    }

    pub fn thread_replies(&self, parent_id: &str) -> Result<Vec<Message>> {
        let conn = self.conn()?;
        let mut stmt =
            conn.prepare("SELECT payload FROM messages WHERE parent_id = ?1 ORDER BY id ASC")?;
        let rows = stmt.query_map([parent_id], |row| row.get::<_, String>(0))?;
        let mut out = Vec::new();
        for row in rows {
            if let Ok(message) = serde_json::from_str(&row?) {
                out.push(message);
            }
        }
        Ok(out)
    }

    pub fn remove_message(&self, message_id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute("DELETE FROM messages WHERE id = ?1", [message_id])?;
        Ok(())
    }

    /// Drop old messages, keeping the newest `keep_per_channel` per channel.
    ///
    /// Without this the cache grows without bound on a long-lived install.
    pub fn prune(&self, keep_per_channel: u32) -> Result<usize> {
        let conn = self.conn()?;
        let removed = conn.execute(
            "DELETE FROM messages WHERE id IN (
                 SELECT id FROM (
                     SELECT id, ROW_NUMBER() OVER (
                         PARTITION BY channel_id ORDER BY id DESC
                     ) AS position
                     FROM messages
                 ) WHERE position > ?1
             )",
            [keep_per_channel],
        )?;
        Ok(removed)
    }

    // ── Outbox ──────────────────────────────────────────────────────────

    /// Queue a message for sending. Returns the entry, whose `client_msg_id`
    /// is the idempotency key the server will honour.
    pub fn enqueue(&self, channel_id: &str, mut payload: NewMessage) -> Result<OutboxEntry> {
        let client_msg_id = payload.client_msg_id.clone().unwrap_or_else(new_ulid);
        payload.client_msg_id = Some(client_msg_id.clone());

        let id = new_ulid();
        let created_at_ms = crate::session::now_ms();
        let serialised =
            serde_json::to_string(&payload).map_err(|e| Error::Cache(e.to_string()))?;

        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO outbox (id, channel_id, client_msg_id, payload, state, created_at_ms)
             VALUES (?1, ?2, ?3, ?4, 'pending', ?5)",
            params![id, channel_id, client_msg_id, serialised, created_at_ms],
        )?;

        Ok(OutboxEntry {
            id,
            channel_id: channel_id.to_string(),
            client_msg_id,
            payload,
            state: OutboxState::Pending,
            attempts: 0,
            last_error: None,
            created_at_ms,
        })
    }

    /// Entries ready to send, oldest first, so messages keep their order.
    pub fn pending(&self, limit: u32) -> Result<Vec<OutboxEntry>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, channel_id, client_msg_id, payload, state, attempts, last_error,
                    created_at_ms
             FROM outbox
             WHERE state IN ('pending', 'sending')
             ORDER BY created_at_ms ASC
             LIMIT ?1",
        )?;
        let rows = stmt.query_map([limit], row_to_entry)?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    pub fn outbox_for_channel(&self, channel_id: &str) -> Result<Vec<OutboxEntry>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, channel_id, client_msg_id, payload, state, attempts, last_error,
                    created_at_ms
             FROM outbox WHERE channel_id = ?1 ORDER BY created_at_ms ASC",
        )?;
        let rows = stmt.query_map([channel_id], row_to_entry)?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    pub fn mark_sending(&self, id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE outbox SET state = 'sending', attempts = attempts + 1 WHERE id = ?1",
            [id],
        )?;
        Ok(())
    }

    /// Sent successfully — drop it from the queue.
    pub fn dequeue(&self, id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute("DELETE FROM outbox WHERE id = ?1", [id])?;
        Ok(())
    }

    /// Send failed. `retryable` decides whether it waits for another attempt
    /// or is parked as failed for the user to retry or discard by hand.
    pub fn mark_result(&self, id: &str, error: &str, retryable: bool) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE outbox SET state = ?2, last_error = ?3 WHERE id = ?1",
            params![
                id,
                if retryable {
                    OutboxState::Pending.as_str()
                } else {
                    OutboxState::Failed.as_str()
                },
                error,
            ],
        )?;
        Ok(())
    }

    pub fn discard(&self, id: &str) -> Result<()> {
        self.dequeue(id)
    }

    /// Move every failed entry back to pending — the "retry all" action.
    pub fn retry_failed(&self) -> Result<usize> {
        let conn = self.conn()?;
        Ok(conn.execute(
            "UPDATE outbox SET state = 'pending', last_error = NULL WHERE state = 'failed'",
            [],
        )?)
    }

    // ── Sync bookkeeping ────────────────────────────────────────────────

    pub fn set_sync_state(&self, key: &str, value: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    pub fn sync_state(&self, key: &str) -> Result<Option<String>> {
        let conn = self.conn()?;
        Ok(conn
            .query_row(
                "SELECT value FROM sync_state WHERE key = ?1",
                [key],
                |row| row.get(0),
            )
            .optional()?)
    }

    /// Wipe everything. Used on sign-out so the next user of the machine sees
    /// nothing of the previous session.
    pub fn clear(&self) -> Result<()> {
        let conn = self.conn()?;
        conn.execute_batch(
            "DELETE FROM messages; DELETE FROM channels; DELETE FROM outbox;
             DELETE FROM sync_state;",
        )?;
        Ok(())
    }
}

fn row_to_entry(row: &rusqlite::Row<'_>) -> rusqlite::Result<OutboxEntry> {
    let payload: String = row.get(3)?;
    let state: String = row.get(4)?;
    Ok(OutboxEntry {
        id: row.get(0)?,
        channel_id: row.get(1)?,
        client_msg_id: row.get(2)?,
        payload: serde_json::from_str(&payload).unwrap_or_default(),
        state: OutboxState::parse(&state),
        attempts: row.get(5)?,
        last_error: row.get(6)?,
        created_at_ms: row.get(7)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{ChannelKind, MessageKind};

    fn channel(id: &str, last_message_at: Option<&str>) -> Channel {
        Channel {
            id: id.into(),
            workspace_id: "01WS".into(),
            kind: ChannelKind::Public,
            slug: Some(id.to_lowercase()),
            name: Some(format!("channel-{id}")),
            topic: None,
            purpose: None,
            is_archived: false,
            last_message_at: last_message_at.map(str::to_string),
            message_count: 0,
            member_count: 1,
            peers: vec![],
            membership: None,
        }
    }

    fn message(id: &str, channel_id: &str, parent_id: Option<&str>) -> Message {
        Message {
            id: id.into(),
            channel_id: channel_id.into(),
            kind: MessageKind::User,
            body: format!("body of {id}"),
            blocks: None,
            client_msg_id: None,
            author: None,
            app_id: None,
            parent_id: parent_id.map(str::to_string),
            reply_count: 0,
            last_reply_at: None,
            also_sent_to_channel: false,
            mentioned_user_ids: vec![],
            mentions_everyone: false,
            attachments: vec![],
            reactions: vec![],
            is_pinned: false,
            edited_at: None,
            deleted_at: None,
            created_at: "2026-01-01T00:00:00Z".into(),
        }
    }

    #[test]
    fn channels_round_trip_ordered_by_recent_activity() {
        let cache = Cache::open_in_memory().unwrap();
        cache
            .put_channels(&[
                channel("01A", Some("2026-01-01T00:00:00Z")),
                channel("01B", Some("2026-02-01T00:00:00Z")),
            ])
            .unwrap();

        let listed = cache.channels("01WS").unwrap();
        assert_eq!(
            listed.iter().map(|c| c.id.as_str()).collect::<Vec<_>>(),
            vec!["01B", "01A"],
            "most recent activity first"
        );
    }

    #[test]
    fn putting_a_channel_twice_updates_rather_than_duplicates() {
        let cache = Cache::open_in_memory().unwrap();
        cache.put_channels(&[channel("01A", None)]).unwrap();

        let mut updated = channel("01A", None);
        updated.topic = Some("새 주제".into());
        cache.put_channels(&[updated]).unwrap();

        let listed = cache.channels("01WS").unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].topic.as_deref(), Some("새 주제"));
    }

    #[test]
    fn channel_history_excludes_thread_replies_and_sorts_oldest_first() {
        let cache = Cache::open_in_memory().unwrap();
        cache
            .put_messages(&[
                message("01M1", "01CH", None),
                message("01M2", "01CH", None),
                message("01M3", "01CH", Some("01M1")),
            ])
            .unwrap();

        let history = cache.channel_history("01CH", 50).unwrap();
        assert_eq!(
            history.iter().map(|m| m.id.as_str()).collect::<Vec<_>>(),
            vec!["01M1", "01M2"],
            "replies belong to the thread pane, not the channel"
        );

        let replies = cache.thread_replies("01M1").unwrap();
        assert_eq!(replies.len(), 1);
        assert_eq!(replies[0].id, "01M3");
    }

    #[test]
    fn history_limit_keeps_the_newest() {
        let cache = Cache::open_in_memory().unwrap();
        let messages: Vec<Message> = (1..=10)
            .map(|i| message(&format!("01M{i:02}"), "01CH", None))
            .collect();
        cache.put_messages(&messages).unwrap();

        let history = cache.channel_history("01CH", 3).unwrap();
        assert_eq!(
            history.iter().map(|m| m.id.as_str()).collect::<Vec<_>>(),
            vec!["01M08", "01M09", "01M10"]
        );
    }

    #[test]
    fn prune_keeps_the_newest_per_channel() {
        let cache = Cache::open_in_memory().unwrap();
        let mut messages = Vec::new();
        for channel_id in ["01CHA", "01CHB"] {
            for i in 1..=5 {
                messages.push(message(&format!("01M{channel_id}{i}"), channel_id, None));
            }
        }
        cache.put_messages(&messages).unwrap();

        let removed = cache.prune(2).unwrap();
        assert_eq!(removed, 6, "3 removed from each of 2 channels");
        assert_eq!(cache.channel_history("01CHA", 50).unwrap().len(), 2);
        assert_eq!(cache.channel_history("01CHB", 50).unwrap().len(), 2);
    }

    #[test]
    fn enqueue_assigns_an_idempotency_key() {
        let cache = Cache::open_in_memory().unwrap();
        let entry = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "오프라인에서 작성".into(),
                    ..Default::default()
                },
            )
            .unwrap();

        assert_eq!(entry.state, OutboxState::Pending);
        assert!(crate::ids::is_ulid(&entry.client_msg_id));
        assert_eq!(
            entry.payload.client_msg_id.as_deref(),
            Some(entry.client_msg_id.as_str()),
            "the key must travel with the payload so the server sees it"
        );
    }

    #[test]
    fn enqueue_preserves_a_caller_supplied_key() {
        let cache = Cache::open_in_memory().unwrap();
        let entry = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "x".into(),
                    client_msg_id: Some("01PROVIDED0000000000000000".into()),
                    ..Default::default()
                },
            )
            .unwrap();
        assert_eq!(entry.client_msg_id, "01PROVIDED0000000000000000");
    }

    #[test]
    fn outbox_replays_in_composition_order() {
        let cache = Cache::open_in_memory().unwrap();
        for body in ["첫째", "둘째", "셋째"] {
            cache
                .enqueue(
                    "01CH",
                    NewMessage {
                        body: body.into(),
                        ..Default::default()
                    },
                )
                .unwrap();
        }
        let pending = cache.pending(10).unwrap();
        assert_eq!(
            pending
                .iter()
                .map(|e| e.payload.body.as_str())
                .collect::<Vec<_>>(),
            vec!["첫째", "둘째", "셋째"]
        );
    }

    #[test]
    fn a_retryable_failure_stays_queued_and_a_permanent_one_is_parked() {
        let cache = Cache::open_in_memory().unwrap();
        let retryable = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "재시도".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        let permanent = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "영구실패".into(),
                    ..Default::default()
                },
            )
            .unwrap();

        cache.mark_sending(&retryable.id).unwrap();
        cache
            .mark_result(&retryable.id, "network down", true)
            .unwrap();
        cache.mark_sending(&permanent.id).unwrap();
        cache
            .mark_result(&permanent.id, "channel_archived", false)
            .unwrap();

        let pending = cache.pending(10).unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].id, retryable.id);
        assert_eq!(pending[0].attempts, 1);

        let all = cache.outbox_for_channel("01CH").unwrap();
        let failed = all.iter().find(|e| e.id == permanent.id).unwrap();
        assert_eq!(failed.state, OutboxState::Failed);
        assert_eq!(failed.last_error.as_deref(), Some("channel_archived"));
    }

    #[test]
    fn retry_failed_requeues_everything_parked() {
        let cache = Cache::open_in_memory().unwrap();
        let entry = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "x".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        cache.mark_result(&entry.id, "boom", false).unwrap();
        assert!(cache.pending(10).unwrap().is_empty());

        assert_eq!(cache.retry_failed().unwrap(), 1);
        let pending = cache.pending(10).unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].last_error, None);
    }

    #[test]
    fn dequeue_removes_a_sent_message() {
        let cache = Cache::open_in_memory().unwrap();
        let entry = cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "보냄".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        cache.dequeue(&entry.id).unwrap();
        assert!(cache.pending(10).unwrap().is_empty());
        assert!(cache.outbox_for_channel("01CH").unwrap().is_empty());
    }

    #[test]
    fn sync_state_round_trips() {
        let cache = Cache::open_in_memory().unwrap();
        assert_eq!(cache.sync_state("cursor").unwrap(), None);
        cache.set_sync_state("cursor", "01M999").unwrap();
        assert_eq!(
            cache.sync_state("cursor").unwrap().as_deref(),
            Some("01M999")
        );
        cache.set_sync_state("cursor", "01MAAA").unwrap();
        assert_eq!(
            cache.sync_state("cursor").unwrap().as_deref(),
            Some("01MAAA")
        );
    }

    #[test]
    fn clear_wipes_everything_for_sign_out() {
        let cache = Cache::open_in_memory().unwrap();
        cache.put_channels(&[channel("01A", None)]).unwrap();
        cache
            .put_messages(&[message("01M1", "01CH", None)])
            .unwrap();
        cache
            .enqueue(
                "01CH",
                NewMessage {
                    body: "x".into(),
                    ..Default::default()
                },
            )
            .unwrap();
        cache.set_sync_state("k", "v").unwrap();

        cache.clear().unwrap();
        assert!(cache.channels("01WS").unwrap().is_empty());
        assert!(cache.channel_history("01CH", 50).unwrap().is_empty());
        assert!(cache.pending(10).unwrap().is_empty());
        assert_eq!(cache.sync_state("k").unwrap(), None);
    }

    #[test]
    fn removing_a_channel_takes_its_messages_with_it() {
        let cache = Cache::open_in_memory().unwrap();
        cache.put_channels(&[channel("01CH", None)]).unwrap();
        cache
            .put_messages(&[message("01M1", "01CH", None)])
            .unwrap();

        cache.remove_channel("01CH").unwrap();
        assert!(cache.channels("01WS").unwrap().is_empty());
        assert!(cache.channel_history("01CH", 50).unwrap().is_empty());
    }
}
