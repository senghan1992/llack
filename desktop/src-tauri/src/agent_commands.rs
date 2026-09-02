//! The agent's IPC surface — and deliberately the whole of it.
//!
//! Every command here is a forwarder. The gate, the audit log, the credential
//! handling and the request vetting all live in `llack_core::agent`, which can
//! be compiled and tested anywhere; this file needs webkit2gtk to build, so
//! anything that lived here would ship unverified. That constraint is the
//! reason the split exists, and it is why these functions are boring.
//!
//! Two things are worth reading closely rather than skimming:
//!
//! 1. **No new webview permission.** `capabilities/default.json` is unchanged
//!    by this feature. The agent can run programs, but the *webview* gained
//!    nothing — it can only ask, and Rust decides.
//! 2. **The key never returns.** `agent_provider_connect` takes it, and
//!    `agent_provider_request` uses it. There is no command that reads it back,
//!    and `CredentialStore::key` is `pub(crate)` in core so one cannot be added
//!    here by accident.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use llack_core::agent::provider::ByteSink;
use llack_core::agent::{
    ApprovalNotifier, ApprovalRequest, ChatLine, ExecOutput, Outcome, ProviderStatus, ToolHost,
};
use llack_core::error::{Error, Result};
use tauri::ipc::Channel;
use tauri::{AppHandle, Emitter, State};

use crate::state::AppState;

/// The event channel the panel listens on.
const AGENT_EVENT: &str = "llack://agent";

// ── Approval delivery ───────────────────────────────────────────────────────

/// Pushes approval requests at the panel.
///
/// The request that crosses here carries no fingerprint and no argv the webview
/// could replay — only an id, a single-use nonce, and the facts Rust computed.
/// The panel can answer a request; it cannot invent one.
pub struct PanelNotifier {
    app: AppHandle,
}

impl PanelNotifier {
    pub fn new(app: AppHandle) -> Self {
        Self { app }
    }
}

impl ApprovalNotifier for PanelNotifier {
    fn opened(&self, request: &ApprovalRequest) {
        let _ = self.app.emit(
            AGENT_EVENT,
            serde_json::json!({ "kind": "approval_pending", "request": request }),
        );
    }

    fn closed(&self, request_id: &str, outcome: Outcome) {
        // The reason is sent along so the panel can say *why* a card vanished.
        // A card that silently disappears on a 60-second timeout reads as a
        // bug, and a user who thinks the UI is flaky stops reading the cards.
        let reason = match outcome {
            Outcome::Approved { .. } => "approved",
            Outcome::Denied => "denied",
            Outcome::Expired => "expired",
            Outcome::Cancelled => "cancelled",
        };
        let _ = self.app.emit(
            AGENT_EVENT,
            serde_json::json!({
                "kind": "approval_closed",
                "request_id": request_id,
                "reason": reason,
            }),
        );
    }
}

// ── The host half of the tools ──────────────────────────────────────────────

/// The real `ToolHost`: this machine, and this signed-in session.
///
/// Constructed per call rather than stored, so it always uses the session that
/// is signed in *now* — a long-lived host would keep working after sign-out.
pub struct DesktopHost {
    state: Arc<AppState>,
}

impl DesktopHost {
    pub fn new(state: Arc<AppState>) -> Self {
        Self { state }
    }
}

