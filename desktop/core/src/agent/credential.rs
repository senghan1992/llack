//! The provider API key: stored in the OS keychain, never handed back.
//!
//! The webview renders untrusted markdown. That single fact decides the whole
//! module: the key is written once on the way in, read only by the byte proxy
//! on its way to `api.anthropic.com`, and the only thing that ever crosses back
//! to the UI is a four-character fingerprint. There is deliberately no
//! `get_key` on this type — if the panel could ask for the key, an injected
//! script in the panel could ask for the key.
//!
//! The account namespace is flat (the OS keychain has no directories), so keys
//! are derived from the user id rather than enumerated. `clear_for_user` has to
//! be told which providers to forget; the list lives in [`PROVIDERS`] so that
//! adding an adapter and forgetting to clear its credential on logout is one
//! diff, not two.

use std::sync::Arc;

use crate::error::{Error, ProviderErrorCode, Result};
use crate::session::TokenStore;

/// Every provider whose credential may be on this machine.
///
/// v1 ships one adapter. The constant exists so `clear_for_user` stays correct
/// when the second one lands.
pub const PROVIDERS: &[&str] = &["anthropic", "openai"];

/// The keychain account for an MCP server's bearer token.
pub fn mcp_account(server_id: &str) -> String {
    format!("mcp:{server_id}")
}

/// The keychain account for a provider key.
fn key_account(provider_id: &str, user_id: &str) -> String {
    format!("agent-provider:{provider_id}:{user_id}")
}

/// The keychain account for the audit chain head.
pub fn audit_head_account(user_id: &str) -> String {
    format!("audit-head:{user_id}")
}

/// What the UI is allowed to know about a stored key.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct KeyFingerprint {
    /// The last four characters. Enough to tell two keys apart on screen,
    /// useless to anyone who steals it.
    pub tail: String,
}

impl KeyFingerprint {
    /// `None` for a key too short to fingerprint without revealing most of it.
    fn of(key: &str) -> Option<Self> {
        let chars: Vec<char> = key.chars().collect();
        if chars.len() < 12 {
            return None;
        }
        Some(Self {
            tail: chars[chars.len() - 4..].iter().collect(),
        })
    }
}

/// The smallest shape a key must have to be worth sending anywhere.
///
/// Not a claim of validity — only the provider can say that, which is why
/// connecting makes one real call. This rejects the mistakes that are cheap to
/// catch locally: an empty box, a pasted line with whitespace or a newline in
/// it, something that is plainly not a key.
pub fn vet_key(provider_id: &str, key: &str) -> Result<()> {
    if key.is_empty() {
        return Err(Error::provider(
            ProviderErrorCode::KeyRejected,
            "API 키를 입력해주세요.",
        ));
    }
    // A newline in a header value is request splitting. It cannot be allowed
    // to reach the proxy even though the proxy checks again.
    if key.chars().any(|c| c.is_whitespace()) {
        return Err(Error::provider(
            ProviderErrorCode::KeyRejected,
            "API 키에 공백이나 줄바꿈이 들어 있습니다. 앞뒤를 확인해주세요.",
        ));
    }
    if !key.is_ascii() {
        return Err(Error::provider(
            ProviderErrorCode::KeyRejected,
            "API 키에 ASCII 가 아닌 문자가 있습니다. 복사 과정에서 섞인 것 같습니다.",
        ));
    }
    if key.len() < 12 {
        return Err(Error::provider(
            ProviderErrorCode::KeyRejected,
            "API 키가 너무 짧습니다.",
        ));
    }
    if provider_id == "anthropic" && !key.starts_with("sk-ant-") {
        return Err(Error::provider(
            ProviderErrorCode::KeyRejected,
            "Anthropic API 키는 sk-ant- 로 시작합니다.",
        ));
    }
    Ok(())
}

/// The keychain-backed credential store.
///
/// Cloneable and cheap: it holds an `Arc` to the same `TokenStore` the session
/// uses, so there is one keychain integration on this machine rather than two.
#[derive(Clone)]
pub struct CredentialStore {
    tokens: Arc<dyn TokenStore>,
}

impl CredentialStore {
    pub fn new(tokens: Arc<dyn TokenStore>) -> Self {
        Self { tokens }
    }

    /// Store a key, returning what the UI may display.
    pub fn put(
        &self,
        provider_id: &str,
        user_id: &str,
        key: &str,
    ) -> Result<Option<KeyFingerprint>> {
        vet_key(provider_id, key)?;
        self.tokens.save(&key_account(provider_id, user_id), key)?;
        Ok(KeyFingerprint::of(key))
    }

    /// The fingerprint of the stored key, or `None` if there is none.
    pub fn fingerprint(&self, provider_id: &str, user_id: &str) -> Result<Option<KeyFingerprint>> {
        Ok(self
            .tokens
            .load(&key_account(provider_id, user_id))?
            .as_deref()
            .and_then(KeyFingerprint::of))
    }

    pub fn has(&self, provider_id: &str, user_id: &str) -> Result<bool> {
        Ok(self
            .tokens
            .load(&key_account(provider_id, user_id))?
            .is_some())
    }

