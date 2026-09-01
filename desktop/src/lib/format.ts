/** Small formatting helpers shared across the UI. */

const KST_FALLBACK = "Asia/Seoul";

export function formatTime(iso: string, timeZone: string = KST_FALLBACK): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(date);
}

export function formatDayHeading(iso: string, timeZone: string = KST_FALLBACK): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  const today = new Date();
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (sameDay(date, today)) return "오늘";

  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (sameDay(date, yesterday)) return "어제";

  return new Intl.DateTimeFormat("ko-KR", {
    year: date.getFullYear() === today.getFullYear() ? undefined : "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
    timeZone,
  }).format(date);
}

/** "3분 전" style relative time, for presence and thread previews. */
export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((Date.now() - then) / 1000);

  if (seconds < 45) return "방금";
  if (seconds < 3600) return `${Math.round(seconds / 60)}분 전`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}시간 전`;
  if (seconds < 604_800) return `${Math.round(seconds / 86_400)}일 전`;
  return formatDayHeading(iso);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

/** Two initials for an avatar placeholder, working for Hangul and Latin. */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  // Hangul names are short; the first character reads better than two.
  if (/[가-힣]/.test(trimmed[0] ?? "")) return trimmed.slice(0, 1);
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return (parts[0] ?? "").slice(0, 2).toUpperCase();
  return `${(parts[0] ?? "")[0] ?? ""}${(parts[1] ?? "")[0] ?? ""}`.toUpperCase();
}

/**
 * A stable plate tint for an identity.
 *
 * Four steps of the neutral ramp rather than a hue wheel: on this surface one
 * colour carries one meaning (당신을 향한 신호), so an avatar may not spend it.
 * Differentiation comes from the initials and a faint step in value, which is
 * what the eye actually uses when scanning a column of names.
 */
export function colorForId(id: string): string {
  const tints = [
    "var(--tint-a)",
    "var(--tint-b)",
    "var(--tint-c)",
    "var(--tint-d)",
  ];
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) | 0;
  }
  return tints[Math.abs(hash) % tints.length] as string;
}

/**
 * The typographic mark before a channel name.
 *
 * `#` is a character, not an icon, so it sets with the label. A private channel
 * has no character that reads correctly at this size and takes a drawn lock
 * instead — see `ChannelMark` in `components/Icon.tsx`.
 */
export function channelPrefix(kind: string): string {
  switch (kind) {
    case "private":
    case "dm":
    case "group_dm":
      return "";
    default:
      return "#";
  }
}

/** Group consecutive messages from the same author within a few minutes. */
export function shouldGroupWithPrevious(
  current: { author?: { id: string } | null; created_at: string; parent_id?: string | null },
  previous: { author?: { id: string } | null; created_at: string } | undefined,
  windowMinutes = 5,
): boolean {
  if (!previous) return false;
  const sameAuthor = (current.author?.id ?? null) === (previous.author?.id ?? null);
  if (!sameAuthor || !current.author) return false;
  const gap = new Date(current.created_at).getTime() - new Date(previous.created_at).getTime();
  return gap >= 0 && gap < windowMinutes * 60_000;
}
