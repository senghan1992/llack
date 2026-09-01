//! Credential storage and access-token refresh.
//!
//! The refresh token is long-lived, so it belongs in the OS keychain, not in a
//! file next to the app. `TokenStore` is a trait for exactly that reason: the
//! core crate stays platform-independent and testable, while the Tauri shell
//! plugs in a keyring-backed implementation.

use std::sync::Arc;

use parking_lot::RwLock;
use tokio::sync::Mutex as AsyncMutex;

use crate::error::{Error, Result};
use crate::models::{TokenPair, User};

/// Where the refresh token is persisted between launches.
pub trait TokenStore: Send + Sync + 'static {
    fn load(&self, account: &str) -> Result<Option<String>>;
    fn save(&self, account: &str, refresh_token: &str) -> Result<()>;
    fn delete(&self, account: &str) -> Result<()>;
}

/// In-memory store. Used in tests, and as a fallback when no OS keychain is
/// available (a headless CI container, for instance) — in that case the user
/// simply has to sign in again on next launch.
#[derive(Default)]
pub struct MemoryTokenStore {
    inner: RwLock<std::collections::HashMap<String, String>>,
}

impl MemoryTokenStore {
    pub fn new() -> Self {
        Self::default()
    }
}

impl TokenStore for MemoryTokenStore {
    fn load(&self, account: &str) -> Result<Option<String>> {
        Ok(self.inner.read().get(account).cloned())
    }

    fn save(&self, account: &str, refresh_token: &str) -> Result<()> {
        self.inner
            .write()
            .insert(account.to_string(), refresh_token.to_string());
        Ok(())
    }

    fn delete(&self, account: &str) -> Result<()> {
        self.inner.write().remove(account);
        Ok(())
    }
}

/// The signed-in state, shared across the API client, realtime client and the
/// Tauri commands.
pub struct Session {
    state: RwLock<SessionState>,
    store: Arc<dyn TokenStore>,
    /// Serialises refresh attempts. Without it, a burst of requests that all
    /// see a 401 would each spend the refresh token, and rotation means only
    /// the first would succeed — the rest would log the user out.
    refresh_lock: AsyncMutex<()>,
    account_key: String,
}

#[derive(Default, Clone)]
struct SessionState {
    access_token: Option<String>,
    refresh_token: Option<String>,
    /// Unix millis at which the access token expires.
    access_expires_at_ms: Option<i64>,
    user: Option<User>,
}

impl Session {
    pub fn new(store: Arc<dyn TokenStore>, account_key: impl Into<String>) -> Self {
        Self {
            state: RwLock::new(SessionState::default()),
            store,
            refresh_lock: AsyncMutex::new(()),
            account_key: account_key.into(),
        }
    }

    /// Restore the refresh token saved by a previous launch. The access token
    /// is intentionally not persisted — it is short-lived and cheap to re-mint.
    pub fn restore(&self) -> Result<bool> {
        let saved = self.store.load(&self.account_key)?;
        let found = saved.is_some();
        self.state.write().refresh_token = saved;
        Ok(found)
    }

    pub fn adopt(&self, tokens: &TokenPair, user: Option<User>) -> Result<()> {
        {
            let mut state = self.state.write();
            state.access_token = Some(tokens.access_token.clone());
            state.refresh_token = Some(tokens.refresh_token.clone());
            state.access_expires_at_ms = parse_rfc3339_ms(&tokens.expires_at);
            if let Some(user) = user {
                state.user = Some(user);
            }
        }
        self.store.save(&self.account_key, &tokens.refresh_token)
    }

    pub fn clear(&self) -> Result<()> {
        *self.state.write() = SessionState::default();
        self.store.delete(&self.account_key)
    }

    pub fn access_token(&self) -> Option<String> {
        self.state.read().access_token.clone()
    }

    pub fn refresh_token(&self) -> Option<String> {
        self.state.read().refresh_token.clone()
    }

    pub fn user(&self) -> Option<User> {
        self.state.read().user.clone()
    }

    pub fn set_user(&self, user: User) {
        self.state.write().user = Some(user);
    }

    pub fn user_id(&self) -> Option<String> {
        self.state.read().user.as_ref().map(|u| u.id.clone())
    }

    pub fn is_authenticated(&self) -> bool {
        self.state.read().refresh_token.is_some()
    }

    /// Whether the access token is expired or close enough that it would
    /// likely expire in flight.
    pub fn access_token_is_stale(&self, skew_seconds: i64) -> bool {
        let state = self.state.read();
        match (state.access_token.as_ref(), state.access_expires_at_ms) {
            (None, _) => true,
            (Some(_), None) => false,
            (Some(_), Some(expires_at)) => now_ms() + skew_seconds * 1000 >= expires_at,
        }
    }

    /// Guard for the single-flight refresh. Callers acquire this, then
    /// re-check staleness — the token may already have been refreshed by
    /// whoever held the lock first.
    pub async fn refresh_guard(&self) -> tokio::sync::MutexGuard<'_, ()> {
        self.refresh_lock.lock().await
    }

    pub fn require_refresh_token(&self) -> Result<String> {
        self.refresh_token()
            .ok_or_else(|| Error::Unauthenticated("no refresh token stored".into()))
    }
}

