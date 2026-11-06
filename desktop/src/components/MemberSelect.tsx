import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search } from "lucide-react";
import { Avatar } from "./Avatar";
import type { Member } from "../lib/types";

interface Props {
  /** The people who can be chosen — everyone but the maker, usually. */
  members: Member[];
  /** The ids already chosen. */
  value: string[];
  onChange: (ids: string[]) => void;
  placeholder?: string;
  emptyText?: string;
}

/** The gap between the field and the list that comes out of it. */
const GAP = 6;
/** The narrowest the list may be, whatever the field is. */
const MIN_WIDTH = 240;
/** The widest it may be — a list of names is not a table. */
const MAX_WIDTH = 380;

/** One row of the list: a person, and whether they are already in. */
interface Row {
  member: Member;
  picked: boolean;
}

/**
 * A field that opens a list of people under itself.
 *
 * The people already chosen stay in the list and carry a tip, so the roster
 * of the room can be read while it is still being picked — you always see
 * who is in, and who is not.
 *
 * The list is written for a company with hundreds of people: it opens with
 * the search already focused, the arrows walk a marker through the rows,
 * Enter takes the row under the marker, and Escape gives the field its
 * focus back. The chosen people stand at the top of the list under their
 * own count, so the roster of the room is readable at a glance.
 *
 * The list is drawn in a portal, the way `Select` draws its menu: a dialog's
 * overflow must never cut the list of people in half.
 */
export function MemberSelect({
  members,
  value,
  onChange,
  placeholder = "함께할 사람 선택",
  emptyText = "팀원이 없습니다.",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [place, setPlace] = useState<{ top: number; left: number; width: number } | null>(
    null,
  );
  /** The person whose row the marker follows after a pick. */
  const [followId, setFollowId] = useState<string | null>(null);

  const listId = useId();
  const pickedLabelId = `${listId}-picked`;
  const restLabelId = `${listId}-rest`;

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const needleRef = useRef("");
  /** The search takes the focus as soon as the list opens. */
  const wantFocus = useRef(false);

  const needle = query.trim().toLowerCase();

  /**
   * The people the list shows: the ones already chosen first, then the
   * rest. A name is matched anywhere in the string, so "민수" finds
   * "김민수"; the email's own first part sits inside the email, so one
   * match on the email covers "minsu" as well.
   */
  const rows = useMemo<Row[]>(() => {
    const hits = (member: Member) => {
      if (!needle) return true;
      const { name, email, title } = member.user;
      return (
        name.toLowerCase().includes(needle) ||
        email.toLowerCase().includes(needle) ||
        (title ?? "").toLowerCase().includes(needle)
      );
    };
    const chosen = members
      .filter((member) => value.includes(member.user.id))
      .filter(hits)
      .sort((a, b) => value.indexOf(a.user.id) - value.indexOf(b.user.id));
    const rest = members
      .filter((member) => !value.includes(member.user.id))
      .filter(hits);
    return [
      ...chosen.map((member) => ({ member, picked: true })),
      ...rest.map((member) => ({ member, picked: false })),
    ];
  }, [members, value, needle]);

  const pickedCount = rows.filter((row) => row.picked).length;
  const restCount = rows.length - pickedCount;
  /** The marker never falls off the end of the list. */
  const activeIndex = rows.length === 0 ? 0 : Math.min(active, rows.length - 1);
  const activeId = rows.length === 0 ? undefined : `${listId}-${activeIndex}`;

  const toggle = (userId: string) => {
    onChange(
      value.includes(userId) ? value.filter((id) => id !== userId) : [...value, userId],
    );
    // The person moves to the top of the list — the marker goes with them.
    setFollowId(userId);
  };

  const openPanel = (seed = "") => {
    // The letter that opened the list goes into the search, so typing on the
    // closed field searches straight away.
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
      if (rootRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      closePanel(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // Escape closes the list first and gives the field its focus back. It is
  // caught on the way down, so the dialog behind the list stays open.
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

  // The marker follows the person who was just picked.
  useEffect(() => {
    if (!followId) return;
    const index = rows.findIndex((row) => row.member.user.id === followId);
    setFollowId(null);
    if (index >= 0) setActive(index);
  }, [rows, followId]);

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

  // The row under the marker stays in sight — also when the list itself
  // moves under the marker, as it does when a person joins the chosen.
  useEffect(() => {
    if (!open || !activeId) return;
    const row = panelRef.current?.querySelector<HTMLElement>(`#${CSS.escape(activeId)}`);
    row?.scrollIntoView({ block: "nearest" });
  }, [open, activeId, rows]);

  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const total = rows.length;
    if (event.key === "Tab") {
      // The list is a layer over the dialog — Tab leaves it behind.
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
      if (row) toggle(row.member.user.id);
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
    // into the search — the same way the palette does.
    if (event.key.length !== 1) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === " ") return;
    openPanel(event.key);
  };

  const chosen = members.filter((member) => value.includes(member.user.id));

  const row = (index: number) => {
    const item = rows[index];
    const picked = item.picked;
    return (
      <div
        key={item.member.user.id}
        id={`${listId}-${index}`}
        role="option"
        aria-selected={picked}
        className="select__row"
        data-active={index === activeIndex || undefined}
        onPointerEnter={() => setActive(index)}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => toggle(item.member.user.id)}
      >
        <Avatar user={item.member.user} size="sm" />
        <span className="select__person">
          <span className="pick__text">
            <span className="pick__name">{item.member.user.name}</span>
            <span className="pick__sub">
              {item.member.user.title ?? "멤버"} · {item.member.user.email}
            </span>
          </span>
        </span>
        {picked ? (
          <span className="tip">
            <Check size={11} aria-hidden="true" />
            추가됨
          </span>
        ) : null}
      </div>
    );
  };

  const panel = open ? (
    <div
      ref={panelRef}
      className="select__panel"
      role="group"
      aria-label="함께할 사람"
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

      {needle ? (
        <p className="select__meta">검색 결과 {rows.length}명</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="select__list" id={listId} role="listbox" aria-label="사람 목록">
          {pickedCount > 0 ? (
            <div role="group" aria-labelledby={pickedLabelId}>
              <p className="select__grouplabel" id={pickedLabelId}>
                선택됨 {pickedCount}명
              </p>
              {rows.slice(0, pickedCount).map((_, index) => row(index))}
            </div>
          ) : null}
          {restCount > 0 ? (
            <div role="group" aria-labelledby={restLabelId}>
              <p className="select__grouplabel" id={restLabelId}>
                전체 {restCount}명
              </p>
              {rows.slice(pickedCount).map((_, index) => row(pickedCount + index))}
            </div>
          ) : null}
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
    <div className="select" ref={rootRef}>
      <button
        type="button"
        ref={triggerRef}
        className="select__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => (open ? closePanel(false) : openPanel())}
        onKeyDown={onTriggerKeyDown}
      >
        {chosen.length === 0 ? (
          <span className="select__placeholder">{placeholder}</span>
        ) : (
          <>
            <span className="select__stack">
              {chosen.slice(0, 4).map((member) => (
                <Avatar key={member.user.id} user={member.user} size="sm" />
              ))}
            </span>
            <span className="select__count">{chosen.length}명</span>
          </>
        )}
        <ChevronDown size={14} className="select__chev" aria-hidden="true" />
      </button>

      {panel ? createPortal(panel, document.body) : null}
    </div>
  );
}
