/**
 * The channel sidebar.
 *
 * Grouped into starred / channels / direct messages, which is the grouping
 * people actually navigate by. Unread counts come from the server's per-member
 * counters, so they agree across devices.
 */

import { useMemo, useState } from "react";

import { ChannelMark, IconPlus } from "./Icon";
import type { Channel } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";

export function Sidebar() {
  const channels = useApp((state) => state.channels);
  const activeChannelId = useApp((state) => state.activeChannelId);
  const openChannel = useApp((state) => state.openChannel);
  const createChannel = useApp((state) => state.createChannel);
  const people = useApp((state) => state.people);
  const presence = useApp((state) => state.presence);
  const me = useApp((state) => state.me);
  const activeWorkspace = useApp((state) =>
    state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId),
  );

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const groups = useMemo(() => {
    const starred: Channel[] = [];
    const rooms: Channel[] = [];
    const dms: Channel[] = [];
    for (const channel of channels) {
      if (channel.membership?.is_starred) starred.push(channel);
      else if (channel.kind === "dm" || channel.kind === "group_dm") dms.push(channel);
      else rooms.push(channel);
    }
    return { starred, rooms, dms };
  }, [channels]);

  const submitNewChannel = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setNewName("");
    setCreating(false);
    await createChannel(name, "public");
  };

  const renderChannel = (channel: Channel) => {
    const unread = channel.membership?.unread_count ?? 0;
    const mentions = channel.membership?.mention_count ?? 0;
    const muted = channel.membership?.is_muted ?? false;
    const isDm = channel.kind === "dm" || channel.kind === "group_dm";
    const peer = isDm ? channel.peers[0] : undefined;
    const label = displayName(channel);

    return (
      <button
        key={channel.id}
        type="button"
        className={[
          "sidebar-item",
          channel.id === activeChannelId ? "is-active" : "",
          unread > 0 && !muted ? "is-unread" : "",
          muted ? "is-muted" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => void openChannel(channel.id)}
        title={channel.topic ?? label}
      >
        {isDm && peer ? (
          <Avatar
            id={peer.id}
            name={peer.display_name}
            avatarUrl={peer.avatar_url}
            size={20}
            presence={presence.get(peer.id) ?? "offline"}
            isBot={peer.is_bot}
          />
        ) : (
          <ChannelMark kind={channel.kind} />
        )}
        <span className="sidebar-label">{label}</span>
        {mentions > 0 ? (
          <span key={`m${mentions}`} className="badge badge-mention">
            {mentions}
          </span>
        ) : unread > 0 && !muted ? (
          <span key={`u${unread}`} className="badge">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>
    );
  };

  function displayName(channel: Channel): string {
    if (channel.name) return channel.name;
    if (channel.peers.length > 0) {
      return channel.peers.map((peer) => peer.display_name).join(", ");
    }
    // A DM with no peers is the note-to-self conversation.
    return me ? `${me.display_name} (나)` : "대화";
  }

  return (
    <nav className="sidebar" aria-label="채널 목록">
      <header className="sidebar-header">
        <div className="sidebar-workspace">
          <strong>{activeWorkspace?.name ?? "Llack"}</strong>
          <span className="sidebar-workspace-meta">
            {activeWorkspace ? `${activeWorkspace.member_count}명` : ""}
          </span>
        </div>
      </header>

      <div className="sidebar-scroll">
        {groups.starred.length > 0 ? (
          <section className="sidebar-section">
            <h2>
              <span aria-hidden="true" />
              중요
              <span className="sidebar-field">안 읽음</span>
              <span aria-hidden="true" />
            </h2>
            {groups.starred.map(renderChannel)}
          </section>
        ) : null}

        <section className="sidebar-section">
          <h2>
            <span aria-hidden="true" />
            채널
            <span className="sidebar-field">안 읽음</span>
            <button
              type="button"
              className="sidebar-add"
              onClick={() => setCreating((open) => !open)}
              aria-label="채널 추가"
              title="채널 추가"
            >
              <IconPlus size={13} />
            </button>
          </h2>
          {creating ? (
            <form className="sidebar-new" onSubmit={submitNewChannel}>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="채널 이름"
                autoFocus
                maxLength={80}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setCreating(false);
                    setNewName("");
                  }
                }}
              />
            </form>
          ) : null}
          {groups.rooms.map(renderChannel)}
        </section>

        <section className="sidebar-section">
          <h2>
            <span aria-hidden="true" />
            다이렉트 메시지
            <span className="sidebar-field">안 읽음</span>
            <span aria-hidden="true" />
          </h2>
          {groups.dms.map(renderChannel)}
          {groups.dms.length === 0 ? (
            <p className="sidebar-empty">
              ⌘K 로 사람을 찾아 대화를 시작하세요.
            </p>
          ) : null}
        </section>
      </div>

      {me ? (
        <footer className="sidebar-footer">
          <Avatar
            id={me.id}
            name={me.display_name}
            avatarUrl={me.avatar_url}
            size={28}
            presence={me.presence}
          />
          <div className="sidebar-me">
            <strong>{me.display_name}</strong>
            <span>
              {me.status_emoji ?? ""} {me.status_text ?? `@${me.handle}`}
            </span>
          </div>
        </footer>
      ) : null}
      <span className="sr-only">{people.size}명의 구성원</span>
    </nav>
  );
}
