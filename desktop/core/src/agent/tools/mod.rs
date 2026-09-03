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
mod eval;
mod host;
mod memory;
mod skill;

use std::collections::BTreeMap;
use std::sync::Arc;

use serde::Serialize;

use crate::agent::approval::{ApprovalBroker, Outcome};
use crate::agent::audit::{AuditEntry, AuditLog, DecisionSource, Verdict};
use crate::agent::mcp::{self, McpToolDef};
use crate::agent::policy::{self, Decision, SessionContext, ToolCall};
use crate::agent::store::AgentStore;
use crate::error::{Error, Result};

/// Runs a call against a connected MCP server. Implemented by the engine,
/// which owns the clients; `None` in a context means no server is reachable
/// (tests, or a call parsed before a refresh).
#[async_trait::async_trait]
pub trait McpInvoker: Send + Sync {
    async fn call(
        &self,
        server_id: &str,
        tool: &str,
        args: &serde_json::Value,
    ) -> Result<serde_json::Value>;
}

/// The catalog's record of one MCP tool: enough to route a call and to fill an
/// approval card without trusting the model's prose.
#[derive(Debug, Clone)]
pub struct McpToolRef {
    pub server_id: String,
    pub server_name: String,
    pub endpoint: String,
    /// The tool's name on the server (not the `mcp.slug.tool` alias).
    pub tool: String,
}

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
    /// Can capture the screen and synthesise mouse/keyboard input. Gated behind
    /// the `screen-control` cargo feature in the shell and off by default, so
    /// these tools are absent from the catalog on a normal build.
    pub screen_control: bool,
}

impl HostCapabilities {
    /// The desktop shell. `screen_control` is passed in because it depends on a
    /// build feature the shell knows and core does not.
    pub fn desktop() -> Self {
        Self {
            computer_control: true,
            workspace: true,
            screen_control: false,
        }
    }

