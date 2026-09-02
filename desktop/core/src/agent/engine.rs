//! The one object the desktop shell holds, and the only surface its commands
//! call.
//!
//! Everything below this line is assembled here — the store, the audit log, the
//! approval broker, the tool catalog, the credential store, the byte proxy —
//! so `src-tauri` never has to know how they fit together. That matters more
//! than it sounds: `src-tauri` cannot be compiled in every environment this
//! repository is worked on (it needs webkit2gtk), so anything that lives there
//! ships unverified. Keeping the assembly here means the assembly is tested.
//!
//! ## What the engine does *not* do
//!
//! It does not run the conversation. There is no `turn()` method and no loop.
//! The webview drives, calling `tool_call` once per `tool_use` block and
//! `proxy` once per HTTP request, and this type answers. That is why the
//! session context lives in a map here rather than in a task: there is no task.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use parking_lot::RwLock;

use crate::error::{Error, ProviderErrorCode, Result};
use crate::session::TokenStore;

use super::approval::{ApprovalBroker, ApprovalNotifier};
use super::audit::{AuditActor, AuditLog};
use super::credential::CredentialStore;
use super::policy::SessionContext;
use super::provider::{self, ByteSink, VettedRequest};
use super::store::{AgentSession, AgentStore, ProviderSettings};
use super::tools::{
    self, ExecuteOutcome, HostCapabilities, ToolCatalog, ToolContext, ToolHost, ToolSpec,
};

/// The model used until the user picks one. The choice itself comes from the
/// account's own `/v1/models` (fetched by the panel through the byte proxy)
/// and lands via [`AgentEngine::set_model`] — never as free-typed text.
pub const DEFAULT_MODEL: &str = "claude-opus-5";

/// The provider id v1 ships an adapter for.
pub const DEFAULT_PROVIDER: &str = "anthropic";

/// What the panel is told about the provider. Never contains the key.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ProviderStatus {
    pub connected: bool,
    pub provider_id: String,
    pub model: String,
    pub key_fingerprint: Option<String>,
    pub last_error: Option<String>,
}

impl ProviderStatus {
    /// The shape shown before anyone has connected anything.
    fn disconnected() -> Self {
        Self {
            connected: false,
            provider_id: DEFAULT_PROVIDER.into(),
            model: DEFAULT_MODEL.into(),
            key_fingerprint: None,
            last_error: None,
        }
    }
}

/// Per-session mutable state: what the user granted, and whether the session
/// has been tainted.
///
/// Kept here rather than in SQLite deliberately. A taint flag that survives a
/// restart would be a lie in the safe direction, but a *grant* that survived
/// one would be a lie in the dangerous direction — and the two belong in the
/// same place so nobody persists one and forgets the other. Closing the app
/// forgets both, which is what makes "it ends when I close the panel"
/// structurally true instead of a promise.
#[derive(Debug, Default, Clone)]
struct SessionState {
    tainted: bool,
    roots: Vec<PathBuf>,
    workspace_id: Option<String>,
    channel_id: Option<String>,
}

pub struct AgentEngine {
    store: AgentStore,
    audit: AuditLog,
    broker: Arc<ApprovalBroker>,
    catalog: ToolCatalog,
    credentials: CredentialStore,
    http: reqwest::Client,
    /// Llack's own data directory — the first thing the path policy denies.
    app_data_dir: PathBuf,
    home: Option<PathBuf>,
    /// The signed-in user. `None` before sign-in and after sign-out, and every
    /// method that needs it fails loudly rather than defaulting to a shared
    /// namespace.
    user_id: RwLock<Option<String>>,
    sessions: RwLock<HashMap<String, SessionState>>,
    capabilities: HostCapabilities,
    /// Provider requests currently being relayed, and the subset the user has
    /// asked to stop. Two sets rather than one map because the common read —
    /// "was this aborted?" — happens per chunk and must not contend with the
    /// registration write.
    live_requests: RwLock<std::collections::HashSet<String>>,
    aborted_requests: RwLock<std::collections::HashSet<String>>,
}

