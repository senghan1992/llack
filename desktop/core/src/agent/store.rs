//! `agent.sqlite3` — the agent's own durable state.
//!
//! ## Why not `cache.sqlite3`
//!
//! The message cache is disposable by design: [`crate::cache`] drops and
//! rebuilds it on a schema bump, and `AppState::reset()` clears it on sign-out.
//! Everything in here is the opposite — a conversation the user had, a decision
//! they made, a large value a later turn still needs. None of it can be
//! re-fetched from a server, so this file gets a real migration ladder and is
//! never cleared by signing out.
//!
//! ## Why not the server
//!
//! Agent sessions contain shell output from the user's own machine. Syncing
//! that to a workspace server is a new privacy surface that needs its own
//! consent design, so v1 keeps it local. The tables carry `user_id` and
//! `workspace_id` from the first migration anyway, so a later opt-in sync is a
//! new feature rather than a migration of meaning.
//!
//! ## The artifact table is the RLM seam
//!
//! A tool that would return a lot of text stores it here and returns a handle
//! plus a small preview. Three things follow from that:
//!
//! - the parent context stays bounded no matter how large the channel is;
//! - a 10 MB build log is queryable instead of either truncated or ruinous;
//! - there is somewhere for a sub-agent's answer to land *other than* the
//!   parent's transcript, which is the property the recursive-language-model
//!   design actually turns on.
//!
//! v1 only slices and filters artifacts through fixed verbs — there is no REPL
//! and no recursion yet. The destination exists; the caller does not.

use std::path::Path;

use r2d2_sqlite::SqliteConnectionManager;
use rusqlite::OptionalExtension;
use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};
use crate::ids::new_ulid;

/// Bumped for every forward migration. Unlike the cache's version, a mismatch
/// here migrates rather than rebuilds.
const SCHEMA_VERSION: i32 = 3;

/// The ceiling on a single memory. A note is a hint for a later turn, not a
/// document store; anything longer is almost certainly a paste that belongs in
/// an artifact, and letting one grow without bound would quietly turn the
/// memory table into an unbounded context on every recall.
pub const MEMORY_TEXT_CAP: usize = 2000;

/// How much of an artifact a preview may carry.
pub const PREVIEW_LINES: usize = 3;

/// Below this, a tool returns the whole thing inline instead of making the
/// model spend a second round trip on a six-message thread. Dogma about
/// handles would be a latency bug on the most common case.
pub const INLINE_BYTE_LIMIT: usize = 2 * 1024;

/// A stored value too large to sit in the model's context.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Artifact {
    pub id: String,
    pub session_id: String,
    /// `chat_history`, `exec_output`, … — what produced it.
    pub kind: String,
    pub bytes: u64,
    pub lines: u64,
    /// Tool-specific facts (channel id, argv, span) — never the payload.
    pub meta: serde_json::Value,
    pub created_at_ms: i64,
}

/// What the model asked of an artifact.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArtifactOp {
    Head { lines: usize },
    Tail { lines: usize },
    Slice { from: usize, to: usize },
    Grep { pattern: String, limit: usize },
    Count,
}

impl ArtifactOp {
    /// The verb name as the tool schema spells it.
    pub fn verb(&self) -> &'static str {
        match self {
            ArtifactOp::Head { .. } => "head",
            ArtifactOp::Tail { .. } => "tail",
            ArtifactOp::Slice { .. } => "slice",
            ArtifactOp::Grep { .. } => "grep",
            ArtifactOp::Count => "count",
        }
    }
}

/// The answer to an [`ArtifactOp`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactSlice {
    pub handle: String,
    pub op: String,
    /// Zero-based line numbers of what came back, for stable citation.
    pub from_line: usize,
    pub lines: Vec<String>,
    pub total_lines: usize,
    /// True when the answer was cut short by the caller's cap.
    pub truncated: bool,
}

/// One agent conversation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentSession {
    pub id: String,
    pub user_id: String,
    pub workspace_id: Option<String>,
    pub title: Option<String>,
    pub provider_id: String,
    pub model: String,
    pub created_at_ms: i64,
    pub last_active_at_ms: i64,
}

/// One turn's worth of content, stored provider-neutral plus an opaque
/// provider payload.
///
/// The payload exists because Anthropic thinking blocks must be replayed
/// verbatim on the same model. Storing the raw provider JSON as the canonical
/// form instead would force a data migration the day a second provider is
/// added; storing it alongside a neutral form costs a column.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentMessage {
    pub session_id: String,
    /// Monotonic within a session and never reused. Compression that creates
    /// lineage (rather than rewriting history) later becomes a row citing a
    /// `seq` range, which is only possible if these are stable.
    pub seq: i64,
    pub role: String,
    pub blocks: serde_json::Value,
    pub provider_payload: Option<serde_json::Value>,
    pub created_at_ms: i64,
}

/// The agent's database.
pub struct AgentStore {
    pool: r2d2::Pool<SqliteConnectionManager>,
}

impl AgentStore {
    /// Open `agent.sqlite3` in `dir`, running any pending migration.
    pub fn open(dir: impl AsRef<Path>) -> Result<Self> {
        let dir = dir.as_ref();
        std::fs::create_dir_all(dir)
            .map_err(|e| Error::Other(format!("could not create the agent data dir: {e}")))?;
        let manager = SqliteConnectionManager::file(dir.join("agent.sqlite3"));
        let pool = r2d2::Pool::builder()
            .max_size(4)
            .build(manager)
            .map_err(Error::from)?;
        let store = Self { pool };
        store.migrate()?;
        Ok(store)
    }

    /// An in-memory store for tests.
    pub fn in_memory() -> Result<Self> {
        let manager = SqliteConnectionManager::memory();
        // One connection: a memory database is per-connection, so a pool of
        // several would hand out empty databases.
        let pool = r2d2::Pool::builder()
            .max_size(1)
            .build(manager)
            .map_err(Error::from)?;
        let store = Self { pool };
        store.migrate()?;
        Ok(store)
    }

    fn conn(&self) -> Result<r2d2::PooledConnection<SqliteConnectionManager>> {
        self.pool.get().map_err(Error::from)
    }