    /// A browser tab: chat tools only.
    pub fn browser() -> Self {
        Self {
            computer_control: false,
            workspace: true,
            screen_control: false,
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
    /// Runs MCP tool calls, when a server is connected.
    pub mcp: Option<&'a dyn McpInvoker>,
    /// The workspace the panel is looking at, when there is one.
    pub workspace_id: Option<&'a str>,
    pub channel_id: Option<&'a str>,
    /// The signed-in user, for memory scoping. `None` in a context with no
    /// session (tests, a headless run), in which case memory tools decline.
    pub user_id: Option<&'a str>,
    /// Where the skill files live. `None` means "no skills here" rather than an
    /// error, so a headless context lists an empty set.
    pub skills_dir: Option<std::path::PathBuf>,
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
    /// Write a file, replacing what was there. The parent directory must
    /// already exist — creating directories is a separate decision the user
    /// never approved.
    async fn write_file(&self, path: &std::path::Path, bytes: &[u8]) -> Result<()>;
    /// List a directory, names only.
    async fn list_dir(&self, path: &std::path::Path) -> Result<Vec<String>>;
    /// Fetch channel history through the signed-in session.
    async fn chat_history(&self, channel_id: &str, limit: u32) -> Result<Vec<ChatLine>>;
    /// Search the workspace through the signed-in session.
    async fn chat_search(&self, workspace_id: &str, query: &str) -> Result<Vec<ChatLine>>;
    /// Post as the signed-in human.
    async fn chat_post(&self, channel_id: &str, body: &str) -> Result<String>;

    /// Capture the screen. Only reached when the `screen-control` feature is on;
    /// the default implementation refuses, so a host that does not build the
    /// feature need not implement it. Image encoding lives in the shell — core
    /// receives the bytes already base64-encoded.
    async fn screenshot(&self, _display: Option<u32>) -> Result<Screenshot> {
        Err(crate::error::Error::Other(
            "이 빌드에는 화면 제어 기능이 없습니다.".into(),
        ))
    }
    /// Move the pointer and click. Refuses by default, as with `screenshot`.
    async fn click(&self, _x: i32, _y: i32, _button: &str) -> Result<()> {
        Err(crate::error::Error::Other(
            "이 빌드에는 화면 제어 기능이 없습니다.".into(),
        ))
    }
    /// Type text through synthesised key events. Refuses by default.
    async fn type_text(&self, _text: &str) -> Result<()> {
        Err(crate::error::Error::Other(
            "이 빌드에는 화면 제어 기능이 없습니다.".into(),
        ))
    }
}

/// A screen capture, already encoded by the shell.
///
/// The full PNG (`png_b64`) is stored as an artifact so the model can ask for
/// it later without it living in the context; the downscaled JPEG
/// (`image_b64`, ~1280px wide) is small enough to hand the model inline so it
/// can actually see the screen. Encoding both stays in the shell — core has no
/// image crate and no reason to grow one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Screenshot {
    /// Base64 of the full-resolution PNG.
    pub png_b64: String,
    /// Base64 of a downscaled JPEG, for inline display to the model.
    pub image_b64: String,
    /// The mime of `image_b64`, e.g. `image/jpeg`.
    pub mime: String,
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

/// The `agent.delegate` spec: registered so the model can call it, but run by
/// the host loop (TS), not by `dispatch` — the executor refuses it.
fn delegate_spec() -> ToolSpec {
    ToolSpec {
        name: "agent.delegate".into(),
        description: "하위 작업을 별도의 에이전트 턴에 맡깁니다. 결과 요약을 \
                      아티팩트 핸들로 돌려받아, 큰 중간 작업이 이 대화의 맥락을 \
                      채우지 않게 합니다. (호스트 루프가 실행합니다.)"
            .into(),
        input_schema: schema(
            serde_json::json!({
                "task": { "type": "string", "description": "하위 에이전트가 할 일" },
                "tools": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "하위 에이전트에게 허용할 도구 이름 (생략 시 읽기 전용)",
                },
                "max_steps": { "type": "integer", "description": "하위 턴의 최대 단계 수" },
            }),
            &["task"],
        ),
        source: ToolSource::Builtin,
    }
}

/// Registered handlers, keyed by tool name.
///
/// `Clone` so the engine can snapshot it for one `execute` call without holding
/// a lock across the `await` inside an MCP dispatch.
#[derive(Clone)]
pub struct ToolCatalog {
    specs: BTreeMap<String, ToolSpec>,
    /// MCP tools by their `mcp.slug.tool` alias. Kept beside `specs` so a call
    /// can be routed to the right server and the approval card filled from the
    /// server record rather than from the model.
    mcp_tools: BTreeMap<String, McpToolRef>,
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
            .chain(eval::specs())
            .chain(host::specs())
            .chain(memory::specs())
            .chain(skill::specs())
            .chain(std::iter::once(delegate_spec()))
        {
            specs.insert(spec.name.clone(), spec);
        }
        Self {
            specs,
            mcp_tools: BTreeMap::new(),
        }
    }

    pub fn register(&mut self, spec: ToolSpec) {
        self.specs.insert(spec.name.clone(), spec);
    }

    pub fn get(&self, name: &str) -> Option<&ToolSpec> {
        self.specs.get(name)
    }

    pub fn mcp_ref(&self, name: &str) -> Option<&McpToolRef> {
        self.mcp_tools.get(name)
    }

    /// Drop every tool from one server (before re-registering on refresh, or
    /// when it is removed). Names are stable per server, so a re-register with
    /// the same slug replaces cleanly.
    pub fn clear_mcp(&mut self, server_id: &str) {
        let names: Vec<String> = self
            .mcp_tools
            .iter()
            .filter(|(_, r)| r.server_id == server_id)
            .map(|(n, _)| n.clone())
            .collect();
        for name in names {
            self.specs.remove(&name);
            self.mcp_tools.remove(&name);
        }
    }