impl AgentEngine {
    /// Assemble the engine.
    ///
    /// `data_dir` is Llack's own directory: the agent database and the audit log
    /// go inside it, and the path policy denies every read and write under it.
    #[allow(clippy::too_many_arguments)]
    pub fn open(
        data_dir: PathBuf,
        home: Option<PathBuf>,
        tokens: Arc<dyn TokenStore>,
        notifier: Arc<dyn ApprovalNotifier>,
        capabilities: HostCapabilities,
    ) -> Result<Self> {
        let store = AgentStore::open(data_dir.join("agent.sqlite3"))?;
        let audit = AuditLog::open(
            data_dir.join("agent-audit"),
            AuditActor {
                session_id: String::new(),
                user_id: None,
                server_url: None,
                workspace_id: None,
            },
            Some(tokens.clone()),
        )?;
        Ok(Self {
            store,
            audit,
            broker: Arc::new(ApprovalBroker::new(notifier)),
            catalog: ToolCatalog::builtin(),
            credentials: CredentialStore::new(tokens),
            http: reqwest::Client::builder()
                // Long enough for a slow first token, short enough that a hung
                // socket does not leave the panel spinning forever. The SDK's
                // own per-request timeout is shorter; this is the backstop.
                .timeout(std::time::Duration::from_secs(600))
                .build()
                .map_err(|e| Error::Other(format!("could not build the HTTP client: {e}")))?,
            app_data_dir: data_dir,
            home,
            user_id: RwLock::new(None),
            sessions: RwLock::new(HashMap::new()),
            capabilities,
            live_requests: RwLock::new(std::collections::HashSet::new()),
            aborted_requests: RwLock::new(std::collections::HashSet::new()),
        })
    }

    pub fn broker(&self) -> Arc<ApprovalBroker> {
        self.broker.clone()
    }

    /// The tools to advertise this turn.
    pub fn tools(&self) -> Vec<ToolSpec> {
        self.catalog.expose(self.capabilities)
    }

    // ── Identity ─────────────────────────────────────────────────────────

    pub fn set_user(&self, user_id: &str) {
        *self.user_id.write() = Some(user_id.to_string());
    }

    /// Sign-out. Denies everything in flight, drops every grant, forgets every
    /// session, and deletes the keychain entries.
    ///
    /// Ordering matters: the broker is cancelled *before* the credentials are
    /// removed, so an approval that is answered during sign-out cannot lead to
    /// a request that finds a key still in place.
    pub fn clear_user(&self) -> Result<()> {
        self.broker.cancel_all();
        self.broker.revoke_grants();
        self.sessions.write().clear();
        let user_id = self.user_id.write().take();
        if let Some(user_id) = user_id {
            self.credentials.clear_for_user(&user_id)?;
            self.store.clear_settings(&user_id)?;
        }
        Ok(())
    }

    fn user(&self) -> Result<String> {
        self.user_id
            .read()
            .clone()
            // `Unauthenticated`, not `Other`: the panel's error handling already
            // routes this code to the sign-in screen, and a generic code would
            // show "unknown error" on a state the app knows exactly how to fix.
            .ok_or_else(|| Error::Unauthenticated("로그인이 필요합니다.".into()))
    }

    // ── Provider ─────────────────────────────────────────────────────────

    pub fn provider_status(&self) -> Result<ProviderStatus> {
        let Ok(user_id) = self.user() else {
            return Ok(ProviderStatus::disconnected());
        };
        let fingerprint = self
            .credentials
            .fingerprint(DEFAULT_PROVIDER, &user_id)?
            .map(|f| f.tail);
        let settings = self.store.settings(&user_id)?;
        Ok(ProviderStatus {
            // Connected means "a key is in the keychain", not "settings exist".
            // The keychain is the truth; the row is display state that can
            // survive a keychain the user cleared from the OS.
            connected: fingerprint.is_some(),
            provider_id: settings
                .as_ref()
                .map(|s| s.provider_id.clone())
                .unwrap_or_else(|| DEFAULT_PROVIDER.into()),
            model: settings
                .as_ref()
                .map(|s| s.model.clone())
                .unwrap_or_else(|| DEFAULT_MODEL.into()),
            key_fingerprint: fingerprint,
            last_error: settings.and_then(|s| s.last_error),
        })
    }

