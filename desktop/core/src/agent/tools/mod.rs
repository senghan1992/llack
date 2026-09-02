//! The tool catalog, and the one door every tool call goes through.
//!
//! ## The structural guarantee
//!
//! [`execute`] is the only public way to run a tool. It classifies, audits,
//! asks, audits again, and only then calls a handler — and the handlers live
//! in private submodules with `pub(super)` entry points. There is no reachable
//! path that runs a tool without passing the gate, so somebody adding a tool
//! next year cannot forget to wire the gate up. That is the whole reason this
//! module exists as a chokepoint rather than as a dispatch table the loop
//! calls into directly.
//!
//! ## Registration is not exposure
//!
//! [`ToolCatalog::register`] says a handler exists; [`ToolCatalog::expose`]
//! says which specs go into *this turn's* request. Splitting them is what lets
//! a host without computer control (the browser build) simply not expose the
//! host tools, so the model never proposes one and no stub is ever hit. It is
//! also what lets an MCP server register a hundred tools later and expose a
//! handful.
//!
//! The exposed list is built per turn rather than cached in a `static`, since
//! a server connected mid-session should appear without a restart. That does
//! invalidate the provider's prompt-cache prefix when the set changes — an
//! acceptable cost, because it happens on connect, not per turn.

mod artifact;
mod chat;
mod host;

use std::collections::BTreeMap;
use std::sync::Arc;

use serde::Serialize;

use crate::agent::approval::{ApprovalBroker, Outcome};
use crate::agent::audit::{AuditEntry, AuditLog, DecisionSource, Verdict};
use crate::agent::policy::{self, Decision, SessionContext, ToolCall};
use crate::agent::store::AgentStore;
use crate::error::{Error, Result};

/// Where a tool came from. One variant today; `Mcp` is what makes v2 additive.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ToolSource {
    Builtin,
    Mcp { server_id: String },
}

/// What the host can actually do. The browser build reports none of the host
/// capabilities, and the exposed tool list shrinks accordingly.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HostCapabilities {
    /// Can run programs and touch files on this machine.
    pub computer_control: bool,
    /// Has a signed-in Llack session to read and post with.
    pub workspace: bool,
}

impl HostCapabilities {
    /// The desktop shell.
    pub fn desktop() -> Self {
        Self {
            computer_control: true,
            workspace: true,
        }
    }

    /// A browser tab: chat tools only.
    pub fn browser() -> Self {
        Self {
            computer_control: false,
            workspace: true,
        }
    }
}

/// One tool as the provider sees it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ToolSpec {
    /// Namespaced from day one (`chat.read_channel`), because renaming a tool
    /// after sessions are stored breaks replay of those sessions.
    pub name: String,
    pub description: String,
    /// JSON Schema. `strict` tool use requires `additionalProperties: false`
    /// and a complete `required` list, so every schema here supplies both.
    pub input_schema: serde_json::Value,
    pub source: ToolSource,
}

/// What a tool hands back.
///
/// `artifact` is the RLM seam: a handler that produced a lot of text puts it in
/// the store and returns a handle here, so the loop can keep the parent context
/// bounded without every handler having to think about it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ToolOutput {
    /// What goes back to the model as the tool result.
    pub content: serde_json::Value,
    /// Set when the full value lives in the artifact store.
    pub artifact: Option<String>,
    /// True when the model should be told this failed.
    pub is_error: bool,
}

impl ToolOutput {
    pub fn ok(content: serde_json::Value) -> Self {
        Self {
            content,
            artifact: None,
            is_error: false,
        }
    }

    pub fn with_artifact(content: serde_json::Value, handle: impl Into<String>) -> Self {
        Self {
            content,
            artifact: Some(handle.into()),
            is_error: false,
        }
    }

    /// A failure the model should see and can react to.
    ///
    /// Deliberately not a Rust error: a denied approval or a missing file is
    /// information for the model, and killing the turn over it trains users
    /// not to deny things.
    pub fn error(message: impl Into<String>) -> Self {
        Self {
            content: serde_json::json!({ "error": message.into() }),
            artifact: None,
            is_error: true,
        }
    }
}

/// Everything a handler is allowed to reach.
pub struct ToolContext<'a> {
    pub session_id: &'a str,
    pub store: &'a AgentStore,
    pub host: &'a dyn ToolHost,
    /// The workspace the panel is looking at, when there is one.
    pub workspace_id: Option<&'a str>,
    pub channel_id: Option<&'a str>,
}

