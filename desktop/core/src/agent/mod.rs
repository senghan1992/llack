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
pub mod policy;
pub mod store;
pub mod tools;

pub use approval::{
    ApprovalBroker, ApprovalNotifier, ApprovalRequest, Outcome, SilentNotifier,
};
pub use audit::{AuditActor, AuditEntry, AuditLog, DecisionSource, Phase, Verdict};
pub use tools::{
    ChatLine, ExecOutput, HostCapabilities, ToolCatalog, ToolContext, ToolHost, ToolOutput,
    ToolSource, ToolSpec,
};
pub use store::{
    AgentMessage, AgentSession, AgentStore, Artifact, ArtifactOp, ArtifactPreview, ArtifactSlice,
    ProviderSettings, INLINE_BYTE_LIMIT,
};
pub use policy::{
    ApprovalFacts, Decision, Fact, Grain, Risk, SessionContext, ToolCall, AUTO_READ_BYTE_CAP,
};