#[async_trait::async_trait]
impl ToolHost for DesktopHost {
    /// Run a program. Never a shell.
    ///
    /// `argv[0]` is the executable and the rest are arguments handed to the OS
    /// as a list, so there is no string for a metacharacter to live in: no
    /// pipes, no redirection, no `;`. The policy has already refused
    /// interpreters and rejected an empty argv, and the user has already
    /// approved this exact argv — but `Command::new(&argv[0]).args(&argv[1..])`
    /// is what makes those checks meaningful rather than advisory.
    async fn exec(&self, argv: &[String], cwd: &Path) -> Result<ExecOutput> {
        let program = argv
            .first()
            .ok_or_else(|| Error::Other("실행할 프로그램이 없습니다.".into()))?;

        let started = std::time::Instant::now();
        let output = tokio::process::Command::new(program)
            .args(&argv[1..])
            .current_dir(cwd)
            // No stdin: a program that waits for input would hang the turn
            // until the panel is closed, and nothing here can type at it.
            .stdin(std::process::Stdio::null())
            // The environment is inherited, which is worth being explicit
            // about: a program the user approved can read this process's
            // environment. That is the same trust the approval already grants.
            .kill_on_drop(true)
            .output()
            .await
            .map_err(|e| Error::Other(format!("{program} 을 실행할 수 없습니다: {e}")))?;

        Ok(ExecOutput {
            // `None` means killed by a signal. Reported as -1 rather than 0:
            // a program the OS killed did not succeed, and the model reading
            // this must not treat it as success.
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            duration_ms: started.elapsed().as_millis() as u64,
            // No wall-clock kill in v1. The field exists so adding one later
            // does not change this trait's shape.
            timed_out: false,
        })
    }

    /// Read a file, refusing anything over the cap before reading it.
    ///
    /// The size is checked with `metadata` first so a 4GB file is a refusal
    /// rather than 4GB of resident memory, and re-checked after the read
    /// because a file can grow between the two.
    async fn read_file(&self, path: &Path, cap: u64) -> Result<Vec<u8>> {
        let metadata = tokio::fs::metadata(path)
            .await
            .map_err(|e| Error::Other(format!("{} 을 읽을 수 없습니다: {e}", path.display())))?;
        if !metadata.is_file() {
            return Err(Error::Other("파일이 아닙니다.".into()));
        }
        if metadata.len() > cap {
            return Err(Error::Other(format!(
                "파일이 너무 큽니다 ({} bytes, 한도 {cap}).",
                metadata.len()
            )));
        }
        let bytes = tokio::fs::read(path)
            .await
            .map_err(|e| Error::Other(format!("{} 을 읽을 수 없습니다: {e}", path.display())))?;
        if bytes.len() as u64 > cap {
            return Err(Error::Other("읽는 중에 파일이 커졌습니다.".into()));
        }
        Ok(bytes)
    }

    async fn list_dir(&self, path: &Path) -> Result<Vec<String>> {
        let mut entries = tokio::fs::read_dir(path)
            .await
            .map_err(|e| Error::Other(format!("{} 을 읽을 수 없습니다: {e}", path.display())))?;
        let mut names = Vec::new();
        while let Some(entry) = entries
            .next_entry()
            .await
            .map_err(|e| Error::Other(format!("디렉터리를 읽는 중 오류: {e}")))?
        {
            names.push(entry.file_name().to_string_lossy().into_owned());
            // A directory with a million entries is a context bomb, not a
            // listing. The cap is here rather than in the tool because it is
            // about this machine, not about the policy.
            if names.len() >= 2_000 {
                break;
            }
        }
        names.sort();
        Ok(names)
    }

    async fn chat_history(&self, channel_id: &str, limit: u32) -> Result<Vec<ChatLine>> {
        let page = self.state.api()?.history(channel_id, limit, None).await?;
        Ok(page.items.iter().map(to_chat_line).collect())
    }

    async fn chat_search(&self, workspace_id: &str, query: &str) -> Result<Vec<ChatLine>> {
        let found = self
            .state
            .api()?
            .search_messages(workspace_id, query)
            .await?;
        Ok(found
            .hits
            .iter()
            .map(|hit| to_chat_line(&hit.message))
            .collect())
    }