    /// Forward-only migrations. Each step is additive and idempotent; nothing
    /// here drops a table, because everything in this file is unrecoverable.
    fn migrate(&self) -> Result<()> {
        let conn = self.conn()?;
        let version: i32 = conn.query_row("PRAGMA user_version", [], |row| row.get(0))?;

        if version > SCHEMA_VERSION {
            return Err(Error::Other(format!(
                "agent.sqlite3 was written by a newer version of Llack \
                 (schema {version}, this build understands {SCHEMA_VERSION})"
            )));
        }

        if version < 1 {
            conn.execute_batch(
                "CREATE TABLE IF NOT EXISTS agent_sessions (
                     id                TEXT PRIMARY KEY,
                     user_id           TEXT NOT NULL,
                     workspace_id      TEXT,
                     title             TEXT,
                     provider_id       TEXT NOT NULL,
                     model             TEXT NOT NULL,
                     created_at_ms     INTEGER NOT NULL,
                     last_active_at_ms INTEGER NOT NULL
                 );
                 CREATE INDEX IF NOT EXISTS ix_agent_sessions_recent
                     ON agent_sessions (user_id, last_active_at_ms DESC);

                 CREATE TABLE IF NOT EXISTS agent_messages (
                     session_id       TEXT NOT NULL
                                      REFERENCES agent_sessions(id) ON DELETE CASCADE,
                     seq              INTEGER NOT NULL,
                     role             TEXT NOT NULL,
                     blocks           TEXT NOT NULL,
                     provider_payload TEXT,
                     created_at_ms    INTEGER NOT NULL,
                     PRIMARY KEY (session_id, seq)
                 );

                 CREATE TABLE IF NOT EXISTS agent_artifacts (
                     id            TEXT PRIMARY KEY,
                     session_id    TEXT NOT NULL,
                     kind          TEXT NOT NULL,
                     body          TEXT NOT NULL,
                     bytes         INTEGER NOT NULL,
                     lines         INTEGER NOT NULL,
                     meta          TEXT NOT NULL,
                     created_at_ms INTEGER NOT NULL
                 );
                 CREATE INDEX IF NOT EXISTS ix_agent_artifacts_session
                     ON agent_artifacts (session_id, created_at_ms DESC);

                 CREATE TABLE IF NOT EXISTS agent_approvals (
                     id            TEXT PRIMARY KEY,
                     session_id    TEXT NOT NULL,
                     tool          TEXT NOT NULL,
                     summary       TEXT NOT NULL,
                     args          TEXT NOT NULL,
                     verdict       TEXT NOT NULL,
                     decided_at_ms INTEGER NOT NULL
                 );
                 CREATE INDEX IF NOT EXISTS ix_agent_approvals_session
                     ON agent_approvals (session_id, decided_at_ms DESC);

                 CREATE TABLE IF NOT EXISTS agent_settings (
                     user_id         TEXT PRIMARY KEY,
                     provider_id     TEXT NOT NULL,
                     model           TEXT NOT NULL,
                     base_url        TEXT,
                     key_fingerprint TEXT,
                     connected_at_ms INTEGER,
                     last_ok_at_ms   INTEGER,
                     last_error      TEXT
                 );",
            )?;
        }

