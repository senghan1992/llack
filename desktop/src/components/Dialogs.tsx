import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  CalendarPlus,
  Copy,
  FolderKanban,
  Hash,
  Lock,
  Search,
  Settings,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { relativeTime } from "../lib/format";
import { renderBody } from "../lib/markdown";
import { Avatar } from "./Avatar";
import { MemberSelect } from "./MemberSelect";
import { Select } from "./Select";
import { Disclosure, FormRow, FormTitle } from "./Form";
import { useStore } from "../store/useStore";
import type { Channel, Member, Message, Role, SearchResult, User } from "../lib/types";

/* ── shell ───────────────────────────────────────────────────────────── */

export function Dialog({
  title,
  onClose,
  children,
  footer,
  wide,
  chart,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
  /** The chart is wide and short — it needs room for a year of months. */
  chart?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="scrim" onPointerDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        className={`dialog${wide ? " dialog--wide" : ""}${chart ? " dialog--chart" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="dialog__head">
          <h2 className="dialog__title">{title}</h2>
          <button type="button" className="iconbtn" aria-label="닫기" onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        {children}
        {footer ? <footer className="dialog__foot">{footer}</footer> : null}
      </div>
    </div>
  );
}

/* ── search ──────────────────────────────────────────────────────────── */

export function SearchDialog() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [busy, setBusy] = useState(false);
  const workspaceId = useStore((s) => s.workspaceId);
  const allChannels = useStore((s) => s.channels);
  const enterChannel = useStore((s) => s.enterChannel);
  const setDialog = useStore((s) => s.setDialog);

  useEffect(() => {
    const timer = setTimeout(async () => {
      const term = query.trim();
      if (!term || !workspaceId) {
        setResults([]);
        setChannels([]);
        return;
      }
      setBusy(true);
      try {
        const [messages, roomChannels] = await Promise.all([
          api.search(workspaceId, term, 24),
          api.channels(workspaceId),
        ]);
        setResults(messages);
        setChannels(
          roomChannels.filter((c) => c.name.toLowerCase().includes(term.toLowerCase())).slice(0, 6),
        );
      } catch {
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [query, workspaceId]);

  return (
    <Dialog title="검색" onClose={() => setDialog(null)} wide>
      <div className="find">
        <Search size={16} className="u-muted" aria-hidden="true" />
        <input
          className="find__input"
          autoFocus
          value={query}
          placeholder="메시지와 채널을 검색하세요"
          onChange={(event) => setQuery(event.target.value)}
          aria-label="검색어"
        />
        {busy ? <span className="u-small u-muted">찾는 중</span> : null}
      </div>

      <div className="dialog__body">
        {!query.trim() ? (
          <div className="u-col u-gap-4">
            <section>
              <p className="u-mb-2 u-tiny u-muted">채널</p>
              <div className="pick">
                {allChannels
                  .filter((c) => c.kind === "channel")
                  .slice(0, 6)
                  .map((channel) => (
                    <button
                      key={channel.id}
                      type="button"
                      className="pick__item"
                      onClick={() => {
                        void enterChannel(channel.id);
                        setDialog(null);
                      }}
                    >
                      <Hash size={14} className="u-muted" aria-hidden="true" />
                      <span className="pick__text">
                        <span className="pick__name">{channel.name}</span>
                        {channel.topic ? <span className="pick__sub">{channel.topic}</span> : null}
                      </span>
                      {channel.is_member ? null : (
                        <span className="u-tiny u-muted">들어가기</span>
                      )}
                    </button>
                  ))}
              </div>
            </section>
          </div>
        ) : null}

        {channels.length ? (
          <section className="u-mb-4">
            <p className="u-mb-2 u-tiny u-muted">채널</p>
            <div className="pick">
              {channels.map((channel) => (
                <button
                  key={channel.id}
                  type="button"
                  className="pick__item"
                  onClick={() => {
                    void enterChannel(channel.id);
                    setDialog(null);
                  }}
                >
                  {channel.is_private ? (
                    <Lock size={14} className="u-muted" aria-hidden="true" />
                  ) : (
                    <Hash size={14} className="u-muted" aria-hidden="true" />
                  )}
                  <span className="pick__text">
                    <span className="pick__name">{channel.name}</span>
                    {channel.topic ? <span className="pick__sub">{channel.topic}</span> : null}
                  </span>
                  {channel.is_member ? null : (
                    <span className="u-tiny u-muted">들어가기</span>
                  )}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {results.length ? (
          <section>
            <p className="u-mb-2 u-tiny u-muted">메시지</p>
            <div className="pick">
              {results.map((result) => (
                <button
                  key={result.message.id}
                  type="button"
                  className="pick__item u-row u-row--start"
                  onClick={() => {
                    void enterChannel(result.channel.id);
                    setDialog(null);
                  }}
                >
                  <Avatar user={result.message.author} size="sm" />
                  <span className="pick__text">
                    <span className="pick__name">
                      {result.message.author.name}
                      <span className="u-ml-2 u-tiny u-normal u-muted">
                        {result.channel.kind === "dm"
                          ? result.channel.name
                          : `#${result.channel.name}`}
                      </span>
                    </span>
                    <span
                      className="pick__sub u-clamp2 u-pre"
                      dangerouslySetInnerHTML={{ __html: renderBody(result.message.body) }}
                    />
                  </span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {query.trim() && !busy && !results.length && !channels.length ? (
          <div className="empty u-py-8">
            <span className="empty__mark" aria-hidden="true">
              <Search size={18} />
            </span>
            <p className="empty__title">일치하는 결과가 없습니다</p>
            <p className="empty__text">다른 단어로 검색해 보세요.</p>
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}

/* ── command palette ─────────────────────────────────────────────────── */

interface PaletteEntry {
  key: string;
  label: string;
  hint?: string;
  group: string;
  icon?: React.ReactNode;
  run: () => void;
}

export function PaletteDialog() {
  const channels = useStore((s) => s.channels);
  const recentRooms = useStore((s) => s.recentRooms);
  const members = useStore((s) => s.members);
  const projects = useStore((s) => s.projects);
  const enterChannel = useStore((s) => s.enterChannel);
  const startDm = useStore((s) => s.startDm);
  const openSchedule = useStore((s) => s.openSchedule);
  const openProjects = useStore((s) => s.openProjects);
  const openProject = useStore((s) => s.openProject);
  const setDialog = useStore((s) => s.setDialog);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const entries = useMemo<PaletteEntry[]>(() => {
    const channelEntries = channels.map((channel) => ({
      key: `channel-${channel.id}`,
      label: channel.kind === "dm" ? channel.name : `#${channel.name}`,
      hint:
        channel.kind === "dm"
          ? "직접 메시지"
          : channel.is_member
            ? "채널"
            : "채널 · 들어가기",
      group: "대화",
      icon:
        channel.kind === "dm" ? (
          <Avatar user={channel.dm_user ?? { id: channel.id, name: channel.name, avatar_color: null }} size="sm" />
        ) : (
          <Hash size={14} aria-hidden="true" />
        ),
      // A public channel you left stays in the workspace's directory —
      // opening it from here puts you back in it.
      run: () => void enterChannel(channel.id),
    }));

    const peopleEntries = members.map((member) => ({
      key: `person-${member.user.id}`,
      label: member.user.name,
      hint: member.user.title ?? "멤버",
      group: "사람",
      icon: <Avatar user={member.user} size="sm" />,
      run: () => void startDm(member.user.id),
    }));

    const projectEntries = projects.map((project) => ({
      key: `project-${project.id}`,
      label: project.name,
      hint: project.is_member ? "내 프로젝트" : "프로젝트",
      group: "프로젝트",
      icon: <FolderKanban size={14} aria-hidden="true" />,
      run: () => void openProject(project.id),
    }));

    const actionEntries: PaletteEntry[] = [
      {
        key: "action-search",
        label: "메시지 검색",
        hint: "워크스페이스 전체",
        group: "동작",
        icon: <Search size={14} aria-hidden="true" />,
        run: () => setDialog("search"),
      },
      {
        key: "action-schedule",
        label: "일정 열기",
        hint: "팀 달력",
        group: "동작",
        icon: <CalendarDays size={14} aria-hidden="true" />,
        run: () => void openSchedule(),
      },
      {
        key: "action-projects",
        label: "프로젝트 열기",
        hint: "할 일 보드",
        group: "동작",
        icon: <FolderKanban size={14} aria-hidden="true" />,
        run: () => void openProjects(),
      },
      {
        key: "action-new-project",
        label: "프로젝트 등록",
        group: "동작",
        icon: <FolderKanban size={14} aria-hidden="true" />,
        run: () => setDialog("project", null),
      },
      {
        key: "action-new-event",
        label: "일정 추가",
        hint: "회의 등록",
        group: "동작",
        icon: <CalendarPlus size={14} aria-hidden="true" />,
        run: () => setDialog("event", null),
      },
      {
        key: "action-channel",
        label: "새 채널 만들기",
        group: "동작",
        icon: <Hash size={14} aria-hidden="true" />,
        run: () => setDialog("newChannel"),
      },
      {
        key: "action-people",
        label: "멤버 보기",
        group: "동작",
        icon: <Users size={14} aria-hidden="true" />,
        run: () => setDialog("people"),
      },
      {
        key: "action-settings",
        label: "설정 열기",
        group: "동작",
        icon: <Settings size={14} aria-hidden="true" />,
        run: () => setDialog("settings"),
      },
    ];

    return [...channelEntries, ...projectEntries, ...peopleEntries, ...actionEntries];
  }, [channels, projects, members, enterChannel, startDm, openSchedule, openProjects, openProject, setDialog]);

  // The rooms you were in lately, newest first. A room that is gone —
  // you left it, it was deleted — is passed over in silence.
  const recentEntries = useMemo<PaletteEntry[]>(
    () =>
      recentRooms
        .map((id) => channels.find((channel) => channel.id === id))
        .filter((channel): channel is Channel => channel !== undefined)
        .filter((channel) => channel.kind === "dm" || channel.is_member !== false)
        .map((channel) => ({
          key: `recent-${channel.id}`,
          label: channel.kind === "dm" ? channel.name : `#${channel.name}`,
          hint: channel.kind === "dm" ? "직접 메시지" : "채널",
          group: "최근",
          icon:
            channel.kind === "dm" ? (
              <Avatar
                user={channel.dm_user ?? { id: channel.id, name: channel.name, avatar_color: null }}
                size="sm"
              />
            ) : (
              <Hash size={14} aria-hidden="true" />
            ),
          run: () => void enterChannel(channel.id),
        })),
    [recentRooms, channels, enterChannel],
  );

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    // With nothing typed, the rooms you were in lately come first, and
    // the rest of the list follows them. A word in the box puts the recent
    // rooms away — what you asked for is what you get.
    if (!term) return [...recentEntries, ...entries.slice(0, 12)];
    return entries.filter((entry) => entry.label.toLowerCase().includes(term)).slice(0, 20);
  }, [entries, recentEntries, query]);

  useEffect(() => setCursor(0), [query]);

  // The entry may open a dialog of its own — the palette steps aside only
  // when it is still the one on the screen.
  const closePalette = () => {
    if (useStore.getState().dialog === "palette") setDialog(null);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => Math.min(c + 1, filtered.length - 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const entry = filtered[cursor];
      if (entry) {
        entry.run();
        closePalette();
      }
    }
  };

  let lastGroup = "";

  return (
    <Dialog title="빠른 이동" onClose={() => setDialog(null)}>
      <div className="find">
        <Search size={16} className="u-muted" aria-hidden="true" />
        <input
          className="find__input"
          autoFocus
          value={query}
          placeholder="채널, 사람, 동작을 찾으세요"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          aria-label="빠른 이동 검색어"
        />
        <span className="kbd">esc</span>
      </div>

      <div className="dialog__body u-p0" ref={listRef}>
        {filtered.length === 0 ? (
          <div className="empty u-py-8">
            <p className="empty__title">일치하는 항목이 없습니다</p>
          </div>
        ) : null}

        {filtered.map((entry, index) => {
          const showGroup = entry.group !== lastGroup;
          lastGroup = entry.group;
          return (
            <div key={entry.key}>
              {showGroup ? <p className="palette__label">{entry.group}</p> : null}
              <button
                type="button"
                className="palette__item"
                aria-selected={index === cursor}
                onMouseEnter={() => setCursor(index)}
                onClick={() => {
                  entry.run();
                  closePalette();
                }}
              >
                {entry.icon}
                {entry.label}
                {entry.hint ? <span className="palette__key">{entry.hint}</span> : null}
              </button>
            </div>
          );
        })}
      </div>
    </Dialog>
  );
}

/* ── new channel ─────────────────────────────────────────────────────── */

export function NewChannelDialog() {
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createChannel = useStore((s) => s.createChannel);
  const setDialog = useStore((s) => s.setDialog);

  const teammates = members.filter((member) => member.user.id !== user?.id);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await createChannel({
        name: trimmed,
        topic: topic.trim() || undefined,
        is_private: isPrivate,
        member_ids: picked,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "채널을 만들지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title="새 채널"
      onClose={() => setDialog(null)}
      footer={
        <>
          <button type="button" className="btn" onClick={() => setDialog(null)}>
            취소
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={busy || !name.trim()}
          >
            만들기
          </button>
        </>
      }
    >
      <div className="dialog__body u-col u-gap-3">
        <div className="form">
          <FormTitle
            id="channel-name"
            value={name}
            onChange={setName}
            placeholder="새 채널 이름"
            label="채널 이름"
            hint="소문자와 하이픈으로 적습니다."
            autoFocus
            onEnter={() => void submit()}
          />

          <FormRow label="주제" htmlFor="channel-topic">
            <input
              id="channel-topic"
              className="field__input"
              value={topic}
              placeholder="이 채널에서 나누는 일을 한 줄로"
              onChange={(event) => setTopic(event.target.value)}
            />
          </FormRow>

          <FormRow label="구성원">
            <MemberSelect
              members={teammates}
              value={picked}
              onChange={setPicked}
              placeholder="함께할 사람 선택"
              emptyText="팀원이 없습니다."
            />
          </FormRow>

          <Disclosure summary="비공개" defaultOpen={isPrivate}>
            <FormRow label="비공개">
              <label className="sched__check">
                <input
                  type="checkbox"
                  checked={isPrivate}
                  onChange={(event) => setIsPrivate(event.target.checked)}
                />
                초대한 사람만 볼 수 있습니다
              </label>
            </FormRow>
          </Disclosure>
        </div>

        {error ? <p className="field__error">{error}</p> : null}
      </div>
    </Dialog>
  );
}

/* ── people ──────────────────────────────────────────────────────────── */

export function PeopleDialog() {
  const members = useStore((s) => s.members);
  const presence = useStore((s) => s.presence);
  const user = useStore((s) => s.user);
  const startDm = useStore((s) => s.startDm);
  const updateMemberRole = useStore((s) => s.updateMemberRole);
  const removeMember = useStore((s) => s.removeMember);
  const setDialog = useStore((s) => s.setDialog);
  const [query, setQuery] = useState("");

  const myRole = members.find((m) => m.user.id === user?.id)?.role;
  const canManage = myRole === "owner" || myRole === "admin";

  const filtered = members.filter((member) =>
    `${member.user.name} ${member.user.email} ${member.user.title ?? ""}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );

  return (
    <Dialog title="사람" onClose={() => setDialog(null)} wide>
      <div className="find">
        <Search size={16} className="u-muted" aria-hidden="true" />
        <input
          className="find__input"
          autoFocus
          value={query}
          placeholder="이름 또는 이메일로 찾기"
          onChange={(event) => setQuery(event.target.value)}
          aria-label="사람 검색"
        />
      </div>
      <div className="dialog__body">
        <div className="pick">
          {filtered.map((member) => (
            <div key={member.user.id} className="pick__item">
              <button
                type="button"
                className="u-row u-grow u-gap-3 u-left"
                onClick={() => void startDm(member.user.id)}
              >
                <Avatar
                  user={member.user}
                  presence={presence[member.user.id] ?? member.user.presence}
                />
                <span className="pick__text">
                  <span className="pick__name">{member.user.name}</span>
                  <span className="pick__sub">
                    {member.user.title ?? "멤버"} · {member.user.email}
                  </span>
                </span>
              </button>
              {canManage ? (
                <span className="u-row u-gap-2">
                  <Select
                    size="sm"
                    value={member.role}
                    ariaLabel={`${member.user.name} 권한`}
                    onChange={(next) =>
                      void updateMemberRole(member.user.id, next as Role)
                    }
                    options={[
                      { value: "owner", label: "소유자" },
                      { value: "admin", label: "관리자" },
                      { value: "member", label: "멤버" },
                    ]}
                  />
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label={`${member.user.name} 내보내기`}
                    onClick={() => void removeMember(member.user.id)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </span>
              ) : (
                <span className="u-tiny u-muted">{member.role}</span>
              )}
            </div>
          ))}
          {filtered.length === 0 ? (
            <p className="u-px-2 u-py-6 u-center-text u-small u-muted">
              일치하는 사람이 없습니다.
            </p>
          ) : null}
        </div>
      </div>
    </Dialog>
  );
}

/* ── new direct message ──────────────────────────────────────────────── */

export function NewDmDialog() {
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const startDm = useStore((s) => s.startDm);
  const setDialog = useStore((s) => s.setDialog);
  const [query, setQuery] = useState("");

  const filtered = members.filter(
    (member) =>
      member.user.id !== user?.id &&
      member.user.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <Dialog title="새 직접 메시지" onClose={() => setDialog(null)}>
      <div className="find">
        <Search size={16} className="u-muted" aria-hidden="true" />
        <input
          className="find__input"
          autoFocus
          value={query}
          placeholder="이름으로 찾기"
          onChange={(event) => setQuery(event.target.value)}
          aria-label="사람 검색"
        />
      </div>
      <div className="dialog__body">
        <div className="pick">
          {filtered.map((member) => (
            <button
              key={member.user.id}
              type="button"
              className="pick__item"
              onClick={() => void startDm(member.user.id)}
            >
              <Avatar user={member.user} presence={member.user.presence} />
              <span className="pick__text">
                <span className="pick__name">{member.user.name}</span>
                <span className="pick__sub">{member.user.title ?? "멤버"}</span>
              </span>
            </button>
          ))}
          {filtered.length === 0 ? (
            <p className="u-px-2 u-py-6 u-center-text u-small u-muted">
              일치하는 사람이 없습니다.
            </p>
          ) : null}
        </div>
      </div>
    </Dialog>
  );
}

/* ── pins ────────────────────────────────────────────────────────────── */

export function PinsDialog() {
  const channel = useStore((s) => s.channels.find((c) => c.id === s.activeId) ?? null);
  const setDialog = useStore((s) => s.setDialog);
  const [pins, setPins] = useState<Message[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!channel) return;
    api
      .pins(channel.id)
      .then(setPins)
      .catch(() => setPins([]))
      .finally(() => setLoaded(true));
  }, [channel]);

  return (
    <Dialog title="고정된 메시지" onClose={() => setDialog(null)}>
      <div className="dialog__body">
        {!loaded ? (
          <div className="u-col u-gap-3" aria-busy="true">
            {[0, 1, 2].map((row) => (
              <div key={row} className="skel u-h-12 u-full" />
            ))}
          </div>
        ) : pins.length === 0 ? (
          <div className="empty u-py-8">
            <p className="empty__title">고정된 메시지가 없습니다</p>
            <p className="empty__text">메시지 메뉴에서 고정한 항목이 여기에 모입니다.</p>
          </div>
        ) : (
          <div className="pick">
            {pins.map((message) => (
              <div key={message.id} className="pick__item u-row u-row--start">
                <Avatar user={message.author} size="sm" />
                <span className="pick__text">
                  <span className="pick__name">
                    {message.author.name}
                    <span className="u-ml-2 u-tiny u-normal u-muted">
                      {relativeTime(message.created_at)}
                    </span>
                  </span>
                  <span
                    className="pick__sub u-pre"
                    dangerouslySetInnerHTML={{ __html: renderBody(message.body) }}
                  />
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}

/* ── channel settings ────────────────────────────────────────────────── */

export function ChannelSettingsDialog() {
  const activeId = useStore((s) => s.activeId);
  const dialogTarget = useStore((s) => s.dialogTarget);
  // The dialog acts on the channel it was opened for — the one in the header,
  // or the one picked from the sidebar menu — and falls back to the open room.
  const targetId = dialogTarget ?? activeId;
  const channel = useStore((s) => s.channels.find((c) => c.id === (s.dialogTarget ?? s.activeId)) ?? null);
  const updateChannel = useStore((s) => s.updateChannel);
  const leaveChannel = useStore((s) => s.leaveChannel);
  const setDialog = useStore((s) => s.setDialog);

  const [name, setName] = useState(channel?.name ?? "");
  const [topic, setTopic] = useState(channel?.topic ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setName(channel?.name ?? "");
    setTopic(channel?.topic ?? "");
  }, [channel?.id, channel?.name, channel?.topic]);

  if (!channel || !targetId) return null;

  const save = async () => {
    setBusy(true);
    try {
      await updateChannel(targetId, {
        name: name.trim() || undefined,
        topic: topic.trim(),
      });
      setDialog(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={channel.kind === "dm" ? "대화 정보" : "채널 설정"}
      onClose={() => setDialog(null)}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setDialog(null);
              void leaveChannel(targetId);
            }}
          >
            채널 나가기
          </button>
          {channel.kind === "channel" ? (
            <button
              type="button"
              className="btn"
              onClick={() => setDialog("addPeople", targetId)}
            >
              사람 추가
            </button>
          ) : null}
          <span className="u-grow" />
          <button type="button" className="btn" onClick={() => setDialog(null)}>
            취소
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void save()}
            disabled={busy}
          >
            저장
          </button>
        </>
      }
    >
      <div className="dialog__body grid gap-4">
        {channel.kind === "dm" ? (
          <p className="u-small u-muted">
            {channel.dm_user?.name}님과의 대화입니다. 이름과 주제는 바꿀 수 없습니다.
          </p>
        ) : (
          <>
            <div className="field">
              <label className="field__label" htmlFor="settings-name">
                채널 이름
              </label>
              <input
                id="settings-name"
                className="field__input"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="settings-topic">
                주제
              </label>
              <input
                id="settings-topic"
                className="field__input"
                value={topic}
                placeholder="이 채널에서 나누는 일을 한 줄로"
                onChange={(event) => setTopic(event.target.value)}
              />
            </div>
            <p className="field__hint">
              {channel.is_private
                ? "비공개 채널입니다. 초대된 멤버만 볼 수 있습니다."
                : "공개 채널입니다. 워크스페이스의 모든 멤버가 볼 수 있습니다."}
            </p>
          </>
        )}
      </div>
    </Dialog>
  );
}

/* ── invites ─────────────────────────────────────────────────────────── */

export function InviteDialog() {
  const invites = useStore((s) => s.invites);
  const loadInvites = useStore((s) => s.loadInvites);
  const createInvite = useStore((s) => s.createInvite);
  const revokeInvite = useStore((s) => s.revokeInvite);
  const setDialog = useStore((s) => s.setDialog);
  const toast = useStore((s) => s.toast);

  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<string | null>(null);

  useEffect(() => {
    void loadInvites();
  }, [loadInvites]);

  const submit = async () => {
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const invite = await createInvite(email);
      setFresh(invite.token);
      setEmail("");
      toast(`${invite.email}님을 초대했습니다`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "초대를 만들지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const copy = async (token: string) => {
    try {
      await navigator.clipboard?.writeText(token);
      toast("초대 코드를 복사했습니다");
    } catch {
      toast("코드를 복사하지 못했습니다");
    }
  };

  return (
    <Dialog title="팀원 초대" onClose={() => setDialog(null)} wide>
      <div className="dialog__body grid gap-4">
        <div className="field">
          <label className="field__label" htmlFor="invite-email">
            이메일
          </label>
          <div className="u-row u-gap-2">
            <input
              id="invite-email"
              className="field__input u-grow"
              type="email"
              value={email}
              placeholder="name@company.com"
              onChange={(event) => setEmail(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
            />
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void submit()}
              disabled={busy || !email.trim()}
            >
              <UserPlus size={14} aria-hidden="true" />
              초대
            </button>
          </div>
          <p className="field__hint">
            만든 뒤 아래 코드를 팀원에게 전달하세요. 코드는 7일 뒤에 만료됩니다.
          </p>
          {error ? <p className="field__error">{error}</p> : null}
        </div>

        {fresh ? (
          <div className="invite-fresh">
            <p className="invite-fresh__label">새 초대 코드</p>
            <div className="u-row u-gap-3">
              <code className="invite-fresh__code">{fresh}</code>
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => void copy(fresh)}
              >
                <Copy size={13} aria-hidden="true" />
                복사
              </button>
            </div>
          </div>
        ) : null}

        <section>
          <p className="u-mb-2 u-tiny u-muted">대기 중인 초대</p>
          {invites.length === 0 ? (
            <p className="u-px-2 u-py-6 u-small u-muted">
              아직 보낸 초대가 없습니다.
            </p>
          ) : (
            <div className="pick">
              {invites.map((invite) => (
                <div key={invite.id} className="pick__item u-row u-row--start">
                  <span className="pick__text">
                    <span className="pick__name">{invite.email}</span>
                    <span className="pick__sub">
                      <code className="invite-code">{invite.token}</code>
                    </span>
                  </span>
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label={`${invite.email} 초대 코드 복사`}
                    onClick={() => void copy(invite.token)}
                  >
                    <Copy size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label={`${invite.email} 초대 취소`}
                    onClick={() => void revokeInvite(invite.id)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Dialog>
  );
}

/* ── room members ────────────────────────────────────────────────────── */

export function AddPeopleDialog() {
  const targetId = useStore((s) => s.dialogTarget ?? s.activeId);
  const channel = useStore((s) => s.channels.find((c) => c.id === (s.dialogTarget ?? s.activeId)) ?? null);
  const members = useStore((s) => s.members);
  // A selector that builds a new array every call would loop React forever —
  // the fallback has to be the same object every time.
  const roster = useStore((s) => (targetId ? s.channelMembers[targetId] : undefined));
  const loadChannelMembers = useStore((s) => s.loadChannelMembers);
  const addChannelMember = useStore((s) => s.addChannelMember);
  const setDialog = useStore((s) => s.setDialog);

  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (targetId) void loadChannelMembers(targetId);
  }, [targetId, loadChannelMembers]);

  if (!channel || !targetId) return null;

  const inside = new Set((roster ?? []).map((member) => member.user.id));
  const needle = query.trim().toLowerCase();
  const candidates = members.filter(
    (member) =>
      !inside.has(member.user.id) &&
      `${member.user.name} ${member.user.email} ${member.user.title ?? ""}`
        .toLowerCase()
        .includes(needle),
  );

  const invite = async (userId: string) => {
    setBusy(userId);
    try {
      await addChannelMember(targetId, userId);
    } catch {
      /* the store's toast carries the reason */
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog
      title={channel.kind === "dm" ? "대화 구성원" : `${channel.name}에 사람 추가`}
      onClose={() => setDialog(null)}
    >
      <div className="find">
        <Search size={16} className="u-muted" aria-hidden="true" />
        <input
          className="find__input"
          autoFocus
          value={query}
          placeholder="이름 또는 이메일로 찾기"
          onChange={(event) => setQuery(event.target.value)}
          aria-label="사람 검색"
        />
      </div>
      <div className="dialog__body">
        <div className="pick">
          {candidates.map((member) => (
            <div key={member.user.id} className="pick__item">
              <button
                type="button"
                className="u-row u-grow u-gap-3 u-left"
                disabled={busy === member.user.id}
                onClick={() => void invite(member.user.id)}
              >
                <Avatar user={member.user} />
                <span className="pick__text">
                  <span className="pick__name">{member.user.name}</span>
                  <span className="pick__sub">
                    {member.user.title ?? "멤버"} · {member.user.email}
                  </span>
                </span>
              </button>
              <span className="u-tiny u-muted">초대</span>
            </div>
          ))}
          {candidates.length === 0 ? (
            <p className="u-small u-muted u-px-3 u-py-2">
              {needle ? "그런 사람이 없습니다." : "팀원이 이미 모두 이 방에 있습니다."}
            </p>
          ) : null}
        </div>
      </div>
    </Dialog>
  );
}

/* ── room leave ───────────────────────────────────────────────────────── */

export function LeaveChannelDialog() {
  const targetId = useStore((s) => s.dialogTarget);
  const channel = useStore((s) => s.channels.find((c) => c.id === s.dialogTarget) ?? null);
  const leaveChannel = useStore((s) => s.leaveChannel);
  const setDialog = useStore((s) => s.setDialog);

  const [busy, setBusy] = useState(false);

  if (!channel || !targetId) return null;

  return (
    <Dialog
      title="방 나가기"
      onClose={() => setDialog(null)}
      footer={
        <>
          <span className="u-grow" />
          <button type="button" className="btn" onClick={() => setDialog(null)}>
            취소
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => {
              setBusy(true);
              void leaveChannel(targetId);
            }}
            disabled={busy}
          >
            나가기
          </button>
        </>
      }
    >
      <div className="dialog__body grid gap-3">
        <p>
          <strong>#{channel.name}</strong>에서 나가시겠습니까?
        </p>
        <p className="u-small u-muted">
          {channel.is_private
            ? "비공개 방입니다. 나간 뒤에는 초대받아야 다시 들어갈 수 있습니다."
            : "공개 방입니다. 나간 뒤에도 ⌘K에서 찾아 다시 들어갈 수 있습니다."}
        </p>
      </div>
    </Dialog>
  );
}

/* ── direct message delete ───────────────────────────────────────────── */

export function DeleteDmDialog() {
  const targetId = useStore((s) => s.dialogTarget);
  const channel = useStore((s) => s.channels.find((c) => c.id === s.dialogTarget) ?? null);
  const deleteDm = useStore((s) => s.deleteDm);
  const setDialog = useStore((s) => s.setDialog);
  const reportError = useStore((s) => s.reportError);

  const [busy, setBusy] = useState(false);

  if (!channel || !targetId) return null;

  const other = channel.dm_user?.name ?? channel.name;

  return (
    <Dialog
      title="대화 삭제"
      onClose={() => setDialog(null)}
      footer={
        <>
          <span className="u-grow" />
          <button type="button" className="btn" onClick={() => setDialog(null)}>
            취소
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => {
              setBusy(true);
              void deleteDm(targetId).catch((error) => {
                setBusy(false);
                reportError(error, "대화를 삭제하지 못했습니다");
              });
            }}
            disabled={busy}
          >
            삭제
          </button>
        </>
      }
    >
      <div className="dialog__body grid gap-3">
        <p>
          <strong>{other}</strong>님과의 대화를 삭제할까요?
        </p>
        <p className="u-small u-muted">
          이 대화와 안의 메시지가 모두 사라집니다. 되돌릴 수 없습니다.
        </p>
      </div>
    </Dialog>
  );
}

export type { Member, User };