    /// Store a key after proving it works.
    ///
    /// Proving comes first: a key that is stored and then found to be invalid
    /// leaves the panel saying "connected" while every turn fails. The proof is
    /// a `GET` on the model, which bills nothing.
    pub async fn connect_provider(
        &self,
        key: &str,
        model: Option<String>,
    ) -> Result<ProviderStatus> {
        let user_id = self.user()?;
        let model = model.unwrap_or_else(|| DEFAULT_MODEL.to_string());

        super::credential::vet_key(DEFAULT_PROVIDER, key)?;

        let (url, method) = provider::validation_request(&model);
        let probe = VettedRequest {
            url,
            method,
            headers: vec![
                ("x-api-key".into(), key.to_string()),
                (
                    "anthropic-version".into(),
                    provider::ANTHROPIC_VERSION.into(),
                ),
            ],
            body: Vec::new(),
        };

        let collector = Collector::default();
        provider::relay(&self.http, probe, &collector).await?;
        // The probe is not abortable and does not need to be: it is one small
        // GET with a short life, and it holds no user-visible stream.
        if let Some(message) = provider::describe_status(collector.status()) {
            let code = match collector.status() {
                401 | 403 | 404 => ProviderErrorCode::KeyRejected,
                _ => ProviderErrorCode::Unavailable,
            };
            // Recorded so the panel can explain itself after a restart, and so
            // the user is not left wondering why the chip says disconnected.
            self.remember_error(&user_id, &model, Some(message.clone()))?;
            return Err(Error::provider(code, message));
        }

        let fingerprint = self.credentials.put(DEFAULT_PROVIDER, &user_id, key)?;
        self.store.save_settings(&ProviderSettings {
            user_id: user_id.clone(),
            provider_id: DEFAULT_PROVIDER.into(),
            model,
            base_url: None,
            key_fingerprint: fingerprint.map(|f| f.tail),
            connected_at_ms: Some(now_ms()),
            last_ok_at_ms: Some(now_ms()),
            last_error: None,
        })?;
        self.provider_status()
    }

