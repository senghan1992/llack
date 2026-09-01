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

/** Deterministic colour per id, so an avatar keeps its colour across sessions. */
export function colorForId(id: string): string {
  const palette = [
    "#4f46e5", "#0891b2", "#059669", "#ca8a04",
    "#dc2626", "#c026d3", "#2563eb", "#ea580c",
  ];
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) | 0;
  }
  return palette[Math.abs(hash) % palette.length] as string;
}

export function channelPrefix(kind: string): string {
  switch (kind) {
    case "private":
      return "🔒";
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
