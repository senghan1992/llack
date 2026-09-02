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

    /// The model provider refused, is unreachable, or was never connected.
    ///
    /// Separate from [`Error::Api`] because that one carries the *Llack*
    /// server's error envelope, and separate from [`Error::Other`] because the
    /// panel has to branch on these: "your key was rejected" opens the setup
    /// form, "rate limited" offers a retry, and telling them apart by
    /// substring-matching a Korean sentence is exactly what `code()` exists to
    /// prevent.
    #[error("{message}")]
    Provider {
        code: ProviderErrorCode,
        message: String,
    },

    /// An approval was not granted.
    ///
    /// Not a failure of the tool — a decision about it, or the absence of one.
    /// The loop tells the model and carries on, and the card that is on screen
    /// needs to know which of the four it was.
    #[error("{message}")]
    Approval {
        code: ApprovalErrorCode,
        message: String,
    },

    #[error("{0}")]
    Other(String),
}

/// Why a provider request did not succeed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderErrorCode {
    /// No key in the keychain. The panel shows the setup form.
    NotConnected,
    /// The provider rejected the key (401/403).
    KeyRejected,
    /// Rate limited or provider-side failure — retrying may work.
    Unavailable,
    /// The request never left this machine: vetting refused it.
    RequestRefused,
    /// The stream was cut before it ended.
    Truncated,
}

impl ProviderErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NotConnected => "provider_not_connected",
            Self::KeyRejected => "provider_key_rejected",
            Self::Unavailable => "provider_unavailable",
            Self::RequestRefused => "provider_request_refused",
            Self::Truncated => "provider_truncated",
        }
    }

    /// Whether the same request could plausibly succeed on a retry.
    pub fn is_retryable(self) -> bool {
        matches!(self, Self::Unavailable | Self::Truncated)
    }
}

/// What happened to an approval request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApprovalErrorCode {
    /// The user said no.
    Denied,
    /// Nobody answered in time.
    Expired,
    /// The turn ended before an answer arrived.
    Cancelled,
    /// The id or nonce did not match anything answerable. Distinct from the
    /// three above: it means the *panel* is out of step, not the user.
    Stale,
    /// The policy refused outright — no approval could have helped.
    Refused,
}

impl ApprovalErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Denied => "approval_denied",
            Self::Expired => "approval_expired",
            Self::Cancelled => "approval_cancelled",
            Self::Stale => "approval_stale",
            Self::Refused => "policy_refused",
        }
    }
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
            Error::Provider { code, .. } => code.as_str(),
            Error::Approval { code, .. } => code.as_str(),
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
            Error::Provider { code, .. } => code.is_retryable(),
            _ => false,
        }
    }

    /// Build a provider error.
    pub fn provider(code: ProviderErrorCode, message: impl Into<String>) -> Self {
        Error::Provider {
            code,
            message: message.into(),
        }
    }

    /// Build an approval error.
    pub fn approval(code: ApprovalErrorCode, message: impl Into<String>) -> Self {
        Error::Approval {
            code,
            message: message.into(),
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

#[cfg(test)]
mod tests {
    use super::*;

    /// The codes are a contract with the webview, which branches on them. A
    /// renamed variant that silently changes a code would turn a handled state
    /// into "unknown error" with no compile error anywhere.
    #[test]
    fn the_agent_codes_are_stable_strings() {
        assert_eq!(
            Error::provider(ProviderErrorCode::NotConnected, "x").code(),
            "provider_not_connected"
        );
        assert_eq!(
            Error::provider(ProviderErrorCode::KeyRejected, "x").code(),
            "provider_key_rejected"
        );
        assert_eq!(
            Error::provider(ProviderErrorCode::RequestRefused, "x").code(),
            "provider_request_refused"
        );
        assert_eq!(
            Error::approval(ApprovalErrorCode::Denied, "x").code(),
            "approval_denied"
        );
        assert_eq!(
            Error::approval(ApprovalErrorCode::Stale, "x").code(),
            "approval_stale"
        );
        assert_eq!(
            Error::approval(ApprovalErrorCode::Refused, "x").code(),
            "policy_refused"
        );
    }

    /// The panel groups by prefix (`approval_*` renders as declined), so the
    /// prefixes have to hold.
    #[test]
    fn approval_codes_share_a_prefix_and_provider_codes_share_theirs() {
        for code in [
            ApprovalErrorCode::Denied,
            ApprovalErrorCode::Expired,
            ApprovalErrorCode::Cancelled,
            ApprovalErrorCode::Stale,
        ] {
            assert!(code.as_str().starts_with("approval_"), "{code:?}");
        }
        for code in [
            ProviderErrorCode::NotConnected,
            ProviderErrorCode::KeyRejected,
            ProviderErrorCode::Unavailable,
            ProviderErrorCode::RequestRefused,
            ProviderErrorCode::Truncated,
        ] {
            assert!(code.as_str().starts_with("provider_"), "{code:?}");
        }
    }

    #[test]
    fn only_a_transient_provider_failure_is_retryable() {
        assert!(Error::provider(ProviderErrorCode::Unavailable, "x").is_retryable());
        assert!(Error::provider(ProviderErrorCode::Truncated, "x").is_retryable());
        // Retrying a refused URL or a rejected key just fails again, and a
        // retry loop on a 401 looks like a brute-force attempt from outside.
        assert!(!Error::provider(ProviderErrorCode::KeyRejected, "x").is_retryable());
        assert!(!Error::provider(ProviderErrorCode::RequestRefused, "x").is_retryable());
        assert!(!Error::provider(ProviderErrorCode::NotConnected, "x").is_retryable());
    }

    #[test]
    fn the_envelope_carries_the_code_and_the_message() {
        let json = serde_json::to_value(Error::provider(
            ProviderErrorCode::KeyRejected,
            "API 키가 거부되었습니다.",
        ))
        .unwrap();
        assert_eq!(json["code"], "provider_key_rejected");
        assert_eq!(json["message"], "API 키가 거부되었습니다.");
        assert_eq!(json["requires_reauth"], false);
    }
}
