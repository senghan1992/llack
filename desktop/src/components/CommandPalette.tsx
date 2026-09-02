/**
 * ⌘K — one input that searches channels, people, apps and message text at
 * once, and can act on the result.
 *
 * This is the main thing the design bets on: in Slack, finding a person,
 * finding a channel and finding a message are three different UIs. Here they
 * are one ranked list, so the user never has to pick a category first.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/ipc";
import { previewText } from "@/lib/markdown";
import type { SearchResult } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";

const DEBOUNCE_MS = 160;

type Entry =
  | { kind: "channel"; id: string; label: string; hint?: string }
  | { kind: "person"; id: string; label: string; hint?: string; avatarUrl?: string | null }
  | { kind: "app"; id: string; label: string; hint?: string }
  | { kind: "message"; id: string; channelId: string; label: string; hint?: string };

export function CommandPalette() {
  const open = useApp((state) => state.paletteOpen);
  const setPalette = useApp((state) => state.setPalette);
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const channels = useApp((state) => state.channels);
  const people = useApp((state) => state.people);
  const installations = useApp((state) => state.installations);
  const openChannel = useApp((state) => state.openChannel);
  const openDm = useApp((state) => state.openDm);
  const openAppPanel = useApp((state) => state.openAppPanel);
  const joinChannel = useApp((state) => state.joinChannel);
  const reportError = useApp((state) => state.reportError);

  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<SearchResult | null>(null);
  const [cursor, setCursor] = useState(0);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setRemote(null);
      setCursor(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Debounced server search. Local matches render immediately, so the list is
  // never empty while the request is in flight.
  useEffect(() => {
    if (!open || !workspaceId) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setRemote(null);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      void api
        .search(workspaceId, trimmed)
        .then(setRemote)
        .catch((error) => reportError(error, "검색에 실패했습니다."))
        .finally(() => setSearching(false));
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      setSearching(false);
    };
  }, [open, query, workspaceId, reportError]);

  const entries = useMemo<Entry[]>(() => {
    const needle = query.trim().toLowerCase();
    const results: Entry[] = [];
    const seen = new Set<string>();

    const push = (entry: Entry) => {
      const key = `${entry.kind}:${entry.id}`;
      if (seen.has(key)) return;
      seen.add(key);
      results.push(entry);
    };

    // Local first — instant, and covers the common "jump to a channel" case.
    for (const channel of channels) {
      const name = channel.name ?? channel.peers.map((p) => p.display_name).join(", ");
      if (!needle || name.toLowerCase().includes(needle)) {
        push({
          kind: "channel",
          id: channel.id,
          label: name,
          ...(channel.topic ? { hint: channel.topic } : {}),
        });
      }
    }
    for (const person of people.values()) {
      if (
        !needle ||
        person.display_name.toLowerCase().includes(needle) ||
        person.handle.toLowerCase().includes(needle)
      ) {
        push({
          kind: "person",
          id: person.id,
          label: person.display_name,
          hint: `@${person.handle}`,
          avatarUrl: person.avatar_url,
        });
      }
    }
    for (const installation of installations) {
      if (!needle || installation.app.name.toLowerCase().includes(needle)) {
        push({
          kind: "app",
          id: installation.id,
          label: installation.app.name,
          ...(installation.app.tagline ? { hint: installation.app.tagline } : {}),
        });
      }
    }

    // Then the server's results, including channels the user has not joined
    // and message-body matches, which local state cannot know about.
    if (remote) {
      for (const channel of remote.channels) {
        push({
          kind: "channel",
          id: channel.id,
          label: channel.name,
          ...(channel.topic ? { hint: channel.topic } : {}),
        });
      }
      for (const person of remote.people) {
        push({
          kind: "person",
          id: person.id,
          label: person.display_name,
          hint: `@${person.handle}`,
          avatarUrl: person.avatar_url,
        });
      }
      for (const hit of remote.messages) {
        push({
          kind: "message",
          id: hit.message.id,
          channelId: hit.channel_id,
          label:
            hit.highlight?.replace(/<\/?mark>/g, "") ??
            previewText(hit.message.body, {
              userName: (id) => people.get(id)?.display_name,
              channelName: () => undefined,
            }),
          hint: `#${hit.channel_name ?? ""} · ${hit.message.author?.display_name ?? ""}`,
        });
      }
    }

    return results.slice(0, 40);
  }, [query, channels, people, installations, remote]);

  const activate = useCallback(
    async (entry: Entry | undefined) => {
      if (!entry) return;
      setPalette(false);
      switch (entry.kind) {
        case "channel": {
          const joined = channels.some((channel) => channel.id === entry.id);
          if (joined) await openChannel(entry.id);
          else await joinChannel(entry.id);
          break;
        }
        case "person":
          await openDm([entry.id]);
          break;
        case "app":
          openAppPanel(entry.id);
          break;
        case "message":
          await openChannel(entry.channelId);
          break;
      }
    },
    [channels, openChannel, joinChannel, openDm, openAppPanel, setPalette],
  );

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={() => setPalette(false)} role="presentation">
      <div
        className="palette"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="검색 및 이동"
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setCursor(0);
          }}
          placeholder="채널, 사람, 앱, 메시지 검색…"
          aria-label="검색"
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setCursor((index) => Math.min(index + 1, entries.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((index) => Math.max(index - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              void activate(entries[cursor]);
            } else if (event.key === "Escape") {
              event.preventDefault();
              setPalette(false);
            }
          }}
        />

        <ul className="palette-results" role="listbox">
          {entries.length === 0 ? (
            <li className="palette-empty">
              {searching ? "검색 중…" : "결과가 없습니다."}
            </li>
          ) : null}

          {entries.map((entry, index) => (
            <li key={`${entry.kind}:${entry.id}`}>
              <button
                type="button"
                className={index === cursor ? "is-active" : ""}
                onMouseEnter={() => setCursor(index)}
                onClick={() => void activate(entry)}
                role="option"
                aria-selected={index === cursor}
              >
                <span className="palette-kind">{kindLabel(entry.kind)}</span>
                {entry.kind === "person" ? (
                  <Avatar
                    id={entry.id}
                    name={entry.label}
                    avatarUrl={entry.avatarUrl}
                    size={20}
                  />
                ) : null}
                <span className="palette-label">{entry.label}</span>
                {entry.hint ? <span className="palette-hint">{entry.hint}</span> : null}
              </button>
            </li>
          ))}
        </ul>

        <footer className="palette-footer">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> 이동 · <kbd>Enter</kbd> 열기 · <kbd>Esc</kbd> 닫기
          </span>
          {/*
            The server's `took_ms` used to be printed here. "2ms" is a number
            for whoever is tuning the query, not for whoever is looking for a
            channel — and a latency readout in a shipping product's search box
            reads as a debug build. It stays available on the response for
            anyone profiling.
          */}
          {/* The count comes from the rendered list, not from a field the
              envelope does not carry. */}
          {entries.length > 0 ? <span>{entries.length}건</span> : null}
        </footer>
      </div>
    </div>
  );
}

function kindLabel(kind: Entry["kind"]): string {
  switch (kind) {
    case "channel":
      return "채널";
    case "person":
      return "사람";
    case "app":
      return "앱";
    case "message":
      return "메시지";
  }
}
