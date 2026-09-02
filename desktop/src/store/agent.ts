/**
 * The agent panel's own store.
 *
 * Deliberately separate from `store/app.ts`, against that file's stated
 * preference for one store. The reason is measurable rather than aesthetic:
 * streaming deltas arrive at token rate and touch none of the chat slices, so
 * routing them through `useApp` would re-render every channel subscriber on
 * every token. There is exactly one crossing back the other way — a successful
 * `chat.post_message` refreshes the channel — and it is written out explicitly
 * below rather than left implicit.
 */

import { create } from "zustand";

import type {
  AgentApprovalRequest,
  AgentBlock,
  AgentProviderStatus,
  AgentSessionSummary,
  AgentToolRun,
  AgentTurn,
} from "@/lib/agent/types";
import { useApp } from "@/store/app";

/** What the panel is doing right now. */
export type AgentPhase = "idle" | "streaming" | "awaiting_approval";

interface AgentState {
  open: boolean;
  phase: AgentPhase;
  sessionId: string | null;
  sessions: AgentSessionSummary[];
  turns: AgentTurn[];
  /**
   * At most one request is shown at a time. The broker may have several open,
   * but stacking approval cards is how people click the wrong one.
   */
  pending: AgentApprovalRequest | null;
  provider: AgentProviderStatus | null;
  /** Whether this host can run programs — false in a browser tab. */
  computerControl: boolean;
  banner: string | null;
  /**
   * True once channel content has entered this session's context. Shown in the
   * panel, because the user should be able to see why the agent started asking
   * more often.
   */
  tainted: boolean;
}

interface AgentActions {
  setOpen: (open: boolean) => void;
  setProvider: (status: AgentProviderStatus | null) => void;
  setComputerControl: (available: boolean) => void;
  setSessions: (sessions: AgentSessionSummary[]) => void;
  startSession: (sessionId: string) => void;

  /** Add the user's message and an empty assistant turn to stream into. */
  submit: (text: string) => string;
  appendText: (turnId: string, delta: string) => void;
  appendThinking: (turnId: string, delta: string) => void;
  startToolRun: (turnId: string, run: AgentToolRun) => void;
  finishToolRun: (turnId: string, runId: string, patch: Partial<AgentToolRun>) => void;
  finishTurn: (turnId: string, error?: string | null) => void;

  showApproval: (request: AgentApprovalRequest) => void;
  clearApproval: (requestId?: string) => void;

  setBanner: (message: string | null) => void;
  markTainted: () => void;
  reset: () => void;

  /** The one crossing into the chat store. */
  notePostedMessage: (channelId: string) => void;
}

export type AgentStore = AgentState & AgentActions;

const EMPTY: AgentState = {
  open: false,
  phase: "idle",
  sessionId: null,
  sessions: [],
  turns: [],
  pending: null,
  provider: null,
  computerControl: false,
  banner: null,
  tainted: false,
};

let turnCounter = 0;

function nextTurnId(): string {
  turnCounter += 1;
  return `turn-${Date.now()}-${turnCounter}`;
}

/** Replace one turn, leaving the rest of the array identity-stable. */
function patchTurn(
  turns: AgentTurn[],
  turnId: string,
  update: (turn: AgentTurn) => AgentTurn,
): AgentTurn[] {
  return turns.map((turn) => (turn.id === turnId ? update(turn) : turn));
}

/**
 * Append to the last block when it is the same kind, so a thousand deltas
 * produce one block rather than a thousand.
 */
function appendToLast(
  blocks: AgentBlock[],
  kind: "text" | "thinking",
  delta: string,
): AgentBlock[] {
  const last = blocks[blocks.length - 1];
  if (last && last.kind === kind) {
    return [...blocks.slice(0, -1), { kind, text: last.text + delta }];
  }
  return [...blocks, { kind, text: delta }];
}

