/**
 * One turn, from the user's message to the last token.
 *
 * The SDK's `toolRunner` owns the loop: request, tool calls, tool results,
 * request again, until the model stops. What this file adds is the three things
 * the SDK cannot know about:
 *
 * 1. **Every tool routes through Rust.** The `run` of each runnable tool calls
 *    `agentToolCall`, which is the only door — policy, audit and approval all
 *    happen behind it. No tool has a JavaScript implementation, so there is no
 *    tool a webview compromise could execute directly.
 * 2. **Streaming lands in the store.** Text, thinking and tool cards are pushed
 *    as they arrive, which is why the panel shows a turn being written rather
 *    than a spinner and then a wall.
 * 3. **A refusal continues the conversation.** A denied tool comes back as a
 *    tool result, not an exception, so the model can say "I could not do that,
 *    shall I try X" instead of the turn dying.
 */

import type Anthropic from "@anthropic-ai/sdk";
import type { BetaRunnableTool } from "@anthropic-ai/sdk/lib/tools/BetaRunnableTool";
import type { BetaTool } from "@anthropic-ai/sdk/resources/beta";

import type {
  AgentToolResult,
  AgentToolRun,
  AgentToolSpec,
  AgentVerdict,
} from "@/lib/agent/types";
import { asCommandError } from "@/lib/errors";
import { agentHost } from "@/lib/ipc";
import { useAgent } from "@/store/agent";

import type { ProviderAdapter } from "./anthropic";

/**
 * Wrap one Rust tool as a runnable the SDK can call.
 *
 * `parse` is the identity on purpose. The schema is enforced in Rust — a call
 * whose arguments do not fit becomes `ToolCall::Unknown`, which the policy
 * refuses — and a second validation here would only be able to reject things
 * Rust would have rejected anyway, while giving a false impression of where the
 * check lives.
 */
function runnable(
  spec: AgentToolSpec,
  sessionId: string,
  turnId: string,
): BetaRunnableTool {
  return {
    name: spec.name,
    description: spec.description,
    input_schema: spec.input_schema as BetaTool["input_schema"],
    parse: (input: unknown) => input,
    run: async (args: unknown, context) => {
      const store = useAgent.getState();
      const runId =
        (context?.toolUse as { id?: string } | undefined)?.id ??
        `${turnId}-${spec.name}-${Date.now()}`;

      store.startToolRun(turnId, {
        id: runId,
        name: spec.name,
        args: (args ?? {}) as Record<string, unknown>,
        state: "running",
        artifact: null,
        summary: null,
      });

      let result: AgentToolResult;
      try {
        result = await agentHost.agentToolCall(sessionId, spec.name, args);
      } catch (error) {
        // A rejected command means the call did not reach the gate at all —
        // no session, no agent, a malformed argument. It becomes a tool
        // *result* so the model is told and the turn survives.
        const envelope = asCommandError(error);
        store.finishToolRun(turnId, runId, {
          state: stateFor(envelope.code),
          summary: envelope.message,
        });
        return JSON.stringify({ error: envelope.message });
      }

      if (result.taints) store.markTainted();

      store.finishToolRun(turnId, runId, {
        // The verdict, not `is_error`. A call the user declined is not a
        // failure, and painting it as one reads as the agent being broken
        // rather than as it doing what it was told.
        state: stateFromVerdict(result.verdict, result.is_error),
        artifact: result.artifact,
        summary: summarise(result),
      });

      // A successful `chat.post_message` is the one thing an agent turn can do
      // that the transcript beside it must notice.
      if (spec.name === "chat.post_message" && !result.is_error) {
        const channelId = (args as { channel_id?: string } | null)?.channel_id;
        if (channelId) store.notePostedMessage(channelId);
      }

      return JSON.stringify(result.content);
    },
  };
}

/** How a card should render, given what the gate decided. */
function stateFromVerdict(
  verdict: AgentVerdict,
  isError: boolean,
): AgentToolRun["state"] {
  switch (verdict) {
    case "denied":
    case "expired":
    case "cancelled":
      // All three are "no answer to act on". Grouped because the distinction
      // matters to the audit log, not to a card in a transcript.
      return "denied";
    case "refused":
      return "refused";
    default:
      return isError ? "error" : "ok";
  }
}

/** How a card should render when the command itself rejected. */
function stateFor(code: string): AgentToolRun["state"] {
  if (code.startsWith("approval_")) return "denied";
  if (code === "policy_refused") return "refused";
  return "error";
}

/** A one-line description of a tool result for the card. */
function summarise(result: AgentToolResult): string | null {
  const content = result.content;
  if (content && typeof content === "object") {
    const record = content as Record<string, unknown>;
    if (typeof record.error === "string") return record.error;
    if (typeof record.message_count === "number") {
      return `${record.message_count}건`;
    }
    if (typeof record.total_lines === "number") {
      return `${record.total_lines}줄`;
    }
    if (typeof record.exit_code === "number") {
      return `종료 코드 ${record.exit_code}`;
    }
  }
  return null;
}

export interface RunTurnOptions {
  adapter: ProviderAdapter;
  sessionId: string;
  /** The assistant turn to stream into, from `useAgent.submit`. */
  turnId: string;
  /** The conversation so far, including the message just submitted. */
  messages: Anthropic.Beta.Messages.BetaMessageParam[];
  tools: AgentToolSpec[];
  signal: AbortSignal;
}

/**
 * Run one turn to completion, streaming into the store.
 *
 * Returns the messages to keep for the next turn — the SDK's own view of the
 * conversation, which already contains the assistant blocks and the tool
 * results in the shape the API wants. Rebuilding that from the store's render
 * model would drift, and the first symptom would be a silently broken cache
 * prefix.
 */
export async function runTurn(
  options: RunTurnOptions,
): Promise<Anthropic.Beta.Messages.BetaMessageParam[]> {
  const { adapter, sessionId, turnId, messages, tools, signal } = options;
  const store = useAgent.getState();

  const runner = adapter.client.beta.messages.toolRunner(
    adapter.turnParams(
      messages,
      tools.map((spec) => runnable(spec, sessionId, turnId)),
    ),
    { signal },
  );

  try {
    for await (const stream of runner) {
      // `stream` is a `BetaMessageStream` because `turnParams` sets
      // `stream: true`. Each iteration is one request/response in the loop.
      stream.on("text", (delta: string) => {
        store.appendText(turnId, delta);
      });
      stream.on("thinking", (delta: string) => {
        store.appendThinking(turnId, delta);
      });

      const message = await stream.finalMessage();

      // Checked before reading `content`: a refusal has no usable content, and
      // treating it as an empty answer would show the user a blank turn.
      if (message.stop_reason === "refusal") {
        store.finishTurn(
          turnId,
          "모델이 이 요청에 응답하지 않았습니다. 다르게 물어봐 주세요.",
        );
        return runner.params.messages as Anthropic.Beta.Messages.BetaMessageParam[];
      }
      if (message.stop_reason === "max_tokens") {
        store.setBanner("답변이 길이 제한에 걸려 중간에 멈췄습니다.");
      }
    }

    store.finishTurn(turnId);
  } catch (error) {
    if (signal.aborted) {
      // The user pressed stop. Not an error, and not a banner.
      store.finishTurn(turnId);
    } else {
      store.finishTurn(
        turnId,
        error instanceof Error ? error.message : "턴을 완료하지 못했습니다.",
      );
    }
  }

  return runner.params.messages as Anthropic.Beta.Messages.BetaMessageParam[];
}
