/**
 * The channel sidebar.
 *
 * Grouped into starred / channels / direct messages, which is the grouping
 * people actually navigate by. Unread counts come from the server's per-member
 * counters, so they agree across devices.
 */

import { useMemo, useState } from "react";

import {
  ChannelMark,
  IconActivity,
  IconBookmark,
  IconFolder,
  IconGear,
  IconMoon,
  IconPlus,
  IconSearch,
} from "./Icon";
import type { Channel } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { BrowseChannels } from "./BrowseChannels";
import { NewDm } from "./NewDm";

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

  const setSettings = useApp((state) => state.setSettings);
  const mainView = useApp((state) => state.mainView);
  const webAppOpen = useApp((state) => state.openWebAppInstallationId !== null);
  const setMainView = useApp((state) => state.setMainView);

  const [creating, setCreating] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [startingDm, setStartingDm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPrivate, setNewPrivate] = useState(false);

  // Rooms split into the person's own sections (membership.section) — a
  // "프로젝트" group above the rest, folded when they want it out of the way.
  const groups = useMemo(() => {
    const starred: Channel[] = [];
    const rooms: Channel[] = [];
    const dms: Channel[] = [];
    const sections = new Map<string, Channel[]>();
    for (const channel of channels) {
      if (channel.membership?.is_starred) starred.push(channel);
      else if (channel.kind === "dm" || channel.kind === "group_dm") dms.push(channel);
      else if (channel.membership?.section) {
        const list = sections.get(channel.membership.section) ?? [];
        list.push(channel);
        sections.set(channel.membership.section, list);
      } else rooms.push(channel);
    }
    return {
      starred,
      rooms,
      dms,
      sections: [...sections.entries()].sort((a, b) => a[0].localeCompare(b[0], "ko")),
    };
  }, [channels]);

  const [folded, setFolded] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(
        window.localStorage.getItem("llack.sidebar-folded") ?? "{}",
      ) as Record<string, boolean>;
    } catch {
      return {};
    }
  });
  const toggleFold = (section: string) => {
    setFolded((current) => {
      const next = { ...current, [section]: !current[section] };
      try {
        window.localStorage.setItem("llack.sidebar-folded", JSON.stringify(next));
      } catch {
        // Not worth a banner.
      }
      return next;
    });
  };

  const submitNewChannel = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setNewName("");
    setCreating(false);
    setNewPrivate(false);
    await createChannel(name, newPrivate ? "private" : "public");
  };

  const renderChannel = (channel: Channel) => {
    const mentions = channel.membership?.mention_count ?? 0;
    // "멘션만" means exactly that: ordinary traffic neither bolds the row nor
    // counts on the badge. The server keeps counting (for the read marker);
    // the sidebar honours the person's choice.
    const level = channel.membership?.notification_level ?? "all";
    const muted = (channel.membership?.is_muted ?? false) || level === "nothing";
    const unread = level === "mentions" ? 0 : (channel.membership?.unread_count ?? 0);
    const isDm = channel.kind === "dm" || channel.kind === "group_dm";
    const peer = isDm ? channel.peers[0] : undefined;
    const label = displayName(channel);

    return (
      <button
        key={channel.id}
        type="button"
        className={[
          "sidebar-item",
          channel.id === activeChannelId && mainView === "channel" && !webAppOpen
            ? "is-active"
            : "",
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
        {/* Both counts when both matter: "1 mention" used to hide 4 other
            unread messages behind it. Mentions keep the signal colour. */}
        {unread > mentions && !muted ? (
          <span key={`u${unread}`} className={`badge ${mentions > 0 ? "badge-soft" : ""}`}>
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
        {mentions > 0 ? (
          <span key={`m${mentions}`} className="badge badge-mention" title="나를 부른 메시지">
            @{mentions}
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
        {/* Two views that are not channels: what was shared, and what
            happened to me. They live above the channel list, where Slack
            keeps its own nav, so a newcomer finds them without being told. */}
        <section className="sidebar-section sidebar-nav" aria-label="보기">
          <button
            type="button"
            className={`sidebar-item ${mainView === "activity" && !webAppOpen ? "is-active" : ""}`}
            onClick={() => setMainView("activity")}
            title="내가 참여한 스레드와 나를 부른 메시지"
          >
            <span className="sidebar-nav-icon">
              <IconActivity size={14} />
            </span>
            <span className="sidebar-label">활동</span>
          </button>
          <button
            type="button"
            className={`sidebar-item ${mainView === "files" && !webAppOpen ? "is-active" : ""}`}
            onClick={() => setMainView("files")}
            title="이 워크스페이스의 파일 모아보기"
          >
            <span className="sidebar-nav-icon">
              <IconFolder size={14} />
            </span>
            <span className="sidebar-label">파일</span>
          </button>
          <button
            type="button"
            className={`sidebar-item ${mainView === "saved" && !webAppOpen ? "is-active" : ""}`}
            onClick={() => setMainView("saved")}
            title="저장한 메시지와 리마인더"
          >
            <span className="sidebar-nav-icon">
              <IconBookmark size={14} />
            </span>
            <span className="sidebar-label">나중에</span>
          </button>
        </section>

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
              onClick={() => setBrowsing(true)}
              aria-label="채널 둘러보기"
              title="채널 둘러보기 — 팀의 공개 채널을 보고 참여합니다"
            >
              <IconSearch size={13} />
            </button>
            <button
              type="button"
              className="sidebar-add"
              onClick={() => setCreating((open) => !open)}
              aria-label="채널 만들기"
              title="채널 만들기"
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
                    setNewPrivate(false);
                  }
                }}
              />
              {/* A private channel could not be created from the UI at all —
                  the kind was hardcoded. One honest checkbox. */}
              <label className="sidebar-new-private">
                <input
                  type="checkbox"
                  checked={newPrivate}
                  onChange={(event) => setNewPrivate(event.target.checked)}
                />
                비공개 채널 (초대한 사람만 볼 수 있습니다)
              </label>
              {/* Enter from the checkbox did nothing; a real button always works. */}
              <button type="submit" className="sidebar-new-submit" disabled={!newName.trim()}>
                만들기
              </button>
            </form>
          ) : null}
          {groups.rooms.length + groups.sections.length <= 1 ? (
            <button
              type="button"
              className="sidebar-empty-action"
              onClick={() => setBrowsing(true)}
            >
              팀 채널 둘러보기
            </button>
          ) : null}
          {groups.sections.map(([section, list]) => {
            const hidden = folded[section] ?? false;
            const unreadInside = list.reduce(
              (sum, channel) => sum + (channel.membership?.unread_count ?? 0),
              0,
            );
            return (
              <div key={section} className="sidebar-subsection">
                <button
                  type="button"
                  className="sidebar-subsection-head"
                  onClick={() => toggleFold(section)}
                  aria-expanded={!hidden}
                >
                  <span className={`sidebar-fold ${hidden ? "is-folded" : ""}`} aria-hidden="true">
                    ▾
                  </span>
                  {section}
                  {hidden && unreadInside > 0 ? <span className="badge">{unreadInside}</span> : null}
                </button>
                {!hidden ? list.map(renderChannel) : null}
              </div>
            );
          })}
          {groups.rooms.map(renderChannel)}
        </section>

        <section className="sidebar-section">
          <h2>
            <span aria-hidden="true" />
            다이렉트 메시지
            <span className="sidebar-field">안 읽음</span>
            {/*
              The control the section was missing. A DM could only be opened
              through ⌘K — which needs you to already know the name and to know
              that ⌘K finds people — so the section had a line of help text
              where its add button should have been.
            */}
            <button
              type="button"
              className="sidebar-add"
              onClick={() => setStartingDm(true)}
              aria-label="새 대화"
              title="새 대화"
            >
              <IconPlus size={13} />
            </button>
          </h2>
          {groups.dms.map(renderChannel)}
          {groups.dms.length === 0 ? (
            <button
              type="button"
              className="sidebar-empty-action"
              onClick={() => setStartingDm(true)}
            >
              대화 시작하기
            </button>
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
            <strong>
              {me.display_name}
              {me.in_dnd ? (
                <span className="dnd-mark" title="방해 금지 중 — 알림이 오지 않습니다">
                  <IconMoon size={11} />
                </span>
              ) : null}
            </strong>
            <span>
              {me.status_emoji ?? ""} {me.status_text ?? `@${me.handle}`}
            </span>
          </div>
          <button
            type="button"
            className="sidebar-settings"
            onClick={() => setSettings(true)}
            aria-label="환경설정"
            title="환경설정"
          >
            <IconGear size={15} />
          </button>
        </footer>
      ) : null}
      <span className="sr-only">{people.size}명의 구성원</span>
      {startingDm ? <NewDm onClose={() => setStartingDm(false)} /> : null}
      {browsing ? <BrowseChannels onClose={() => setBrowsing(false)} /> : null}
    </nav>
  );
}
