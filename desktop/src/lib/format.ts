import { AVATAR_PALETTE } from "./color";
import { getSettings } from "./settings";

const KOREAN = /[가-힯]/;

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * 메시지 옆의 시간. 표기 방식은 설정이 정한다 — 24시간制와 12시간制.
 */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (getSettings().clock === "12h") {
    const hour = d.getHours();
    const twelve = hour % 12 === 0 ? 12 : hour % 12;
    return `${hour < 12 ? "오전" : "오후"} ${twelve}:${pad(d.getMinutes())}`;
  }
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatDateLong(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`;
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export function weekday(iso: string): string {
  return WEEKDAYS[new Date(iso).getDay()];
}

/** 오늘 · 어제 · 11월 2일 (화) — the relative label a team actually reads. */
export function dayLabel(iso: string): { rel: string; date: string } {
  const d = new Date(iso);
  const today = new Date();
  const same = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  if (same(d, today)) return { rel: "오늘", date: formatDate(iso) };

  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (same(d, yesterday)) return { rel: "어제", date: formatDate(iso) };

  const sameYear = d.getFullYear() === today.getFullYear();
  const date = sameYear
    ? `${d.getMonth() + 1}월 ${d.getDate()}일`
    : `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
  return { rel: `${date} (${weekday(iso)})`, date: formatDate(iso) };
}

export function isSameDay(a: string, b: string): boolean {
  const x = new Date(a);
  const y = new Date(b);
  return (
    x.getFullYear() === y.getFullYear() && x.getMonth() === y.getMonth() && x.getDate() === y.getDate()
  );
}

/** A period of time, as the short range a milestone shows: 03/01 – 06/30. */
export function dateRange(startIso: string, endIso: string): string {
  return `${monthDay(startIso)} – ${monthDay(endIso)}`;
}

/**
 * The period a project occupies — `2026.11.03 – 01.05`.
 *
 * The year is written where it changes, because a reader who sees `01.05`
 * must not mistake it for January of this year.
 */
export function periodLabel(startIso: string, endIso: string): string {
  const start = new Date(startIso);
  const end = new Date(endIso);
  const left = `${start.getFullYear()}.${pad(start.getMonth() + 1)}.${pad(start.getDate())}`;
  const right =
    start.getFullYear() === end.getFullYear()
      ? `${pad(end.getMonth() + 1)}.${pad(end.getDate())}`
      : `${end.getFullYear()}.${pad(end.getMonth() + 1)}.${pad(end.getDate())}`;
  return `${left} – ${right}`;
}

/** The day of an instant, as `MM/DD`. */
function monthDay(iso: string): string {
  const date = new Date(iso);
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
}

/** Two initials. Korean names take the given name, Latin names the first letters. */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  if (KOREAN.test(trimmed)) return trimmed.slice(-2);
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}일 전`;
  return formatDate(iso);
}

/** A stable colour from a name, so an avatar keeps its colour without a stored field. */
export function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

/** Whether a message body names a person — "@김현진" and the like. */
export function mentionsUser(body: string, name: string): boolean {
  const trimmed = name.trim();
  if (!trimmed) return false;
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`@${escaped}(?![\\w가-힯])`).test(body);
}
