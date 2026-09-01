//! Error type shared by every core operation.

use std::fmt;

/// The stable error envelope every Llack API endpoint returns.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct ApiErrorBody {
    pub code: String,
    pub message: String,
    #[serde(default)]
    pub details: Option<serde_json::Value>,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct ApiErrorEnvelope {
    pub error: ApiErrorBody,
}

#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// The server answered with a non-2xx status and a parseable error body.
    #[error("{}: {}", .body.code, .body.message)]
    Api { status: u16, body: ApiErrorBody },

    /// The request never reached the server, or the response was unreadable.
    #[error("network error: {0}")]
    Network(String),

    /// Credentials are missing, expired, or were revoked server-side.
    #[error("not authenticated: {0}")]
    Unauthenticated(String),

    #[error("local cache error: {0}")]
    Cache(String),

    #[error("realtime error: {0}")]
    Realtime(String),

    #[error("invalid configuration: {0}")]
    Config(String),

    #[error("{0}")]
    Other(String),
}

impl Error {
    /// The machine-readable code, so callers can branch without string
    /// matching on messages.
    pub fn code(&self) -> &str {
        match self {
            Error::Api { body, .. } => &body.code,
            Error::Network(_) => "network_error",
            Error::Unauthenticated(_) => "unauthenticated",
            Error::Cache(_) => "cache_error",
            Error::Realtime(_) => "realtime_error",
            Error::Config(_) => "config_error",
            Error::Other(_) => "unknown_error",
        }
    }

    pub fn status(&self) -> Option<u16> {
        match self {
            Error::Api { status, .. } => Some(*status),
            _ => None,
        }
    }

    /// Whether retrying the same request could plausibly succeed.
    ///
    /// Used by the outbox: a retryable failure stays queued, anything else is
    /// surfaced to the user instead of being retried forever.
    pub fn is_retryable(&self) -> bool {
        match self {
            Error::Network(_) => true,
            Error::Api { status, .. } => *status == 429 || *status >= 500,
            _ => false,
        }
    }

    /// Whether the local session is no longer usable and the user must sign in.
    pub fn requires_reauth(&self) -> bool {
        match self {
            Error::Unauthenticated(_) => true,
            Error::Api { status, body } => {
                *status == 401
                    && matches!(
                        body.code.as_str(),
                        "session_revoked"
                            | "refresh_expired"
                            | "refresh_invalid"
                            | "account_inactive"
                    )
            }
            _ => false,
        }
    }
}

impl From<reqwest::Error> for Error {
    fn from(value: reqwest::Error) -> Self {
        Error::Network(value.to_string())
    }
}

impl From<rusqlite::Error> for Error {
    fn from(value: rusqlite::Error) -> Self {
        Error::Cache(value.to_string())
    }
}

impl From<r2d2::Error> for Error {
    fn from(value: r2d2::Error) -> Self {
        Error::Cache(value.to_string())
    }
}

impl serde::Serialize for Error {
    /// Serialised for the Tauri IPC boundary, keeping the code/message split
    /// so the UI can localise on `code` rather than parse a string.
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut state = serializer.serialize_struct("Error", 4)?;
        state.serialize_field("code", self.code())?;
        state.serialize_field("message", &self.to_string())?;
        state.serialize_field("status", &self.status())?;
        state.serialize_field("requires_reauth", &self.requires_reauth())?;
        state.end()
    }
}

pub type Result<T> = std::result::Result<T, Error>;

/// Small helper so `?` works on things that only carry a message.
pub fn other<E: fmt::Display>(err: E) -> Error {
    Error::Other(err.to_string())
}