/// The parts of a tool that only the real shell can do.
///
/// A trait so `llack-core` stays free of Tauri and of any process spawning,
/// which is what keeps every test in this crate runnable without a GUI. The
/// desktop shell supplies the real implementation; tests supply a fake.
#[async_trait::async_trait]
pub trait ToolHost: Send + Sync {
    /// Run a program. Never a shell: `argv[0]` is the executable.
    async fn exec(&self, argv: &[String], cwd: &std::path::Path) -> Result<ExecOutput>;
    /// Read a file, refusing anything over `cap` bytes.
    async fn read_file(&self, path: &std::path::Path, cap: u64) -> Result<Vec<u8>>;
    /// List a directory, names only.
    async fn list_dir(&self, path: &std::path::Path) -> Result<Vec<String>>;
    /// Fetch channel history through the signed-in session.
    async fn chat_history(&self, channel_id: &str, limit: u32) -> Result<Vec<ChatLine>>;
    /// Search the workspace through the signed-in session.
    async fn chat_search(&self, workspace_id: &str, query: &str) -> Result<Vec<ChatLine>>;
    /// Post as the signed-in human.
    async fn chat_post(&self, channel_id: &str, body: &str) -> Result<String>;
}

/// One message, flattened for the model.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ChatLine {
    pub id: String,
    pub author: String,
    pub at: String,
    pub body: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecOutput {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub duration_ms: u64,
    /// True when the process was killed for exceeding its wall clock.
    pub timed_out: bool,
}

/// Registered handlers, keyed by tool name.
pub struct ToolCatalog {
    specs: BTreeMap<String, ToolSpec>,
}

impl ToolCatalog {
    /// The built-in set. Ordered (BTreeMap) so the exposed list is byte-stable
    /// across runs — an unstable tool order silently breaks the provider's
    /// prompt cache, since `tools` is rendered before `system`.
    pub fn builtin() -> Self {
        let mut specs = BTreeMap::new();
        for spec in chat::specs()
            .into_iter()
            .chain(artifact::specs())
            .chain(host::specs())
        {
            specs.insert(spec.name.clone(), spec);
        }
        Self { specs }
    }

    pub fn register(&mut self, spec: ToolSpec) {
        self.specs.insert(spec.name.clone(), spec);
    }

    pub fn get(&self, name: &str) -> Option<&ToolSpec> {
        self.specs.get(name)
    }

    /// The specs to send this turn, filtered by what the host can do.
    ///
    /// Filtering here rather than in the UI is the real fix for "computer
    /// control is desktop-only": the model never sees a tool it cannot use, so
    /// it never proposes one and no browser stub is ever reached. A stub that
    /// does get hit therefore means a bug, and it shows up in the audit log as
    /// one.
    pub fn expose(&self, caps: HostCapabilities) -> Vec<ToolSpec> {
        self.specs
            .values()
            .filter(|spec| {
                if spec.name.starts_with("host.") && !caps.computer_control {
                    return false;
                }
                if spec.name.starts_with("chat.") && !caps.workspace {
                    return false;
                }
                true
            })
            .cloned()
            .collect()
    }
}

impl Default for ToolCatalog {
    fn default() -> Self {
        Self::builtin()
    }
}

/// Run one tool call, gate and all.
///
/// The order is deliberate and load-bearing:
///
/// 1. parse the name and arguments into a [`ToolCall`] — an unknown name is
///    refused here, before anything else looks at it;
/// 2. [`policy::classify`];
/// 3. write the **intent** audit record, so a crash mid-execution still leaves
///    evidence of what was attempted;
/// 4. ask, if the decision says to;
/// 5. execute;
/// 6. write the **outcome** record.
#[allow(clippy::too_many_arguments)]
pub async fn execute(
    name: &str,
    args: &serde_json::Value,
    rationale: Option<String>,
    ctx: &ToolContext<'_>,
    session: &SessionContext,
    broker: &ApprovalBroker,
    audit: &AuditLog,
    catalog: &ToolCatalog,
) -> Result<ExecuteOutcome> {
    let call = parse_call(name, args, catalog);
    let decision = policy::classify(&call, session);
    let rule = decision.rule();
    let redacted = redact_args(&call);

    audit.append(AuditEntry::intent(name, redacted.clone(), rule).tainted(session.tainted))?;

    let (verdict, source) = match &decision {
        Decision::Refuse { reason, .. } => {
            audit.append(
                AuditEntry::outcome(name, Verdict::Refused)
                    .rule(rule)
                    .source(DecisionSource::Policy)
                    .tainted(session.tainted),
            )?;
            ctx.store
                .record_approval(ctx.session_id, name, reason, &redacted, "refused")?;
            return Ok(ExecuteOutcome {
                output: ToolOutput::error(*reason),
                taints: false,
                verdict: Verdict::Refused,
            });
        }
        Decision::Auto { .. } => (Verdict::Auto, DecisionSource::PolicyAuto),
        Decision::Approve { risk, grain, facts } => {
            let outcome = broker
                .ask(ctx.session_id, name, *risk, grain, facts.clone(), rationale)
                .await;
            match outcome {
                Outcome::Approved { source } => (Verdict::Approved, source),
                Outcome::Denied | Outcome::Expired | Outcome::Cancelled => {
                    let verdict = match outcome {
                        Outcome::Denied => Verdict::Denied,
                        Outcome::Expired => Verdict::Expired,
                        _ => Verdict::Cancelled,
                    };
                    audit.append(
                        AuditEntry::outcome(name, verdict)
                            .rule(rule)
                            .tainted(session.tainted),
                    )?;
                    ctx.store.record_approval(
                        ctx.session_id,
                        name,
                        facts.title,
                        &redacted,
                        "denied",
                    )?;
                    // The model is told, in the operator's voice, not to retry.
                    return Ok(ExecuteOutcome {
                        output: ToolOutput::error(
                            "사용자가 이 작업을 거부했습니다. 같은 작업을 다시 요청하지 마세요.",
                        ),
                        taints: false,
                        verdict,
                    });
                }
            }
        }
    };

    let started = std::time::Instant::now();
    let result = dispatch(&call, args, ctx).await;
    let elapsed = started.elapsed().as_millis() as u64;

    let taints = matches!(decision, Decision::Auto { taints: true });

    match result {
        Ok(output) => {
            let bytes = serde_json::to_vec(&output.content).unwrap_or_default();
            audit.append(
                AuditEntry::outcome(name, verdict)
                    .rule(rule)
                    .source(source)
                    .tainted(session.tainted)
                    .duration_ms(elapsed)
                    .output(&bytes),
            )?;
            if verdict == Verdict::Approved {
                ctx.store
                    .record_approval(ctx.session_id, name, "실행됨", &redacted, "approved")?;
            }
            Ok(ExecuteOutcome {
                output,
                taints,
                verdict,
            })
        }
        Err(err) => {
            audit.append(
                AuditEntry::outcome(name, verdict)
                    .rule(rule)
                    .source(source)
                    .tainted(session.tainted)
                    .duration_ms(elapsed)
                    .error_code(err.code()),
            )?;
            // A failed tool is information for the model, not a dead turn.
            Ok(ExecuteOutcome {
                output: ToolOutput::error(err.to_string()),
                taints,
                verdict,
            })
        }
    }
}

