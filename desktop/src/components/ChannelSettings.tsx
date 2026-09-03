/**
 * 채널 설정 — 이름·주제, 구성원, 그리고 채널의 마지막(보관·나가기).
 *
 * Every control states its own rule instead of silently disabling: a member
 * who cannot rename the channel is told it takes a channel admin, not shown a
 * dead input. The server re-checks every privileged change; the role here
 * only decides what to *offer*.
 *
 * There is no hard delete. Archiving is the product's deletion: the channel
 * leaves the sidebar and refuses new messages, but history stays searchable —
 * and the copy says exactly that, so nobody archives expecting a shredder.
 */

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/ipc";
import type { Channel, ChannelMemberEntry, Id } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { IconClose, IconSearch } from "./Icon";

export function ChannelSettings({
  channel,
  onClose,
}: {
  channel: Channel;
  onClose: () => void;
}) {
  const me = useApp((state) => state.me);
  const people = useApp((state) => state.people);
  const refreshSidebar = useApp((state) => state.refreshSidebar);
  const leaveChannel = useApp((state) => state.leaveChannel);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const isAdmin = channel.membership?.role === "admin";

  const [name, setName] = useState(channel.name ?? "");
  const [topic, setTopic] = useState(channel.topic ?? "");
  const [saving, setSaving] = useState(false);

  const [members, setMembers] = useState<ChannelMemberEntry[] | null>(null);
  const [inviteQuery, setInviteQuery] = useState("");
  const [busyUserId, setBusyUserId] = useState<Id | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .channelMembers(channel.id)
      .then((rows) => {
        if (alive) setMembers(rows);
      })
      .catch((error) => {
        if (alive) {
          setMembers([]);
          reportError(error, "구성원 목록을 불러오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, [channel.id, reportError]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const memberIds = useMemo(
    () => new Set((members ?? []).map((entry) => entry.user.id)),
    [members],
  );

  /** Workspace people who are not in the channel yet, filtered by the query. */
  const invitable = useMemo(() => {
    const needle = inviteQuery.trim().toLowerCase();
    if (!needle) return [];
    return [...people.values()]
      .filter(
        (person) =>
          !memberIds.has(person.id) &&
          (person.display_name.toLowerCase().includes(needle) ||
            person.handle.toLowerCase().includes(needle)),
      )
      .slice(0, 6);
  }, [people, memberIds, inviteQuery]);

  const dirty = name !== (channel.name ?? "") || topic !== (channel.topic ?? "");

  const save = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const patch: { name?: string; topic?: string } = {};
      if (name !== (channel.name ?? "")) patch.name = name.trim();
      if (topic !== (channel.topic ?? "")) patch.topic = topic.trim();
      await api.updateChannel(channel.id, patch);
      await refreshSidebar();
      showBanner("info", "채널 정보를 저장했습니다.");
    } catch (error) {
      reportError(error, "채널 정보를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const addMember = async (userId: Id) => {
    setBusyUserId(userId);
    try {
      await api.addChannelMembers(channel.id, [userId]);
      setMembers(await api.channelMembers(channel.id));
      setInviteQuery("");
      await refreshSidebar();
    } catch (error) {
      reportError(error, "구성원을 추가하지 못했습니다.");
    } finally {
      setBusyUserId(null);
    }
  };

  /** Hand admin to a teammate (or take it back). The creator was the only
   *  admin for life before this; one holiday froze the channel. */
  const setRole = async (userId: Id, role: "admin" | "member") => {
    setBusyUserId(userId);
    try {
      const updated = await api.setChannelMemberRole(channel.id, userId, role);
      setMembers((current) =>
        (current ?? []).map((entry) => (entry.user.id === userId ? updated : entry)),
      );
      showBanner(
        "info",
        role === "admin"
          ? `${updated.user.display_name} 님을 채널 관리자로 지정했습니다.`
          : `${updated.user.display_name} 님의 관리자 권한을 해제했습니다.`,
      );
    } catch (error) {
      reportError(error, "권한을 바꾸지 못했습니다.");
    } finally {
      setBusyUserId(null);
    }
  };

  const removeMember = async (userId: Id) => {
    setBusyUserId(userId);
    try {
      await api.removeChannelMember(channel.id, userId);
      setMembers((current) =>
        (current ?? []).filter((entry) => entry.user.id !== userId),
      );
      await refreshSidebar();
    } catch (error) {
      reportError(error, "구성원을 제거하지 못했습니다.");
    } finally {
      setBusyUserId(null);
    }
  };

  const [notificationLevel, setNotificationLevel] = useState(
    channel.membership?.notification_level ?? "all",
  );

  // Sidebar section: mine, not the channel's. Existing names are offered so a
  // "프로젝트" group does not become "프로젠트" and "프로젝트" by a typo.
  const allChannels = useApp((state) => state.channels);
  const knownSections = useMemo(
    () =>
      [...new Set(allChannels.map((entry) => entry.membership?.section).filter(Boolean) as string[])].sort(
        (a, b) => a.localeCompare(b, "ko"),
      ),
    [allChannels],
  );
  const [section, setSection] = useState(channel.membership?.section ?? "");
  const [sectionBusy, setSectionBusy] = useState(false);
  const saveSection = async (value: string) => {
    setSectionBusy(true);
    try {
      await api.updateMembership(channel.id, { section: value.trim() || null });
      await refreshSidebar();
      showBanner("info", value.trim() ? `사이드바 '${value.trim()}' 섹션으로 옮겼습니다.` : "섹션에서 뺐습니다.");
    } catch (error) {
      reportError(error, "섹션을 바꾸지 못했습니다.");
    } finally {
      setSectionBusy(false);
    }
  };

  // Retention override (admin): days, or empty for the workspace default.
  const [retention, setRetention] = useState(
    channel.retention_days != null ? String(channel.retention_days) : "",
  );
  const [retentionBusy, setRetentionBusy] = useState(false);
  const saveRetention = async () => {
    setRetentionBusy(true);
    try {
      const days = retention.trim() === "" ? null : Math.max(1, Number(retention));
      await api.updateChannel(channel.id, { retention_days: days });
      await refreshSidebar();
      showBanner(
        "info",
        days === null
          ? "이 채널은 워크스페이스 보관 정책을 따릅니다."
          : `이 채널의 메시지는 ${days}일 뒤 자동 삭제됩니다.`,
      );
    } catch (error) {
      reportError(error, "보관 기간을 바꾸지 못했습니다.");
    } finally {
      setRetentionBusy(false);
    }
  };

  const changeNotificationLevel = async (level: string) => {
    const previous = notificationLevel;
    setNotificationLevel(level as typeof notificationLevel);
    try {
      await api.updateMembership(channel.id, { notification_level: level });
      await refreshSidebar();
    } catch (error) {
      setNotificationLevel(previous);
      reportError(error, "알림 수준을 바꾸지 못했습니다.");
    }
  };

  // Archiving empties everyone's sidebar of this channel; one extra click is
  // cheap insurance against a slip on a button with no undo.
  const [confirmingArchive, setConfirmingArchive] = useState(false);

  const archive = async () => {
    if (!confirmingArchive) {
      setConfirmingArchive(true);
      return;
    }
    try {
      await api.updateChannel(channel.id, { is_archived: true });
      await refreshSidebar();
      showBanner("info", "채널을 보관했습니다. 기록은 검색에 남습니다.");
      onClose();
    } catch (error) {
      reportError(error, "채널을 보관하지 못했습니다.");
      setConfirmingArchive(false);
    }
  };

  const leave = async () => {
    await leaveChannel(channel.id);
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal channel-settings"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="채널 설정"
      >
        <header className="modal-header">
          <h2># {channel.name ?? "채널"} 설정</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body settings-body">
          <section className="settings-section">
            <h3>이름과 주제</h3>
            <label className="settings-field">
              <span>채널 이름</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={!isAdmin}
                maxLength={80}
              />
            </label>
            {!isAdmin ? (
              <p className="settings-hint">
                이름 변경과 보관은 채널 관리자만 할 수 있습니다. 주제는 누구나
                바꿀 수 있습니다.
              </p>
            ) : null}
            <label className="settings-field">
              <span>주제</span>
              <input
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="이 채널이 무엇을 다루는지 한 줄로"
                maxLength={250}
              />
            </label>
            <div className="settings-actions">
              <button
                type="button"
                className="settings-primary"
                onClick={() => void save()}
                disabled={!dirty || saving}
              >
                {saving ? "저장 중…" : "저장"}
              </button>
            </div>
          </section>

          <section className="settings-section">
            <h3>구성원 {members ? `${members.length}명` : ""}</h3>
            <div className="share-field">
              <IconSearch size={14} />
              <input
                value={inviteQuery}
                onChange={(event) => setInviteQuery(event.target.value)}
                placeholder="이름이나 핸들로 검색해 추가"
                aria-label="추가할 사람 검색"
              />
            </div>
            {invitable.length > 0 ? (
              <ul className="member-list member-candidates">
                {invitable.map((person) => (
                  <li key={person.id}>
                    <Avatar
                      id={person.id}
                      name={person.display_name}
                      avatarUrl={person.avatar_url}
                      size={22}
                      isBot={person.is_bot}
                    />
                    <span className="member-name">{person.display_name}</span>
                    <span className="member-handle">@{person.handle}</span>
                    <button
                      type="button"
                      className="member-action"
                      onClick={() => void addMember(person.id)}
                      disabled={busyUserId === person.id}
                    >
                      추가
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <ul className="member-list">
              {members === null ? (
                <li className="modal-empty">불러오는 중…</li>
              ) : (
                members.map((entry) => (
                  <li key={entry.id}>
                    <Avatar
                      id={entry.user.id}
                      name={entry.user.display_name}
                      avatarUrl={entry.user.avatar_url}
                      size={22}
                      isBot={entry.user.is_bot}
                    />
                    <span className="member-name">
                      {entry.user.display_name}
                      {entry.user.id === me?.id ? " (나)" : ""}
                    </span>
                    <span className="member-handle">@{entry.user.handle}</span>
                    {entry.role === "admin" ? (
                      <span className="member-role">관리자</span>
                    ) : null}
                    {isAdmin && entry.user.id !== me?.id ? (
                      <>
                        <button
                          type="button"
                          className="member-action"
                          onClick={() =>
                            void setRole(
                              entry.user.id,
                              entry.role === "admin" ? "member" : "admin",
                            )
                          }
                          disabled={busyUserId === entry.user.id}
                          title={
                            entry.role === "admin"
                              ? "관리자 권한 해제"
                              : "채널 관리자로 지정 (이름 변경·보관·구성원 제거 가능)"
                          }
                        >
                          {entry.role === "admin" ? "관리자 해제" : "관리자로"}
                        </button>
                        <button
                          type="button"
                          className="member-action is-destructive"
                          onClick={() => void removeMember(entry.user.id)}
                          disabled={busyUserId === entry.user.id}
                          title="채널에서 제거 (다시 추가할 수 있습니다)"
                        >
                          제거
                        </button>
                      </>
                    ) : null}
                  </li>
                ))
              )}
            </ul>
          </section>

          <section className="settings-section">
            <h3>알림</h3>
            <p className="settings-hint">
              이 채널의 새 메시지를 언제 알릴지 정합니다. 음소거(머리글의 종)와
              별개로, 알림 수준은 토스트와 배지 집계에 적용됩니다.
            </p>
            <label className="settings-field">
              <span>알림 수준</span>
              <select
                value={notificationLevel}
                onChange={(event) => void changeNotificationLevel(event.target.value)}
              >
                <option value="all">모든 메시지</option>
                <option value="mentions">나를 부르는 멘션만</option>
                <option value="nothing">알리지 않음</option>
              </select>
            </label>
          </section>

          <section className="settings-section">
            <h3>사이드바 섹션</h3>
            <p className="settings-hint">
              나만의 묶음입니다. 같은 이름을 쓴 채널들이 사이드바에서 한 묶음으로 보이고 접을 수 있습니다.
            </p>
            <div className="linkapp-row">
              <input
                className="settings-invite-input"
                list={`sections-${channel.id}`}
                value={section}
                onChange={(event) => setSection(event.target.value)}
                placeholder="예: 프로젝트, 참고용 (비우면 섹션 없음)"
                maxLength={80}
                aria-label="사이드바 섹션"
                onKeyDown={(event) => {
                  if (event.key === "Enter") void saveSection(section);
                }}
              />
              <datalist id={`sections-${channel.id}`}>
                {knownSections.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <button
                type="button"
                className="settings-primary"
                onClick={() => void saveSection(section)}
                disabled={sectionBusy || (section.trim() || null) === (channel.membership?.section ?? null)}
              >
                적용
              </button>
            </div>
          </section>

          {isAdmin ? (
            <section className="settings-section">
              <h3>보관 기간</h3>
              <p className="settings-hint">
                이 채널만의 보관 기간입니다. 비우면 워크스페이스 정책(환경설정 → 보관 정책)을 따릅니다. 기한이
                지난 메시지는 매시간 자동으로 지워지고 되돌릴 수 없습니다.
              </p>
              <div className="linkapp-row">
                <input
                  className="settings-invite-input"
                  type="number"
                  min={1}
                  max={3650}
                  value={retention}
                  onChange={(event) => setRetention(event.target.value)}
                  placeholder="일 수 (비우면 기본 정책)"
                  aria-label="보관 기간(일)"
                />
                <button
                  type="button"
                  className="settings-primary"
                  onClick={() => void saveRetention()}
                  disabled={retentionBusy}
                >
                  저장
                </button>
              </div>
            </section>
          ) : null}

          <section className="settings-section settings-danger">
            <h3>정리</h3>
            <div className="settings-danger-row">
              <div>
                <strong>채널에서 나가기</strong>
                <p>사이드바에서 사라집니다. 언제든 다시 참여할 수 있습니다.</p>
              </div>
              <button type="button" onClick={() => void leave()}>
                나가기
              </button>
            </div>
            <div className="settings-danger-row">
              <div>
                <strong>채널 보관</strong>
                <p>
                  {isAdmin
                    ? "모든 구성원의 목록에서 사라지고 새 메시지를 받지 않습니다. 기록은 검색에 남습니다."
                    : "채널 관리자만 보관할 수 있습니다."}
                </p>
              </div>
              <button
                type="button"
                className="is-destructive"
                onClick={() => void archive()}
                onMouseLeave={() => setConfirmingArchive(false)}
                disabled={!isAdmin}
              >
                {confirmingArchive ? "정말 보관할까요?" : "보관"}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
