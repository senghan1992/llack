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
use super::credential::{self, CredentialStore};
use super::mcp::{McpClient, McpServer, McpServerView, Transport};
use super::policy::SessionContext;
use super::provider::{self, ByteSink, Provider, ProviderId, VettedRequest};
use super::skills::{self, AgentSkill};
use super::store::{AgentMemory, AgentSession, AgentStore, ProviderSettings};
use super::tools::{
    self, ExecuteOutcome, HostCapabilities, McpInvoker, ToolCatalog, ToolContext, ToolHost,
    ToolSpec,
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
    /// The connect-time base URL for an OpenAI-compatible gateway, if any.
    pub base_url: Option<String>,
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
            base_url: None,
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
    /// Behind a lock because MCP registration mutates it at runtime. Snapshotted
    /// (cloned) for each tool call so no guard is held across the `await` in an
    /// MCP dispatch.
    catalog: RwLock<ToolCatalog>,
    /// Connected MCP servers by id. Cheap `Arc` clones so a call can drop the
    /// lock before awaiting the server.
    mcp_clients: RwLock<HashMap<String, Arc<McpClient>>>,
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
        let broker = Arc::new(ApprovalBroker::new(notifier));
        // The native-dialog setting is machine-local and survives restarts, so
        // it lives in the store rather than in per-user settings. A missing key
        // leaves the broker's default (on); "0" is the only value that turns it
        // off, which is also what a headless or test host writes.
        if let Ok(Some(value)) = store.get_pref("native_dialogs") {
            broker.set_native_dialogs(value != "0");
        }
        Ok(Self {
            store,
            audit,
            broker,
            catalog: RwLock::new(ToolCatalog::builtin()),
            mcp_clients: RwLock::new(HashMap::new()),
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
        self.catalog.read().expose(self.capabilities)
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
        // Drop live MCP connections and forget their tokens. The server rows
        // are durable like sessions, but a keychain token must not outlive the
        // sign-out that was supposed to end this machine's access.
        self.mcp_clients.write().clear();
        {
            let mut catalog = self.catalog.write();
            *catalog = ToolCatalog::builtin();
        }
        let user_id = self.user_id.write().take();
        if let Some(user_id) = user_id {
            if let Ok(servers) = self.store.mcp_servers(&user_id) {
                for server in servers {
                    let _ = self
                        .credentials
                        .delete_secret(&credential::mcp_account(&server.id));
                }
            }
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
        let settings = self.store.settings(&user_id)?;
        let provider_id = settings
            .as_ref()
            .map(|s| s.provider_id.clone())
            .unwrap_or_else(|| DEFAULT_PROVIDER.into());
        let fingerprint = self
            .credentials
            .fingerprint(&provider_id, &user_id)?
            .map(|f| f.tail);
        Ok(ProviderStatus {
            // Connected means "a key is in the keychain", not "settings exist".
            // The keychain is the truth; the row is display state that can
            // survive a keychain the user cleared from the OS.
            connected: fingerprint.is_some(),
            provider_id,
            model: settings
                .as_ref()
                .map(|s| s.model.clone())
                .unwrap_or_else(|| DEFAULT_MODEL.into()),
            base_url: settings.as_ref().and_then(|s| s.base_url.clone()),
            key_fingerprint: fingerprint,
            last_error: settings.and_then(|s| s.last_error),
        })
    }

    /// Store a key after proving it works.
    ///
    /// Proving comes first: a key that is stored and then found to be invalid
    /// leaves the panel saying "connected" while every turn fails. The proof is
    /// a `GET` that bills nothing. `base_url` only applies to OpenAI-compatible
    /// gateways; Anthropic ignores it.
    pub async fn connect_provider(
        &self,
        provider_id: &str,
        key: &str,
        model: Option<String>,
        base_url: Option<String>,
    ) -> Result<ProviderStatus> {
        let user_id = self.user()?;
        let id = ProviderId::parse(provider_id).ok_or_else(|| {
            Error::provider(
                ProviderErrorCode::RequestRefused,
                format!("아직 지원하지 않는 프로바이더입니다: {provider_id}"),
            )
        })?;
        let default_model = match id {
            ProviderId::Anthropic => DEFAULT_MODEL,
            ProviderId::OpenAi => "gpt-5",
        };
        let model = model.unwrap_or_else(|| default_model.to_string());

        super::credential::vet_key(id.as_str(), key)?;
        let provider = Provider::resolve(id, base_url.as_deref())?;

        let (url, method) = provider::validation_request_for(&provider, &model);
        let probe = VettedRequest {
            url,
            method,
            headers: provider::probe_headers(&provider, key),
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
            self.remember_error(
                &user_id,
                id.as_str(),
                &model,
                base_url.clone(),
                Some(message.clone()),
            )?;
            return Err(Error::provider(code, message));
        }

        let fingerprint = self.credentials.put(id.as_str(), &user_id, key)?;
        self.store.save_settings(&ProviderSettings {
            user_id: user_id.clone(),
            provider_id: id.as_str().into(),
            model,
            base_url,
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
        let existing = self.store.settings(&user_id)?;
        let provider_id = existing
            .as_ref()
            .map(|s| s.provider_id.clone())
            .unwrap_or_else(|| DEFAULT_PROVIDER.into());
        if !self.credentials.has(&provider_id, &user_id)? {
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

        self.store.save_settings(&ProviderSettings {
            user_id: user_id.clone(),
            provider_id,
            model: model.to_string(),
            base_url: existing.as_ref().and_then(|s| s.base_url.clone()),
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
        let provider_id = self
            .store
            .settings(&user_id)?
            .map(|s| s.provider_id)
            .unwrap_or_else(|| DEFAULT_PROVIDER.into());
        self.credentials.delete(&provider_id, &user_id)?;
        self.store.clear_settings(&user_id)?;
        // Grants outlive a disconnect otherwise, and "I disconnected the model"
        // should mean the agent can no longer act.
        self.broker.cancel_all();
        self.broker.revoke_grants();
        self.provider_status()
    }

    fn remember_error(
        &self,
        user_id: &str,
        provider_id: &str,
        model: &str,
        base_url: Option<String>,
        error: Option<String>,
    ) -> Result<()> {
        let existing = self.store.settings(user_id)?;
        self.store.save_settings(&ProviderSettings {
            user_id: user_id.to_string(),
            provider_id: provider_id.to_string(),
            model: model.to_string(),
            base_url,
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
        // Which provider (and which host) this request is allowed to reach is
        // decided by the stored connection, never by the request itself.
        let settings = self.store.settings(&user_id)?;
        let provider_id = settings
            .as_ref()
            .map(|s| s.provider_id.clone())
            .unwrap_or_else(|| DEFAULT_PROVIDER.into());
        let id = ProviderId::parse(&provider_id).ok_or_else(|| {
            Error::provider(
                ProviderErrorCode::RequestRefused,
                "연결된 프로바이더를 알 수 없습니다.",
            )
        })?;
        let provider =
            Provider::resolve(id, settings.as_ref().and_then(|s| s.base_url.as_deref()))?;
        let request = provider::vet_request(
            url,
            method,
            headers,
            body,
            &self.credentials,
            &provider,
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

        // The signed-in user scopes memory; a call before sign-in simply has no
        // user, and the memory tools decline rather than share a namespace.
        let user = self.user_id.read().clone();
        let ctx = ToolContext {
            session_id,
            store: &self.store,
            host,
            mcp: Some(self),
            workspace_id: state.workspace_id.as_deref(),
            channel_id: state.channel_id.as_deref(),
            user_id: user.as_deref(),
            skills_dir: Some(self.skills_dir()),
        };

        // Snapshot the catalog so no lock is held across the await inside an
        // MCP dispatch. Cheap: it is a couple of BTreeMaps.
        let catalog = self.catalog.read().clone();
        let outcome = tools::execute(
            name,
            args,
            rationale,
            &ctx,
            &self.context_for(session_id),
            &self.broker,
            &self.audit,
            &catalog,
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

    /// One day's audit records, for the "what did it do on my machine" screen.
    /// A missing or unknown date falls back to the most recent day.
    pub fn audit_entries(
        &self,
        date: Option<&str>,
        limit: Option<usize>,
    ) -> Result<super::audit::AuditEntriesView> {
        super::audit::entries_for(self.app_data_dir.join("agent-audit"), date, limit)
    }

    // ── Memory ─────────────────────────────────────────────────────────────

    /// The user's saved memories, most recently used first.
    pub fn memories_list(&self, limit: u32) -> Result<Vec<AgentMemory>> {
        self.store.list_memories(&self.user()?, limit)
    }

    /// Save a memory the user typed directly (not through the model). A note
    /// authored by the user is not subject to the taint rule the tool applies.
    pub fn memory_add(&self, text: &str, tags: &[String]) -> Result<AgentMemory> {
        self.store.add_memory(&self.user()?, text, tags, None)
    }

    pub fn memory_delete(&self, id: &str) -> Result<()> {
        self.store.delete_memory(&self.user()?, id)
    }

    // ── Skills ─────────────────────────────────────────────────────────────

    /// Where the skill files live: one directory under Llack's own data dir.
    fn skills_dir(&self) -> PathBuf {
        self.app_data_dir.join("agent-skills")
    }

    pub fn skills_list(&self) -> Result<Vec<AgentSkill>> {
        skills::list(&self.skills_dir())
    }

    pub fn skill_read(&self, name: &str) -> Result<String> {
        skills::read(&self.skills_dir(), name)
    }

    pub fn skill_save(&self, name: &str, body: &str) -> Result<AgentSkill> {
        skills::save(&self.skills_dir(), name, body)
    }

    pub fn skill_delete(&self, name: &str) -> Result<()> {
        skills::delete(&self.skills_dir(), name)
    }

    // ── Native dialogs ───────────────────────────────────────────────────

    /// Read (`None`) or set the native-dialog preference, returning the value
    /// now in effect. Persisted so it survives a restart, and pushed to the
    /// broker so the next class-3 request reflects it immediately.
    pub fn native_dialogs(&self, enabled: Option<bool>) -> Result<bool> {
        if let Some(enabled) = enabled {
            self.store
                .set_pref("native_dialogs", if enabled { "1" } else { "0" })?;
            self.broker.set_native_dialogs(enabled);
        }
        Ok(self.broker.native_dialogs())
    }

    // ── MCP servers ────────────────────────────────────────────────────────

    /// Every server the user registered, as the panel may see them (no token).
    pub fn mcp_list(&self) -> Result<Vec<McpServerView>> {
        let user_id = self.user()?;
        let servers = self.store.mcp_servers(&user_id)?;
        let catalog = self.catalog.read();
        Ok(servers
            .iter()
            .map(|s| {
                let has_credential = self
                    .credentials
                    .has_secret(&credential::mcp_account(&s.id))
                    .unwrap_or(false);
                McpServerView::from_server(s, catalog.mcp_tool_count(&s.id), has_credential)
            })
            .collect())
    }

    /// The exposed specs a server contributed — for a settings "what can it do".
    pub fn mcp_tools(&self, server_id: &str) -> Vec<ToolSpec> {
        self.catalog.read().mcp_specs(server_id)
    }

    /// Add a server: handshake, list its tools, and only then persist. A server
    /// whose handshake fails stores nothing, so the list never shows a dead
    /// entry the user has to clean up.
    pub async fn mcp_add(
        &self,
        name: &str,
        transport: &str,
        url: Option<String>,
        command: Option<String>,
        args: Vec<String>,
        token: Option<String>,
    ) -> Result<McpServerView> {
        let user_id = self.user()?;
        let transport = Transport::parse(transport)
            .ok_or_else(|| Error::Other("transport 는 http 또는 stdio 여야 합니다.".into()))?;
        let server = McpServer {
            id: crate::ids::new_ulid(),
            user_id: user_id.clone(),
            name: name.trim().to_string(),
            transport,
            url: url.filter(|u| !u.trim().is_empty()),
            command: command.filter(|c| !c.trim().is_empty()),
            args,
            enabled: true,
            created_at_ms: now_ms(),
            last_ok_at_ms: None,
            last_error: None,
        };

        let (client, tools) = self.connect_mcp(&server, token.clone()).await?;

        // Persist only after a successful handshake.
        self.store.save_mcp_server(&server)?;
        self.store.mcp_touch(&server.id, None)?;
        if let Some(token) = token.filter(|t| !t.is_empty()) {
            self.credentials
                .put_secret(&credential::mcp_account(&server.id), &token)?;
        }
        self.register_client(&server, client, &tools);
        self.view_for(&server.id)
    }

    pub fn mcp_remove(&self, server_id: &str) -> Result<()> {
        let _ = self.user()?;
        self.mcp_clients.write().remove(server_id);
        self.catalog.write().clear_mcp(server_id);
        self.credentials
            .delete_secret(&credential::mcp_account(server_id))?;
        self.store.delete_mcp_server(server_id)?;
        Ok(())
    }

    pub async fn mcp_set_enabled(&self, server_id: &str, enabled: bool) -> Result<McpServerView> {
        let _ = self.user()?;
        self.store.set_mcp_enabled(server_id, enabled)?;
        if enabled {
            if let Some(server) = self.store.mcp_server(server_id)? {
                let token = self
                    .credentials
                    .secret(&credential::mcp_account(server_id))?;
                match self.connect_mcp(&server, token).await {
                    Ok((client, tools)) => {
                        self.store.mcp_touch(server_id, None)?;
                        self.register_client(&server, client, &tools);
                    }
                    Err(err) => {
                        self.store.mcp_touch(server_id, Some(&err.to_string()))?;
                    }
                }
            }
        } else {
            self.mcp_clients.write().remove(server_id);
            self.catalog.write().clear_mcp(server_id);
        }
        self.view_for(server_id)
    }

    /// Reconnect every enabled server and rebuild the catalog's MCP tools.
    /// Failures are per-server: one dead server does not take the others down.
    pub async fn refresh_mcp(&self) -> Result<Vec<McpServerView>> {
        let user_id = self.user()?;
        // Start from a clean MCP slate, then re-add what connects.
        {
            let mut clients = self.mcp_clients.write();
            let ids: Vec<String> = clients.keys().cloned().collect();
            clients.clear();
            drop(clients);
            let mut catalog = self.catalog.write();
            for id in ids {
                catalog.clear_mcp(&id);
            }
        }
        for server in self.store.mcp_servers(&user_id)? {
            if !server.enabled {
                continue;
            }
            let token = self
                .credentials
                .secret(&credential::mcp_account(&server.id))?;
            match self.connect_mcp(&server, token).await {
                Ok((client, tools)) => {
                    self.store.mcp_touch(&server.id, None)?;
                    self.register_client(&server, client, &tools);
                }
                Err(err) => {
                    self.store.mcp_touch(&server.id, Some(&err.to_string()))?;
                }
            }
        }
        self.mcp_list()
    }

    /// Store a large value produced outside a tool handler — a sub-agent's
    /// answer — so the parent turn holds a handle, not the whole thing.
    pub fn artifact_put(&self, session_id: &str, label: &str, text: &str) -> Result<(String, u64)> {
        self.store.store_text(session_id, label, text)
    }

    async fn connect_mcp(
        &self,
        server: &McpServer,
        token: Option<String>,
    ) -> Result<(Arc<McpClient>, Vec<super::mcp::McpToolDef>)> {
        let (client, _info) = McpClient::connect(self.http.clone(), server.clone(), token).await?;
        let tools = client.list_tools().await?;
        Ok((Arc::new(client), tools))
    }

    /// Put a connected client in the map and register its tools under a slug
    /// that does not collide with an already-registered server.
    fn register_client(
        &self,
        server: &McpServer,
        client: Arc<McpClient>,
        tools: &[super::mcp::McpToolDef],
    ) {
        self.mcp_clients.write().insert(server.id.clone(), client);
        let mut catalog = self.catalog.write();
        // A slug clash between two servers would let one shadow the other's
        // tools; number the later one.
        let base = super::mcp::slugify(&server.name);
        let existing: std::collections::HashSet<String> = self
            .store
            .mcp_servers(&server.user_id)
            .unwrap_or_default()
            .iter()
            .filter(|s| s.id != server.id)
            .map(|s| super::mcp::slugify(&s.name))
            .collect();
        let mut slug = base.clone();
        let mut n = 2;
        while existing.contains(&slug) {
            slug = format!("{base}-{n}");
            n += 1;
        }
        catalog.register_mcp(&server.id, &server.name, &server.endpoint(), &slug, tools);
    }

    fn view_for(&self, server_id: &str) -> Result<McpServerView> {
        let server = self
            .store
            .mcp_server(server_id)?
            .ok_or_else(|| Error::Other("서버를 찾을 수 없습니다.".into()))?;
        let has_credential = self
            .credentials
            .has_secret(&credential::mcp_account(server_id))
            .unwrap_or(false);
        Ok(McpServerView::from_server(
            &server,
            self.catalog.read().mcp_tool_count(server_id),
            has_credential,
        ))
    }
}

/// The engine routes an MCP tool call to the connected client that owns it.
#[async_trait::async_trait]
impl McpInvoker for AgentEngine {
    async fn call(
        &self,
        server_id: &str,
        tool: &str,
        args: &serde_json::Value,
    ) -> Result<serde_json::Value> {
        let client = self
            .mcp_clients
            .read()
            .get(server_id)
            .cloned()
            .ok_or_else(|| Error::Other("이 MCP 서버에 연결되어 있지 않습니다.".into()))?;
        let result = client.call_tool(tool, args).await;
        // Record the outcome so the settings view can show a server that has
        // started failing without waiting for a refresh.
        match &result {
            Ok(_) => {
                let _ = self.store.mcp_touch(server_id, None);
            }
            Err(err) => {
                let _ = self.store.mcp_touch(server_id, Some(&err.to_string()));
            }
        }
        result
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
            .remember_error(
                "u1",
                "anthropic",
                "claude-opus-5",
                None,
                Some("옛 오류".into()),
            )
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
                screen_control: false,
            },
        )
        .unwrap();
        assert!(!browser.tools().iter().any(|s| s.name.starts_with("host.")));
        // And the rest of the catalog is still there — no computer control is
        // not no agent.
        assert!(browser.tools().iter().any(|s| s.name.starts_with("chat.")));
    }

    /// Approves every approval the moment it opens, so an MCP call (class 3,
    /// asked every time) can be driven without a UI.
    struct AutoApprove {
        broker: parking_lot::Mutex<Option<Arc<ApprovalBroker>>>,
        seen: std::sync::atomic::AtomicUsize,
    }

    impl AutoApprove {
        fn new() -> Arc<Self> {
            Arc::new(Self {
                broker: parking_lot::Mutex::new(None),
                seen: std::sync::atomic::AtomicUsize::new(0),
            })
        }
    }

    impl ApprovalNotifier for AutoApprove {
        fn opened(&self, request: &crate::agent::approval::ApprovalRequest) {
            self.seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            if let Some(broker) = self.broker.lock().clone() {
                let _ = broker.resolve(&request.id, &request.nonce, true, false);
            }
        }
        fn closed(&self, _id: &str, _outcome: crate::agent::approval::Outcome) {}
    }

    #[tokio::test]
    async fn an_mcp_server_registers_its_tools_and_a_call_routes_to_it() {
        use crate::agent::mcp::testing::FakeMcpServer;

        let dir = tempdir();
        let answer = AutoApprove::new();
        let engine = AgentEngine::open(
            dir.clone(),
            Some(PathBuf::from("/home/u")),
            Arc::new(MemoryTokenStore::default()),
            answer.clone(),
            HostCapabilities::desktop(),
        )
        .unwrap();
        *answer.broker.lock() = Some(engine.broker());
        engine.set_user("u1");
        let session = engine.open_session(None, Some("w1"), Some("c1")).unwrap();

        let fake = FakeMcpServer::start(false, None).await;
        let view = engine
            .mcp_add(
                "Fake Tools",
                "http",
                Some(fake.url.clone()),
                None,
                Vec::new(),
                None,
            )
            .await
            .unwrap();
        assert_eq!(view.tool_count, 2, "the server's two tools were registered");
        assert!(view.last_error.is_none());

        // The tools appear in the catalog under mcp.slug.tool.
        let names: Vec<String> = engine.tools().into_iter().map(|s| s.name).collect();
        assert!(
            names.iter().any(|n| n == "mcp.fake-tools.echo"),
            "{names:?}"
        );

        // A call is class 3 (asked every time). It routes to the server and
        // comes back as text, and it taints the session.
        let host = FakeHost::default();
        let outcome = engine
            .tool_call(
                &session,
                "mcp.fake-tools.echo",
                &serde_json::json!({ "text": "안녕" }),
                None,
                &host,
            )
            .await
            .unwrap();
        assert!(!outcome.output.is_error, "{:?}", outcome.output);
        assert!(outcome.taints, "an MCP result taints the session");
        assert_eq!(
            answer.seen.load(std::sync::atomic::Ordering::SeqCst),
            1,
            "MCP calls are asked every time"
        );

        // Removing it takes its tools back out of the catalog.
        engine.mcp_remove(&view.id).unwrap();
        let names: Vec<String> = engine.tools().into_iter().map(|s| s.name).collect();
        assert!(!names.iter().any(|n| n.starts_with("mcp.")));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn the_audit_chain_verifies_on_a_fresh_engine() {
        let dir = tempdir();
        let engine = engine(&dir);
        let report = engine.verify_audit().unwrap();
        assert_eq!(report.broken_at, None);
    }

    #[test]
    fn a_user_typed_memory_round_trips_and_lists() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        let saved = engine
            .memory_add("앨리스는 KST 로 일합니다", &["timezone".into()])
            .unwrap();
        let listed = engine.memories_list(10).unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].id, saved.id);
        engine.memory_delete(&saved.id).unwrap();
        assert!(engine.memories_list(10).unwrap().is_empty());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_skill_written_by_a_command_is_listed_read_and_deleted() {
        let dir = tempdir();
        let engine = engine(&dir);
        let saved = engine
            .skill_save("release", "# 릴리스\n분기 배포\n본문")
            .unwrap();
        assert_eq!(saved.title, "릴리스");
        assert_eq!(engine.skills_list().unwrap().len(), 1);
        assert!(engine.skill_read("release").unwrap().contains("분기 배포"));
        engine.skill_delete("release").unwrap();
        assert!(engine.skills_list().unwrap().is_empty());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn the_native_dialog_preference_defaults_on_and_persists() {
        let dir = tempdir();
        {
            let engine = engine(&dir);
            assert!(engine.native_dialogs(None).unwrap(), "the default is on");
            assert!(!engine.native_dialogs(Some(false)).unwrap());
        }
        // A fresh engine on the same directory must read the stored choice.
        let reopened = engine(&dir);
        assert!(
            !reopened.native_dialogs(None).unwrap(),
            "the off choice survives a restart"
        );
        std::fs::remove_dir_all(&dir).ok();
    }

    #[tokio::test]
    async fn the_audit_viewer_sees_a_recorded_call() {
        let dir = tempdir();
        let engine = engine(&dir);
        engine.set_user("u1");
        let session = engine.open_session(None, Some("w1"), Some("c1")).unwrap();
        let host = FakeHost::default();
        engine
            .tool_call(
                &session,
                "chat.read_channel",
                &serde_json::json!({ "channel_id": "c1", "limit": 10 }),
                None,
                &host,
            )
            .await
            .unwrap();

        let view = engine.audit_entries(None, Some(50)).unwrap();
        assert_eq!(view.dates.len(), 1);
        assert!(view.verified);
        assert!(!view.entries.is_empty(), "the read must be on the record");
        std::fs::remove_dir_all(&dir).ok();
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