/// What [`execute`] concluded.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecuteOutcome {
    pub output: ToolOutput,
    /// True when the caller must now mark the session tainted.
    pub taints: bool,
    pub verdict: Verdict,
}

/// Turn a name plus JSON into a typed call.
///
/// Anything the catalog does not know, or any argument shape that does not fit,
/// becomes [`ToolCall::Unknown`] — which the policy refuses. Guessing at a
/// malformed call is how a tool ends up running with a default the model never
/// asked for.
fn parse_call(name: &str, args: &serde_json::Value, catalog: &ToolCatalog) -> ToolCall {
    if catalog.get(name).is_none() {
        return ToolCall::Unknown {
            name: name.to_string(),
        };
    }
    let unknown = || ToolCall::Unknown {
        name: name.to_string(),
    };

    match name {
        "agent.context" => ToolCall::AgentContext,

        "chat.read_channel" => match args.get("channel_id").and_then(|v| v.as_str()) {
            Some(channel_id) => ToolCall::ChatReadChannel {
                channel_id: channel_id.to_string(),
                limit: args
                    .get("limit")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(80)
                    .clamp(1, 200) as u32,
            },
            None => unknown(),
        },

        "chat.search" => match args.get("query").and_then(|v| v.as_str()) {
            Some(query) => ToolCall::ChatSearch {
                query: query.to_string(),
            },
            None => unknown(),
        },

        "chat.post_message" => match (
            args.get("channel_id").and_then(|v| v.as_str()),
            args.get("body").and_then(|v| v.as_str()),
        ) {
            (Some(channel_id), Some(body)) => ToolCall::ChatPostMessage {
                channel_id: channel_id.to_string(),
                body: body.to_string(),
            },
            _ => unknown(),
        },

        "artifact.query" => match (
            args.get("handle").and_then(|v| v.as_str()),
            args.get("op").and_then(|v| v.as_str()),
        ) {
            (Some(handle), Some(op)) => ToolCall::ArtifactQuery {
                handle: handle.to_string(),
                op: op.to_string(),
            },
            _ => unknown(),
        },

        "host.exec" => {
            let argv: Option<Vec<String>> = args.get("argv").and_then(|v| v.as_array()).map(|a| {
                a.iter()
                    .filter_map(|item| item.as_str().map(str::to_string))
                    .collect()
            });
            match (argv, args.get("cwd").and_then(|v| v.as_str())) {
                // An empty argv reaches the policy, which refuses it with a
                // named rule — better an audited refusal than a silent
                // "unknown tool".
                (Some(argv), Some(cwd)) => ToolCall::HostExec {
                    argv,
                    cwd: std::path::PathBuf::from(cwd),
                },
                _ => unknown(),
            }
        }

        "host.read_file" => match args.get("path").and_then(|v| v.as_str()) {
            Some(path) => ToolCall::HostReadFile {
                path: std::path::PathBuf::from(path),
            },
            None => unknown(),
        },

        "host.list_dir" => match args.get("path").and_then(|v| v.as_str()) {
            Some(path) => ToolCall::HostListDir {
                path: std::path::PathBuf::from(path),
            },
            None => unknown(),
        },

        _ => unknown(),
    }
}