    /// Register a connected server's tools under `mcp.{slug}.{tool}`.
    ///
    /// `slug` is pre-computed by the engine with collisions already resolved,
    /// so two servers named the same do not fight over a prefix.
    pub fn register_mcp(
        &mut self,
        server_id: &str,
        server_name: &str,
        endpoint: &str,
        slug: &str,
        tools: &[McpToolDef],
    ) {
        self.clear_mcp(server_id);
        for tool in tools {
            let name = mcp::tool_name(slug, &tool.name);
            self.specs.insert(
                name.clone(),
                ToolSpec {
                    name: name.clone(),
                    description: tool.description.clone(),
                    input_schema: tool.input_schema.clone(),
                    source: ToolSource::Mcp {
                        server_id: server_id.to_string(),
                    },
                },
            );
            self.mcp_tools.insert(
                name,
                McpToolRef {
                    server_id: server_id.to_string(),
                    server_name: server_name.to_string(),
                    endpoint: endpoint.to_string(),
                    tool: tool.name.clone(),
                },
            );
        }
    }

    /// How many tools a server contributed. For the settings view.
    pub fn mcp_tool_count(&self, server_id: &str) -> usize {
        self.mcp_tools
            .values()
            .filter(|r| r.server_id == server_id)
            .count()
    }

