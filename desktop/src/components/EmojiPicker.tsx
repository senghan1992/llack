/**
 * The emoji picker — reactions beyond the four quick ones, and emoji in text.
 *
 * Searchable in Korean and English (`웃음`, `tada`, `:+1:`), grouped like every
 * picker people already know, with the ones you actually use at the top.
 * Rendered as a popover by whoever opens it (a message's reaction row, the
 * composer); the caller decides what "pick" means.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  EMOJI_GROUPS,
  type EmojiEntry,
  type EmojiGroup,
  groupEntries,
  noteEmojiUse,
  recentEmoji,
  searchEmoji,
} from "@/lib/emoji";

import { IconClose, IconSearch } from "./Icon";

export function EmojiPicker({
  onPick,
  onClose,
  label = "이모지 선택",
}: {
  onPick: (emoji: string) => void;
  onClose: () => void;
  label?: string;
}) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<EmojiGroup>(EMOJI_GROUPS[0] ?? "표정");
  const [recent, setRecent] = useState<string[]>(() => recentEmoji());
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const results = useMemo<EmojiEntry[]>(() => {
    const needle = query.trim();
    return needle ? searchEmoji(needle, 60) : groupEntries(group);
  }, [query, group]);

  const pick = (emoji: string) => {
    noteEmojiUse(emoji);
    setRecent(recentEmoji());
    onPick(emoji);
  };

  return (
    <div
      className="emoji-picker"
      role="dialog"
      aria-label={label}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="emoji-search share-field">
        <IconSearch size={13} />
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="이름으로 찾기 (웃음, tada, +1)"
          aria-label="이모지 찾기"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              const first = results[0];
              if (first) {
                event.preventDefault();
                pick(first.char);
              }
            }
          }}
        />
        <button type="button" onClick={onClose} aria-label="닫기">
          <IconClose size={12} />
        </button>
      </div>

      {!query.trim() && recent.length > 0 ? (
        <div className="emoji-recent" aria-label="최근 사용">
          {recent.map((emoji) => (
            <button key={emoji} type="button" onClick={() => pick(emoji)} title="최근 사용">
              {emoji}
            </button>
          ))}
        </div>
      ) : null}

      {!query.trim() ? (
        <div className="emoji-groups" role="tablist" aria-label="이모지 분류">
          {EMOJI_GROUPS.map((candidate) => (
            <button
              key={candidate}
              type="button"
              role="tab"
              aria-selected={group === candidate}
              className={group === candidate ? "is-active" : ""}
              onClick={() => setGroup(candidate)}
            >
              {candidate}
            </button>
          ))}
        </div>
      ) : null}

      <div className="emoji-grid" role="listbox" aria-label={query.trim() ? "검색 결과" : group}>
        {results.length === 0 ? (
          <p className="emoji-empty">찾는 이모지가 없습니다.</p>
        ) : (
          results.map((entry) => (
            <button
              key={entry.char}
              type="button"
              role="option"
              aria-selected={false}
              onClick={() => pick(entry.char)}
              title={`:${entry.code}:`}
            >
              {entry.char}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