    /// Switch models on an already-connected provider, without the key.
    ///
    /// The panel offers the models it fetched from the account through the byte
    /// proxy, so what arrives here has normally been seen in a real `/v1/models`
    /// response — but this is an IPC surface, so the string is still checked:
    /// it later travels into a request path, and a model id is the one part of
    /// that URL the webview gets to choose.
    pub fn set_model(&self, model: &str) -> Result<ProviderStatus> {
        let user_id = self.user()?;
        if !self.credentials.has(DEFAULT_PROVIDER, &user_id)? {
            return Err(Error::provider(
                ProviderErrorCode::RequestRefused,
                "프로바이더가 연결되어 있지 않습니다. 먼저 연결해주세요.",
            ));
        }

        let model = model.trim();
        let sane = !model.is_empty()
            && model.len() <= 128
            && model
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '.' | '_'));
        if !sane {
            return Err(Error::provider(
                ProviderErrorCode::RequestRefused,
                "모델 이름에 사용할 수 없는 문자가 있습니다.",
            ));
        }

        let existing = self.store.settings(&user_id)?;
        self.store.save_settings(&ProviderSettings {
            user_id: user_id.clone(),
            provider_id: DEFAULT_PROVIDER.into(),
            model: model.to_string(),
            base_url: None,
            key_fingerprint: existing.as_ref().and_then(|s| s.key_fingerprint.clone()),
            connected_at_ms: existing.as_ref().and_then(|s| s.connected_at_ms),
            last_ok_at_ms: existing.and_then(|s| s.last_ok_at_ms),
            // A model choice supersedes whatever the old model last complained
            // about; a stale 404 under a freshly chosen model reads as broken.
            last_error: None,
        })?;
        self.provider_status()
    }

    pub fn disconnect_provider(&self) -> Result<ProviderStatus> {
        let user_id = self.user()?;
        self.credentials.delete(DEFAULT_PROVIDER, &user_id)?;
        self.store.clear_settings(&user_id)?;
        // Grants outlive a disconnect otherwise, and "I disconnected the model"
        // should mean the agent can no longer act.
        self.broker.cancel_all();
        self.broker.revoke_grants();
        self.provider_status()
    }

    fn remember_error(&self, user_id: &str, model: &str, error: Option<String>) -> Result<()> {
        let existing = self.store.settings(user_id)?;
        self.store.save_settings(&ProviderSettings {
            user_id: user_id.to_string(),
            provider_id: DEFAULT_PROVIDER.into(),
            model: model.to_string(),
            base_url: None,
            key_fingerprint: existing.as_ref().and_then(|s| s.key_fingerprint.clone()),
            connected_at_ms: existing.as_ref().and_then(|s| s.connected_at_ms),
            last_ok_at_ms: existing.and_then(|s| s.last_ok_at_ms),
            last_error: error,
        })
    }

    /// Relay one provider HTTP request. The key is attached here and nowhere
    /// else.
    ///
    /// `request_id` is generated by the caller and exists so the request can be
    /// aborted. Without it, "stop" would only stop the webview *reading* the
    /// stream while the upstream request ran to completion — still billed, and
    /// still holding a socket. A cancel button that does not cancel is worse
    /// than no cancel button, because the user believes it.
    pub async fn proxy(
        &self,
        request_id: &str,
        url: &str,
        method: &str,
        headers: &[(String, String)],
        body: Vec<u8>,
        sink: &dyn ByteSink,
    ) -> Result<()> {
        let user_id = self.user()?;
        let request = provider::vet_request(
            url,
            method,
            headers,
            body,
            &self.credentials,
            DEFAULT_PROVIDER,
            &user_id,
        )?;

        // Registered *before* the first byte, so an abort that arrives while
        // the connection is still being established is not lost.
        self.live_requests.write().insert(request_id.to_string());
        let guard = AbortAware {
            inner: sink,
            aborted: &self.aborted_requests,
            request_id,
        };
        let result = provider::relay(&self.http, request, &guard).await;
        self.live_requests.write().remove(request_id);
        self.aborted_requests.write().remove(request_id);
        result
    }

    /// Ask an in-flight relay to stop. Takes effect on the next chunk.
    ///
    /// Returns whether there was anything to stop, so the panel can tell
    /// "stopped" from "it had already finished" instead of guessing.
    pub fn abort_request(&self, request_id: &str) -> bool {
        let live = self.live_requests.read().contains(request_id);
        if live {
            self.aborted_requests.write().insert(request_id.to_string());
        }
        live
    }

    // ── Sessions ─────────────────────────────────────────────────────────

    pub fn sessions(&self, limit: u32) -> Result<Vec<AgentSession>> {
        self.store.sessions(&self.user()?, limit)
    }

    /// Open an existing session or start a new one.
    pub fn open_session(
        &self,
        session_id: Option<&str>,
        workspace_id: Option<&str>,
        channel_id: Option<&str>,
    ) -> Result<String> {
        let user_id = self.user()?;
        let status = self.provider_status()?;

        let id = match session_id {
            Some(id) => id.to_string(),
            None => {
                self.store
                    .create_session(&user_id, workspace_id, &status.provider_id, &status.model)?
                    .id
            }
        };

        // A reopened session starts untainted on purpose: the taint marks what
        // is in the *model's context*, and reopening does not replay the
        // transcript into it. If a later version resends history, this is the
        // line that has to change with it.
        self.sessions.write().insert(
            id.clone(),
            SessionState {
                tainted: false,
                roots: Vec::new(),
                workspace_id: workspace_id.map(str::to_string),
                channel_id: channel_id.map(str::to_string),
            },
        );
        Ok(id)
    }

    /// Point the session at a different channel, so `chat.read_channel` with no
    /// argument means "the one I am looking at".
    pub fn focus(&self, session_id: &str, channel_id: Option<&str>) {
        if let Some(state) = self.sessions.write().get_mut(session_id) {
            state.channel_id = channel_id.map(str::to_string);
        }
    }

    /// Grant a directory to a session. The user picks it through the OS dialog;
    /// this only records it.
    pub fn add_root(&self, session_id: &str, root: PathBuf) -> Result<()> {
        let mut sessions = self.sessions.write();
        let state = sessions
            .get_mut(session_id)
            .ok_or_else(|| Error::Other("세션을 찾을 수 없습니다.".into()))?;
        if !state.roots.contains(&root) {
            state.roots.push(root);
        }
        Ok(())
    }

    pub fn is_tainted(&self, session_id: &str) -> bool {
        self.sessions
            .read()
            .get(session_id)
            .map(|s| s.tainted)
            .unwrap_or(false)
    }

    fn context_for(&self, session_id: &str) -> SessionContext {
        let state = self
            .sessions
            .read()
            .get(session_id)
            .cloned()
            .unwrap_or_default();
        SessionContext {
            tainted: state.tainted,
            roots: state.roots,
            home: self.home.clone(),
            app_data_dir: self.app_data_dir.clone(),
        }
    }

    // ── Tools ────────────────────────────────────────────────────────────

    /// Run one tool call. The gate, the audit records, and the approval prompt
    /// all happen inside `tools::execute`; this only supplies the context and
    /// applies the taint afterwards.
    pub async fn tool_call(
        &self,
        session_id: &str,
        name: &str,
        args: &serde_json::Value,
        rationale: Option<String>,
        host: &dyn ToolHost,
    ) -> Result<ExecuteOutcome> {
        let state = self
            .sessions
            .read()
            .get(session_id)
            .cloned()
            .unwrap_or_default();

        let ctx = ToolContext {
            session_id,
            store: &self.store,
            host,
            workspace_id: state.workspace_id.as_deref(),
            channel_id: state.channel_id.as_deref(),
        };

        let outcome = tools::execute(
            name,
            args,
            rationale,
            &ctx,
            &self.context_for(session_id),
            &self.broker,
            &self.audit,
            &self.catalog,
        )
        .await?;

        // Taint is set after the fact and never cleared. Setting it before the
        // call would tighten the gate for the very call that is introducing the
        // untrusted content, which is a call the user already sees; setting it
        // after tightens every call that could *act* on that content, which is
        // the one that matters.
        if outcome.taints {
            if let Some(state) = self.sessions.write().get_mut(session_id) {
                state.tainted = true;
            }
        }
        Ok(outcome)
    }

    /// Answer a pending approval. Returns false when the id or nonce is stale.
    pub fn resolve_approval(
        &self,
        request_id: &str,
        nonce: &str,
        approve: bool,
        remember: bool,
    ) -> Result<()> {
        self.broker.resolve(request_id, nonce, approve, remember)
    }

    /// Stop a turn: everything waiting on an approval is denied.
    ///
    /// Denied rather than left pending. A cancel that leaves a prompt open
    /// means a click a minute later runs a command for a turn the user already
    /// abandoned.
    pub fn cancel(&self) {
        self.broker.cancel_all();
    }

    /// Verify the audit chain. Exposed so the answer to "can I trust the log"
    /// is a button rather than a claim in a document.
    pub fn verify_audit(&self) -> Result<super::audit::VerifyReport> {
        super::audit::verify(self.app_data_dir.join("agent-audit"))
    }
}

