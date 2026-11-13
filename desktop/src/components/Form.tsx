/**
 * The parts a form is made of.
 *
 * A form in this app is a sheet of rows: the name of the thing on the left,
 * the thing you fill in on the right. One row is one line, so the whole form
 * is read at a glance instead of scrolled through.
 *
 * The title is not a row. It is the subject of the form, and it reads like a
 * line on the page — the way a note's first line does.
 *
 * The date and the time are ours: the platform's own `<input type="date">`
 * paints its menu with the operating system, so it can never wear this app's
 * material. These are wells like every other field, and what comes out of
 * them is drawn the way the app draws everything else.
 */

import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import {
  addMonths,
  dateKey,
  isSameMonth,
  monthGrid,
  parseDateKey,
} from "../lib/calendar";
import { useSettings } from "../lib/settings";
import { Select } from "./Select";

const WEEKDAYS = ["일", "월", "화", "목", "금", "토"];

/** The gap between the field and the panel that comes out of it. */
const GAP = 6;
/** A month of days needs room to be read, whatever the field's width is. */
const MIN_WIDTH = 248;

/* ── the title ───────────────────────────────────────────────────────── */

/**
 * The subject of the form. The name of the thing sits above it, small and
 * quiet; the thing itself is written large under it, and the rule beneath
 * says "this is what you are writing".
 */
export function FormTitle({
  value,
  onChange,
  placeholder,
  label,
  hint,
  id,
  autoFocus,
  maxLength,
  onEnter,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** What the field is — it is written above the line. */
  label: string;
  /** A sentence about the field, under the line. */
  hint?: string;
  id?: string;
  autoFocus?: boolean;
  maxLength?: number;
  /** What Enter means here — usually "save". */
  onEnter?: () => void;
}) {
  return (
    <div className="formtitle__block">
      <span className="formtitle__eyebrow">{label}</span>
      <input
        id={id}
        className="formtitle"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && onEnter) {
            event.preventDefault();
            onEnter();
          }
        }}
        placeholder={placeholder}
        aria-label={label}
        autoFocus={autoFocus}
        maxLength={maxLength}
      />
      {hint ? <p className="formtitle__hint">{hint}</p> : null}
    </div>
  );
}

/* ── a row ──────────────────────────────────────────────────────────── */

/** One line of a form: the name on the left, the thing to fill in on the right. */
export function FormRow({
  label,
  children,
  htmlFor,
  stack,
}: {
  label: ReactNode;
  children: ReactNode;
  /** The control's id — the name then focuses it when it is clicked. */
  htmlFor?: string;
  /** The name above the control, for a name too long to stand beside it. */
  stack?: boolean;
}) {
  return (
    <div className={`formrow${stack ? " formrow--stack" : ""}`}>
      {htmlFor ? (
        <label className="formrow__label" htmlFor={htmlFor}>
          {label}
        </label>
      ) : (
        <span className="formrow__label">{label}</span>
      )}
      <div className="formrow__control">{children}</div>
    </div>
  );
}

/* ── a choice between a few ways ────────────────────────────────────── */