    /// Every MCP tool spec for one server, for the settings view.
    pub fn mcp_specs(&self, server_id: &str) -> Vec<ToolSpec> {
        self.specs
            .values()
            .filter(|s| matches!(&s.source, ToolSource::Mcp { server_id: sid } if sid == server_id))
            .cloned()
            .collect()
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
                // The screen-control tools are `host.` tools too, so they need
                // computer control — but they also need their own feature, and
                // are hidden without it even on a full desktop build.
                if is_screen_tool(&spec.name) && !caps.screen_control {
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

    // An MCP result is third-party text entering the context, exactly like a
    // channel read — so it taints, even though it arrived through an approval
    // rather than an auto-tainting read.
    let taints =
        matches!(decision, Decision::Auto { taints: true }) || matches!(call, ToolCall::Mcp { .. });

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

        "artifact.eval" => match (
            args.get("handle").and_then(|v| v.as_str()),
            args.get("script").and_then(|v| v.as_str()),
        ) {
            (Some(handle), Some(_)) => ToolCall::ArtifactEval {
                handle: handle.to_string(),
            },
            _ => unknown(),
        },

        "agent.delegate" => ToolCall::AgentDelegate,

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

        "host.write_file" => match (
            args.get("path").and_then(|v| v.as_str()),
            args.get("content").and_then(|v| v.as_str()),
        ) {
            (Some(path), Some(content)) => ToolCall::HostWriteFile {
                path: std::path::PathBuf::from(path),
                content: content.to_string(),
            },
            _ => unknown(),
        },

        "memory.save" => match args.get("text").and_then(|v| v.as_str()) {
            Some(text) => ToolCall::MemorySave {
                text: text.to_string(),
            },
            None => unknown(),
        },

        "memory.search" => match args.get("query").and_then(|v| v.as_str()) {
            Some(query) => ToolCall::MemorySearch {
                query: query.to_string(),
            },
            None => unknown(),
        },

        "memory.forget" => match args.get("id").and_then(|v| v.as_str()) {
            Some(id) => ToolCall::MemoryForget { id: id.to_string() },
            None => unknown(),
        },

        "skill.list" => ToolCall::SkillList,

        "skill.read" => match args.get("name").and_then(|v| v.as_str()) {
            Some(name) => ToolCall::SkillRead {
                name: name.to_string(),
            },
            None => unknown(),
        },

        "host.screenshot" => ToolCall::HostScreenshot {
            display: args
                .get("display")
                .and_then(|v| v.as_u64())
                .map(|n| n as u32),
        },

        "host.click" => match (
            args.get("x").and_then(|v| v.as_i64()),
            args.get("y").and_then(|v| v.as_i64()),
        ) {
            (Some(x), Some(y)) => ToolCall::HostClick {
                x: x as i32,
                y: y as i32,
                button: args
                    .get("button")
                    .and_then(|v| v.as_str())
                    .unwrap_or("left")
                    .to_string(),
            },
            _ => unknown(),
        },

        "host.type_text" => match args.get("text").and_then(|v| v.as_str()) {
            Some(text) => ToolCall::HostType {
                text: text.to_string(),
            },
            None => unknown(),
        },

        // A connected MCP tool. The server metadata comes from the catalog's
        // own record, never from the arguments, so an approval card cannot be
        // steered by what the model passes.
        name if name.starts_with("mcp.") => match catalog.mcp_ref(name) {
            Some(mcp_ref) => ToolCall::Mcp {
                server_id: mcp_ref.server_id.clone(),
                server_name: mcp_ref.server_name.clone(),
                endpoint: mcp_ref.endpoint.clone(),
                tool: mcp_ref.tool.clone(),
                args_preview: compact_json(args, 400),
            },
            None => unknown(),
        },

        _ => unknown(),
    }
}

/// A short one-line rendering of arguments for an approval card.
fn compact_json(value: &serde_json::Value, cap: usize) -> String {
    let text = value.to_string();
    if text.chars().count() <= cap {
        text
    } else {
        let head: String = text.chars().take(cap).collect();
        format!("{head}…")
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
        ToolCall::ArtifactEval { handle } => {
            let script = args.get("script").and_then(|v| v.as_str()).unwrap_or("");
            eval::eval(ctx, handle, script)
        }
        ToolCall::HostExec { argv, cwd } => host::exec(ctx, argv, cwd).await,
        ToolCall::HostReadFile { path } => host::read_file(ctx, path).await,
        ToolCall::HostListDir { path } => host::list_dir(ctx, path).await,
        ToolCall::HostWriteFile { path, content } => host::write_file(ctx, path, content).await,
        ToolCall::HostScreenshot { display } => host::screenshot(ctx, *display).await,
        ToolCall::HostClick { x, y, button } => host::click(ctx, *x, *y, button).await,
        ToolCall::HostType { text } => host::type_text(ctx, text).await,
        ToolCall::MemorySave { text } => {
            let tags = args
                .get("tags")
                .and_then(|v| v.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|item| item.as_str().map(str::to_string))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            memory::save(ctx, text, &tags)
        }
        ToolCall::MemorySearch { query } => {
            let limit = args
                .get("limit")
                .and_then(|v| v.as_u64())
                .unwrap_or(10)
                .clamp(1, 50) as u32;
            memory::search(ctx, query, limit)
        }
        ToolCall::MemoryForget { id } => memory::forget(ctx, id),
        ToolCall::SkillList => skill::list(ctx),
        ToolCall::SkillRead { name } => skill::read(ctx, name),
        ToolCall::Mcp {
            server_id, tool, ..
        } => {
            let arguments = args
                .get("arguments")
                .cloned()
                .unwrap_or_else(|| args.clone());
            match ctx.mcp {
                Some(invoker) => {
                    let result = invoker.call(server_id, tool, &arguments).await?;
                    let (text, is_error) = mcp::result_text(&result);
                    // Large tool results become a handle, like a channel read;
                    // small ones come back inline.
                    let (handle, bytes) =
                        ctx.store.store_text(ctx.session_id, "mcp_result", &text)?;
                    let content = if bytes as usize <= crate::agent::store::INLINE_BYTE_LIMIT {
                        serde_json::json!({ "result": text })
                    } else {
                        serde_json::json!({
                            "bytes": bytes,
                            "note": "결과가 커서 아티팩트로 저장했습니다. artifact.query 로 확인하세요.",
                        })
                    };
                    Ok(ToolOutput {
                        content,
                        artifact: Some(handle),
                        is_error,
                    })
                }
                None => Ok(ToolOutput::error(
                    "이 MCP 서버에 연결되어 있지 않습니다. 설정에서 다시 연결해주세요.",
                )),
            }
        }
        // The host loop runs delegation; if it reaches here the loop did not
        // intercept it, which is a bug, so it is refused rather than ignored.
        ToolCall::AgentDelegate => Ok(ToolOutput::error(
            "agent.delegate 는 호스트 루프가 처리해야 합니다.",
        )),
        // Refused by the policy before it can reach here.
        ToolCall::Unknown { .. } => Err(Error::Other("이 도구는 실행할 수 없습니다.".into())),
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
        ToolCall::ArtifactEval { handle } => serde_json::json!({ "handle": handle }),
        ToolCall::AgentDelegate => serde_json::json!({}),
        ToolCall::HostExec { argv, cwd } => serde_json::json!({
            "argv": argv,
            "cwd": cwd.display().to_string(),
        }),
        ToolCall::HostReadFile { path } | ToolCall::HostListDir { path } => {
            serde_json::json!({ "path": path.display().to_string() })
        }
        ToolCall::HostWriteFile { path, content } => serde_json::json!({
            "path": path.display().to_string(),
            "bytes": content.len(),
        }),
        // The note's text can carry secrets or attacker-planted instructions,
        // so the log keeps its size, not its words — as with a written file.
        ToolCall::MemorySave { text } => serde_json::json!({ "bytes": text.len() }),
        // A search term is the model's own words, not a payload, and it explains
        // why memory was read — kept, like a chat search.
        ToolCall::MemorySearch { query } => serde_json::json!({ "query": query }),
        ToolCall::MemoryForget { id } => serde_json::json!({ "id": id }),
        ToolCall::SkillList => serde_json::json!({}),
        ToolCall::SkillRead { name } => serde_json::json!({ "name": name }),
        ToolCall::HostScreenshot { display } => serde_json::json!({ "display": display }),
        ToolCall::HostClick { x, y, button } => {
            serde_json::json!({ "x": x, "y": y, "button": button })
        }
        // Synthesised keystrokes can be a password; only the size is recorded.
        ToolCall::HostType { text } => serde_json::json!({ "bytes": text.len() }),
        ToolCall::Mcp {
            server_id, tool, ..
        } => serde_json::json!({ "server_id": server_id, "tool": tool }),
        ToolCall::Unknown { name } => serde_json::json!({ "name": name }),
    }
}

/// The three tools gated behind the `screen-control` feature.
fn is_screen_tool(name: &str) -> bool {
    matches!(name, "host.screenshot" | "host.click" | "host.type_text")
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
        pub writes: Mutex<Vec<(std::path::PathBuf, Vec<u8>)>>,
        pub history: Mutex<Vec<ChatLine>>,
        pub exec_stdout: Mutex<String>,
        pub fail_next: Mutex<bool>,
        pub clicks: Mutex<Vec<(i32, i32, String)>>,
        pub typed: Mutex<Vec<String>>,
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

        async fn write_file(&self, path: &std::path::Path, bytes: &[u8]) -> Result<()> {
            self.writes
                .lock()
                .push((path.to_path_buf(), bytes.to_vec()));
            Ok(())
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

        async fn screenshot(&self, _display: Option<u32>) -> Result<Screenshot> {
            Ok(Screenshot {
                png_b64: "iVBORw0KGgo=".into(),
                image_b64: "/9j/4AAQSkZJRg==".into(),
                mime: "image/jpeg".into(),
            })
        }

        async fn click(&self, x: i32, y: i32, button: &str) -> Result<()> {
            self.clicks.lock().push((x, y, button.to_string()));
            Ok(())
        }

        async fn type_text(&self, text: &str) -> Result<()> {
            self.typed.lock().push(text.to_string());
            Ok(())
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
        skills_dir: PathBuf,
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
        let skills_dir = std::env::temp_dir().join(format!(
            "llack-tool-skills-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        Harness {
            store,
            audit_dir,
            skills_dir,
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
                mcp: None,
                workspace_id: Some("01WS"),
                channel_id: Some("01CH"),
                user_id: Some("01ALICE"),
                skills_dir: Some(self.skills_dir.clone()),
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
            std::fs::remove_dir_all(&self.skills_dir).ok();
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

    // ── host.write_file: never automatic, gated like everything else ────

    #[tokio::test]
    async fn a_write_asks_even_inside_a_chosen_root_and_lands_only_after_approval() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.write_file",
                serde_json::json!({ "path": "/home/me/app/README.md", "content": "# 새 문서" }),
            )
            .await;

        assert!(!outcome.output.is_error, "{:?}", outcome.output);
        assert_eq!(outcome.verdict, Verdict::Approved);
        assert_eq!(
            answer.seen.lock().len(),
            1,
            "a write inside a chosen root must still ask"
        );
        let card = &answer.seen.lock()[0];
        assert_eq!(card.facts.title, "이 파일을 씁니다 (있으면 덮어씀)");
        assert!(
            card.facts
                .facts
                .iter()
                .any(|row| row.value.contains("새 문서")),
            "the card must show what is about to land on disk"
        );
        let writes = host.writes.lock();
        assert_eq!(writes.len(), 1);
        assert_eq!(writes[0].0, PathBuf::from("/home/me/app/README.md"));
        assert_eq!(writes[0].1, "# 새 문서".as_bytes());
    }

    #[tokio::test]
    async fn a_denied_write_never_touches_the_disk() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let answer = AutoAnswer::new(false);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.write_file",
                serde_json::json!({ "path": "/home/me/app/README.md", "content": "x" }),
            )
            .await;

        assert!(outcome.output.is_error);
        assert_eq!(outcome.verdict, Verdict::Denied);
        assert!(host.writes.lock().is_empty());
    }

    #[tokio::test]
    async fn a_write_into_credentials_is_refused_before_reaching_the_host() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.write_file",
                serde_json::json!({ "path": "/home/me/.ssh/config", "content": "Host *" }),
            )
            .await;

