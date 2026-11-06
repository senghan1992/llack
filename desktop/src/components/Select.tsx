/**
 * A field that opens a list of choices.
 *
 * The platform's own `<select>` is not used: the list it opens is drawn by
 * the operating system, so it can never wear this app's material. This one
 * is a well like every other field, and the list that comes out of it is a
 * raised surface in the app's own language — the chosen row wears the
 * signal colour, the way the selected day wears it on the calendar.
 *
 * The keyboard is part of the control: the arrows walk the list, Enter
 * takes the row under the marker, Escape gives the field its focus back.
 */

import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
  /** A mark that leads the row — a face, a hash. */
  lead?: ReactNode;
  /** A second line under the label. */
  hint?: string;
  disabled?: boolean;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  /** What the closed field says when the value is not in the list. */
  placeholder?: string;
  /** The name of the field, when the visible label is not enough. */
  ariaLabel?: string;
  /** `sm` is the inline size — beside a row of controls, not on its own. */
  size?: "field" | "sm";
  disabled?: boolean;
}

/** The gap between the field and the list that comes out of it. */
const GAP = 6;
/** The narrowest the list may be, whatever the field is. */
const MIN_WIDTH = 168;
/** The widest it may be — a list of names is not a table. */
const MAX_WIDTH = 360;

export function Select({
  value,
  onChange,
  options,
  placeholder = "선택",
  ariaLabel,
  size = "field",
  disabled = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  /** What has been typed since the last pause — the jump-to-a-letter. */
  const typed = useRef({ text: "", at: 0 });

  const chosenIndex = options.findIndex((option) => option.value === value);
  const chosen = chosenIndex >= 0 ? options[chosenIndex] : null;

  const openMenu = (from?: number) => {
    setOpen(true);
    setActive(from ?? (chosenIndex >= 0 ? chosenIndex : 0));
  };

  const closeMenu = (focus = true) => {
    setOpen(false);
    if (focus) triggerRef.current?.focus();
  };

  // The list hangs under the field, or above it when the window has no room
  // below. It follows the field while the page scrolls.
  useLayoutEffect(() => {
    if (!open) return;
    const placeMenu = () => {
      const trigger = triggerRef.current;
      const menu = menuRef.current;
      if (!trigger || !menu) return;
      const rect = trigger.getBoundingClientRect();
      const box = menu.getBoundingClientRect();
      let left = Math.min(Math.max(8, rect.left), window.innerWidth - box.width - 8);
      let top = rect.bottom + GAP;
      if (top + box.height > window.innerHeight - 8) {
        const above = rect.top - box.height - GAP;
        top = above >= 8 ? above : Math.max(8, window.innerHeight - box.height - 8);
      }
      setPlace({ top, left });
    };
    placeMenu();
    window.addEventListener("resize", placeMenu);
    document.addEventListener("scroll", placeMenu, true);
    return () => {
      window.removeEventListener("resize", placeMenu);
      document.removeEventListener("scroll", placeMenu, true);
    };
  }, [open, options.length]);

  // A click anywhere else ends the choosing.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // The row under the marker stays in sight.
  useEffect(() => {
    if (!open) return;
    const row = menuRef.current?.querySelector<HTMLElement>(
      `#${CSS.escape(`${listId}-${active}`)}`,
    );
    row?.scrollIntoView({ block: "nearest" });
  }, [open, active, listId]);

  const take = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    closeMenu();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (event.key === "Escape") {
      if (!open) return;
      // The list is the inner layer — Escape ends it, and the dialog behind
      // it stays open.
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
      return;
    }

    if (event.key === "Tab") {
      if (open) closeMenu(false);
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        const from =
          event.key === "ArrowDown"
            ? chosenIndex >= 0
              ? chosenIndex
              : 0
            : chosenIndex >= 0
              ? chosenIndex
              : options.length - 1;
        openMenu(from);
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + step + options.length) % options.length);
      return;
    }

    if (event.key === "Home" && open) {
      event.preventDefault();
      setActive(0);
      return;
    }

    if (event.key === "End" && open) {
      event.preventDefault();
      setActive(options.length - 1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      take(active);
      return;
    }

    // Typing a letter walks to the row that starts with it.
    if (open && event.key.length === 1 && /\S/.test(event.key)) {
      const now = Date.now();
      const query =
        now - typed.current.at > 800 ? event.key : typed.current.text + event.key;
      typed.current = { text: query, at: now };
      const needle = query.toLowerCase();
      const from = options.findIndex(
        (option, index) =>
          index > active && option.label.toLowerCase().startsWith(needle),
      );
      const first = options.findIndex((option) =>
        option.label.toLowerCase().startsWith(needle),
      );
      const hit = from >= 0 ? from : first;
      if (hit >= 0) setActive(hit);
    }
  };

  const menu = open
    ? createPortal(
        <div
          ref={menuRef}
          className="select__menu"
          role="listbox"
          id={listId}
          aria-label={ariaLabel}
          style={{
            top: place?.top ?? -9999,
            left: place?.left ?? -9999,
            minWidth: MIN_WIDTH,
            maxWidth: MAX_WIDTH,
            visibility: place ? "visible" : "hidden",
          }}
        >
          {options.map((option, index) => (
            <div
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={option.value === value}
              aria-disabled={option.disabled || undefined}
              className="select__option"
              data-active={index === active || undefined}
              onPointerEnter={() => setActive(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => take(index)}
            >
              {option.lead ? <span className="select__lead">{option.lead}</span> : null}
              <span className="select__label">
                {option.label}
                {option.hint ? <span className="select__hint">{option.hint}</span> : null}
              </span>
              {option.value === value ? (
                <Check size={14} className="select__check" aria-hidden="true" />
              ) : null}
            </div>
          ))}
        </div>,
        document.body,
      )
    : null;

  return (
    <div className={`select${size === "sm" ? " select--sm" : ""}`}>
      <button
        type="button"
        ref={triggerRef}
        className="select__trigger"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? closeMenu(false) : openMenu())}
        onKeyDown={onKeyDown}
      >
        {chosen?.lead ? <span className="select__lead">{chosen.lead}</span> : null}
        <span className={`select__label${chosen ? "" : " select__placeholder"}`}>
          {chosen ? chosen.label : placeholder}
        </span>
        <ChevronDown size={14} className="select__chev" aria-hidden="true" />
      </button>
      {menu}
    </div>
  );
}