    /// Post as the signed-in human.
    ///
    /// There is no bot identity and no separate token: the message is *from the
    /// user*, which is exactly why the policy makes this a high-risk approval
    /// every single time and never remembers it.
    async fn chat_post(&self, channel_id: &str, body: &str) -> Result<String> {
        let sent = self
            .state
            .api()?
            .post_message(
                channel_id,
                &llack_core::NewMessage {
                    body: body.to_string(),
                    blocks: None,
                    // Generated here, so a retry after a dropped response
                    // cannot double-post as the user.
                    client_msg_id: Some(llack_core::ids::new_ulid()),
                    parent_id: None,
                    also_send_to_channel: false,
                    file_ids: Vec::new(),
                },
            )
            .await?;
        Ok(sent.id)
    }
}

/// Flatten a message for the model.
///
/// Only four fields cross: who, when, what, and the id. Not the reaction list,
/// not the attachment list, not `mentioned_user_ids` — those would spend context
/// on structure the model cannot act on, and every extra field is more
/// attacker-controlled text in a prompt.
fn to_chat_line(message: &llack_core::Message) -> ChatLine {
    ChatLine {
        id: message.id.clone(),
        author: message
            .author
            .as_ref()
            .map(|a| a.display_name.clone())
            .unwrap_or_else(|| "(알 수 없음)".into()),
        at: message.created_at.clone(),
        body: message.body.clone(),
    }
}

// ── The byte proxy's sink ───────────────────────────────────────────────────

/// What the panel receives on the streaming channel.
///
/// Bytes are base64 because a Tauri channel payload is JSON, and a JSON array
/// of integers costs several bytes per byte. The 33% base64 overhead is the
/// cheap option, and it keeps this side from having to know anything about the
/// content — which is the point: Rust does not parse SSE.
#[derive(serde::Serialize, Clone)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ProxyEvent {
    Head {
        status: u16,
        headers: Vec<(String, String)>,
    },
    Chunk {
        b64: String,
    },
    Done,
    Failed {
        message: String,
    },
}

struct ChannelSink {
    channel: Channel<ProxyEvent>,
}

impl ByteSink for ChannelSink {
    fn head(&self, status: u16, headers: Vec<(String, String)>) -> Result<()> {
        self.channel
            .send(ProxyEvent::Head { status, headers })
            .map_err(|e| Error::Other(format!("응답을 전달할 수 없습니다: {e}")))
    }

    fn chunk(&self, bytes: &[u8]) -> Result<()> {
        use base64::Engine;
        self.channel
            .send(ProxyEvent::Chunk {
                b64: base64::engine::general_purpose::STANDARD.encode(bytes),
            })
            // A send failure here means the panel is gone (window closed, page
            // reloaded). Returning an error stops the relay, which is what
            // aborts the upstream request instead of streaming into nothing.
            .map_err(|e| Error::Other(format!("응답을 전달할 수 없습니다: {e}")))
    }

    fn done(&self) -> Result<()> {
        let _ = self.channel.send(ProxyEvent::Done);
        Ok(())
    }

    fn failed(&self, message: &str) {
        let _ = self.channel.send(ProxyEvent::Failed {
            message: message.to_string(),
        });
    }
}

// ── Commands ────────────────────────────────────────────────────────────────

#[tauri::command]
pub fn agent_provider_status(state: State<'_, Arc<AppState>>) -> Result<ProviderStatus> {
    state.agent()?.provider_status()
}

/// Store a provider key.
///
/// The key crosses the IPC boundary exactly once, here. It is validated against
/// the provider before being written, so the panel never says "connected" about
/// a key that does not work.
#[tauri::command]
pub async fn agent_provider_connect(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    provider_id: Option<String>,
    api_key: String,
    model: Option<String>,
) -> Result<ProviderStatus> {
    // Accepted and checked rather than ignored. The webview's contract already
    // sends it, and serde would have silently dropped an unknown field — which
    // would make "connect to provider X" quietly connect to Anthropic instead
    // the day a second adapter is added to the UI before it exists here.
    if let Some(requested) = provider_id.as_deref() {
        if requested != llack_core::agent::DEFAULT_PROVIDER {
            return Err(Error::provider(
                llack_core::error::ProviderErrorCode::RequestRefused,
                format!("아직 지원하지 않는 프로바이더입니다: {requested}"),
            ));
        }
    }
    let status = state.agent()?.connect_provider(&api_key, model).await?;
    // The key is dropped here with the argument. Nothing keeps a copy: the
    // keychain has it, and `String` has no other owner.
    let _ = app.emit(
        AGENT_EVENT,
        serde_json::json!({ "kind": "provider_changed", "status": status }),
    );
    Ok(status)
}

