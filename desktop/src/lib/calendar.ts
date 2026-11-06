/** Calendar helpers. Everything works in the reader's own timezone. */

const pad = (n: number) => String(n).padStart(2, "0");

/** The local calendar day of a date, as `YYYY-MM-DD`. */
export function dateKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** The local month of a date, as `YYYY-MM`. */
export function monthKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

export function parseDateKey(key: string): Date {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function parseMonthKey(key: string): Date {
  const [year, month] = key.split("-").map(Number);
  return new Date(year, month - 1, 1);
}

export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function addMonths(date: Date, count: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + count, 1);
}

/** The day a date falls on, counting Sunday as 0 — the Korean week starts on Sunday. */
function weekdayIndex(date: Date): number {
  return date.getDay();
}

/** The six-week grid that covers a month, Sunday first. */
export function monthGrid(month: Date): Date[] {
  const first = startOfMonth(month);
  const start = new Date(first);
  start.setDate(first.getDate() - weekdayIndex(first));

  const cells: Date[] = [];
  const cursor = new Date(start);
  for (let index = 0; index < 42; index += 1) {
    cells.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return cells;
}

/** Local midnight, the start of a day. */
export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** The first moment after a day — used as the end of an all-day event. */
export function endOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59, 59);
}

/** The day an ISO instant falls on, in local time. */
export function dayOf(iso: string): string {
  return dateKey(new Date(iso));
}

/** A local `YYYY-MM-DDTHH:mm` string, the shape a datetime input takes. */
export function toLocalInput(iso: string): string {
  const date = new Date(iso);
  return `${dateKey(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** A local `YYYY-MM-DD` string for a date input. */
export function toDateInput(iso: string): string {
  return dateKey(new Date(iso));
}

/** A local `HH:mm` string for a time input. */
export function toTimeInput(iso: string): string {
  const date = new Date(iso);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Turn the two inputs of a form into an instant the server can store. */
export function fromDateTimeInput(date: string, time: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const [hours, minutes] = time.split(":").map(Number);
  return new Date(year, month - 1, day, hours, minutes, 0, 0).toISOString();
}

export function isSameMonth(date: Date, month: Date): boolean {
  return (
    date.getFullYear() === month.getFullYear() && date.getMonth() === month.getMonth()
  );
}
