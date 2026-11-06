/** Timeline helpers for the project chart — the Gantt view of a project's work. */

import { dayOf, parseDateKey } from "./calendar";

/**
 * The local midnight of the day an instant falls on. The chart counts in
 * days, not in seconds: a milestone is a period of days, and a day is what
 * the reader thinks in.
 */
export function dayStart(iso: string): number {
  return parseDateKey(dayOf(iso)).getTime();
}

/** The midnight after that day — so a one-day bar still has a width. */
export function nextDay(iso: string): number {
  const date = parseDateKey(dayOf(iso));
  date.setDate(date.getDate() + 1);
  return date.getTime();
}

/** The first day of the month a moment falls in. */
export function monthStartOf(time: number): Date {
  const date = new Date(time);
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export interface MonthCell {
  /** `YYYY-M` — the month this cell is. */
  key: string;
  /** The month as the reader names it: `3월`. */
  label: string;
  year: number;
  /** The midnight the month opens at. */
  start: number;
  /** The midnight the month after it opens at — the month ends here. */
  end: number;
}

/**
 * The months a span covers, as the cells of the timeline's header. `to` is
 * exclusive: a span that ends on 1 February shows January and stops. The
 * months are as long as they really are — February is shorter, and the
 * chart says so.
 */
export function monthCells(from: Date, to: Date): MonthCell[] {
  const cells: MonthCell[] = [];
  const cursor = new Date(from.getFullYear(), from.getMonth(), 1);
  while (cursor.getTime() < to.getTime()) {
    const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    cells.push({
      key: `${cursor.getFullYear()}-${cursor.getMonth() + 1}`,
      label: `${cursor.getMonth() + 1}월`,
      year: cursor.getFullYear(),
      start: cursor.getTime(),
      end: next.getTime(),
    });
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return cells;
}

/**
 * Where an instant sits on the timeline, from 0 to 1. The ends are the
 * clamps: a bar never leaves the chart, not even by a day.
 */
export function ratio(at: number, from: number, to: number): number {
  if (to <= from) return 0;
  const value = (at - from) / (to - from);
  return Math.max(0, Math.min(1, value));
}
