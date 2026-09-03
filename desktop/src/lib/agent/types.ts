/**
 * The agent's shared shapes.
 *
 * These mirror the Rust side in `desktop/core/src/agent/`. They are
 * hand-maintained rather than generated, so a change in Rust produces one
 * compile error here rather than silent runtime drift — the same bargain the
 * rest of `lib/types.ts` makes.
 */

/** How much friction an approval carries. Mirrors `policy::Risk`. */
export type AgentRisk = "moderate" | "high";

/**
 * A label/value pair the approval card renders as authoritative.
 *
 * Computed in Rust from the tool call. Never from anything the model wrote —
 * see `rationale` below for why that distinction is load-bearing.
 */
export interface AgentFact {
  label: string;
  value: string;
}

export interface AgentApprovalFacts {
  title: string;
  facts: AgentFact[];
}

/** Mirrors `approval::ApprovalRequest`. */
export interface AgentApprovalRequest {
  id: string;
  /** Single-use. Required to answer, and never reused. */
  nonce: string;
  session_id: string;
  tool: string;
  risk: AgentRisk;
  facts: AgentApprovalFacts;
  /**
   * The model's own words. Untrusted: whoever can write a channel message the
   * agent read can write this string, so the card shows it subordinate to
   * `facts` and labelled as unreliable.
   */
  rationale: string | null;
  remembering_offered: boolean;
  /**
   * True when this approval is being answered in a native OS dialog (class-3
   * calls, when the setting is on). The in-app card then shows a waiting state
   * with disabled buttons — the webview cannot resolve the request, only the
   * dialog can.
   */
  native?: boolean;
}

/** What the provider connection looks like, minus the secret. */
export interface AgentProviderStatus {
  connected: boolean;
  /** "anthropic" | "openai" (OpenAI-compatible) | "fake" in the browser. */
  provider_id: string;
  model: string;
  /** Last four characters of the key, for display. Never the key. */
  key_fingerprint: string | null;
  last_error: string | null;
  /** OpenAI-compatible gateways: the base the byte proxy allows. */
  base_url?: string | null;
}

/** An MCP server as Rust lists it — never its credential. */
export interface McpServerView {
  id: string;
  name: string;
  transport: "http" | "stdio";
  url?: string | null;
  command?: string | null;
  args?: string[];
  enabled: boolean;
  tool_count: number;
  /** Epoch ms of the last successful handshake, or null. */
  last_ok_at_ms?: number | null;
  last_error?: string | null;
  has_credential: boolean;
}

export interface AgentMemory {
  id: string;
  text: string;
  tags: string[];
  created_at?: number | string | null;
  last_used_at?: number | string | null;
}

export interface AgentSkill {
  name: string;
  title: string;
  description: string;
  bytes: number;
}

export interface AgentAuditEntries {
  dates: string[];
  entries: Array<Record<string, unknown>>;
  verified: boolean;
}

/** One stored conversation. Mirrors `store::AgentSession`. */
export interface AgentSessionSummary {
  id: string;
  title: string | null;
  model: string;
  created_at_ms: number;
  last_active_at_ms: number;
}

/**
 * A tool as Rust advertises it. Mirrors `tools::ToolSpec`.
 *
 * The schema is generated in Rust and passed through untouched — the loop does
 * not validate against it and neither does the UI. Rust is where a call that
 * does not fit becomes a refusal, and a second validation in the webview would
 * suggest the check lives here.
 */
export interface AgentToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

/**
 * What a tool call looks like in the transcript.
 *
 * `artifact` is the RLM seam surfacing in the UI: a card can say "400 messages"
 * and offer to show a slice, rather than dumping the value into the panel.
 */
/** What the gate decided about a call. Mirrors `audit::Verdict`. */
export type AgentVerdict =
  | "auto"
  | "approved"
  | "denied"
  | "refused"
  | "expired"
  | "cancelled";

/** What `agent_tool_call` resolves with. Mirrors `ToolCallResult`. */
export interface AgentToolResult {
  content: unknown;
  artifact: string | null;
  is_error: boolean;
  taints: boolean;
  verdict: AgentVerdict;
}

export interface AgentToolRun {
  id: string;
  name: string;
  /** Redacted args as the audit log records them — never a payload. */
  args: Record<string, unknown>;
  state: "running" | "ok" | "error" | "denied" | "refused";
  artifact: string | null;
  summary: string | null;
  /** A screenshot the tool returned for the model, shown in the card too. */
  image?: string | null;
}

/** One turn's worth of rendered content in the panel. */
export type AgentBlock =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "tool"; run: AgentToolRun };

export interface AgentTurn {
  id: string;
  role: "user" | "assistant";
  blocks: AgentBlock[];
  /** Set while the assistant turn is still streaming. */
  streaming: boolean;
  error: string | null;
}

/**
 * Events the shell pushes at the panel. Mirrors what `agent_commands.rs`
 * emits on `llack://agent`.
 */
export type AgentEvent =
  | { kind: "session_started"; session_id: string }
  | { kind: "approval_pending"; request: AgentApprovalRequest }
  | { kind: "approval_closed"; request_id: string }
  | { kind: "provider_changed"; status: AgentProviderStatus };
