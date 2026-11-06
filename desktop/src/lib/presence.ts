import type { Presence } from "./types";

/** One state a person can put on, and how the app names it. */
export interface PresenceState {
  value: Presence;
  label: string;
  /** The line under the name in the rail, and the tooltip on a face. */
  hint: string;
}

/**
 * The states a person may claim, in the order a menu shows them: the calm
 * one first, then the ones that ask for space, then the two that say "not
 * for a while".
 */
export const PRESENCE_STATES: PresenceState[] = [
  { value: "online", label: "온라인", hint: "온라인" },
  { value: "busy", label: "바쁨", hint: "바쁨" },
  { value: "dnd", label: "방해 금지", hint: "방해 금지" },
  { value: "away", label: "잠시 자리 비움", hint: "잠시 자리 비움" },
  { value: "brb", label: "곧 돌아오겠습니다", hint: "곧 돌아오겠습니다" },
];

const LABELS: Record<Presence, string> = {
  online: "온라인",
  busy: "바쁨",
  dnd: "방해 금지",
  away: "잠시 자리 비움",
  brb: "곧 돌아오겠습니다",
  offline: "오프라인",
};

/** The name of a presence, in the app's own voice. */
export function presenceLabel(presence: Presence | null | undefined): string {
  if (!presence) return "오프라인";
  return LABELS[presence] ?? LABELS.offline;
}