/// Only reachable from [`execute`], after the gate.
///
/// Takes the raw `args` as well as the typed call: the policy only needs to
/// know *which* tool and which resource, while a handler may need parameters
/// that carry no authorisation weight (how many lines of an artifact to
/// return). Threading both keeps the policy's view minimal without the handler
/// having to guess.
async fn dispatch(
    call: &ToolCall,
    args: &serde_json::Value,
    ctx: &ToolContext<'_>,
) -> Result<ToolOutput> {
    match call {
        ToolCall::AgentContext => Ok(ToolOutput::ok(serde_json::json!({
            "workspace_id": ctx.workspace_id,
            "channel_id": ctx.channel_id,
        }))),
        ToolCall::ChatReadChannel { channel_id, limit } => {
            chat::read_channel(ctx, channel_id, *limit).await
        }
        ToolCall::ChatSearch { query } => chat::search(ctx, query).await,
        ToolCall::ChatPostMessage { channel_id, body } => {
            chat::post_message(ctx, channel_id, body).await
        }
        ToolCall::ArtifactQuery { handle, op } => artifact::query(ctx, handle, op, args),
        ToolCall::HostExec { argv, cwd } => host::exec(ctx, argv, cwd).await,
        ToolCall::HostReadFile { path } => host::read_file(ctx, path).await,
        ToolCall::HostListDir { path } => host::list_dir(ctx, path).await,
        // The policy classifies writes already, but v1 exposes no write tool,
        // so `parse_call` cannot produce this and there is nothing to run. The
        // arm is explicit rather than a catch-all so that adding the tool later
        // is a compile error here instead of a silent no-op.
        ToolCall::HostWriteFile { .. } => Err(Error::Other(
            "파일 쓰기 도구는 아직 제공되지 않습니다.".into(),
        )),
        // Refused by the policy before it can reach here.
        ToolCall::Mcp { .. } | ToolCall::Unknown { .. } => {
            Err(Error::Other("이 도구는 실행할 수 없습니다.".into()))
        }
    }
}

/// The audit log's view of a call: canonical, and free of payloads.
///
/// A message body or a file's contents must not reach the log — see
/// [`crate::agent::audit`] for why. What is kept is enough to answer "what did
/// it try to do", which is the question the log exists for.
fn redact_args(call: &ToolCall) -> serde_json::Value {
    match call {
        ToolCall::AgentContext => serde_json::json!({}),
        ToolCall::ChatReadChannel { channel_id, limit } => {
            serde_json::json!({ "channel_id": channel_id, "limit": limit })
        }
        ToolCall::ChatSearch { query } => {
            // The query is the user's own words, not a payload, and without it
            // the log cannot explain why a channel was read.
            serde_json::json!({ "query": query })
        }
        ToolCall::ChatPostMessage { channel_id, body } => serde_json::json!({
            "channel_id": channel_id,
            "body_bytes": body.len(),
        }),
        ToolCall::ArtifactQuery { handle, op } => {
            serde_json::json!({ "handle": handle, "op": op })
        }
        ToolCall::HostExec { argv, cwd } => serde_json::json!({
            "argv": argv,
            "cwd": cwd.display().to_string(),
        }),
        ToolCall::HostReadFile { path } | ToolCall::HostListDir { path } => {
            serde_json::json!({ "path": path.display().to_string() })
        }
        ToolCall::HostWriteFile { path, bytes } => serde_json::json!({
            "path": path.display().to_string(),
            "bytes": bytes,
        }),
        ToolCall::Mcp { server, tool } => serde_json::json!({ "server": server, "tool": tool }),
        ToolCall::Unknown { name } => serde_json::json!({ "name": name }),
    }
}

/// A schema shaped for `strict: true`: closed object, complete `required`.
pub(crate) fn schema(properties: serde_json::Value, required: &[&str]) -> serde_json::Value {
    serde_json::json!({
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": false,
    })
}

/// Wrap a `ToolHost` in an `Arc` for a context. Convenience for callers.
pub fn host_ref(host: &Arc<dyn ToolHost>) -> &dyn ToolHost {
    host.as_ref()
}

#[cfg(test)]
pub(crate) mod testing {
    //! A `ToolHost` that records what it was asked and answers from a script,
    //! so the catalog and the gate can be tested with no process spawning and
    //! no network.

    use super::*;
    use parking_lot::Mutex;

    #[derive(Default)]
    pub struct FakeHost {
        pub exec_calls: Mutex<Vec<Vec<String>>>,
        pub posted: Mutex<Vec<(String, String)>>,
        pub reads: Mutex<Vec<std::path::PathBuf>>,
        pub history: Mutex<Vec<ChatLine>>,
        pub exec_stdout: Mutex<String>,
        pub fail_next: Mutex<bool>,
    }