        if version < 2 {
            // MCP servers the user connected. The credential is *not* here —
            // it lives in the keychain, keyed by `id` — so this table can be
            // read for display without touching a secret.
            conn.execute_batch(
                "CREATE TABLE IF NOT EXISTS mcp_servers (
                     id            TEXT PRIMARY KEY,
                     user_id       TEXT NOT NULL,
                     name          TEXT NOT NULL,
                     transport     TEXT NOT NULL,
                     url           TEXT,
                     command       TEXT,
                     args          TEXT NOT NULL,
                     enabled       INTEGER NOT NULL DEFAULT 1,
                     created_at_ms INTEGER NOT NULL,
                     last_ok_at_ms INTEGER,
                     last_error    TEXT
                 );
                 CREATE INDEX IF NOT EXISTS ix_mcp_servers_user
                     ON mcp_servers (user_id, created_at_ms);",
            )?;
        }

        if version < 3 {
            // Two unrelated things land in the same step because they share a
            // version bump, not a purpose.
            //
            // `agent_memories` is the agent's own long-term notes: durable, per
            // user, and never re-fetchable, so it belongs here rather than in
            // the disposable cache. `source_session` records where a note came
            // from so a later audit can tell an operator "this was saved while
            // reading a channel" — the one fact that decides whether a memory is
            // trustworthy.
            //
            // `agent_prefs` is a tiny key/value table for machine-local
            // switches (whether class-3 approvals use the OS dialog). It is not
            // user-scoped: it is a property of *this install*, not of an
            // account, and it must be readable before anyone signs in.
            conn.execute_batch(
                "CREATE TABLE IF NOT EXISTS agent_memories (
                     id             TEXT PRIMARY KEY,
                     user_id        TEXT NOT NULL,
                     text           TEXT NOT NULL,
                     tags           TEXT NOT NULL,
                     created_at     INTEGER NOT NULL,
                     last_used_at   INTEGER,
                     source_session TEXT
                 );
                 CREATE INDEX IF NOT EXISTS ix_agent_memories_recent
                     ON agent_memories (user_id, last_used_at DESC, created_at DESC);

                 CREATE TABLE IF NOT EXISTS agent_prefs (
                     key   TEXT PRIMARY KEY,
                     value TEXT NOT NULL
                 );",
            )?;
        }

        conn.execute_batch(&format!("PRAGMA user_version = {SCHEMA_VERSION}"))?;
        Ok(())
    }

    // ── Memories ────────────────────────────────────────────────────────

    /// Save a note. `text` is capped at [`MEMORY_TEXT_CAP`] characters; a
    /// longer one is refused rather than silently truncated, because a note cut
    /// mid-sentence is worse than no note.
    pub fn add_memory(
        &self,
        user_id: &str,
        text: &str,
        tags: &[String],
        source_session: Option<&str>,
    ) -> Result<AgentMemory> {
        let text = text.trim();
        if text.is_empty() {
            return Err(Error::Other("빈 기억은 저장할 수 없습니다.".into()));
        }
        if text.chars().count() > MEMORY_TEXT_CAP {
            return Err(Error::Other(format!(
                "기억은 {MEMORY_TEXT_CAP}자를 넘을 수 없습니다."
            )));
        }
        let memory = AgentMemory {
            id: new_ulid(),
            text: text.to_string(),
            tags: tags.to_vec(),
            created_at: Some(now_ms()),
            last_used_at: None,
        };
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_memories
                 (id, user_id, text, tags, created_at, last_used_at, source_session)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            rusqlite::params![
                memory.id,
                user_id,
                memory.text,
                serde_json::to_string(&memory.tags).unwrap_or_else(|_| "[]".into()),
                memory.created_at,
                memory.last_used_at,
                source_session,
            ],
        )?;
        Ok(memory)
    }

    /// The most recently used (then most recently created) memories.
    pub fn list_memories(&self, user_id: &str, limit: u32) -> Result<Vec<AgentMemory>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, text, tags, created_at, last_used_at
             FROM agent_memories WHERE user_id = ?1
             ORDER BY COALESCE(last_used_at, created_at) DESC, created_at DESC
             LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![user_id, limit], memory_from_row)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// Find memories matching `query` in their text or tags, most recent first,
    /// and mark the hits as just used so recall keeps a note near the top.
    pub fn search_memories(
        &self,
        user_id: &str,
        query: &str,
        limit: u32,
    ) -> Result<Vec<AgentMemory>> {
        let conn = self.conn()?;
        // `escape` so a user searching for `50%` or `a_b` gets a literal match
        // rather than a wildcard.
        let pattern = format!(
            "%{}%",
            query
                .replace('\\', "\\\\")
                .replace('%', "\\%")
                .replace('_', "\\_")
        );
        let mut stmt = conn.prepare(
            "SELECT id, text, tags, created_at, last_used_at
             FROM agent_memories
             WHERE user_id = ?1
               AND (text LIKE ?2 ESCAPE '\\' OR tags LIKE ?2 ESCAPE '\\')
             ORDER BY COALESCE(last_used_at, created_at) DESC, created_at DESC
             LIMIT ?3",
        )?;
        let mut rows = stmt
            .query_map(rusqlite::params![user_id, pattern, limit], memory_from_row)?
            .collect::<rusqlite::Result<Vec<_>>>()?;

        if !rows.is_empty() {
            let now = now_ms();
            for memory in &mut rows {
                conn.execute(
                    "UPDATE agent_memories SET last_used_at = ?2 WHERE id = ?1",
                    rusqlite::params![memory.id, now],
                )?;
                // Reflect the touch in what we return, so a caller sees the note
                // it just used as freshly used rather than reading stale state.
                memory.last_used_at = Some(now);
            }
        }
        Ok(rows)
    }

    /// Forget one note. Scoped to the user so a stale id from another account
    /// cannot delete something it never owned.
    pub fn delete_memory(&self, user_id: &str, id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "DELETE FROM agent_memories WHERE id = ?1 AND user_id = ?2",
            rusqlite::params![id, user_id],
        )?;
        Ok(())
    }

    // ── Preferences ─────────────────────────────────────────────────────

    /// Read a machine-local preference, if it has ever been set.
    pub fn get_pref(&self, key: &str) -> Result<Option<String>> {
        let conn = self.conn()?;
        Ok(conn
            .query_row(
                "SELECT value FROM agent_prefs WHERE key = ?1",
                rusqlite::params![key],
                |row| row.get(0),
            )
            .optional()?)
    }

    /// Set a machine-local preference.
    pub fn set_pref(&self, key: &str, value: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_prefs (key, value) VALUES (?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            rusqlite::params![key, value],
        )?;
        Ok(())
    }

    // ── MCP servers ───────────────────────────────────────────────────────

    /// Insert or replace a server record. The credential is stored separately
    /// in the keychain by the engine; nothing here touches it.
    pub fn save_mcp_server(&self, server: &crate::agent::mcp::McpServer) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO mcp_servers
                 (id, user_id, name, transport, url, command, args, enabled,
                  created_at_ms, last_ok_at_ms, last_error)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)
             ON CONFLICT(id) DO UPDATE SET
                 name          = excluded.name,
                 transport     = excluded.transport,
                 url           = excluded.url,
                 command       = excluded.command,
                 args          = excluded.args,
                 enabled       = excluded.enabled,
                 last_ok_at_ms = excluded.last_ok_at_ms,
                 last_error    = excluded.last_error",
            rusqlite::params![
                server.id,
                server.user_id,
                server.name,
                server.transport.as_str(),
                server.url,
                server.command,
                serde_json::to_string(&server.args).unwrap_or_else(|_| "[]".into()),
                server.enabled as i32,
                server.created_at_ms,
                server.last_ok_at_ms,
                server.last_error,
            ],
        )?;
        Ok(())
    }

    pub fn mcp_servers(&self, user_id: &str) -> Result<Vec<crate::agent::mcp::McpServer>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, user_id, name, transport, url, command, args, enabled,
                    created_at_ms, last_ok_at_ms, last_error
             FROM mcp_servers WHERE user_id = ?1 ORDER BY created_at_ms",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![user_id], |row| {
                let transport: String = row.get(3)?;
                let args: String = row.get(6)?;
                let enabled: i32 = row.get(7)?;
                Ok(crate::agent::mcp::McpServer {
                    id: row.get(0)?,
                    user_id: row.get(1)?,
                    name: row.get(2)?,
                    transport: crate::agent::mcp::Transport::parse(&transport)
                        .unwrap_or(crate::agent::mcp::Transport::Http),
                    url: row.get(4)?,
                    command: row.get(5)?,
                    args: serde_json::from_str(&args).unwrap_or_default(),
                    enabled: enabled != 0,
                    created_at_ms: row.get(8)?,
                    last_ok_at_ms: row.get(9)?,
                    last_error: row.get(10)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    pub fn mcp_server(&self, id: &str) -> Result<Option<crate::agent::mcp::McpServer>> {
        Ok(self.mcp_servers_by_id(id)?.into_iter().next())
    }

    fn mcp_servers_by_id(&self, id: &str) -> Result<Vec<crate::agent::mcp::McpServer>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, user_id, name, transport, url, command, args, enabled,
                    created_at_ms, last_ok_at_ms, last_error
             FROM mcp_servers WHERE id = ?1",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![id], |row| {
                let transport: String = row.get(3)?;
                let args: String = row.get(6)?;
                let enabled: i32 = row.get(7)?;
                Ok(crate::agent::mcp::McpServer {
                    id: row.get(0)?,
                    user_id: row.get(1)?,
                    name: row.get(2)?,
                    transport: crate::agent::mcp::Transport::parse(&transport)
                        .unwrap_or(crate::agent::mcp::Transport::Http),
                    url: row.get(4)?,
                    command: row.get(5)?,
                    args: serde_json::from_str(&args).unwrap_or_default(),
                    enabled: enabled != 0,
                    created_at_ms: row.get(8)?,
                    last_ok_at_ms: row.get(9)?,
                    last_error: row.get(10)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    pub fn set_mcp_enabled(&self, id: &str, enabled: bool) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE mcp_servers SET enabled = ?2 WHERE id = ?1",
            rusqlite::params![id, enabled as i32],
        )?;
        Ok(())
    }

    pub fn mcp_touch(&self, id: &str, error: Option<&str>) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE mcp_servers SET last_ok_at_ms = ?2, last_error = ?3 WHERE id = ?1",
            rusqlite::params![
                id,
                if error.is_none() {
                    Some(now_ms())
                } else {
                    None::<i64>
                },
                error,
            ],
        )?;
        Ok(())
    }

    pub fn delete_mcp_server(&self, id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "DELETE FROM mcp_servers WHERE id = ?1",
            rusqlite::params![id],
        )?;
        Ok(())
    }

    /// Put a large value in the artifact store from outside a tool handler
    /// (a sub-agent's answer). Returns the handle and byte count.
    pub fn store_text(&self, session_id: &str, label: &str, text: &str) -> Result<(String, u64)> {
        let (artifact, _) = self.put_artifact(
            session_id,
            label,
            text,
            serde_json::json!({ "label": label }),
        )?;
        Ok((artifact.id, artifact.bytes))
    }

    /// The schema version currently on disk.
    pub fn schema_version(&self) -> Result<i32> {
        let conn = self.conn()?;
        Ok(conn.query_row("PRAGMA user_version", [], |row| row.get(0))?)
    }

    // ── Sessions ────────────────────────────────────────────────────────

    pub fn create_session(
        &self,
        user_id: &str,
        workspace_id: Option<&str>,
        provider_id: &str,
        model: &str,
    ) -> Result<AgentSession> {
        let now = now_ms();
        let session = AgentSession {
            id: new_ulid(),
            user_id: user_id.to_string(),
            workspace_id: workspace_id.map(str::to_string),
            title: None,
            provider_id: provider_id.to_string(),
            model: model.to_string(),
            created_at_ms: now,
            last_active_at_ms: now,
        };
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_sessions
                 (id, user_id, workspace_id, title, provider_id, model,
                  created_at_ms, last_active_at_ms)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            rusqlite::params![
                session.id,
                session.user_id,
                session.workspace_id,
                session.title,
                session.provider_id,
                session.model,
                session.created_at_ms,
                session.last_active_at_ms,
            ],
        )?;
        Ok(session)
    }

    /// Most recently active first.
    pub fn sessions(&self, user_id: &str, limit: u32) -> Result<Vec<AgentSession>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT id, user_id, workspace_id, title, provider_id, model,
                    created_at_ms, last_active_at_ms
             FROM agent_sessions WHERE user_id = ?1
             ORDER BY last_active_at_ms DESC LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![user_id, limit], |row| {
                Ok(AgentSession {
                    id: row.get(0)?,
                    user_id: row.get(1)?,
                    workspace_id: row.get(2)?,
                    title: row.get(3)?,
                    provider_id: row.get(4)?,
                    model: row.get(5)?,
                    created_at_ms: row.get(6)?,
                    last_active_at_ms: row.get(7)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    pub fn set_session_title(&self, session_id: &str, title: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "UPDATE agent_sessions SET title = ?2, last_active_at_ms = ?3 WHERE id = ?1",
            rusqlite::params![session_id, title, now_ms()],
        )?;
        Ok(())
    }

    // ── Messages ────────────────────────────────────────────────────────

    /// Append a turn. `seq` is assigned here so it can never be reused.
    pub fn append_message(
        &self,
        session_id: &str,
        role: &str,
        blocks: &serde_json::Value,
        provider_payload: Option<&serde_json::Value>,
    ) -> Result<i64> {
        let conn = self.conn()?;
        let next: i64 = conn
            .query_row(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_messages WHERE session_id = ?1",
                rusqlite::params![session_id],
                |row| row.get(0),
            )
            .optional()?
            .unwrap_or(1);

        conn.execute(
            "INSERT INTO agent_messages
                 (session_id, seq, role, blocks, provider_payload, created_at_ms)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            rusqlite::params![
                session_id,
                next,
                role,
                blocks.to_string(),
                provider_payload.map(|p| p.to_string()),
                now_ms(),
            ],
        )?;
        conn.execute(
            "UPDATE agent_sessions SET last_active_at_ms = ?2 WHERE id = ?1",
            rusqlite::params![session_id, now_ms()],
        )?;
        Ok(next)
    }

    /// Every turn in a session, oldest first.
    pub fn messages(&self, session_id: &str) -> Result<Vec<AgentMessage>> {
        let conn = self.conn()?;
        let mut stmt = conn.prepare(
            "SELECT session_id, seq, role, blocks, provider_payload, created_at_ms
             FROM agent_messages WHERE session_id = ?1 ORDER BY seq",
        )?;
        let rows = stmt
            .query_map(rusqlite::params![session_id], |row| {
                let blocks: String = row.get(3)?;
                let payload: Option<String> = row.get(4)?;
                Ok(AgentMessage {
                    session_id: row.get(0)?,
                    seq: row.get(1)?,
                    role: row.get(2)?,
                    blocks: serde_json::from_str(&blocks).unwrap_or(serde_json::Value::Null),
                    provider_payload: payload.and_then(|p| serde_json::from_str(&p).ok()),
                    created_at_ms: row.get(5)?,
                })
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    }

    // ── Artifacts: the RLM seam ─────────────────────────────────────────

    /// Store a large value and get back its handle plus a preview.
    ///
    /// The preview is head and tail rather than a prefix: for a channel
    /// history or a build log, the last few lines are usually the ones that
    /// matter, and a prefix-only preview makes the model spend a turn asking
    /// for the tail every single time.
    pub fn put_artifact(
        &self,
        session_id: &str,
        kind: &str,
        body: &str,
        meta: serde_json::Value,
    ) -> Result<(Artifact, ArtifactPreview)> {
        let lines: Vec<&str> = body.lines().collect();
        let artifact = Artifact {
            id: format!("art_{}", new_ulid()),
            session_id: session_id.to_string(),
            kind: kind.to_string(),
            bytes: body.len() as u64,
            lines: lines.len() as u64,
            meta,
            created_at_ms: now_ms(),
        };

        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_artifacts
                 (id, session_id, kind, body, bytes, lines, meta, created_at_ms)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            rusqlite::params![
                artifact.id,
                artifact.session_id,
                artifact.kind,
                body,
                artifact.bytes,
                artifact.lines,
                artifact.meta.to_string(),
                artifact.created_at_ms,
            ],
        )?;

        let preview = ArtifactPreview {
            handle: artifact.id.clone(),
            total_lines: lines.len(),
            bytes: body.len(),
            head: lines
                .iter()
                .take(PREVIEW_LINES)
                .map(|s| s.to_string())
                .collect(),
            tail: if lines.len() > PREVIEW_LINES * 2 {
                lines
                    .iter()
                    .skip(lines.len() - PREVIEW_LINES)
                    .map(|s| s.to_string())
                    .collect()
            } else {
                Vec::new()
            },
            inline: if body.len() <= INLINE_BYTE_LIMIT {
                Some(body.to_string())
            } else {
                None
            },
        };

        Ok((artifact, preview))
    }

    pub fn artifact(&self, handle: &str) -> Result<Option<Artifact>> {
        let conn = self.conn()?;
        let row = conn
            .query_row(
                "SELECT id, session_id, kind, bytes, lines, meta, created_at_ms
                 FROM agent_artifacts WHERE id = ?1",
                rusqlite::params![handle],
                |row| {
                    let meta: String = row.get(5)?;
                    Ok(Artifact {
                        id: row.get(0)?,
                        session_id: row.get(1)?,
                        kind: row.get(2)?,
                        bytes: row.get(3)?,
                        lines: row.get(4)?,
                        meta: serde_json::from_str(&meta).unwrap_or(serde_json::Value::Null),
                        created_at_ms: row.get(6)?,
                    })
                },
            )
            .optional()?;
        Ok(row)
    }

    /// Run one fixed verb against a stored artifact.
    ///
    /// `max_lines` is the caller's cap, not the model's: a `grep` that matches
    /// everything must not undo the point of storing the value out of context.
    pub fn query_artifact(
        &self,
        handle: &str,
        op: &ArtifactOp,
        max_lines: usize,
    ) -> Result<ArtifactSlice> {
        let conn = self.conn()?;
        let body: String = conn
            .query_row(
                "SELECT body FROM agent_artifacts WHERE id = ?1",
                rusqlite::params![handle],
                |row| row.get(0),
            )
            .optional()?
            .ok_or_else(|| Error::Other(format!("no artifact with the handle {handle}")))?;

        let lines: Vec<&str> = body.lines().collect();
        let total = lines.len();

        let (from, selected): (usize, Vec<String>) = match op {
            ArtifactOp::Count => (0, Vec::new()),
            ArtifactOp::Head { lines: n } => (
                0,
                lines
                    .iter()
                    .take((*n).min(max_lines))
                    .map(|s| s.to_string())
                    .collect(),
            ),
            ArtifactOp::Tail { lines: n } => {
                let take = (*n).min(max_lines).min(total);
                (
                    total - take,
                    lines[total - take..]
                        .iter()
                        .map(|s| s.to_string())
                        .collect(),
                )
            }
            ArtifactOp::Slice { from, to } => {
                let start = (*from).min(total);
                let end = (*to).min(total).max(start);
                let end = end.min(start + max_lines);
                (
                    start,
                    lines[start..end].iter().map(|s| s.to_string()).collect(),
                )
            }
            ArtifactOp::Grep { pattern, limit } => {
                let cap = (*limit).min(max_lines);
                let matched: Vec<String> = lines
                    .iter()
                    .filter(|line| line.contains(pattern.as_str()))
                    .take(cap)
                    .map(|s| s.to_string())
                    .collect();
                (0, matched)
            }
        };

        let requested = match op {
            ArtifactOp::Head { lines: n } | ArtifactOp::Tail { lines: n } => *n,
            ArtifactOp::Slice { from, to } => to.saturating_sub(*from),
            ArtifactOp::Grep { limit, .. } => *limit,
            ArtifactOp::Count => 0,
        };

        Ok(ArtifactSlice {
            handle: handle.to_string(),
            op: op.verb().to_string(),
            from_line: from,
            truncated: requested > selected.len() && selected.len() == max_lines,
            lines: selected,
            total_lines: total,
        })
    }

    /// Drop artifacts older than `keep_ms`. Called when a panel opens; there
    /// is no reason to carry last week's build logs around.
    pub fn prune_artifacts(&self, keep_ms: i64) -> Result<usize> {
        let conn = self.conn()?;
        let cutoff = now_ms() - keep_ms;
        let removed = conn.execute(
            "DELETE FROM agent_artifacts WHERE created_at_ms < ?1",
            rusqlite::params![cutoff],
        )?;
        Ok(removed)
    }

    // ── Approvals ───────────────────────────────────────────────────────

    /// Record what the user decided. This is the honest answer to "what did it
    /// do on my machine", and the seed data for an audit screen.
    pub fn record_approval(
        &self,
        session_id: &str,
        tool: &str,
        summary: &str,
        args: &serde_json::Value,
        verdict: &str,
    ) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_approvals
                 (id, session_id, tool, summary, args, verdict, decided_at_ms)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            rusqlite::params![
                new_ulid(),
                session_id,
                tool,
                summary,
                args.to_string(),
                verdict,
                now_ms(),
            ],
        )?;
        Ok(())
    }

    pub fn approval_count(&self, session_id: &str) -> Result<i64> {
        let conn = self.conn()?;
        Ok(conn.query_row(
            "SELECT COUNT(*) FROM agent_approvals WHERE session_id = ?1",
            rusqlite::params![session_id],
            |row| row.get(0),
        )?)
    }

    // ── Settings ────────────────────────────────────────────────────────

    /// Store the provider selection. Never the key — only a fingerprint for
    /// display, so a settings screen can say "…a91b" without the secret ever
    /// leaving the keychain.
    pub fn save_settings(&self, settings: &ProviderSettings) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "INSERT INTO agent_settings
                 (user_id, provider_id, model, base_url, key_fingerprint,
                  connected_at_ms, last_ok_at_ms, last_error)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
             ON CONFLICT(user_id) DO UPDATE SET
                 provider_id     = excluded.provider_id,
                 model           = excluded.model,
                 base_url        = excluded.base_url,
                 key_fingerprint = excluded.key_fingerprint,
                 connected_at_ms = excluded.connected_at_ms,
                 last_ok_at_ms   = excluded.last_ok_at_ms,
                 last_error      = excluded.last_error",
            rusqlite::params![
                settings.user_id,
                settings.provider_id,
                settings.model,
                settings.base_url,
                settings.key_fingerprint,
                settings.connected_at_ms,
                settings.last_ok_at_ms,
                settings.last_error,
            ],
        )?;
        Ok(())
    }

    pub fn settings(&self, user_id: &str) -> Result<Option<ProviderSettings>> {
        let conn = self.conn()?;
        let row = conn
            .query_row(
                "SELECT user_id, provider_id, model, base_url, key_fingerprint,
                        connected_at_ms, last_ok_at_ms, last_error
                 FROM agent_settings WHERE user_id = ?1",
                rusqlite::params![user_id],
                |row| {
                    Ok(ProviderSettings {
                        user_id: row.get(0)?,
                        provider_id: row.get(1)?,
                        model: row.get(2)?,
                        base_url: row.get(3)?,
                        key_fingerprint: row.get(4)?,
                        connected_at_ms: row.get(5)?,
                        last_ok_at_ms: row.get(6)?,
                        last_error: row.get(7)?,
                    })
                },
            )
            .optional()?;
        Ok(row)
    }

    pub fn clear_settings(&self, user_id: &str) -> Result<()> {
        let conn = self.conn()?;
        conn.execute(
            "DELETE FROM agent_settings WHERE user_id = ?1",
            rusqlite::params![user_id],
        )?;
        Ok(())
    }
}