/**
 * A choice between two, three or four ways, in a well.
 *
 * The chosen one is a raised surface in the well — the way the selected day
 * wears the signal on the calendar.
 */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled = false,
}: {
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (next: T) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented__item"
          aria-pressed={option.value === value}
          disabled={disabled || option.disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/* ── the rare things, folded away ───────────────────────────────────── */

/**
 * 더 보기 — the fields most forms do not need.
 *
 * They are folded, not gone: the row says what is inside it, so the reader
 * knows the form can do more without opening it to find out.
 */
export function Disclosure({
  summary,
  children,
  defaultOpen = false,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  // The folded fields may already hold something — an event that has a place
  // opens with its place showing, not with a hidden answer.
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  return (
    <div className="disclosure">
      <button
        type="button"
        className="disclosure__toggle"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((current) => !current)}
      >
        <ChevronRight size={13} className="disclosure__chev" aria-hidden="true" />
        <span>{summary}</span>
      </button>
      {open ? (
        <div className="disclosure__body" id={bodyId}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

/* ── the day ────────────────────────────────────────────────────────── */

/**
 * A field that opens a month under itself.
 *
 * The grid is the same one the schedule shows, so a day looks the same
 * wherever it is picked. The keyboard is the control, and it answers the same
 * way every other choice in this app does: the field keeps the focus, the
 * arrows walk a marker through the days, Enter takes the day under it, and
 * Escape closes the month and leaves the dialog behind it open.
 */
export function DateField({
  value,
  onChange,
  ariaLabel,
  placeholder = "날짜 고르기",
  disabled = false,
}: {
  /** The day, as `YYYY-MM-DD`. */
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<Date | null>(null);
  const [marked, setMarked] = useState<string | null>(null);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const gridId = useId();

  const today = useMemo(() => new Date(), []);
  const todayKey = dateKey(today);

  // The month on show: the month of the day that is set, else this month.
  const shown = useMemo(
    () => anchor ?? (value ? parseDateKey(value) : today),
    [anchor, value, today],
  );

  // The day under the marker: the day the pointer has walked to, else the
  // day that is set, else today.
  const markedKey = marked ?? value ?? dateKey(shown);

  const cells = useMemo(() => monthGrid(shown), [shown]);

  const close = (focus = true) => {
    setOpen(false);
    setAnchor(null);
    setMarked(null);
    if (focus) triggerRef.current?.focus();
  };

  const openPanel = () => {
    setOpen(true);
    setAnchor(null);
    setMarked(value || todayKey);
  };

  const take = (key: string) => {
    onChange(key);
    close();
  };

  // The panel hangs under the field, or above it when the window has no room
  // below. It follows the field while the page scrolls.
  useLayoutEffect(() => {
    if (!open) return;
    const placePanel = () => {
      const trigger = triggerRef.current;
      const panel = panelRef.current;
      if (!trigger || !panel) return;
      const rect = trigger.getBoundingClientRect();
      const box = panel.getBoundingClientRect();
      let left = Math.min(Math.max(8, rect.left), window.innerWidth - box.width - 8);
      let top = rect.bottom + GAP;
      if (top + box.height > window.innerHeight - 8) {
        const above = rect.top - box.height - GAP;
        top = above >= 8 ? above : Math.max(8, window.innerHeight - box.height - 8);
      }
      setPlace({ top, left });
    };
    placePanel();
    window.addEventListener("resize", placePanel);
    document.addEventListener("scroll", placePanel, true);
    return () => {
      window.removeEventListener("resize", placePanel);
      document.removeEventListener("scroll", placePanel, true);
    };
  }, [open]);

  // A click anywhere else ends the choosing.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      close(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // The day under the marker stays in sight.
  useEffect(() => {
    if (!open) return;
    const day = panelRef.current?.querySelector<HTMLElement>(
      `[data-day="${CSS.escape(markedKey)}"]`,
    );
    day?.scrollIntoView({ block: "nearest" });
  }, [open, markedKey, shown]);

  const move = (days: number) => {
    const next = new Date(parseDateKey(markedKey));
    next.setDate(next.getDate() + days);
    const key = dateKey(next);
    setMarked(key);
    // Walking into another month follows it.
    if (!isSameMonth(next, shown)) setAnchor(next);
  };

  const onTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (event.key === "Escape" && open) {
      // The month is the inner layer — Escape ends it, and the dialog behind
      // it stays open.
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) take(markedKey);
      else openPanel();
      return;
    }

    if (!open) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openPanel();
      }
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      move(-7);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      move(7);
      return;
    }
    if (event.key === "PageUp") {
      event.preventDefault();
      const next = addMonths(shown, -1);
      setAnchor(next);
      setMarked(dateKey(next));
      return;
    }
    if (event.key === "PageDown") {
      event.preventDefault();
      const next = addMonths(shown, 1);
      setAnchor(next);
      setMarked(dateKey(next));
    }
  };

  const label = value ? formatDay(value) : placeholder;

  const panel = open ? (
    <div
      ref={panelRef}
      className="datepick"
      style={{
        top: place?.top ?? -9999,
        left: place?.left ?? -9999,
        minWidth: MIN_WIDTH,
        visibility: place ? "visible" : "hidden",
      }}
    >
      <div className="datepick__head">
        <button
          type="button"
          className="iconbtn"
          aria-label="이전 달"
          onClick={() => setAnchor(addMonths(shown, -1))}
        >
          <ChevronLeft size={15} aria-hidden="true" />
        </button>
        <span className="datepick__month">
          {shown.getFullYear()}년 {shown.getMonth() + 1}월
        </span>
        <button
          type="button"
          className="iconbtn"
          aria-label="다음 달"
          onClick={() => setAnchor(addMonths(shown, 1))}
        >
          <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>

      <div className="datepick__weekdays" aria-hidden="true">
        {WEEKDAYS.map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>

      <div
        className="datepick__grid"
        id={gridId}
        role="grid"
        aria-label={`${shown.getFullYear()}년 ${shown.getMonth() + 1}월`}
      >
        {cells.map((cell) => {
          const key = dateKey(cell);
          const classes = ["datepick__day"];
          if (!isSameMonth(cell, shown)) classes.push("datepick__day--out");
          if (key === todayKey) classes.push("datepick__day--today");
          if (key === value) classes.push("datepick__day--sel");
          if (key === markedKey) classes.push("datepick__day--on");
          return (
            <button
              key={key}
              type="button"
              id={`${gridId}-${key}`}
              data-day={key}
              className={classes.join(" ")}
              tabIndex={-1}
              aria-current={key === todayKey ? "date" : undefined}
              aria-selected={key === value}
              onClick={() => take(key)}
            >
              {cell.getDate()}
            </button>
          );
        })}
      </div>

      <div className="datepick__foot">
        <button type="button" className="btn btn--quiet btn--sm" onClick={() => take(todayKey)}>
          오늘
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div className="select">
      <button
        type="button"
        ref={triggerRef}
        className="select__trigger"
        role="combobox"
        aria-haspopup="grid"
        aria-expanded={open}
        aria-controls={gridId}
        aria-activedescendant={open ? `${gridId}-${markedKey}` : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? close(false) : openPanel())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="select__lead">
          <CalendarDays size={13} aria-hidden="true" />
        </span>
        <span className={`select__label${value ? "" : " select__placeholder"}`}>{label}</span>
        <ChevronDown size={14} className="select__chev" aria-hidden="true" />
      </button>
      {panel ? createPortal(panel, document.body) : null}
    </div>
  );
}

/* ── the hour ───────────────────────────────────────────────────────── */

/**
 * A field that opens a list of times.
 *
 * It is the app's own dropdown — a well that opens a raised list, the way
 * every other choice in this app does.
 */
export function TimeField({
  value,
  onChange,
  ariaLabel,
  disabled = false,
}: {
  /** The time, as `HH:mm`. */
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
}) {
  const settings = useSettings();
  const options = useMemo(() => {
    const out: { value: string; label: string }[] = [];
    for (let minutes = 0; minutes < 24 * 60; minutes += 15) {
      const hour = Math.floor(minutes / 60);
      const minute = minutes % 60;
      out.push({ value: `${pad(hour)}:${pad(minute)}`, label: clockLabel(hour, minute, settings.clock) });
    }
    return out;
  }, [settings.clock]);

  return (
    <Select
      value={value}
      onChange={onChange}
      options={options}
      ariaLabel={ariaLabel}
      disabled={disabled}
    />
  );
}

/* ── helpers ────────────────────────────────────────────────────────── */

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** The day a field shows: "11월 12일 (수)". */
function formatDay(key: string): string {
  const date = parseDateKey(key);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const base = sameYear
    ? `${date.getMonth() + 1}월 ${date.getDate()}일`
    : `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일`;
  return `${base} (${WEEKDAYS[date.getDay()]})`;
}

/** The hour a field shows, in the clock the reader set. */
function clockLabel(hour: number, minute: number, clock: "12h" | "24h"): string {
  if (clock === "12h") {
    const twelve = hour % 12 === 0 ? 12 : hour % 12;
    return `${hour < 12 ? "오전" : "오후"} ${twelve}:${pad(minute)}`;
  }
  return `${pad(hour)}:${pad(minute)}`;
}