    /// Read the key for outbound use only.
    ///
    /// `pub(crate)` on purpose: the byte proxy in `provider` is the only caller,
    /// and no Tauri command can reach it. This is the boundary the module doc
    /// is about, and Rust enforces it rather than a convention.
    pub(crate) fn key(&self, provider_id: &str, user_id: &str) -> Result<String> {
        self.tokens
            .load(&key_account(provider_id, user_id))?
            .ok_or_else(|| {
                Error::provider(
                    ProviderErrorCode::NotConnected,
                    "연결된 프로바이더가 없습니다.",
                )
            })
    }

    pub fn delete(&self, provider_id: &str, user_id: &str) -> Result<()> {
        self.tokens.delete(&key_account(provider_id, user_id))
    }

    /// Store a secret under an arbitrary account (MCP bearer tokens).
    ///
    /// The same keychain-only discipline as a provider key: written on the way
    /// in, read only for an outbound request, never returned to the webview.
    pub fn put_secret(&self, account: &str, secret: &str) -> Result<()> {
        self.tokens.save(account, secret)
    }

    /// Read a stored secret. `pub(crate)` like [`Self::key`]: only the MCP
    /// client, reached through the engine, calls it.
    pub(crate) fn secret(&self, account: &str) -> Result<Option<String>> {
        self.tokens.load(account)
    }

    pub fn has_secret(&self, account: &str) -> Result<bool> {
        Ok(self.tokens.load(account)?.is_some())
    }

    pub fn delete_secret(&self, account: &str) -> Result<()> {
        self.tokens.delete(account)
    }

    /// Forget everything this user's agent stored in the keychain.
    ///
    /// Called from sign-out and from `AppState::reset`. Deleting a key that is
    /// not there is not an error: the keychain cannot be enumerated, so the
    /// only way to be thorough is to ask for each name unconditionally.
    pub fn clear_for_user(&self, user_id: &str) -> Result<()> {
        let mut first_error = None;
        for provider in PROVIDERS {
            if let Err(error) = self.tokens.delete(&key_account(provider, user_id)) {
                first_error = first_error.or(Some(error));
            }
        }
        if let Err(error) = self.tokens.delete(&audit_head_account(user_id)) {
            first_error = first_error.or(Some(error));
        }
        match first_error {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::MemoryTokenStore;

    const KEY: &str = "sk-ant-api03-abcdefghijklmnop-XYZW";

    fn store() -> (CredentialStore, Arc<MemoryTokenStore>) {
        let tokens = Arc::new(MemoryTokenStore::default());
        (CredentialStore::new(tokens.clone()), tokens)
    }

    #[test]
    fn a_key_goes_in_and_only_a_fingerprint_comes_out() {
        let (creds, _) = store();
        let fingerprint = creds.put("anthropic", "u1", KEY).unwrap().unwrap();
        assert_eq!(fingerprint.tail, "XYZW");
        assert_eq!(
            creds.fingerprint("anthropic", "u1").unwrap(),
            Some(fingerprint)
        );
        assert!(creds.has("anthropic", "u1").unwrap());
    }

    #[test]
    fn the_fingerprint_never_contains_the_secret_part() {
        let (creds, _) = store();
        let fingerprint = creds.put("anthropic", "u1", KEY).unwrap().unwrap();
        assert!(!KEY.contains(&format!("{}{}", "sk-ant-", fingerprint.tail)));
        assert_eq!(fingerprint.tail.chars().count(), 4);
    }

    #[test]
    fn two_users_on_one_machine_do_not_share_a_key() {
        let (creds, _) = store();
        creds.put("anthropic", "u1", KEY).unwrap();
        assert!(!creds.has("anthropic", "u2").unwrap());
        assert!(creds.key("anthropic", "u2").is_err());
    }

    #[test]
    fn signing_out_removes_the_key_and_the_audit_anchor() {
        let (creds, tokens) = store();
        creds.put("anthropic", "u1", KEY).unwrap();
        tokens.save(&audit_head_account("u1"), "deadbeef").unwrap();

        creds.clear_for_user("u1").unwrap();

        assert!(!creds.has("anthropic", "u1").unwrap());
        assert_eq!(tokens.load(&audit_head_account("u1")).unwrap(), None);
    }

    #[test]
    fn clearing_a_user_with_nothing_stored_is_not_an_error() {
        let (creds, _) = store();
        creds.clear_for_user("never-signed-in").unwrap();
    }

    #[test]
    fn a_key_with_a_newline_is_refused_before_it_can_split_a_request() {
        let (creds, _) = store();
        for bad in [
            "sk-ant-api03-abc\r\nX-Evil: 1",
            "sk-ant-api03-abc def",
            "sk-ant-api03-abc\n",
            " sk-ant-api03-abcdefghijkl",
        ] {
            assert!(
                creds.put("anthropic", "u1", bad).is_err(),
                "accepted {bad:?}"
            );
        }
        assert!(!creds.has("anthropic", "u1").unwrap(), "nothing was stored");
    }

    #[test]
    fn obvious_non_keys_are_refused_locally() {
        let (creds, _) = store();
        for bad in [
            "",
            "short",
            "sk-ant-x",
            "키를여기에붙여넣으세요",
            "hunter2hunter2",
        ] {
            assert!(
                creds.put("anthropic", "u1", bad).is_err(),
                "accepted {bad:?}"
            );
        }
    }

    #[test]
    fn a_short_key_gets_no_fingerprint_rather_than_a_revealing_one() {
        // Reached only if a provider's format check does not apply, but the
        // rule belongs to the fingerprint rather than to the caller.
        assert_eq!(KeyFingerprint::of("sk-ant-abc"), None);
    }
}