/// Switch models on the connected provider.
///
/// No key crosses here: the choice attaches to the key already in the keychain,
/// and the engine refuses when there is none. The list the user chose from was
/// fetched from the account itself through the byte proxy (`GET /v1/models`),
/// so this is a selection, not free-form configuration.
#[tauri::command]
pub fn agent_provider_set_model(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    model: String,
) -> Result<ProviderStatus> {
    let status = state.agent()?.set_model(&model)?;
    let _ = app.emit(
        AGENT_EVENT,
        serde_json::json!({ "kind": "provider_changed", "status": status }),
    );
    Ok(status)
}

#[tauri::command]
pub fn agent_provider_disconnect(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
) -> Result<ProviderStatus> {
    let status = state.agent()?.disconnect_provider()?;
    let _ = app.emit(
        AGENT_EVENT,
        serde_json::json!({ "kind": "provider_changed", "status": status }),
    );
    Ok(status)
}

/// The one command that carries the API key outbound.
///
/// `Channel` streams the response body back as it arrives, so a turn renders
/// token by token without this side understanding a single event type.
#[tauri::command]
pub async fn agent_provider_request(
    state: State<'_, Arc<AppState>>,
    request_id: String,
    url: String,
    method: String,
    headers: Vec<(String, String)>,
    body: Option<String>,
    channel: Channel<ProxyEvent>,
) -> Result<()> {
    let sink = ChannelSink { channel };
    let bytes = body.map(String::into_bytes).unwrap_or_default();
    let result = state
        .agent()?
        .proxy(&request_id, &url, &method, &headers, bytes, &sink)
        .await;
    if let Err(error) = &result {
        // Reported on the channel as well as returned: the SDK is awaiting the
        // stream, not this promise, so an error that only comes back through
        // `invoke` leaves the stream hanging.
        sink.failed(&error.to_string());
    }
    result
}

/// Stop one in-flight provider request.
///
/// Returns false when there was nothing to stop, so the panel can distinguish
/// "stopped" from "it had already finished" rather than showing a stop that did
/// nothing.
#[tauri::command]
pub fn agent_provider_abort(state: State<'_, Arc<AppState>>, request_id: String) -> Result<bool> {
    Ok(state.agent()?.abort_request(&request_id))
}

/// The tools to advertise this turn.
///
/// Computed in Rust rather than listed in the webview, so `host.*` disappearing
/// on a host without computer control is one filter in one place. A webview
/// that added a tool to this list would gain nothing: `agent_tool_call` looks
/// the name up in its own catalog.
#[tauri::command]
pub fn agent_tools(state: State<'_, Arc<AppState>>) -> Result<Vec<llack_core::agent::ToolSpec>> {
    Ok(state.agent()?.tools())
}

#[tauri::command]
pub fn agent_sessions(
    state: State<'_, Arc<AppState>>,
    limit: Option<u32>,
) -> Result<Vec<llack_core::agent::AgentSession>> {
    state.agent()?.sessions(limit.unwrap_or(20).min(200))
}

#[tauri::command]
pub fn agent_open_session(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    session_id: Option<String>,
) -> Result<String> {
    let engine = state.agent()?;
    let id = engine.open_session(
        session_id.as_deref(),
        state.active_workspace_id().as_deref(),
        None,
    )?;
    let _ = app.emit(
        AGENT_EVENT,
        serde_json::json!({ "kind": "session_started", "session_id": id }),
    );
    Ok(id)
}