/// Wraps a sink so an aborted request stops relaying.
///
/// The check is on `chunk` rather than on a select! around the read, because
/// returning an error from the sink is a path [`provider::relay`] already
/// handles: it stops reading, drops the response, and the connection closes.
/// One mechanism instead of two.
struct AbortAware<'a> {
    inner: &'a dyn ByteSink,
    aborted: &'a RwLock<std::collections::HashSet<String>>,
    request_id: &'a str,
}

impl AbortAware<'_> {
    fn stopped(&self) -> bool {
        self.aborted.read().contains(self.request_id)
    }
}

impl ByteSink for AbortAware<'_> {
    fn head(&self, status: u16, headers: Vec<(String, String)>) -> Result<()> {
        if self.stopped() {
            return Err(Error::Other("중단되었습니다.".into()));
        }
        self.inner.head(status, headers)
    }

    fn chunk(&self, bytes: &[u8]) -> Result<()> {
        if self.stopped() {
            // Not reported through `failed`: the user asked for this, so it is
            // not something to show them as an error.
            return Err(Error::Other("중단되었습니다.".into()));
        }
        self.inner.chunk(bytes)
    }

    fn done(&self) -> Result<()> {
        self.inner.done()
    }

    fn failed(&self, message: &str) {
        if !self.stopped() {
            self.inner.failed(message);
        }
    }
}