    impl FakeHost {
        pub fn with_history(lines: Vec<ChatLine>) -> Self {
            Self {
                history: Mutex::new(lines),
                ..Default::default()
            }
        }

        pub fn with_stdout(text: &str) -> Self {
            Self {
                exec_stdout: Mutex::new(text.to_string()),
                ..Default::default()
            }
        }
    }

    #[async_trait::async_trait]
    impl ToolHost for FakeHost {
        async fn exec(&self, argv: &[String], _cwd: &std::path::Path) -> Result<ExecOutput> {
            self.exec_calls.lock().push(argv.to_vec());
            if *self.fail_next.lock() {
                return Err(Error::Other("자식 프로세스를 시작할 수 없습니다".into()));
            }
            Ok(ExecOutput {
                exit_code: 0,
                stdout: self.exec_stdout.lock().clone(),
                stderr: String::new(),
                duration_ms: 1,
                timed_out: false,
            })
        }

        async fn read_file(&self, path: &std::path::Path, _cap: u64) -> Result<Vec<u8>> {
            self.reads.lock().push(path.to_path_buf());
            Ok(b"file contents".to_vec())
        }

        async fn list_dir(&self, _path: &std::path::Path) -> Result<Vec<String>> {
            Ok(vec!["a.rs".into(), "b.rs".into()])
        }

        async fn chat_history(&self, _channel_id: &str, limit: u32) -> Result<Vec<ChatLine>> {
            let lines = self.history.lock().clone();
            Ok(lines.into_iter().take(limit as usize).collect())
        }

        async fn chat_search(&self, _workspace_id: &str, _query: &str) -> Result<Vec<ChatLine>> {
            Ok(self.history.lock().clone())
        }

        async fn chat_post(&self, channel_id: &str, body: &str) -> Result<String> {
            self.posted
                .lock()
                .push((channel_id.to_string(), body.to_string()));
            Ok("01POSTED".into())
        }
    }

    pub fn line(id: &str, author: &str, body: &str) -> ChatLine {
        ChatLine {
            id: id.into(),
            author: author.into(),
            at: "2026-09-02T10:00:00Z".into(),
            body: body.into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::testing::{line, FakeHost};
    use super::*;
    use crate::agent::approval::{ApprovalNotifier, ApprovalRequest, SilentNotifier};
    use crate::agent::audit::AuditActor;
    use crate::agent::policy::SessionContext;
    use parking_lot::Mutex;
    use std::path::PathBuf;

    /// Approves (or denies) every request the moment it opens, so a test can
    /// drive the whole gate without a UI.
    struct AutoAnswer {
        approve: bool,
        /// Whether the simulated user ticks "remember this".
        remember: Mutex<bool>,
        seen: Mutex<Vec<ApprovalRequest>>,
        broker: Mutex<Option<Arc<ApprovalBroker>>>,
    }

    impl AutoAnswer {
        fn new(approve: bool) -> Arc<Self> {
            Arc::new(Self {
                approve,
                remember: Mutex::new(false),
                seen: Mutex::new(Vec::new()),
                broker: Mutex::new(None),
            })
        }
    }

    impl ApprovalNotifier for AutoAnswer {
        fn opened(&self, request: &ApprovalRequest) {
            self.seen.lock().push(request.clone());
            if let Some(broker) = self.broker.lock().clone() {
                let remember = *self.remember.lock();
                let _ = broker.resolve(&request.id, &request.nonce, self.approve, remember);
            }
        }
        fn closed(&self, _id: &str, _outcome: Outcome) {}
    }

    struct Harness {
        store: AgentStore,
        audit_dir: PathBuf,
        audit: AuditLog,
        catalog: ToolCatalog,
        session_id: String,
        host: Arc<FakeHost>,
    }

    fn harness(host: Arc<FakeHost>) -> Harness {
        let store = AgentStore::in_memory().unwrap();
        let session = store
            .create_session("01ALICE", Some("01WS"), "anthropic", "claude-opus-5")
            .unwrap();
        let audit_dir = std::env::temp_dir().join(format!(
            "llack-tools-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let audit = AuditLog::open(
            &audit_dir,
            AuditActor {
                session_id: session.id.clone(),
                user_id: Some("01ALICE".into()),
                server_url: None,
                workspace_id: Some("01WS".into()),
            },
            None,
        )
        .unwrap();
        Harness {
            store,
            audit_dir,
            audit,
            catalog: ToolCatalog::builtin(),
            session_id: session.id,
            host,
        }
    }

    impl Harness {
        fn ctx(&self) -> ToolContext<'_> {
            ToolContext {
                session_id: &self.session_id,
                store: &self.store,
                host: self.host.as_ref(),
                workspace_id: Some("01WS"),
                channel_id: Some("01CH"),
            }
        }

        async fn run(
            &self,
            broker: &ApprovalBroker,
            session: &SessionContext,
            name: &str,
            args: serde_json::Value,
        ) -> ExecuteOutcome {
            execute(
                name,
                &args,
                None,
                &self.ctx(),
                session,
                broker,
                &self.audit,
                &self.catalog,
            )
            .await
            .unwrap()
        }

        fn audit_records(&self) -> Vec<crate::agent::audit::AuditRecord> {
            crate::agent::audit::read_all(&self.audit_dir).unwrap()
        }
    }

    impl Drop for Harness {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.audit_dir).ok();
        }
    }