/// Tell the engine which channel the panel is looking at.
#[tauri::command]
pub fn agent_focus(
    state: State<'_, Arc<AppState>>,
    session_id: String,
    channel_id: Option<String>,
) -> Result<()> {
    state.agent()?.focus(&session_id, channel_id.as_deref());
    Ok(())
}

/// Run one tool call.
///
/// The webview names a tool and passes arguments. It cannot name a program, a
/// path, or a channel that the policy has not already agreed to — and the
/// `rationale` it passes is the model's words, which travel to the approval
/// card labelled untrustworthy and are never used in a decision.
#[tauri::command]
pub async fn agent_tool_call(
    state: State<'_, Arc<AppState>>,
    session_id: String,
    name: String,
    args: serde_json::Value,
    rationale: Option<String>,
) -> Result<ToolCallResult> {
    let engine = state.agent()?;
    let host = DesktopHost::new(state.inner().clone());
    let outcome = engine
        .tool_call(&session_id, &name, &args, rationale, &host)
        .await?;
    Ok(ToolCallResult {
        content: outcome.output.content,
        artifact: outcome.output.artifact,
        is_error: outcome.output.is_error,
        taints: outcome.taints,
        verdict: outcome.verdict,
    })
}

#[derive(serde::Serialize)]
pub struct ToolCallResult {
    pub content: serde_json::Value,
    pub artifact: Option<String>,
    pub is_error: bool,
    pub taints: bool,
    /// What the gate decided.
    ///
    /// Without this the panel cannot tell "you declined this" from "the tool
    /// failed", and a card the user deliberately denied renders as a fault —
    /// which reads as the agent being broken rather than as it being obedient.
    pub verdict: llack_core::agent::Verdict,
}

#[tauri::command]
pub fn agent_resolve_approval(
    state: State<'_, Arc<AppState>>,
    request_id: String,
    nonce: String,
    approve: bool,
    remember: bool,
) -> Result<()> {
    state
        .agent()?
        .resolve_approval(&request_id, &nonce, approve, remember)
}

#[tauri::command]
pub fn agent_cancel(state: State<'_, Arc<AppState>>, session_id: Option<String>) -> Result<()> {
    let _ = session_id;
    // Cancels every pending approval, not only this session's. Two concurrent
    // agent turns are not a shape this version supports, and a cancel that
    // leaves someone else's prompt open would be worse than one that is too
    // broad.
    state.agent()?.cancel();
    Ok(())
}

/// Let the user grant a directory through the OS dialog.
///
/// The dialog is the grant. A path the webview typed would be a path the model
/// chose, and the whole value of a root is that a human picked it.
#[tauri::command]
pub async fn agent_pick_root(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    session_id: String,
) -> Result<Option<String>> {
    use tauri_plugin_dialog::DialogExt;

    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .set_title("에이전트가 읽을 폴더를 선택하세요")
        .pick_folder(move |picked| {
            let _ = tx.send(picked);
        });
    let picked = rx
        .await
        .map_err(|_| Error::Other("폴더 선택이 취소되었습니다.".into()))?;

    let Some(picked) = picked else {
        return Ok(None);
    };
    let path: PathBuf = picked
        .into_path()
        .map_err(|e| Error::Other(format!("폴더 경로를 읽을 수 없습니다: {e}")))?;
    // Canonicalise before recording: the policy compares prefixes, and a root
    // recorded through a symlink would not match the paths it is meant to allow.
    let path = std::fs::canonicalize(&path)
        .map_err(|e| Error::Other(format!("폴더를 확인할 수 없습니다: {e}")))?;

    state.agent()?.add_root(&session_id, path.clone())?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// Re-verify the audit chain. A button, so "the log is tamper-evident" is
/// checkable rather than asserted.
#[tauri::command]
pub fn agent_verify_audit(
    state: State<'_, Arc<AppState>>,
) -> Result<llack_core::agent::audit::VerifyReport> {
    state.agent()?.verify_audit()
}