/// A [`ByteSink`] that keeps the response in memory.
///
/// Used for the connection probe, which is one short JSON body. Never used for
/// a streaming turn — that is the whole reason `ByteSink` is a trait.
#[derive(Default)]
struct Collector {
    status: parking_lot::Mutex<u16>,
    body: parking_lot::Mutex<Vec<u8>>,
}

impl Collector {
    fn status(&self) -> u16 {
        *self.status.lock()
    }

    #[allow(dead_code)]
    fn body(&self) -> Vec<u8> {
        self.body.lock().clone()
    }
}

impl ByteSink for Collector {
    fn head(&self, status: u16, _headers: Vec<(String, String)>) -> Result<()> {
        *self.status.lock() = status;
        Ok(())
    }

    fn chunk(&self, bytes: &[u8]) -> Result<()> {
        let mut body = self.body.lock();
        // A probe response is small; a runaway one is a bug, not something to
        // buffer to death.
        if body.len() + bytes.len() <= 64 * 1024 {
            body.extend_from_slice(bytes);
        }
        Ok(())
    }

    fn done(&self) -> Result<()> {
        Ok(())
    }

    fn failed(&self, _message: &str) {}
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
    use crate::agent::approval::SilentNotifier;
    use crate::agent::tools::testing::FakeHost;
    use crate::session::MemoryTokenStore;

    const KEY: &str = "sk-ant-api03-abcdefghijklmnop-XYZW";

    fn engine(dir: &std::path::Path) -> AgentEngine {
        AgentEngine::open(
            dir.to_path_buf(),
            Some(PathBuf::from("/home/u")),
            Arc::new(MemoryTokenStore::default()),
            Arc::new(SilentNotifier),
            HostCapabilities::desktop(),
        )
        .unwrap()
    }

