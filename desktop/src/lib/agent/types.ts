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
}

/** What the provider connection looks like, minus the secret. */
export interface AgentProviderStatus {
  connected: boolean;
  provider_id: string;
  model: string;
  /** Last four characters of the key, for display. Never the key. */
  key_fingerprint: string | null;
  last_error: string | null;
}

/** One stored conversation. Mirrors `store::AgentSession`. */
export interface AgentSessionSummary {
  id: string;
  title: string | null;
  model: string;
  created_at_ms: number;
  last_active_at_ms: number;
}

/** A tool as the panel renders it — metadata the UI does not interpret. */
export interface AgentToolSpec {
  name: string;
  description: string;
}

/**
 * What a tool call looks like in the transcript.
 *
 * `artifact` is the RLM seam surfacing in the UI: a card can say "400 messages"
 * and offer to show a slice, rather than dumping the value into the panel.
 */
export interface AgentToolRun {
  id: string;
  name: string;
  /** Redacted args as the audit log records them — never a payload. */
  args: Record<string, unknown>;
  state: "running" | "ok" | "error" | "denied" | "refused";
  artifact: string | null;
  summary: string | null;
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
