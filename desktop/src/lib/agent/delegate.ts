/**
 * `agent.delegate` — a sub-agent turn.
 *
 * The model hands off a task; a nested turn runs with a *narrower* tool set
 * and a step ceiling, its transcript stays out of the panel, and what comes
 * back is a summary plus an artifact handle holding the full text. The parent
 * context grows by one tool result instead of by the whole investigation.
 *
 * Rust registers the tool spec and refuses to execute it itself; the loop
 * that owns the provider connection is the only place a nested model call can
 * happen. The gate is unchanged: every tool the sub-agent calls still goes
 * through `agent_tool_call`, with the same approvals and the same taint.
 */

import type { AgentToolSpec } from "@/lib/agent/types";
import { agentHost } from "@/lib/ipc";

export interface DelegateArgs {
  task: string;
  tools?: string[];
  max_steps?: number;
}

/** What the driver knows and the loop does not: how to run a turn. */
export type SubTurnRunner = (input: {
  task: string;
  tools: AgentToolSpec[];
  maxSteps: number;
  turnId: string;
}) => Promise<string>;

let runner: SubTurnRunner | null = null;
let depth = 0;
const MAX_DEPTH = 2;
const SUMMARY_CHARS = 1800;

/** The active driver installs the runner for its provider; one at a time. */
export function setSubTurnRunner(next: SubTurnRunner | null): void {
  runner = next;
}

/** Never hand the sub-agent something the parent could not do itself. */
export function delegateToolset(all: AgentToolSpec[], requested?: string[]): AgentToolSpec[] {
  const base = all.filter(
    (spec) =>
      spec.name !== "agent.delegate" &&
      spec.name !== "chat.post_message" &&
      spec.name !== "host.exec" &&
      spec.name !== "host.write_file",
  );
  if (!requested || requested.length === 0) return base;
  const wanted = new Set(requested);
  return base.filter((spec) => wanted.has(spec.name));
}

export async function runDelegate(
  sessionId: string,
  all: AgentToolSpec[],
  rawArgs: unknown,
): Promise<{ content: unknown; artifact: string | null; isError: boolean }> {
  const args = (rawArgs ?? {}) as Partial<DelegateArgs>;
  const task = typeof args.task === "string" ? args.task.trim() : "";
  if (!task) return { content: { error: "task 가 비어 있습니다." }, artifact: null, isError: true };
  if (!runner) {
    return { content: { error: "이 호스트에서는 하위 작업을 실행할 수 없습니다." }, artifact: null, isError: true };
  }
  if (depth >= MAX_DEPTH) {
    return { content: { error: `하위 작업은 ${MAX_DEPTH}단계까지만 중첩됩니다.` }, artifact: null, isError: true };
  }

  const tools = delegateToolset(all, Array.isArray(args.tools) ? args.tools.filter((t) => typeof t === "string") : undefined);
  const maxSteps = Math.max(1, Math.min(12, Number(args.max_steps) || 8));
  const turnId = `sub-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  depth += 1;
  try {
    const text = await runner({ task, tools, maxSteps, turnId });
    const trimmed = text.trim();
    let artifact: string | null = null;
    try {
      const put = await agentHost.agentArtifactPut(sessionId, `delegate: ${task.slice(0, 60)}`, trimmed);
      artifact = put.handle;
    } catch {
      // Without a handle the summary still answers; the full text is lost.
    }
    const summary = trimmed.length > SUMMARY_CHARS ? `${trimmed.slice(0, SUMMARY_CHARS)}…` : trimmed;
    return {
      content: { summary, artifact, full_length: trimmed.length, steps_limit: maxSteps, tools: tools.map((t) => t.name) },
      artifact,
      isError: false,
    };
  } catch (error) {
    return {
      content: { error: error instanceof Error ? error.message : "하위 작업이 실패했습니다." },
      artifact: null,
      isError: true,
    };
  } finally {
    depth -= 1;
  }
}