    /// A fresh directory per test, matching the convention in `audit.rs` and
    /// `store.rs` — this crate has no `tempfile` dev-dependency and adding one
    /// for four tests is not worth the supply chain.
    fn tempdir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "llack-engine-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn before_sign_in_nothing_is_connected_and_nothing_errors() {
        let dir = tempdir();
        let engine = engine(&dir);
        let status = engine.provider_status().unwrap();
        assert!(!status.connected);
        assert_eq!(status.model, DEFAULT_MODEL);
        // And the calls that need a user say so rather than using a shared
        // namespace.
        assert!(engine.sessions(10).is_err());
        assert!(engine.open_session(None, None, None).is_err());
    }

    #[test]
    fn a_stored_key_makes_the_provider_connected() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        // Written directly: `connect_provider` needs the network.
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();

        let status = engine.provider_status().unwrap();
        assert!(status.connected);
        assert_eq!(status.key_fingerprint.as_deref(), Some("XYZW"));
    }

    #[test]
    fn the_status_never_carries_the_key() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();
        let json = serde_json::to_string(&engine.provider_status().unwrap()).unwrap();
        assert!(!json.contains(KEY), "{json}");
        assert!(json.contains("XYZW"));
    }

    #[test]
    fn the_model_can_be_switched_without_the_key() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();

        let status = engine.set_model("claude-sonnet-5").unwrap();
        assert!(status.connected);
        assert_eq!(status.model, "claude-sonnet-5");
        // And it sticks: a fresh status read agrees.
        assert_eq!(engine.provider_status().unwrap().model, "claude-sonnet-5");
    }

    #[test]
    fn switching_models_clears_a_stale_error() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();
        engine
            .remember_error("u1", "claude-opus-5", Some("옛 오류".into()))
            .unwrap();

        let status = engine.set_model("claude-sonnet-5").unwrap();
        assert_eq!(status.last_error, None);
    }

    #[test]
    fn set_model_refuses_without_a_connection_and_refuses_garbage() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        // No key stored yet: nothing to attach the choice to.
        assert!(engine.set_model("claude-sonnet-5").is_err());

        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();
        // The model id becomes part of a request path, so anything that could
        // change the URL's shape is refused here.
        for bad in ["", " ", "a/b", "a?b", "모델", "a\nb", "a b", "a#b"] {
            assert!(engine.set_model(bad).is_err(), "accepted {bad:?}");
        }
        // A trimmed, plain id passes.
        assert!(engine.set_model(" claude-opus-5 ").is_ok());
    }

    #[test]
    fn disconnecting_removes_the_key() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();

        let status = engine.disconnect_provider().unwrap();
        assert!(!status.connected);
        assert!(!engine.credentials.has(DEFAULT_PROVIDER, "u1").unwrap());
    }

    #[test]
    fn signing_out_forgets_the_key_the_settings_and_every_session() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        engine.credentials.put(DEFAULT_PROVIDER, "u1", KEY).unwrap();
        let session = engine.open_session(None, Some("w1"), Some("c1")).unwrap();
        engine
            .add_root(&session, PathBuf::from("/home/u/project"))
            .unwrap();

        engine.clear_user().unwrap();

        assert!(!engine.credentials.has(DEFAULT_PROVIDER, "u1").unwrap());
        assert!(engine.sessions.read().is_empty());
        assert!(!engine.provider_status().unwrap().connected);
        // And the roots are gone with the session, so a new session cannot
        // inherit a grant the old one held.
        assert!(engine.add_root(&session, PathBuf::from("/tmp")).is_err());
    }

    #[test]
    fn a_root_is_recorded_once_and_reaches_the_policy_context() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        let session = engine.open_session(None, None, None).unwrap();

        let root = PathBuf::from("/home/u/project");
        engine.add_root(&session, root.clone()).unwrap();
        engine.add_root(&session, root.clone()).unwrap();

        let ctx = engine.context_for(&session);
        assert_eq!(ctx.roots, vec![root]);
        assert_eq!(ctx.app_data_dir, dir);
        assert!(!ctx.tainted);
    }

    #[test]
    fn an_unknown_session_gets_the_most_restrictive_context() {
        let dir = tempdir();
        let engine = engine(&dir);
        // Not "no context" and not a default with roots: no roots, not tainted,
        // and Llack's own directory still denied.
        let ctx = engine.context_for("never-opened");
        assert!(ctx.roots.is_empty());
        assert_eq!(ctx.app_data_dir, dir);
    }

    #[tokio::test]
    async fn reading_a_channel_taints_the_session_and_the_taint_sticks() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        let session = engine.open_session(None, Some("w1"), Some("c1")).unwrap();
        assert!(!engine.is_tainted(&session));

        let host = FakeHost::default();
        let outcome = engine
            .tool_call(
                &session,
                "chat.read_channel",
                &serde_json::json!({ "channel_id": "c1", "limit": 10 }),
                None,
                &host,
            )
            .await
            .unwrap();
        assert!(outcome.taints);
        assert!(engine.is_tainted(&session));

        // A later read-only call must not clear it.
        engine
            .tool_call(
                &session,
                "agent.context",
                &serde_json::json!({}),
                None,
                &host,
            )
            .await
            .ok();
        assert!(engine.is_tainted(&session));
        assert!(engine.context_for(&session).tainted);
    }

    #[tokio::test]
    async fn the_channel_the_panel_is_looking_at_follows_the_focus() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        let session = engine.open_session(None, Some("w1"), Some("c1")).unwrap();
        engine.focus(&session, Some("c2"));
        assert_eq!(
            engine.sessions.read()[&session].channel_id.as_deref(),
            Some("c2")
        );
    }

    #[test]
    fn the_exposed_tool_list_follows_the_host() {
        let dir = tempdir();
        let with_control = engine(&dir);
        assert!(with_control
            .tools()
            .iter()
            .any(|s| s.name.starts_with("host.")));

        let dir2 = tempdir();
        let browser = AgentEngine::open(
            dir2.clone(),
            None,
            Arc::new(MemoryTokenStore::default()),
            Arc::new(SilentNotifier),
            HostCapabilities {
                computer_control: false,
                workspace: true,
            },
        )
        .unwrap();
        assert!(!browser.tools().iter().any(|s| s.name.starts_with("host.")));
        // And the rest of the catalog is still there — no computer control is
        // not no agent.
        assert!(browser.tools().iter().any(|s| s.name.starts_with("chat.")));
    }

    #[test]
    fn the_audit_chain_verifies_on_a_fresh_engine() {
        let dir = tempdir();
        let engine = engine(&dir);
        let report = engine.verify_audit().unwrap();
        assert_eq!(report.broken_at, None);
    }

    #[test]
    fn aborting_an_unknown_request_reports_that_there_was_nothing_to_stop() {
        let dir = tempdir();
        let engine = engine(&dir);
        assert!(!engine.abort_request("never-started"));
        // And it must not leave a poison entry that would abort a later
        // request that happens to reuse the id.
        assert!(engine.aborted_requests.read().is_empty());
    }

    #[test]
    fn an_abort_stops_the_next_chunk_and_says_nothing_to_the_user() {
        let aborted = RwLock::new(std::collections::HashSet::new());
        let inner = Collector::default();
        let guard = AbortAware {
            inner: &inner,
            aborted: &aborted,
            request_id: "r1",
        };

        guard.head(200, Vec::new()).unwrap();
        guard.chunk(b"data: one").unwrap();
        assert_eq!(inner.body(), b"data: one");

        aborted.write().insert("r1".to_string());
        assert!(guard.chunk(b"data: two").is_err());
        // The stopped stream is not reported as a failure — the user asked.
        guard.failed("would be shown");
        assert_eq!(inner.body(), b"data: one", "nothing more was relayed");
    }

    #[test]
    fn a_live_request_can_be_aborted_and_the_flag_is_scoped_to_it() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.live_requests.write().insert("r1".to_string());
        assert!(engine.abort_request("r1"));
        assert!(!engine.abort_request("r2"));
        assert!(engine.aborted_requests.read().contains("r1"));
        assert!(!engine.aborted_requests.read().contains("r2"));
    }

    #[test]
    fn a_probe_collector_keeps_the_status_and_caps_the_body() {
        let collector = Collector::default();
        collector.head(401, Vec::new()).unwrap();
        collector.chunk(&vec![b'x'; 200 * 1024]).unwrap();
        assert_eq!(collector.status(), 401);
        assert!(collector.body().len() <= 64 * 1024);
    }
}