/// What a tool hands back instead of a wall of text.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactPreview {
    pub handle: String,
    pub total_lines: usize,
    pub bytes: usize,
    pub head: Vec<String>,
    /// Empty when the whole thing already fits in `head`.
    pub tail: Vec<String>,
    /// The full body, present only when it is small enough that a second round
    /// trip would cost more than the tokens.
    pub inline: Option<String>,
}

/// One saved note the agent may recall in a later turn.
///
/// `created_at` and `last_used_at` are epoch milliseconds. They are `Option`
/// so the shape survives a future migration that adds a memory without a
/// timestamp, and so the field names match the panel's own type exactly.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentMemory {
    pub id: String,
    pub text: String,
    pub tags: Vec<String>,
    pub created_at: Option<i64>,
    pub last_used_at: Option<i64>,
}

/// Read a memory out of a `SELECT id, text, tags, created_at, last_used_at` row.
fn memory_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<AgentMemory> {
    let tags: String = row.get(2)?;
    Ok(AgentMemory {
        id: row.get(0)?,
        text: row.get(1)?,
        tags: serde_json::from_str(&tags).unwrap_or_default(),
        created_at: row.get(3)?,
        last_used_at: row.get(4)?,
    })
}

/// The provider selection, minus the secret.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProviderSettings {
    pub user_id: String,
    pub provider_id: String,
    pub model: String,
    pub base_url: Option<String>,
    /// Last four characters of the key, for display only.
    pub key_fingerprint: Option<String>,
    pub connected_at_ms: Option<i64>,
    pub last_ok_at_ms: Option<i64>,
    pub last_error: Option<String>,
}

fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> AgentStore {
        AgentStore::in_memory().unwrap()
    }

    fn session(store: &AgentStore) -> AgentSession {
        store
            .create_session("01ALICE", Some("01WS"), "anthropic", "claude-opus-5")
            .unwrap()
    }

    #[test]
    fn a_fresh_store_is_at_the_current_schema_version() {
        assert_eq!(store().schema_version().unwrap(), SCHEMA_VERSION);
    }

    #[test]
    fn mcp_servers_round_trip_and_forget_cleanly() {
        use crate::agent::mcp::{McpServer, Transport};
        let store = store();
        let server = McpServer {
            id: "01SRV".into(),
            user_id: "u1".into(),
            name: "Notion".into(),
            transport: Transport::Http,
            url: Some("https://mcp.notion.example/".into()),
            command: None,
            args: vec![],
            enabled: true,
            created_at_ms: now_ms(),
            last_ok_at_ms: None,
            last_error: None,
        };
        store.save_mcp_server(&server).unwrap();
        let loaded = store.mcp_servers("u1").unwrap();
        assert_eq!(loaded.len(), 1);
        assert_eq!(
            loaded[0].url.as_deref(),
            Some("https://mcp.notion.example/")
        );
        assert!(store.mcp_servers("u2").unwrap().is_empty());

        store.set_mcp_enabled("01SRV", false).unwrap();
        assert!(!store.mcp_server("01SRV").unwrap().unwrap().enabled);
        store.mcp_touch("01SRV", Some("연결 실패")).unwrap();
        assert_eq!(
            store
                .mcp_server("01SRV")
                .unwrap()
                .unwrap()
                .last_error
                .as_deref(),
            Some("연결 실패")
        );

        // A stdio server keeps its command and args across the round trip.
        store
            .save_mcp_server(&McpServer {
                id: "01STD".into(),
                user_id: "u1".into(),
                name: "local".into(),
                transport: Transport::Stdio,
                url: None,
                command: Some("mcp-fs".into()),
                args: vec!["--root".into(), "/tmp".into()],
                enabled: true,
                created_at_ms: now_ms(),
                last_ok_at_ms: None,
                last_error: None,
            })
            .unwrap();
        let std_server = store.mcp_server("01STD").unwrap().unwrap();
        assert_eq!(std_server.args, vec!["--root", "/tmp"]);

        store.delete_mcp_server("01SRV").unwrap();
        assert_eq!(store.mcp_servers("u1").unwrap().len(), 1);
    }

    #[test]
    fn a_store_written_by_a_newer_build_is_refused_rather_than_downgraded() {
        let dir = std::env::temp_dir().join(format!(
            "llack-agent-future-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        {
            let store = AgentStore::open(&dir).unwrap();
            let conn = store.conn().unwrap();
            conn.execute_batch("PRAGMA user_version = 99").unwrap();
        }
        // Matched rather than `unwrap_err`'d: `AgentStore` holds a connection
        // pool and is deliberately not `Debug`.
        match AgentStore::open(&dir) {
            Err(err) => assert!(err.to_string().contains("newer version"), "got {err}"),
            Ok(_) => panic!("a newer schema must not be opened by an older build"),
        }
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn sessions_come_back_most_recently_active_first() {
        let store = store();
        let first = session(&store);
        std::thread::sleep(std::time::Duration::from_millis(2));
        let second = session(&store);
        store
            .append_message(&second.id, "user", &serde_json::json!([]), None)
            .unwrap();

        let listed = store.sessions("01ALICE", 10).unwrap();
        assert_eq!(listed[0].id, second.id);
        assert_eq!(listed[1].id, first.id);
    }

    #[test]
    fn another_users_sessions_are_not_listed() {
        let store = store();
        session(&store);
        assert!(store.sessions("01BOB", 10).unwrap().is_empty());
    }

    #[test]
    fn message_seq_starts_at_one_and_is_never_reused() {
        let store = store();
        let s = session(&store);
        assert_eq!(
            store
                .append_message(&s.id, "user", &serde_json::json!([{"type":"text"}]), None)
                .unwrap(),
            1
        );
        assert_eq!(
            store
                .append_message(&s.id, "assistant", &serde_json::json!([]), None)
                .unwrap(),
            2
        );
        assert_eq!(
            store
                .append_message(&s.id, "user", &serde_json::json!([]), None)
                .unwrap(),
            3
        );
    }

    #[test]
    fn the_provider_payload_survives_the_round_trip() {
        let store = store();
        let s = session(&store);
        // Anthropic thinking blocks have to be replayed verbatim, so this
        // column existing is what stops a second provider forcing a migration.
        let payload = serde_json::json!({"provider": "anthropic", "thinking": "opaque"});
        store
            .append_message(&s.id, "assistant", &serde_json::json!([]), Some(&payload))
            .unwrap();
        let messages = store.messages(&s.id).unwrap();
        assert_eq!(messages[0].provider_payload.as_ref().unwrap(), &payload);
    }

    // ── Artifacts ───────────────────────────────────────────────────────

    #[test]
    fn a_small_body_comes_back_inline_so_no_second_round_trip_is_needed() {
        let store = store();
        let s = session(&store);
        let (_, preview) = store
            .put_artifact(
                &s.id,
                "chat_history",
                "one\ntwo\nthree",
                serde_json::json!({}),
            )
            .unwrap();
        assert_eq!(preview.inline.as_deref(), Some("one\ntwo\nthree"));
        assert_eq!(preview.total_lines, 3);
    }

    #[test]
    fn a_large_body_is_a_handle_with_a_head_and_a_tail_but_no_inline() {
        let store = store();
        let s = session(&store);
        let body: String = (0..500).map(|i| format!("line {i}\n")).collect();
        let (artifact, preview) = store
            .put_artifact(
                &s.id,
                "exec_output",
                &body,
                serde_json::json!({"argv": ["make"]}),
            )
            .unwrap();

        assert!(preview.inline.is_none(), "a large body must not be inlined");
        assert!(artifact.id.starts_with("art_"));
        assert_eq!(preview.total_lines, 500);
        assert_eq!(preview.head.len(), PREVIEW_LINES);
        assert_eq!(preview.tail.len(), PREVIEW_LINES);
        assert_eq!(preview.head[0], "line 0");
        assert_eq!(preview.tail[PREVIEW_LINES - 1], "line 499");
    }

    #[test]
    fn head_tail_slice_and_count_return_the_right_windows() {
        let store = store();
        let s = session(&store);
        let body: String = (0..100).map(|i| format!("l{i}\n")).collect();
        let (artifact, _) = store
            .put_artifact(&s.id, "exec_output", &body, serde_json::json!({}))
            .unwrap();

        let head = store
            .query_artifact(&artifact.id, &ArtifactOp::Head { lines: 5 }, 50)
            .unwrap();
        assert_eq!(head.from_line, 0);
        assert_eq!(head.lines, vec!["l0", "l1", "l2", "l3", "l4"]);
        assert_eq!(head.total_lines, 100);

        let tail = store
            .query_artifact(&artifact.id, &ArtifactOp::Tail { lines: 3 }, 50)
            .unwrap();
        assert_eq!(tail.from_line, 97);
        assert_eq!(tail.lines, vec!["l97", "l98", "l99"]);

        let slice = store
            .query_artifact(&artifact.id, &ArtifactOp::Slice { from: 10, to: 13 }, 50)
            .unwrap();
        assert_eq!(slice.from_line, 10);
        assert_eq!(slice.lines, vec!["l10", "l11", "l12"]);

        let count = store
            .query_artifact(&artifact.id, &ArtifactOp::Count, 50)
            .unwrap();
        assert_eq!(count.total_lines, 100);
        assert!(count.lines.is_empty());
    }

    #[test]
    fn a_grep_that_matches_everything_is_still_capped() {
        let store = store();
        let s = session(&store);
        let body: String = (0..1000).map(|i| format!("match {i}\n")).collect();
        let (artifact, _) = store
            .put_artifact(&s.id, "exec_output", &body, serde_json::json!({}))
            .unwrap();

        let hit = store
            .query_artifact(
                &artifact.id,
                &ArtifactOp::Grep {
                    pattern: "match".into(),
                    limit: 10_000,
                },
                20,
            )
            .unwrap();
        assert_eq!(hit.lines.len(), 20, "the caller's cap must win");
        assert!(hit.truncated);
    }

    #[test]
    fn a_window_past_the_end_is_clamped_rather_than_panicking() {
        let store = store();
        let s = session(&store);
        let (artifact, _) = store
            .put_artifact(&s.id, "exec_output", "a\nb\n", serde_json::json!({}))
            .unwrap();

        for op in [
            ArtifactOp::Head { lines: 999 },
            ArtifactOp::Tail { lines: 999 },
            ArtifactOp::Slice { from: 50, to: 90 },
            ArtifactOp::Slice { from: 1, to: 0 },
        ] {
            let slice = store.query_artifact(&artifact.id, &op, 100).unwrap();
            assert!(slice.lines.len() <= 2, "{op:?} returned {slice:?}");
        }
    }

    #[test]
    fn multibyte_lines_survive_slicing() {
        let store = store();
        let s = session(&store);
        let body = "첫째 줄\n둘째 줄\n셋째 줄\n";
        let (artifact, _) = store
            .put_artifact(&s.id, "chat_history", body, serde_json::json!({}))
            .unwrap();
        let slice = store
            .query_artifact(&artifact.id, &ArtifactOp::Slice { from: 1, to: 2 }, 10)
            .unwrap();
        assert_eq!(slice.lines, vec!["둘째 줄"]);
    }

    #[test]
    fn querying_an_unknown_handle_is_an_error_not_an_empty_result() {
        let store = store();
        let err = store
            .query_artifact("art_nope", &ArtifactOp::Count, 10)
            .unwrap_err();
        assert!(err.to_string().contains("art_nope"), "got {err}");
    }

    #[test]
    fn pruning_drops_old_artifacts_and_keeps_new_ones() {
        let store = store();
        let s = session(&store);
        let (old, _) = store
            .put_artifact(&s.id, "exec_output", "old", serde_json::json!({}))
            .unwrap();
        // Backdate it a week.
        {
            let conn = store.conn().unwrap();
            conn.execute(
                "UPDATE agent_artifacts SET created_at_ms = ?2 WHERE id = ?1",
                rusqlite::params![old.id, now_ms() - 7 * 86_400_000],
            )
            .unwrap();
        }
        let (fresh, _) = store
            .put_artifact(&s.id, "exec_output", "new", serde_json::json!({}))
            .unwrap();

        assert_eq!(store.prune_artifacts(86_400_000).unwrap(), 1);
        assert!(store.artifact(&old.id).unwrap().is_none());
        assert!(store.artifact(&fresh.id).unwrap().is_some());
    }

    #[test]
    fn artifact_metadata_is_kept_but_never_the_body_in_the_summary_row() {
        let store = store();
        let s = session(&store);
        let (artifact, _) = store
            .put_artifact(
                &s.id,
                "chat_history",
                "secret content here",
                serde_json::json!({"channel_id": "01CH", "message_count": 3}),
            )
            .unwrap();
        let stored = store.artifact(&artifact.id).unwrap().unwrap();
        assert_eq!(stored.meta["channel_id"], "01CH");
        assert_eq!(stored.bytes, 19);
        // `Artifact` intentionally has no body field: the summary a caller
        // passes around cannot leak the payload by accident.
        let json = serde_json::to_string(&stored).unwrap();
        assert!(!json.contains("secret content"));
    }

    // ── Approvals and settings ──────────────────────────────────────────

    #[test]
    fn approvals_are_recorded_per_session() {
        let store = store();
        let s = session(&store);
        store
            .record_approval(
                &s.id,
                "host.exec",
                "이 명령을 실행합니다",
                &serde_json::json!({"argv": ["git", "status"]}),
                "approved",
            )
            .unwrap();
        store
            .record_approval(
                &s.id,
                "host.exec",
                "이 명령을 실행합니다",
                &serde_json::json!({"argv": ["rm", "-rf", "/"]}),
                "refused",
            )
            .unwrap();
        assert_eq!(store.approval_count(&s.id).unwrap(), 2);
    }

    #[test]
    fn settings_round_trip_and_hold_a_fingerprint_not_a_key() {
        let store = store();
        let settings = ProviderSettings {
            user_id: "01ALICE".into(),
            provider_id: "anthropic".into(),
            model: "claude-opus-5".into(),
            base_url: None,
            key_fingerprint: Some("a91b".into()),
            connected_at_ms: Some(now_ms()),
            last_ok_at_ms: None,
            last_error: None,
        };
        store.save_settings(&settings).unwrap();
        let loaded = store.settings("01ALICE").unwrap().unwrap();
        assert_eq!(loaded, settings);
        assert_eq!(loaded.key_fingerprint.as_deref().unwrap().len(), 4);

        // Saving again updates rather than duplicating.
        store.save_settings(&settings).unwrap();
        assert!(store.settings("01ALICE").unwrap().is_some());

        store.clear_settings("01ALICE").unwrap();
        assert!(store.settings("01ALICE").unwrap().is_none());
    }

    // ── Memories ────────────────────────────────────────────────────────

    #[test]
    fn a_memory_round_trips_with_its_tags() {
        let store = store();
        let memory = store
            .add_memory(
                "01ALICE",
                "배포는 화요일에",
                &["deploy".into(), "schedule".into()],
                Some("01SESSION"),
            )
            .unwrap();
        assert!(memory.created_at.is_some());
        assert!(memory.last_used_at.is_none());

        let listed = store.list_memories("01ALICE", 10).unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].text, "배포는 화요일에");
        assert_eq!(listed[0].tags, vec!["deploy", "schedule"]);
    }

    #[test]
    fn another_users_memories_are_neither_listed_nor_searchable() {
        let store = store();
        store
            .add_memory("01ALICE", "앨리스의 기억", &[], None)
            .unwrap();
        assert!(store.list_memories("01BOB", 10).unwrap().is_empty());
        assert!(store
            .search_memories("01BOB", "기억", 10)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn an_over_long_or_empty_memory_is_refused_rather_than_truncated() {
        let store = store();
        assert!(store.add_memory("01ALICE", "   ", &[], None).is_err());
        let long = "가".repeat(MEMORY_TEXT_CAP + 1);
        assert!(store.add_memory("01ALICE", &long, &[], None).is_err());
        // Exactly at the cap is fine.
        assert!(store
            .add_memory("01ALICE", &"나".repeat(MEMORY_TEXT_CAP), &[], None)
            .is_ok());
    }

    #[test]
    fn searching_matches_text_or_tags_and_marks_the_hit_as_used() {
        let store = store();
        store
            .add_memory("01ALICE", "스테이징 URL", &["infra".into()], None)
            .unwrap();
        store
            .add_memory("01ALICE", "관련 없는 메모", &["misc".into()], None)
            .unwrap();

        // A tag match counts, not just a body match.
        let by_tag = store.search_memories("01ALICE", "infra", 10).unwrap();
        assert_eq!(by_tag.len(), 1);
        assert_eq!(by_tag[0].text, "스테이징 URL");
        assert!(
            by_tag[0].last_used_at.is_some(),
            "a hit must be marked as just used"
        );

        let by_text = store.search_memories("01ALICE", "메모", 10).unwrap();
        assert_eq!(by_text.len(), 1);
        assert_eq!(by_text[0].text, "관련 없는 메모");
    }

    #[test]
    fn a_wildcard_in_the_query_is_matched_literally() {
        let store = store();
        store
            .add_memory("01ALICE", "쿠폰은 50% 할인", &[], None)
            .unwrap();
        store
            .add_memory("01ALICE", "그냥 텍스트", &[], None)
            .unwrap();
        // `%` must not behave as a wildcard that matches everything.
        let hits = store.search_memories("01ALICE", "50%", 10).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].text, "쿠폰은 50% 할인");
    }

    #[test]
    fn forgetting_a_memory_removes_it_but_only_for_its_owner() {
        let store = store();
        let memory = store.add_memory("01ALICE", "지울 기억", &[], None).unwrap();
        // Another user cannot delete it.
        store.delete_memory("01BOB", &memory.id).unwrap();
        assert_eq!(store.list_memories("01ALICE", 10).unwrap().len(), 1);
        // The owner can.
        store.delete_memory("01ALICE", &memory.id).unwrap();
        assert!(store.list_memories("01ALICE", 10).unwrap().is_empty());
    }

    // ── Preferences ─────────────────────────────────────────────────────

    #[test]
    fn a_pref_round_trips_and_updates_in_place() {
        let store = store();
        assert_eq!(store.get_pref("native_dialogs").unwrap(), None);
        store.set_pref("native_dialogs", "0").unwrap();
        assert_eq!(
            store.get_pref("native_dialogs").unwrap().as_deref(),
            Some("0")
        );
        store.set_pref("native_dialogs", "1").unwrap();
        assert_eq!(
            store.get_pref("native_dialogs").unwrap().as_deref(),
            Some("1")
        );
    }
}