    fn session() -> SessionContext {
        SessionContext {
            tainted: false,
            roots: vec![PathBuf::from("/home/me/app")],
            home: Some(PathBuf::from("/home/me")),
            app_data_dir: PathBuf::from("/home/me/.local/share/com.llack.desktop"),
        }
    }

    // ── Exposure ────────────────────────────────────────────────────────

    #[test]
    fn a_browser_host_is_never_offered_the_host_tools() {
        let catalog = ToolCatalog::builtin();
        let desktop: Vec<String> = catalog
            .expose(HostCapabilities::desktop())
            .into_iter()
            .map(|s| s.name)
            .collect();
        let browser: Vec<String> = catalog
            .expose(HostCapabilities::browser())
            .into_iter()
            .map(|s| s.name)
            .collect();

        assert!(desktop.iter().any(|n| n == "host.exec"));
        assert!(
            !browser.iter().any(|n| n.starts_with("host.")),
            "the model must never see a tool this host cannot run: {browser:?}"
        );
        assert!(browser.iter().any(|n| n == "chat.read_channel"));
        assert!(browser.iter().any(|n| n == "artifact.query"));
    }

    #[test]
    fn the_exposed_order_is_stable_so_the_prompt_cache_survives() {
        let catalog = ToolCatalog::builtin();
        let first: Vec<String> = catalog
            .expose(HostCapabilities::desktop())
            .into_iter()
            .map(|s| s.name)
            .collect();
        let second: Vec<String> = ToolCatalog::builtin()
            .expose(HostCapabilities::desktop())
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert_eq!(first, second);
        let mut sorted = first.clone();
        sorted.sort();
        assert_eq!(first, sorted, "exposure must be deterministic");
    }

    #[test]
    fn every_schema_is_shaped_for_strict_tool_use() {
        for spec in ToolCatalog::builtin().expose(HostCapabilities::desktop()) {
            assert_eq!(
                spec.input_schema["additionalProperties"],
                serde_json::json!(false),
                "{} must close its schema for strict tool use",
                spec.name
            );
            assert!(
                spec.input_schema["required"].is_array(),
                "{} must list required properties",
                spec.name
            );
            assert!(
                spec.name.contains('.'),
                "{} must be namespaced so stored sessions stay replayable",
                spec.name
            );
        }
    }

    // ── The gate cannot be skipped ──────────────────────────────────────

