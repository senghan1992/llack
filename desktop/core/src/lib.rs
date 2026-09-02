//! # llack-core
//!
//! Everything the Llack desktop client does that is not a window: talking to
//! the API, holding the session, keeping the realtime socket alive, caching
//! for offline use, and deciding what a server event changes locally.
//!
//! It deliberately has no dependency on Tauri or any webview, so it builds and
//! its tests run on any machine — including CI without GUI libraries. The
//! `src-tauri` crate is a thin shell that wires this into the desktop shell.
//!
//! ## Shape
//!
//! ```text
//!   Session ─── holds tokens, refreshes them (single-flight)
//!      │
//!   ApiClient ── typed REST calls, error envelope decoding
//!      │
//!   RealtimeClient ── WebSocket, reconnect w/ backoff, seq-gap detection
//!      │
//!   SyncEngine ── applies frames to Cache, drains the outbox
//!      │
//!   Cache ─── SQLite: channels, messages, offline send queue
//! ```

pub mod agent;
pub mod api;
pub mod cache;
pub mod error;
pub mod ids;
pub mod models;
pub mod realtime;
pub mod session;
pub mod sync;

pub use api::{ApiClient, ApiConfig};
pub use cache::{Cache, OutboxEntry, OutboxState};
pub use error::{Error, Result};
pub use models::*;
pub use realtime::{RealtimeClient, RealtimeCommand, RealtimeEvent, RealtimeHandle, ServerFrame};
pub use session::{MemoryTokenStore, Session, TokenStore};
pub use sync::{DrainReport, SyncEffect, SyncEngine};

/// The realtime protocol version this client speaks. The gateway reports its
/// own in `hello`; a mismatch means the client should prompt for an update
/// rather than silently mis-handle frames.
pub const REALTIME_PROTOCOL_VERSION: u32 = 1;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