pub fn now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// Parse the subset of RFC 3339 the backend emits, to Unix millis.
///
/// A hand-rolled parser rather than a date library: the only input is our own
/// server's `datetime.isoformat()` output, and this keeps the dependency
/// surface of the desktop client smaller.
pub fn parse_rfc3339_ms(value: &str) -> Option<i64> {
    let bytes = value.as_bytes();
    if bytes.len() < 19 {
        return None;
    }
    let num =
        |range: std::ops::Range<usize>| -> Option<i64> { value.get(range)?.parse::<i64>().ok() };
    let year = num(0..4)?;
    let month = num(5..7)?;
    let day = num(8..10)?;
    let hour = num(11..13)?;
    let minute = num(14..16)?;
    let second = num(17..19)?;

    if !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return None;
    }

    // Fractional seconds, if present.
    let mut millis = 0i64;
    let rest = &value[19..];
    let mut offset_part = rest;
    if let Some(stripped) = rest.strip_prefix('.') {
        let digits: String = stripped
            .chars()
            .take_while(|c| c.is_ascii_digit())
            .collect();
        offset_part = &stripped[digits.len()..];
        let mut frac = digits;
        frac.truncate(3);
        while frac.len() < 3 {
            frac.push('0');
        }
        millis = frac.parse().unwrap_or(0);
    }

    let days = days_from_civil(year, month as u32, day as u32);
    let mut epoch_ms = ((days * 86_400) + hour * 3600 + minute * 60 + second) * 1000 + millis;

    // Timezone offset. 'Z' or missing means UTC.
    if let Some(sign_index) = offset_part.find(['+', '-']) {
        let sign = if offset_part.as_bytes()[sign_index] == b'-' {
            1
        } else {
            -1
        };
        let tz = &offset_part[sign_index + 1..];
        let tz_hours: i64 = tz.get(0..2).and_then(|s| s.parse().ok()).unwrap_or(0);
        let tz_minutes: i64 = tz.get(3..5).and_then(|s| s.parse().ok()).unwrap_or(0);
        epoch_ms += sign * (tz_hours * 3600 + tz_minutes * 60) * 1000;
    }
    Some(epoch_ms)
}

/// Days since 1970-01-01 — Howard Hinnant's `days_from_civil`.
fn days_from_civil(year: i64, month: u32, day: u32) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (month as i64 + 9) % 12;
    let doy = (153 * mp + 2) / 5 + day as i64 - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tokens(expires_at: &str) -> TokenPair {
        TokenPair {
            access_token: "access".into(),
            refresh_token: "refresh".into(),
            token_type: "Bearer".into(),
            expires_at: expires_at.into(),
            expires_in: 900,
        }
    }

    #[test]
    fn parses_utc_timestamps() {
        assert_eq!(parse_rfc3339_ms("1970-01-01T00:00:00Z"), Some(0));
        assert_eq!(parse_rfc3339_ms("1970-01-01T00:00:01Z"), Some(1_000));
        assert_eq!(
            parse_rfc3339_ms("2024-01-01T00:00:00Z"),
            Some(1_704_067_200_000)
        );
        // Python's isoformat() emits microseconds and +00:00 rather than Z.
        assert_eq!(
            parse_rfc3339_ms("2024-01-01T00:00:00.500000+00:00"),
            Some(1_704_067_200_500)
        );
    }

    #[test]
    fn applies_timezone_offsets() {
        // 09:00 in KST is 00:00 UTC.
        assert_eq!(
            parse_rfc3339_ms("2024-01-01T09:00:00+09:00"),
            Some(1_704_067_200_000)
        );
    }

    #[test]
    fn rejects_garbage_timestamps() {
        assert_eq!(parse_rfc3339_ms("not-a-date"), None);
        assert_eq!(parse_rfc3339_ms(""), None);
        assert_eq!(parse_rfc3339_ms("2024-13-01T00:00:00Z"), None);
    }

    #[test]
    fn adopting_tokens_persists_only_the_refresh_token() {
        let store = std::sync::Arc::new(MemoryTokenStore::new());
        let session = Session::new(store.clone(), "https://api.example.com");

        assert!(!session.is_authenticated());
        session
            .adopt(&tokens("2099-01-01T00:00:00Z"), None)
            .unwrap();

        assert!(session.is_authenticated());
        assert_eq!(session.access_token().as_deref(), Some("access"));
        assert_eq!(
            store.load("https://api.example.com").unwrap().as_deref(),
            Some("refresh"),
            "the refresh token belongs in the keychain"
        );
    }

    #[test]
    fn restore_brings_back_a_saved_refresh_token() {
        let store = std::sync::Arc::new(MemoryTokenStore::new());
        store.save("acct", "saved-refresh").unwrap();

        let session = Session::new(store, "acct");
        assert!(session.restore().unwrap());
        assert_eq!(session.refresh_token().as_deref(), Some("saved-refresh"));
        // The access token is not persisted, so it must be re-minted.
        assert!(session.access_token().is_none());
        assert!(session.access_token_is_stale(0));
    }

    #[test]
    fn staleness_accounts_for_clock_skew() {
        let store = std::sync::Arc::new(MemoryTokenStore::new());
        let session = Session::new(store, "acct");

        session
            .adopt(&tokens("2099-01-01T00:00:00Z"), None)
            .unwrap();
        assert!(!session.access_token_is_stale(30));

        session
            .adopt(&tokens("2000-01-01T00:00:00Z"), None)
            .unwrap();
        assert!(
            session.access_token_is_stale(0),
            "an expired token is stale"
        );
    }

    #[test]
    fn clear_forgets_everything_including_the_keychain_entry() {
        let store = std::sync::Arc::new(MemoryTokenStore::new());
        let session = Session::new(store.clone(), "acct");
        session
            .adopt(&tokens("2099-01-01T00:00:00Z"), None)
            .unwrap();

        session.clear().unwrap();
        assert!(!session.is_authenticated());
        assert!(session.access_token().is_none());
        assert_eq!(store.load("acct").unwrap(), None);
    }
}
