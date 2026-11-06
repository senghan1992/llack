/**
 * A field that opens a list of people under itself — one person, chosen
 * from many.
 *
 * The plain `Select` draws a list of names. This one is written for a
 * company with hundreds of people: the list opens with the search already
 * focused, a name is matched anywhere in the string (the email and the
 * title count too), the arrows walk a marker through the rows, Enter takes
 * the row under it, and Escape gives the field its focus back.
 *
 * The list is drawn in a portal, the way `Select` draws its menu: a panel's
 * overflow must never cut the list of people in half.
 */

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Search } from "lucide-react";
import { Avatar } from "./Avatar";
import type { Member } from "../lib/types";

interface Props {
  /** Everyone who could be picked. */
  members: Member[];
  /** The ids that are already in place — they are not offered again. */
  exclude?: string[];
  /** The one the reader picks. */
  onPick: (userId: string) => void;
  placeholder?: string;
  emptyText?: string;
  ariaLabel?: string;
  size?: "field" | "sm";
}

/** The gap between the field and the list that comes out of it. */
const GAP = 6;
/** The narrowest the list may be, whatever the field is. */
const MIN_WIDTH = 240;
/** The widest it may be — a list of names is not a table. */
const MAX_WIDTH = 380;

export function PersonPicker({
  members,
  exclude = [],
  onPick,
  placeholder = "사람 선택",
  emptyText = "사람이 없습니다.",
  ariaLabel,
  size = "field",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<{ top: number; left: number; width: number } | null>(
    null,
  );

  const listId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const needleRef = useRef("");
  /** The search takes the focus as soon as the list opens. */
  const wantFocus = useRef(false);

  const needle = query.trim().toLowerCase();

  /**
   * The people the list shows. A name is matched anywhere in the string, so
   * "민수" finds "김민수"; the email's own first part sits inside the
   * email, so one match on the email covers "minsu" as well.
   */
  const rows = useMemo(
    () =>
      members.filter((member) => {
        if (exclude.includes(member.user.id)) return false;
        if (!needle) return true;
        const { name, email, title } = member.user;
        return (
          name.toLowerCase().includes(needle) ||
          email.toLowerCase().includes(needle) ||
          (title ?? "").toLowerCase().includes(needle)
        );
      }),
    [members, exclude, needle],
  );

  /** The marker never falls off the end of the list. */
  const activeIndex = rows.length === 0 ? 0 : Math.min(active, rows.length - 1);
  const activeId = rows.length === 0 ? undefined : `${listId}-${activeIndex}`;

  const openPanel = (seed = "") => {
    // The letter that opened the list goes into the search, so typing on
    // the closed field searches straight away.
    setQuery(seed);
    setActive(0);
    wantFocus.current = true;
    setOpen(true);
  };

  const closePanel = (focus = true) => {
    setOpen(false);
    setQuery("");
    if (focus) triggerRef.current?.focus();
  };

  const pick = (userId: string) => {
    onPick(userId);
    closePanel(false);
  };

  // The search has the focus the moment the list opens — for hundreds of
  // people, typing is the whole point. It is taken in a layout effect, so
  // the key that opened the list lands in the search and not on the page.
  useLayoutEffect(() => {
    if (!open || !wantFocus.current) return;
    const input = inputRef.current;
    if (!input) return;
    wantFocus.current = false;
    input.focus();
    const end = input.value.length;
    input.setSelectionRange(end, end);
  }, [open]);

  // A click anywhere else ends the choosing.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      closePanel(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // Escape closes the list and gives the field its focus back. It is caught
  // on the way down, so the dialog behind the list stays open.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      closePanel();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open]);

  // The marker follows the filtered list: a new search starts at the top.
  useEffect(() => {
    if (needleRef.current === needle) return;
    needleRef.current = needle;
    setActive(0);
  }, [needle]);

  // The list hangs under the field, or above it when the window has no room
  // below. It follows the field while the page scrolls.
  useLayoutEffect(() => {
    if (!open) return;
    const placePanel = () => {
      const trigger = triggerRef.current;
      const panel = panelRef.current;
      if (!trigger || !panel) return;
      const rect = trigger.getBoundingClientRect();
      const box = panel.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, MIN_WIDTH), MAX_WIDTH);
      let left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
      let top = rect.bottom + GAP;
      if (top + box.height > window.innerHeight - 8) {
        const above = rect.top - box.height - GAP;
        top = above >= 8 ? above : Math.max(8, window.innerHeight - box.height - 8);
      }
      setPlace({ top, left, width });
    };
    placePanel();
    window.addEventListener("resize", placePanel);
    document.addEventListener("scroll", placePanel, true);
    return () => {
      window.removeEventListener("resize", placePanel);
      document.removeEventListener("scroll", placePanel, true);
    };
  }, [open, rows.length, place?.width]);

  // The row under the marker stays in sight.
  useEffect(() => {
    if (!open || !activeId) return;
    const row = panelRef.current?.querySelector<HTMLElement>(`#${CSS.escape(activeId)}`);
    row?.scrollIntoView({ block: "nearest" });
  }, [open, activeId, rows]);

  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const total = rows.length;
    if (event.key === "Tab") {
      // The list is a layer over the page — Tab leaves it behind.
      closePanel(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!total) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((activeIndex + step + total) % total);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setActive(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setActive(total - 1);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const row = rows[activeIndex];
      if (row) pick(row.user.id);
    }
  };

  const onTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openPanel();
      return;
    }
    // Typing on the closed field opens the list, and the letter itself goes
    // into the search.
    if (event.key.length !== 1) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === " ") return;
    openPanel(event.key);
  };

  const panel = open ? (
    <div
      ref={panelRef}
      className="select__panel"
      role="group"
      aria-label={ariaLabel ?? "사람 선택"}
      style={{
        top: place?.top ?? 0,
        left: place?.left ?? 0,
        width: place?.width,
        opacity: place ? 1 : 0,
        pointerEvents: place ? "auto" : "none",
      }}
    >
      <div className="select__search">
        <Search size={14} className="u-muted" aria-hidden="true" />
        <input
          ref={inputRef}
          className="select__input"
          value={query}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-label="사람 검색"
          placeholder="이름 또는 이메일로 찾기"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onSearchKeyDown}
        />
      </div>

      {needle ? <p className="select__meta">검색 결과 {rows.length}명</p> : null}

      {rows.length > 0 ? (
        <div className="select__list" id={listId} role="listbox" aria-label="사람 목록">
          {needle ? null : (
            <p className="select__grouplabel">전체 {rows.length}명</p>
          )}
          {rows.map((member, index) => (
            <div
              key={member.user.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={false}
              className="select__row"
              data-active={index === activeIndex || undefined}
              onPointerEnter={() => setActive(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(member.user.id)}
            >
              <Avatar user={member.user} size="sm" />
              <span className="select__person">
                <span className="pick__text">
                  <span className="pick__name">{member.user.name}</span>
                  <span className="pick__sub">
                    {member.user.title ?? "멤버"} · {member.user.email}
                  </span>
                </span>
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {rows.length === 0 ? (
        <div className="select__empty">
          {members.length === 0 ? (
            <p className="select__emptytext">{emptyText}</p>
          ) : needle ? (
            <>
              <p className="select__emptytitle">찾은 사람이 없습니다</p>
              <p className="select__emptytext">
                “<span className="select__term">{query.trim()}</span>”은 이름·이메일·직함
                어디에도 없습니다.
              </p>
              <button
                type="button"
                className="btn btn--quiet btn--sm"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  setQuery("");
                  inputRef.current?.focus();
                }}
              >
                검색어 지우기
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  ) : null;

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
        aria-activedescendant={open ? activeId : undefined}
        aria-label={ariaLabel}
        onClick={() => (open ? closePanel(false) : openPanel())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="select__label select__placeholder">{placeholder}</span>
        <ChevronDown size={14} className="select__chev" aria-hidden="true" />
      </button>
      {panel ? createPortal(panel, document.body) : null}
    </div>
  );
}