export const useAgent = create<AgentStore>((set, get) => ({
  ...EMPTY,

  setOpen: (open) => {
    // At most one sheet — see `atMostOneSheet` below for why.
    if (open) useApp.getState().openAppPanel(null);
    set((state) => ({
      open,
      // Closing the panel abandons any approval on screen; the broker denies
      // the request on its own timeout, and leaving a stale card visible would
      // invite a click that answers nothing.
      pending: open ? state.pending : null,
      phase: open ? state.phase : "idle",
    }));
  },

  setProvider: (provider) => set({ provider }),
  setComputerControl: (computerControl) => set({ computerControl }),
  setSessions: (sessions) => set({ sessions }),

  startSession: (sessionId) =>
    set({ sessionId, turns: [], tainted: false, phase: "idle", banner: null }),

  submit: (text) => {
    const assistantId = nextTurnId();
    set((state) => ({
      phase: "streaming",
      banner: null,
      turns: [
        ...state.turns,
        {
          id: nextTurnId(),
          role: "user",
          blocks: [{ kind: "text", text }],
          streaming: false,
          error: null,
        },
        {
          id: assistantId,
          role: "assistant",
          blocks: [],
          streaming: true,
          error: null,
        },
      ],
    }));
    return assistantId;
  },

  appendText: (turnId, delta) =>
    set((state) => ({
      turns: patchTurn(state.turns, turnId, (turn) => ({
        ...turn,
        blocks: appendToLast(turn.blocks, "text", delta),
      })),
    })),

  appendThinking: (turnId, delta) =>
    set((state) => ({
      turns: patchTurn(state.turns, turnId, (turn) => ({
        ...turn,
        blocks: appendToLast(turn.blocks, "thinking", delta),
      })),
    })),

  startToolRun: (turnId, run) =>
    set((state) => ({
      turns: patchTurn(state.turns, turnId, (turn) => ({
        ...turn,
        blocks: [...turn.blocks, { kind: "tool", run }],
      })),
    })),

  finishToolRun: (turnId, runId, patch) =>
    set((state) => ({
      turns: patchTurn(state.turns, turnId, (turn) => ({
        ...turn,
        blocks: turn.blocks.map((block) =>
          block.kind === "tool" && block.run.id === runId
            ? { kind: "tool", run: { ...block.run, ...patch } }
            : block,
        ),
      })),
    })),

  finishTurn: (turnId, error = null) =>
    set((state) => ({
      phase: "idle",
      turns: patchTurn(state.turns, turnId, (turn) => ({
        ...turn,
        streaming: false,
        error,
      })),
    })),

  showApproval: (request) => set({ pending: request, phase: "awaiting_approval" }),

  clearApproval: (requestId) =>
    set((state) => {
      if (requestId && state.pending?.id !== requestId) return state;
      return {
        pending: null,
        // Back to streaming: the turn continues after an answer, whichever way
        // it went.
        phase: state.phase === "awaiting_approval" ? "streaming" : state.phase,
      };
    }),

  setBanner: (banner) => set({ banner }),

  markTainted: () => {
    if (get().tainted) return;
    set({ tainted: true });
  },

  reset: () => set({ ...EMPTY, provider: get().provider, computerControl: get().computerControl }),

  notePostedMessage: (channelId) => {
    // The chat store owns the transcript; the agent store only tells it
    // something arrived. Written out rather than reached for implicitly, so the
    // single dependency between the two stores is greppable.
    const app = useApp.getState();
    if (app.activeChannelId === channelId) {
      void app.refreshChannel(channelId);
    }
    void app.refreshSidebar();
  },
}));

/**
 * At most one sheet.
 *
 * The Tauri window's floor is 940px and the two-sheet stacking rule fires at
 * 960px, so thread + mini-app + agent at the same time would leave a transcript
 * around 200px wide. Opening one docked sheet therefore closes the other.
 *
 * Both directions live here, not in `app.ts`, so the dependency stays
 * one-directional: the agent store knows about chat, chat knows nothing about
 * the agent. And both live in the *store* rather than in the dock's click
 * handler because `openAppPanel` has five call sites — the command palette and
 * the mini-app bridge among them — and a rule enforced at call sites is a rule
 * someone will add a sixth call site without.
 */
useApp.subscribe((state, previous) => {
  if (
    state.openPanelInstallationId &&
    state.openPanelInstallationId !== previous.openPanelInstallationId &&
    useAgent.getState().open
  ) {
    // Not `setOpen(false)`: that would call back into `openAppPanel` and close
    // the panel this subscription is reacting to.
    useAgent.setState({ open: false, pending: null, phase: "idle" });
  }
});
