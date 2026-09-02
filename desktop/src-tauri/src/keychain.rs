//! OS keychain-backed [`TokenStore`].
//!
//! Refresh tokens are long-lived credentials, so they belong in the platform
//! secret store — Keychain on macOS, Credential Manager on Windows, Secret
//! Service on Linux — not a file next to the app.
//!
//! If no keychain is reachable (a locked session, a headless container), the
//! store degrades to in-memory rather than failing the launch: the user simply
//! has to sign in again next time, which is strictly better than an app that
//! will not start.

use std::sync::Arc;

use llack_core::error::{Error, Result};
use llack_core::session::{MemoryTokenStore, TokenStore};

const SERVICE: &str = "com.llack.desktop";

pub struct KeychainTokenStore {
    /// Used when the platform keychain is unavailable.
    fallback: MemoryTokenStore,
    keychain_available: bool,
}

impl KeychainTokenStore {
    pub fn new() -> Self {
        // Probe once at construction rather than on every access, and treat a
        // "not found" result as success — the slot is simply empty.
        let keychain_available = match keyring::Entry::new(SERVICE, "__probe__") {
            Ok(entry) => !matches!(
                entry.get_password(),
                Err(keyring::Error::PlatformFailure(_))
            ),
            Err(_) => false,
        };
        if !keychain_available {
            tracing::warn!("OS keychain unavailable; credentials will not persist across restarts");
        }
        Self {
            fallback: MemoryTokenStore::new(),
            keychain_available,
        }
    }

    pub fn shared() -> Arc<dyn TokenStore> {
        Arc::new(Self::new())
    }
}

impl Default for KeychainTokenStore {
    fn default() -> Self {
        Self::new()
    }
}

impl TokenStore for KeychainTokenStore {
    fn load(&self, account: &str) -> Result<Option<String>> {
        if !self.keychain_available {
            return self.fallback.load(account);
        }
        let entry = keyring::Entry::new(SERVICE, account)
            .map_err(|e| Error::Other(format!("keychain: {e}")))?;
        match entry.get_password() {
            Ok(secret) => Ok(Some(secret)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(err) => Err(Error::Other(format!("keychain read failed: {err}"))),
        }
    }

    fn save(&self, account: &str, refresh_token: &str) -> Result<()> {
        if !self.keychain_available {
            return self.fallback.save(account, refresh_token);
        }
        let entry = keyring::Entry::new(SERVICE, account)
            .map_err(|e| Error::Other(format!("keychain: {e}")))?;
        entry
            .set_password(refresh_token)
            .map_err(|e| Error::Other(format!("keychain write failed: {e}")))
    }

    fn delete(&self, account: &str) -> Result<()> {
        if !self.keychain_available {
            return self.fallback.delete(account);
        }
        let entry = keyring::Entry::new(SERVICE, account)
            .map_err(|e| Error::Other(format!("keychain: {e}")))?;
        match entry.delete_credential() {
            // Deleting something that is not there is the desired end state.
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(err) => Err(Error::Other(format!("keychain delete failed: {err}"))),
        }
    }
}
