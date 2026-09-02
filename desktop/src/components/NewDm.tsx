/**
 * Start a conversation.
 *
 * Until now a DM could only be opened through ⌘K, which means it could only be
 * opened by someone who already knew the name they were looking for and knew
 * that ⌘K would find people. Every other affordance in the app is discoverable
 * from the surface it belongs to; this one was a keyboard secret with a line of
 * help text where the control should have been.
 *
 * Group DMs come free: the API takes a list of ids, so the picker is
 * multi-select and a single selection is simply a list of one.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import type { Channel, Id, User } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { IconCheck, IconClose, IconSearch } from "./Icon";

/** An existing conversation with exactly this set of people, if there is one. */
function findExisting(channels: Channel[], ids: Id[]): Channel | undefined {
  const wanted = [...ids].sort().join(",");
  return channels.find((channel) => {
    if (channel.kind !== "dm" && channel.kind !== "group_dm") return false;
    return channel.peers.map((peer) => peer.id).sort().join(",") === wanted;
  });
}

export function NewDm({ onClose }: { onClose: () => void }) {
  const people = useApp((state) => state.people);
  const presence = useApp((state) => state.presence);
  const channels = useApp((state) => state.channels);
  const me = useApp((state) => state.me);
  const openDm = useApp((state) => state.openDm);
  const openChannel = useApp((state) => state.openChannel);
  const reportError = useApp((state) => state.reportError);

  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Id[]>([]);
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /*
   * Everyone but me, and bots last.
   *
   * Bots are addressable — an app posts as itself and can be replied to — but
   * they are never who you are looking for when you open this, so they sort
   * to the bottom rather than being filtered out.
   */
  const candidates = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all = [...people.values()].filter((person) => person.id !== me?.id);
    const matched = needle
      ? all.filter(
          (person) =>
            person.display_name.toLowerCase().includes(needle) ||
            person.handle.toLowerCase().includes(needle) ||
            (person.title ?? "").toLowerCase().includes(needle),
        )
      : all;
    return matched.sort((a, b) => {
      if (a.is_bot !== b.is_bot) return a.is_bot ? 1 : -1;
      return a.display_name.localeCompare(b.display_name, "ko");
    });
  }, [people, me, query]);

  // The cursor must not point past a list the query just shortened.
  useEffect(() => {
    setCursor((current) => Math.min(current, Math.max(0, candidates.length - 1)));
  }, [candidates.length]);

  const toggle = (id: Id) => {
    setPicked((current) =>
      current.includes(id) ? current.filter((each) => each !== id) : [...current, id],
    );
    setQuery("");
    inputRef.current?.focus();
  };

  const start = async () => {
    if (picked.length === 0 || busy) return;
    setBusy(true);
    try {
      // An existing conversation is opened, not duplicated. The server would
      // return the same channel anyway; going straight there skips a round
      // trip and, more importantly, never flashes an empty transcript for a
      // conversation that already has history.
      const existing = findExisting(channels, picked);
      if (existing) {
        await openChannel(existing.id);
      } else {
        await openDm(picked);
      }
      onClose();
    } catch (error) {
      reportError(error, "대화를 시작할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((current) => Math.min(current + 1, candidates.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      // Enter picks the highlighted person; Enter with nothing left to pick
      // starts the conversation. One key, and it always does the next thing.
      const hit = candidates[cursor];
      if (hit && !picked.includes(hit.id)) toggle(hit.id);
      else void start();
    } else if (event.key === "Backspace" && query === "" && picked.length > 0) {
      // The chip behaviour every mail client has: backspace on an empty field
      // removes the last recipient.
      setPicked((current) => current.slice(0, -1));
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };

  const existing = picked.length > 0 ? findExisting(channels, picked) : undefined;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal new-dm"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="새 대화"
      >
        <header className="modal-header">
          <strong>새 대화</strong>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        {/* The field and the chosen people share one box, so the selection
            reads as the recipient line of a message rather than as a list
            somewhere else on the dialog. */}
        <div className="new-dm-field">
          <IconSearch size={14} className="new-dm-search" />
          {picked.map((id) => {
            const person = people.get(id);
            return (
              <span key={id} className="new-dm-chip">
                {person?.display_name ?? id}
                <button
                  type="button"
                  onClick={() => toggle(id)}
                  aria-label={`${person?.display_name ?? id} 제외`}
                >
                  <IconClose size={10} />
                </button>
              </span>
            );
          })}
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={picked.length > 0 ? "더 추가" : "이름 또는 @핸들"}
            aria-label="사람 찾기"
          />
        </div>

        <div className="modal-body new-dm-body">
          {candidates.length === 0 ? (
            <p className="modal-empty">
              {query ? `"${query}" 와 맞는 사람이 없습니다.` : "다른 구성원이 없습니다."}
            </p>
          ) : (
            <ul className="new-dm-list" role="listbox" aria-label="구성원">
              {candidates.map((person, index) => (
                <PersonRow
                  key={person.id}
                  person={person}
                  presence={presence.get(person.id) ?? "offline"}
                  picked={picked.includes(person.id)}
                  active={index === cursor}
                  hasDm={Boolean(findExisting(channels, [person.id]))}
                  onPick={() => toggle(person.id)}
                  onHover={() => setCursor(index)}
                />
              ))}
            </ul>
          )}
        </div>

        <footer className="new-dm-footer">
          <span>
            {picked.length === 0
              ? "대화할 사람을 고르세요."
              : existing
                ? "이미 대화가 있습니다. 그 대화로 이동합니다."
                : picked.length === 1
                  ? "1:1 대화를 시작합니다."
                  : `${picked.length}명과 그룹 대화를 시작합니다.`}
          </span>
          <button
            type="button"
            className="new-dm-start"
            onClick={() => void start()}
            disabled={picked.length === 0 || busy}
          >
            {busy ? "여는 중…" : existing ? "이동" : "시작"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function PersonRow({
  person,
  presence,
  picked,
  active,
  hasDm,
  onPick,
  onHover,
}: {
  person: User;
  presence: "active" | "away" | "dnd" | "offline";
  picked: boolean;
  active: boolean;
  hasDm: boolean;
  onPick: () => void;
  onHover: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={`new-dm-row ${active ? "is-active" : ""} ${picked ? "is-picked" : ""}`}
        onClick={onPick}
        onMouseEnter={onHover}
        role="option"
        aria-selected={picked}
      >
        <Avatar
          id={person.id}
          name={person.display_name}
          avatarUrl={person.avatar_url}
          size={28}
          presence={presence}
          isBot={person.is_bot}
        />
        <span className="new-dm-name">
          <strong>{person.display_name}</strong>
          <span>
            @{person.handle}
            {person.title ? ` · ${person.title}` : ""}
          </span>
        </span>
        {person.is_bot ? <span className="tag-bot">앱</span> : null}
        {hasDm && !picked ? <span className="new-dm-note">대화 중</span> : null}
        {/* From the icon set, not a `✓` glyph and not two rotated bars: both
            arrive with their own weight and neither joins at the corner. */}
        {picked ? (
          <span className="new-dm-check">
            <IconCheck size={15} />
          </span>
        ) : null}
      </button>
    </li>
  );
}
