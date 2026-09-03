//! The agent: a panel that can read this workspace and act on this machine.
//!
//! ## Where the pieces live, and why
//!
//! The conversation loop is **not** here — it runs in the webview against the
//! official Anthropic SDK. What lives in Rust is everything the webview must
//! not be trusted with:
//!
//! - the provider credential, which stays in the OS keychain and is attached
//!   to outbound requests by a byte proxy the webview cannot read;
//! - [`policy`], which decides what the agent may do;
//! - the approval broker, the audit log, and the tool executors.
//!
//! That split is deliberate. Rust has no official Anthropic SDK, so putting
//! the loop here would mean owning SSE parsing and every future API change
//! forever — for no security gain, because the key is equally absent from the
//! webview either way. Meanwhile the gate has to be somewhere the webview
//! cannot reach, and that can only be here.
//!
//! ## The one rule that keeps it honest
//!
//! `tools::execute` is the only public way to run a tool. It calls
//! [`policy::classify`], then the audit log, then a private executor. A
//! contributor adding a tool cannot forget the gate, because there is no
//! reachable path around it.

pub mod approval;
pub mod audit;
pub mod credential;
pub mod engine;
pub mod mcp;
pub mod policy;
pub mod provider;
pub mod skills;
pub mod store;
pub mod tools;

pub use approval::{ApprovalBroker, ApprovalNotifier, ApprovalRequest, Outcome, SilentNotifier};
pub use audit::{
    AuditActor, AuditEntriesView, AuditEntry, AuditLog, DecisionSource, Phase, Verdict,
};
pub use engine::{AgentEngine, ProviderStatus, DEFAULT_MODEL, DEFAULT_PROVIDER};
pub use mcp::{McpServer, McpServerView, Transport as McpTransport};
pub use policy::{
    ApprovalFacts, Decision, Fact, Grain, Risk, SessionContext, ToolCall, AUTO_READ_BYTE_CAP,
};
pub use skills::AgentSkill;
pub use store::{
    AgentMemory, AgentMessage, AgentSession, AgentStore, Artifact, ArtifactOp, ArtifactPreview,
    ArtifactSlice, ProviderSettings, INLINE_BYTE_LIMIT,
};
pub use tools::{
    ChatLine, ExecOutput, HostCapabilities, McpInvoker, ToolCatalog, ToolContext, ToolHost,
    ToolOutput, ToolSource, ToolSpec,
};