    #[tokio::test]
    async fn a_refused_command_never_reaches_the_host() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": ["sudo", "rm", "-rf", "/"], "cwd": "/home/me/app" }),
            )
            .await;

        assert!(outcome.output.is_error);
        assert_eq!(outcome.verdict, Verdict::Refused);
        assert!(
            host.exec_calls.lock().is_empty(),
            "a refusal must not spawn anything"
        );
        // And it is on the record, with the rule that refused it.
        let records = h.audit_records();
        assert_eq!(records.len(), 2, "intent then outcome, always");
        assert_eq!(
            records[1].matched_rule.as_deref(),
            Some("exec_privilege_elevation")
        );
    }

    #[tokio::test]
    async fn a_denied_command_never_reaches_the_host_and_the_model_is_told_not_to_retry() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let answer = AutoAnswer::new(false);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": ["git", "status"], "cwd": "/home/me/app" }),
            )
            .await;

        assert!(outcome.output.is_error);
        assert_eq!(outcome.verdict, Verdict::Denied);
        assert!(host.exec_calls.lock().is_empty());
        let message = outcome.output.content["error"].as_str().unwrap();
        assert!(
            message.contains("다시 요청하지 마세요"),
            "a denial must carry an operator instruction: {message}"
        );
    }

    #[tokio::test]
    async fn an_approved_command_runs_and_its_output_becomes_an_artifact() {
        let host = Arc::new(FakeHost::with_stdout(
            &(0..500)
                .map(|i| format!("build line {i}\n"))
                .collect::<String>(),
        ));
        let h = harness(host.clone());
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": ["make", "build"], "cwd": "/home/me/app" }),
            )
            .await;

        assert!(!outcome.output.is_error);
        assert_eq!(outcome.verdict, Verdict::Approved);
        assert_eq!(host.exec_calls.lock()[0], vec!["make", "build"]);

        // A 500-line log must not be in the tool result.
        let handle = outcome
            .output
            .artifact
            .expect("large output needs a handle");
        assert!(handle.starts_with("art_"));
        let rendered = outcome.output.content.to_string();
        assert!(
            !rendered.contains("build line 250"),
            "the middle of a large log must stay out of the context"
        );
        assert!(h.store.artifact(&handle).unwrap().is_some());
    }

    #[tokio::test]
    async fn an_unknown_tool_is_refused_and_audited() {
        let h = harness(Arc::new(FakeHost::default()));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));
        let outcome = h
            .run(
                &broker,
                &session(),
                "host.definitely_not_real",
                serde_json::json!({}),
            )
            .await;
        assert_eq!(outcome.verdict, Verdict::Refused);
        assert_eq!(
            h.audit_records()[1].matched_rule.as_deref(),
            Some("unknown_tool")
        );
    }

    #[tokio::test]
    async fn a_malformed_call_is_refused_rather_than_defaulted() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        // `cwd` missing: guessing one would run the command somewhere the
        // model never named.
        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": ["git", "status"] }),
            )
            .await;
        assert_eq!(outcome.verdict, Verdict::Refused);
        assert!(host.exec_calls.lock().is_empty());
    }

    #[tokio::test]
    async fn an_empty_argv_is_refused_with_its_own_rule_not_as_an_unknown_tool() {
        let h = harness(Arc::new(FakeHost::default()));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));
        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": [], "cwd": "/home/me/app" }),
            )
            .await;
        assert_eq!(outcome.verdict, Verdict::Refused);
        assert_eq!(
            h.audit_records()[1].matched_rule.as_deref(),
            Some("exec_empty_argv")
        );
    }

    // ── Chat tools and the RLM seam ─────────────────────────────────────

    #[tokio::test]
    async fn reading_a_channel_needs_no_approval_and_reports_that_it_taints() {
        let host = Arc::new(FakeHost::with_history(vec![
            line("01M1", "김앨리스", "배포 준비됐습니다"),
            line("01M2", "이밥", "확인했습니다"),
        ]));
        let h = harness(host);
        let answer = AutoAnswer::new(false);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "chat.read_channel",
                serde_json::json!({ "channel_id": "01CH", "limit": 80 }),
            )
            .await;

        assert!(!outcome.output.is_error);
        assert_eq!(outcome.verdict, Verdict::Auto);
        assert!(
            outcome.taints,
            "ingesting channel text must tell the caller to taint the session"
        );
        assert!(
            answer.seen.lock().is_empty(),
            "reading chat must not interrupt the user"
        );

        // Small history comes back inline: no second round trip for two lines.
        assert!(outcome.output.content["inline"].is_string());
        assert_eq!(outcome.output.content["total_lines"], 2);
    }

    #[tokio::test]
    async fn a_large_channel_comes_back_as_a_handle_that_can_be_sliced() {
        let lines: Vec<ChatLine> = (0..400)
            .map(|i| line(&format!("01M{i}"), "봇", &format!("메시지 {i}")))
            .collect();
        let h = harness(Arc::new(FakeHost::with_history(lines)));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        let read = h
            .run(
                &broker,
                &session(),
                "chat.read_channel",
                serde_json::json!({ "channel_id": "01CH", "limit": 200 }),
            )
            .await;
        let handle = read.output.artifact.clone().unwrap();
        assert!(
            read.output.content["inline"].is_null(),
            "a large history must not be inlined"
        );

        // grep, with the pattern actually threaded through.
        let hit = h
            .run(
                &broker,
                &session(),
                "artifact.query",
                serde_json::json!({ "handle": handle, "op": "grep", "pattern": "메시지 137" }),
            )
            .await;
        assert!(!hit.output.is_error, "{:?}", hit.output);
        let found = hit.output.content["lines"].as_array().unwrap();
        assert_eq!(found.len(), 1);
        assert!(found[0].as_str().unwrap().contains("메시지 137"));

        // tail honours its own line count.
        let tail = h
            .run(
                &broker,
                &session(),
                "artifact.query",
                serde_json::json!({ "handle": handle, "op": "tail", "lines": 3 }),
            )
            .await;
        assert_eq!(tail.output.content["lines"].as_array().unwrap().len(), 3);
    }

    #[tokio::test]
    async fn a_grep_without_a_pattern_tells_the_model_instead_of_failing_the_turn() {
        let h = harness(Arc::new(FakeHost::with_history(vec![line(
            "01M", "a", "b",
        )])));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));
        let read = h
            .run(
                &broker,
                &session(),
                "chat.read_channel",
                serde_json::json!({ "channel_id": "01CH" }),
            )
            .await;
        let handle = read.output.artifact.unwrap();

        let outcome = h
            .run(
                &broker,
                &session(),
                "artifact.query",
                serde_json::json!({ "handle": handle, "op": "grep" }),
            )
            .await;
        assert!(outcome.output.is_error);
        assert!(outcome.output.content["error"]
            .as_str()
            .unwrap()
            .contains("pattern"));
    }

    #[tokio::test]
    async fn posting_requires_approval_and_reaches_the_host_only_once_allowed() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "chat.post_message",
                serde_json::json!({ "channel_id": "01CH", "body": "요약입니다" }),
            )
            .await;

        assert!(!outcome.output.is_error);
        assert_eq!(answer.seen.lock().len(), 1, "posting must always ask");
        assert_eq!(
            answer.seen.lock()[0].facts.title,
            "당신의 이름으로 채널에 게시합니다"
        );
        assert_eq!(host.posted.lock()[0].1, "요약입니다");
    }

    // ── The audit log never carries payloads ────────────────────────────

    #[tokio::test]
    async fn the_audit_log_records_the_shape_of_a_post_but_not_its_words() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host);
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        h.run(
            &broker,
            &session(),
            "chat.post_message",
            serde_json::json!({ "channel_id": "01CH", "body": "내부 비밀 프로젝트 이름" }),
        )
        .await;

        let raw = std::fs::read_to_string(
            std::fs::read_dir(&h.audit_dir)
                .unwrap()
                .next()
                .unwrap()
                .unwrap()
                .path(),
        )
        .unwrap();
        assert!(
            !raw.contains("내부 비밀"),
            "the log must record a byte count, not the message"
        );
        assert!(raw.contains("body_bytes"));
    }

    #[tokio::test]
    async fn a_host_failure_becomes_information_for_the_model_not_a_dead_turn() {
        let host = Arc::new(FakeHost::default());
        *host.fail_next.lock() = true;
        let h = harness(host);
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.exec",
                serde_json::json!({ "argv": ["git", "status"], "cwd": "/home/me/app" }),
            )
            .await;

        assert!(outcome.output.is_error, "the model must be told");
        assert_eq!(
            outcome.verdict,
            Verdict::Approved,
            "the decision was still an approval; the execution failed"
        );
        assert_eq!(h.audit_records().len(), 2);
    }

    #[tokio::test]
    async fn approvals_are_recorded_in_the_store_for_the_what_did_it_do_screen() {
        let h = harness(Arc::new(FakeHost::default()));
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        h.run(
            &broker,
            &session(),
            "host.exec",
            serde_json::json!({ "argv": ["git", "status"], "cwd": "/home/me/app" }),
        )
        .await;
        h.run(
            &broker,
            &session(),
            "host.exec",
            serde_json::json!({ "argv": ["sudo", "ls"], "cwd": "/home/me/app" }),
        )
        .await;

        assert_eq!(
            h.store.approval_count(&h.session_id).unwrap(),
            2,
            "both the approval and the refusal belong on the record"
        );
    }

    #[tokio::test]
    async fn a_tainted_session_asks_again_for_something_it_had_remembered() {
        let h = harness(Arc::new(FakeHost::default()));
        let answer = AutoAnswer::new(true);
        *answer.remember.lock() = true;
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let args = serde_json::json!({ "argv": ["git", "status"], "cwd": "/home/me/app" });
        let clean = session();

        // First call in a clean session: asked once, and remembered.
        h.run(&broker, &clean, "host.exec", args.clone()).await;
        assert_eq!(answer.seen.lock().len(), 1);
        assert!(
            answer.seen.lock()[0].remembering_offered,
            "an untainted, non-interpreter command may be remembered"
        );
        assert_eq!(broker.granted_count(), 1);

        // Same call again: the grant answers it without asking.
        h.run(&broker, &clean, "host.exec", args.clone()).await;
        assert_eq!(
            answer.seen.lock().len(),
            1,
            "a remembered command must not ask again"
        );

        // Now the session has read a channel. The grain drops to Once, so the
        // grant cannot match and the user is asked again — the whole point of
        // the taint downgrade.
        let dirty = SessionContext {
            tainted: true,
            ..session()
        };
        h.run(&broker, &dirty, "host.exec", args).await;
        assert_eq!(
            answer.seen.lock().len(),
            2,
            "reading a channel must make a remembered command ask again"
        );
        assert!(
            !answer.seen.lock()[1].remembering_offered,
            "a tainted session must not offer to remember"
        );
    }

    #[tokio::test]
    async fn an_interpreter_is_never_offered_for_remembering_even_when_clean() {
        let h = harness(Arc::new(FakeHost::default()));
        let answer = AutoAnswer::new(true);
        *answer.remember.lock() = true;
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        h.run(
            &broker,
            &session(),
            "host.exec",
            serde_json::json!({ "argv": ["bash", "-c", "echo hi"], "cwd": "/home/me/app" }),
        )
        .await;

        assert!(!answer.seen.lock()[0].remembering_offered);
        assert_eq!(
            broker.granted_count(),
            0,
            "remembering an interpreter would remember every program it can run"
        );
    }
}
