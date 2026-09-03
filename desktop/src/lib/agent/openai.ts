/**
 * The second provider: any OpenAI-compatible Chat Completions endpoint.
 *
 * There is no SDK here on purpose. The Anthropic loop leans on the official
 * SDK's tool runner; OpenAI-compatible gateways (OpenAI, Azure, OpenRouter,
 * vLLM, Ollama) differ just enough that a hand-rolled SSE reader over the
 * same `ipcFetch` is smaller and more honest than a second SDK. Everything
 * security-relevant is unchanged: the key never leaves Rust (the byte proxy
 * injects `Authorization`), and every tool call still goes through
 * `agent_tool_call` — the gate does not know or care which model asked.
 */

import type { AgentToolSpec } from "@/lib/agent/types";
import { useAgent } from "@/store/agent";

import { executeTool } from "./loop";
import { createIpcFetch } from "./ipcFetch";
import { AGENT_SYSTEM_PROMPT } from "./anthropic";

/** OpenAI wire shapes — only what the loop touches. */
export type OpenAiMessage =
  | { role: "system" | "user"; content: string }
  | {
      role: "assistant";
      content: string | null;
      tool_calls?: Array<{
        id: string;
        type: "function";
        function: { name: string; arguments: string };
      }>;
    }
  | { role: "tool"; tool_call_id: string; content: string };

export interface OpenAiTurnOptions {
  model: string;
  baseUrl: string;
  sessionId: string;
  turnId: string;
  messages: OpenAiMessage[];
  tools: AgentToolSpec[];
  signal: AbortSignal;
  system?: string;
  /** Loop ceiling; the Anthropic side uses 24 as well. */
  maxIterations?: number;
}

interface StreamedCall {
  id: string;
  name: string;
  arguments: string;
}

/** Tool names must match `^[a-zA-Z0-9_-]{1,64}$` on this API; ours have dots. */
function wireName(name: string): string {
  return name.replace(/\./g, "__");
}
function ourName(wire: string): string {
  return wire.replace(/__/g, ".");
}

/**
 * Run one turn against an OpenAI-compatible endpoint, streaming into the
 * store. Returns the messages to keep for the next turn.
 */
export async function runOpenAiTurn(options: OpenAiTurnOptions): Promise<OpenAiMessage[]> {
  const { model, sessionId, turnId, tools, signal } = options;
  const store = useAgent.getState();
  const fetch = createIpcFetch();
  const base = options.baseUrl.replace(/\/+$/, "");
  const endpoint = `${base}/v1/chat/completions`;

  let messages: OpenAiMessage[] = options.messages;
  if (!messages.some((message) => message.role === "system")) {
    messages = [{ role: "system", content: options.system ?? AGENT_SYSTEM_PROMPT }, ...messages];
  }

  const wireTools = tools.map((spec) => ({
    type: "function" as const,
    function: {
      name: wireName(spec.name),
      description: spec.description,
      parameters: spec.input_schema,
    },
  }));

  const ceiling = options.maxIterations ?? 24;
  try {
    for (let iteration = 0; iteration < ceiling; iteration += 1) {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify({
          model,
          stream: true,
          messages,
          tools: wireTools.length > 0 ? wireTools : undefined,
          tool_choice: wireTools.length > 0 ? "auto" : undefined,
        }),
        signal,
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(describeFailure(response.status, text));
      }

      const { text, calls, finish } = await readStream(response, (delta) =>
        store.appendText(turnId, delta),
      );

      const assistant: OpenAiMessage = {
        role: "assistant",
        content: text || null,
        ...(calls.length > 0
          ? {
              tool_calls: calls.map((call) => ({
                id: call.id,
                type: "function" as const,
                function: { name: call.name, arguments: call.arguments || "{}" },
              })),
            }
          : {}),
      };
      messages = [...messages, assistant];

      if (finish === "length") {
        store.setBanner("답변이 길이 제한에 걸려 중간에 멈췼습니다.");
      }
      if (calls.length === 0) break;

      // Tool calls run one at a time, through the gate, like the other loop.
      for (const call of calls) {
        let args: unknown = {};
        try {
          args = call.arguments ? JSON.parse(call.arguments) : {};
        } catch {
          messages = [
            ...messages,
            { role: "tool", tool_call_id: call.id, content: JSON.stringify({ error: "인수 JSON 이 잘못되었습니다." }) },
          ];
          continue;
        }
        const spec = tools.find((candidate) => wireName(candidate.name) === call.name || candidate.name === ourName(call.name));
        const result = spec
          ? await executeTool(spec, sessionId, turnId, args, call.id)
          : JSON.stringify({ error: `알 수 없는 도구: ${call.name}` });
        messages = [...messages, { role: "tool", tool_call_id: call.id, content: result }];
      }
    }
    store.finishTurn(turnId);
  } catch (error) {
    if (signal.aborted) {
      store.finishTurn(turnId);
    } else {
      store.finishTurn(turnId, error instanceof Error ? error.message : "턴을 완료하지 못했습니다.");
    }
  }
  return messages;
}

function describeFailure(status: number, body: string): string {
  let detail = "";
  try {
    const parsed = JSON.parse(body) as { error?: { message?: string } };
    detail = parsed.error?.message ?? "";
  } catch {
    detail = body.slice(0, 200);
  }
  const prefix =
    status === 401
      ? "API 키가 거부되었습니다."
      : status === 429
        ? "요청 한도에 걸렸습니다."
        : status >= 500
          ? "프로바이더 서버 오류입니다."
          : `요청이 실패했습니다 (HTTP ${status}).`;
  return detail ? `${prefix} ${detail}` : prefix;
}

/**
 * Read a Chat Completions SSE stream: text deltas go to `onText`, tool-call
 * fragments are accumulated by index (arguments arrive as partial JSON).
 */
async function readStream(
  response: Response,
  onText: (delta: string) => void,
): Promise<{ text: string; calls: StreamedCall[]; finish: string | null }> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("응답 본문이 없습니다.");
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  let finish: string | null = null;
  const calls = new Map<number, StreamedCall>();

  const handle = (payload: string) => {
    if (payload === "[DONE]") return;
    let chunk: {
      choices?: Array<{
        delta?: {
          content?: string | null;
          tool_calls?: Array<{
            index: number;
            id?: string;
            function?: { name?: string; arguments?: string };
          }>;
        };
        finish_reason?: string | null;
      }>;
    };
    try {
      chunk = JSON.parse(payload);
    } catch {
      return;
    }
    const choice = chunk.choices?.[0];
    if (!choice) return;
    if (choice.delta?.content) {
      text += choice.delta.content;
      onText(choice.delta.content);
    }
    for (const fragment of choice.delta?.tool_calls ?? []) {
      const existing = calls.get(fragment.index) ?? { id: "", name: "", arguments: "" };
      if (fragment.id) existing.id = fragment.id;
      if (fragment.function?.name) existing.name += fragment.function.name;
      if (fragment.function?.arguments) existing.arguments += fragment.function.arguments;
      calls.set(fragment.index, existing);
    }
    if (choice.finish_reason) finish = choice.finish_reason;
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of event.split("\n")) {
        if (line.startsWith("data:")) handle(line.slice(5).trim());
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
  // A final event without the trailing blank line.
  for (const line of buffer.split("\n")) {
    if (line.startsWith("data:")) handle(line.slice(5).trim());
  }

  const ordered = [...calls.entries()].sort((a, b) => a[0] - b[0]).map(([, call], index) => ({
    ...call,
    id: call.id || `call_${index}`,
  }));
  return { text, calls: ordered, finish };
}
