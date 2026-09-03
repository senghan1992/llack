/**
 * 채널 둘러보기 — the team's public channels, joined or not.
 *
 * A newcomer used to land in #general with no way to learn that #q3-런치
 * existed: the sidebar "+" created channels, and ⌘K only surfaced unjoined
 * channels once two characters of the right name were typed. Browsing is the
 * door that was missing — every public channel, what it is for, how many are
 * in it, one click to join.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/ipc";
import type { Channel, Id } from "@/lib/types";
import { useApp } from "@/store/app";

import { ChannelMark, IconClose, IconSearch } from "./Icon";

export function BrowseChannels({ onClose }: { onClose: () => void }) {
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const mine = useApp((state) => state.channels);
  const joinChannel = useApp((state) => state.joinChannel);
  const openChannel = useApp((state) => state.openChannel);
  const reportError = useApp((state) => state.reportError);

  const [query, setQuery] = useState("");
  const [rooms, setRooms] = useState<Channel[] | null>(null);
  const [busyId, setBusyId] = useState<Id | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!workspaceId) return undefined;
    let alive = true;
    api
      .browseChannels(workspaceId)
      .then((list) => {
        if (alive) setRooms(list);
      })
      .catch((error) => {
        if (alive) {
          setRooms([]);
          reportError(error, "채널 목록을 불러오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, [workspaceId, reportError]);

  const joined = useMemo(() => new Set(mine.map((channel) => channel.id)), [mine]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (rooms ?? [])
      .filter((channel) => channel.kind === "public" && !channel.is_archived)
      .filter(
        (channel) =>
          !needle ||
          (channel.name ?? "").toLowerCase().includes(needle) ||
          (channel.topic ?? "").toLowerCase().includes(needle),
      )
      .sort((a, b) => {
        // Channels I am not in first — that is what I came here to find.
        const aj = joined.has(a.id) ? 1 : 0;
        const bj = joined.has(b.id) ? 1 : 0;
        if (aj !== bj) return aj - bj;
        return b.member_count - a.member_count;
      });
  }, [rooms, query, joined]);

  const join = async (channel: Channel) => {
    setBusyId(channel.id);
    try {
      await joinChannel(channel.id);
      onClose();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal browse-channels"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="채널 둘러보기"
      >
        <header className="modal-header">
          <h2>채널 둘러보기</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body browse-body">
          <p className="browse-intro">
            팀의 공개 채널입니다. 참여하면 사이드바에 생기고, 지난 대화도 모두 볼 수 있습니다.
          </p>
          <div className="share-field">
            <IconSearch size={14} />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="채널 이름이나 주제로 찾기"
              aria-label="채널 찾기"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  onClose();
                }
              }}
            />
          </div>

          <ul className="browse-list" aria-label="공개 채널">
            {rooms === null ? (
              <li className="modal-empty">불러오는 중…</li>
            ) : visible.length === 0 ? (
              <li className="modal-empty">
                {query.trim() ? "찾는 채널이 없습니다." : "아직 공개 채널이 없습니다."}
              </li>
            ) : (
              visible.map((channel) => {
                const isMember = joined.has(channel.id);
                return (
                  <li key={channel.id} className={isMember ? "is-joined" : ""}>
                    <ChannelMark kind={channel.kind} />
                    <div className="browse-text">
                      <strong>{channel.name}</strong>
                      <span>
                        {channel.member_count}명
                        {channel.topic ? ` · ${channel.topic}` : ""}
                      </span>
                    </div>
                    {isMember ? (
                      <button
                        type="button"
                        className="member-action"
                        onClick={() => {
                          void openChannel(channel.id);
                          onClose();
                        }}
                      >
                        열기
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="member-action is-primary"
                        onClick={() => void join(channel)}
                        disabled={busyId === channel.id}
                      >
                        {busyId === channel.id ? "참여 중…" : "참여"}
                      </button>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