        assert_eq!(outcome.verdict, Verdict::Refused);
        assert!(host.writes.lock().is_empty());
    }

    #[tokio::test]
    async fn the_audit_log_records_a_write_byte_count_but_not_its_content() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host);
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        h.run(
            &broker,
            &session(),
            "host.write_file",
            serde_json::json!({ "path": "/home/me/app/notes.md", "content": "내부 비밀 메모" }),
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
            "the log must record a byte count, not the file's content"
        );
        assert!(raw.contains("bytes"));
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

    // ── Memory ──────────────────────────────────────────────────────────

    #[tokio::test]
    async fn saving_memory_in_a_clean_session_is_automatic_and_search_finds_it() {
        let h = harness(Arc::new(FakeHost::default()));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        let saved = h
            .run(
                &broker,
                &session(),
                "memory.save",
                serde_json::json!({ "text": "앨리스는 다크 모드를 선호합니다", "tags": ["선호"] }),
            )
            .await;
        assert_eq!(saved.verdict, Verdict::Auto, "a clean save does not ask");
        assert!(!saved.output.is_error);

        let found = h
            .run(
                &broker,
                &session(),
                "memory.search",
                serde_json::json!({ "query": "다크" }),
            )
            .await;
        assert_eq!(found.output.content["count"], 1);
        assert!(!found.taints, "reading one's own memory must not taint");
    }

    #[tokio::test]
    async fn saving_memory_from_a_tainted_session_asks_first() {
        let h = harness(Arc::new(FakeHost::default()));
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let dirty = SessionContext {
            tainted: true,
            ..session()
        };
        let saved = h
            .run(
                &broker,
                &dirty,
                "memory.save",
                serde_json::json!({ "text": "채널에서 읽은 무언가" }),
            )
            .await;
        assert_eq!(saved.verdict, Verdict::Approved);
        assert_eq!(answer.seen.lock().len(), 1, "a tainted save must ask");
        assert_eq!(answer.seen.lock()[0].risk, crate::agent::policy::Risk::High);
    }

    #[tokio::test]
    async fn the_audit_log_keeps_a_memory_size_not_its_words() {
        let h = harness(Arc::new(FakeHost::default()));
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));
        h.run(
            &broker,
            &session(),
            "memory.save",
            serde_json::json!({ "text": "내부 비밀 프로젝트 코드명" }),
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
            "the note itself must not be logged"
        );
        assert!(raw.contains("bytes"));
    }

    // ── Skills ──────────────────────────────────────────────────────────

    #[tokio::test]
    async fn listing_and_reading_skills_is_automatic() {
        let h = harness(Arc::new(FakeHost::default()));
        crate::agent::skills::save(&h.skills_dir, "release", "# 릴리스\n분기 배포 절차\n본문")
            .unwrap();
        let broker = ApprovalBroker::new(Arc::new(SilentNotifier));

        let listed = h
            .run(&broker, &session(), "skill.list", serde_json::json!({}))
            .await;
        assert_eq!(listed.verdict, Verdict::Auto);
        let skills = listed.output.content["skills"].as_array().unwrap();
        assert_eq!(skills.len(), 1);
        assert_eq!(skills[0]["title"], "릴리스");

        let read = h
            .run(
                &broker,
                &session(),
                "skill.read",
                serde_json::json!({ "name": "release" }),
            )
            .await;
        assert!(read.output.content["body"]
            .as_str()
            .unwrap()
            .contains("분기 배포 절차"));
    }

    // ── Screen control: gated by feature and class 3 ────────────────────

    #[test]
    fn screen_tools_appear_only_when_the_feature_is_on() {
        let caps_off = HostCapabilities::desktop();
        let off: Vec<String> = ToolCatalog::builtin()
            .expose(caps_off)
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert!(
            !off.iter().any(|n| is_screen_tool(n)),
            "screen tools must be hidden without the feature: {off:?}"
        );

        let caps_on = HostCapabilities {
            screen_control: true,
            ..HostCapabilities::desktop()
        };
        let on: Vec<String> = ToolCatalog::builtin()
            .expose(caps_on)
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert!(on.iter().any(|n| n == "host.screenshot"));
        assert!(on.iter().any(|n| n == "host.click"));
        assert!(on.iter().any(|n| n == "host.type_text"));
    }

    #[tokio::test]
    async fn an_approved_screenshot_returns_an_inline_image_and_stores_the_png() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host);
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        let outcome = h
            .run(
                &broker,
                &session(),
                "host.screenshot",
                serde_json::json!({}),
            )
            .await;
        assert!(!outcome.output.is_error);
        assert_eq!(answer.seen.lock().len(), 1, "a screenshot must ask");
        assert!(outcome.output.content["image_b64"].is_string());
        let handle = outcome.output.artifact.expect("the PNG must be stored");
        assert!(h.store.artifact(&handle).unwrap().is_some());
    }

    #[tokio::test]
    async fn clicking_and_typing_are_class_three_and_reach_the_host_once_allowed() {
        let host = Arc::new(FakeHost::default());
        let h = harness(host.clone());
        let answer = AutoAnswer::new(true);
        let broker = Arc::new(ApprovalBroker::new(answer.clone()));
        *answer.broker.lock() = Some(broker.clone());

        h.run(
            &broker,
            &session(),
            "host.click",
            serde_json::json!({ "x": 10, "y": 20, "button": "left" }),
        )
        .await;
        h.run(
            &broker,
            &session(),
            "host.type_text",
            serde_json::json!({ "text": "hi" }),
        )
        .await;

        assert_eq!(host.clicks.lock()[0], (10, 20, "left".to_string()));
        assert_eq!(host.typed.lock()[0], "hi");
        assert!(
            answer
                .seen
                .lock()
                .iter()
                .all(|r| r.risk == crate::agent::policy::Risk::High),
            "input synthesis is always class 3"
        );
    }
}
