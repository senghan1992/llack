/**
 * One conversation, driven.
 *
 * The panel calls `send` and `stop`; everything else — the provider client, the
 * message history, the abort controller — lives here. Two reasons that split is
 * worth a file:
 *
 * 1. **Message history is not render state.** The store holds blocks shaped for
 *    the screen; the driver holds `BetaMessageParam[]` shaped for the API,
 *    which is what the SDK hands back after each turn. Deriving one from the
 *    other would drift, and the first symptom would be a silently broken prompt
 *    cache prefix — expensive and invisible.
 * 2. **The browser needs the same surface.** There is no keychain and no Rust
 *    in a browser tab, so the panel there is driven by a scripted fake. Both
 *    implementations satisfy the same interface and the panel cannot tell them
 *    apart, which is what makes the CDP pass meaningful evidence about the real
 *    panel rather than about a demo mode.
 */

import type Anthropic from "@anthropic-ai/sdk";

import type { AgentToolSpec } from "@/lib/agent/types";
import { agentHost, capabilities } from "@/lib/ipc";
import { useAgent } from "@/store/agent";

export interface TurnDriver {
  /** Add the user's message and run a turn to completion. */
  send(text: string): Promise<void>;
  /** Abandon the turn in flight. Idempotent. */
  stop(): void;
}

/** The real driver: SDK loop, byte proxy, Rust-gated tools. */
class ModelDriver implements TurnDriver {
  private messages: Anthropic.Beta.Messages.BetaMessageParam[] = [];
  private tools: AgentToolSpec[] | null = null;
  private abort: AbortController | null = null;

  constructor(
    private readonly sessionId: string,
    private readonly model: string,
  ) {}

  async send(text: string): Promise<void> {
    const store = useAgent.getState();
    // Imported lazily so the SDK — the largest dependency in the bundle — is
    // not in the initial chunk. A user who never opens the agent never
    // downloads it.
    const [{ anthropicAdapter }, { runTurn }] = await Promise.all([
      import("./anthropic"),
      import("./loop"),
    ]);

    if (!this.tools) this.tools = await agentHost.agentTools();

    const turnId = store.submit(text);
    this.messages = [...this.messages, { role: "user", content: text }];
    this.abort = new AbortController();

    try {
      this.messages = await runTurn({
        adapter: anthropicAdapter(this.model),
        sessionId: this.sessionId,
        turnId,
        messages: this.messages,
        tools: this.tools,
        signal: this.abort.signal,
      });
    } finally {
      this.abort = null;
    }
  }

  stop(): void {
    this.abort?.abort();
    // Two halves, because they stop different things: the controller stops the
    // HTTP stream, and `agentCancel` denies any approval still on screen. A
    // stop that left a prompt open would let a click a minute later run a
    // command for a turn the user already abandoned.
    void agentHost.agentCancel(this.sessionId).catch(() => {});
  }
}

/**
 * The browser driver.
 *
 * Not a mock of the model — a scripted stand-in that exercises the panel's real
 * code paths: it streams token by token into the same store actions, opens a
 * real tool card through the same `agentToolCall`, and honours stop. What it
 * cannot do is think, and it says so rather than pretending.
 */
class ScriptedDriver implements TurnDriver {
  private stopped = false;

  constructor(private readonly sessionId: string) {}

  async send(text: string): Promise<void> {
    const store = useAgent.getState();
    const turnId = store.submit(text);
    this.stopped = false;

    // A tool card, so the panel's tool rendering is exercised here too.
    const runId = `${turnId}-fake`;
    store.startToolRun(turnId, {
      id: runId,
      name: "chat.read_channel",
      args: { channel_id: "(현재 채널)" },
      state: "running",
      artifact: null,
      summary: null,
    });
    try {
      const result = await agentHost.agentToolCall(
        this.sessionId,
        "chat.read_channel",
        { channel_id: "current" },
      );
      if (result.taints) store.markTainted();
      store.finishToolRun(turnId, runId, {
        state: result.is_error ? "error" : "ok",
        artifact: result.artifact,
        summary: "브라우저 모드의 가짜 결과",
      });
    } catch {
      store.finishToolRun(turnId, runId, { state: "refused" });
    }

    const answer =
      "브라우저 모드에서는 모델에 연결하지 않습니다. 프로바이더 키는 OS 키체인에 저장되고, 요청은 데스크톱 앱의 Rust 프록시를 거치기 때문입니다.\n\n이 화면은 데스크톱 앱과 같은 컴포넌트·같은 스토어·같은 도구 경로를 사용합니다. 실제 모델 응답만 이 자리에 들어옵니다.";

    for (const chunk of answer.match(/[\s\S]{1,6}/g) ?? []) {
      if (this.stopped) break;
      store.appendText(turnId, chunk);
      await new Promise((resolve) => setTimeout(resolve, 14));
    }
    store.finishTurn(turnId);
  }

  stop(): void {
    this.stopped = true;
  }
}

/**
 * Build the driver for this host.
 *
 * `computerControl` is the discriminator because it is exactly the thing that
 * differs: a host that can run programs is a host with a keychain and a byte
 * proxy. Testing for "am I in a browser" separately would be a second source of
 * truth for the same fact.
 */
export function createDriver(sessionId: string, model: string): TurnDriver {
  return capabilities.computerControl
    ? new ModelDriver(sessionId, model)
    : new ScriptedDriver(sessionId);
}
