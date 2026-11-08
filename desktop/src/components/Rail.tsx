import { useRef, useState } from "react";
import {
  Building2,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  FolderKanban,
  Hash,
  Lock,
  LogOut,
  MessageSquare,
  PanelLeft,
  PanelRight,
  Plus,
  Search,
  Settings,
  SquareArrowOutUpRight,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { Menu, MenuSub } from "./Menu";
import { api } from "../lib/api";
import { PRESENCE_STATES, presenceLabel } from "../lib/presence";
import { openRoomWindow } from "../lib/popout";
import { useStore } from "../store/useStore";

export function Rail() {
  const channels = useStore((s) => s.channels);
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const presence = useStore((s) => s.presence);
  const activeId = useStore((s) => s.activeId);
  const view = useStore((s) => s.view);
  const board = useStore((s) => s.board);
  const idle = useStore((s) => s.idle);
  const workspaceName = useStore((s) => s.workspaceName);
  const openChannel = useStore((s) => s.openChannel);
  const openSchedule = useStore((s) => s.openSchedule);
  const openProjects = useStore((s) => s.openProjects);
  const openOrg = useStore((s) => s.openOrg);
  const orgManagedUnitIds = useStore((s) => s.orgManagedUnitIds);
  const myTasks = useStore((s) => s.myTasks);
  const updateProfile = useStore((s) => s.updateProfile);
  const setDialog = useStore((s) => s.setDialog);
  const reportError = useStore((s) => s.reportError);
  const signOut = useStore((s) => s.signOut);
  const loadWorkspace = useStore((s) => s.loadWorkspace);
  const workspaceId = useStore((s) => s.workspaceId);
  const railCollapsed = useStore((s) => s.railCollapsed);
  const setRailCollapsed = useStore((s) => s.setRailCollapsed);

  const [workspaceAnchor, setWorkspaceAnchor] = useState<HTMLElement | null>(null);
  const [meAnchor, setMeAnchor] = useState<HTMLElement | null>(null);
  const [presenceOpen, setPresenceOpen] = useState(false);
  const statusItemRef = useRef<HTMLButtonElement>(null);
  const [workspaces, setWorkspaces] = useState<{ id: string; name: string }[]>([]);
  const [rowMenu, setRowMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  /** The folded rail opens over the conversation while the pointer — or the
      keyboard — is on it. It is a look, not a state: nothing is chosen
      while it is open. */
  const [peek, setPeek] = useState(false);
  /** The strip itself: marks only, no words. */
  const folded = railCollapsed && !peek;

  // One selection at a time. The board may sit *beside* the conversation, but
  // the rail still says where the eye is: the surface that was picked last.
  // The other one keeps a thin mark of its own, so nothing is lost. A
  // cleared screen selects nothing at all — not even a room that stayed.
  const boardKind = board ?? (view === "channel" ? null : view);
  const chatFocused = !idle && board === null && view === "channel";
  const besideRoom = !idle && board !== null;

  // The organization is the administrator's own page: it is there for the
  // owners and the admins of the workspace, and for the people who manage
  // at least one unit.
  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const orgVisible =
    myRole === "owner" || myRole === "admin" || orgManagedUnitIds.length > 0;
  const orgFocused = !idle && board === null && view === "org";

  // Only the rooms you are in. A public channel stays in the workspace's
  // directory after you leave it — the palette still finds it, and opening
  // it from there joins you back. A channel that never carried the flag (an
  // older API) stays in the list rather than vanishing from the rail.
  const roomChannels = channels.filter((c) => c.kind === "channel" && c.is_member !== false);
  const dms = channels.filter((c) => c.kind === "dm");
  const menuTarget = rowMenu ? channels.find((c) => c.id === rowMenu.id) ?? null : null;

  const openWorkspaceMenu = async (anchor: HTMLElement) => {
    // The same button that opened the menu closes it again.
    if (workspaceAnchor) {
      setWorkspaceAnchor(null);
      return;
    }
    setWorkspaceAnchor(anchor);
    try {
      const list = await api.workspaces();
      setWorkspaces(list.map((w) => ({ id: w.id, name: w.name })));
    } catch {
      setWorkspaces([]);
    }
  };

  return (
    <nav
      className={`rail${folded ? " rail--collapsed" : ""}${peek ? " rail--peek" : ""}`}
      aria-label="채널과 대화"
      onMouseEnter={() => railCollapsed && setPeek(true)}
      onMouseLeave={() => setPeek(false)}
      onFocusCapture={() => railCollapsed && setPeek(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPeek(false);
      }}
    >
      <div className="rail__top">
        <div className="rail__brand">
          <button
            type="button"
            className="wkey"
            onClick={(event) => void openWorkspaceMenu(event.currentTarget)}
            aria-haspopup="menu"
            aria-expanded={Boolean(workspaceAnchor)}
          >
            <span className="wkey__mark" aria-hidden="true">
              {(workspaceName || "L").slice(0, 1)}
            </span>
            <span className="wkey__name">{workspaceName || "워크스페이스"}</span>
            <ChevronDown size={14} className="wkey__chev" aria-hidden="true" />
          </button>
          {/* The rail's own shape: folded to a strip of icons, or open
              again. The key stays in the same place in both. */}
          <button
            type="button"
            className="iconbtn rail__toggle"
            aria-label={railCollapsed ? "레일 펼치기" : "레일 접기"}
            title={railCollapsed ? "레일 펼치기 (⌘B)" : "레일 접기 (⌘B)"}
            onClick={() => setRailCollapsed(!railCollapsed)}
          >
            {railCollapsed ? (
              <PanelRight size={16} aria-hidden="true" />
            ) : (
              <PanelLeft size={16} aria-hidden="true" />
            )}
          </button>
        </div>

        <button type="button" className="rail__search" onClick={() => setDialog("palette")}>
          <Search size={14} aria-hidden="true" />
          <span>검색</span>
          <span className="kbd">⌘K</span>
        </button>
      </div>

      <div className="rail__scroll">
        <section className="rail__group" aria-label="일정과 프로젝트">
          <button
            type="button"
            className="row"
            aria-current={boardKind === "schedule" ? "true" : undefined}
            onClick={() => void openSchedule()}
          >
            <CalendarDays size={14} className="row__hash" aria-hidden="true" />
            <span className="row__name">일정</span>
          </button>
          <button
            type="button"
            className="row"
            aria-current={boardKind === "projects" ? "true" : undefined}
            onClick={() => void openProjects()}
          >
            <FolderKanban size={14} className="row__hash" aria-hidden="true" />
            <span className="row__name">프로젝트</span>
            {myTasks.length > 0 ? (
              <span className="row__count" aria-label={`내 할일 ${myTasks.length}개`}>
                {myTasks.length}
              </span>
            ) : null}
          </button>
        </section>

        {orgVisible ? (
          <section className="rail__group" aria-label="관리">
            <button
              type="button"
              className="row"
              aria-current={orgFocused ? "true" : undefined}
              onClick={() => void openOrg()}
            >
              <Building2 size={14} className="row__hash" aria-hidden="true" />
              <span className="row__name">조직 관리</span>
            </button>
          </section>
        ) : null}

        <section className="rail__group" aria-label="채널">
          <div className="rail__groupline">
            <span className="rail__grouptitle">채널</span>
            <button
              type="button"
              className="rail__add"
              aria-label="채널 만들기"
              onClick={() => setDialog("newChannel")}
            >
              <Plus size={14} aria-hidden="true" />
            </button>
          </div>

          {roomChannels.length === 0 ? (
            <p className="u-px-2 u-py-1 u-small u-muted">아직 채널이 없습니다.</p>
          ) : null}

          {roomChannels.map((channel) => {
            const unread = channel.unread_count > 0;
            const beside = besideRoom && activeId === channel.id;
            return (
              <button
                key={channel.id}
                type="button"
                className={`row${unread ? " row--unread" : ""}${beside ? " row--beside" : ""}`}
                aria-current={chatFocused && activeId === channel.id ? "true" : undefined}
                onClick={() => void openChannel(channel.id)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  setRowMenu({ id: channel.id, x: event.clientX, y: event.clientY });
                }}
              >
                {channel.is_private ? (
                  <Lock size={13} className="row__hash" aria-hidden="true" />
                ) : (
                  <Hash size={14} className="row__hash" aria-hidden="true" />
                )}
                <span className="row__name">{channel.name}</span>
                {unread ? (
                  <span className="row__count" aria-label={`읽지 않은 메시지 ${channel.unread_count}개`}>
                    {channel.unread_count}
                  </span>
                ) : null}
              </button>
            );
          })}

          {rowMenu && menuTarget?.kind === "channel" ? (
            <Menu
              anchor={null}
              at={{ x: rowMenu.x, y: rowMenu.y }}
              onClose={() => setRowMenu(null)}
              width={210}
            >
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  void openChannel(id);
                }}
              >
                <Hash size={14} aria-hidden="true" />
                방 열기
              </button>
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const target = menuTarget;
                  setRowMenu(null);
                  if (!target) return;
                  void openRoomWindow(target).catch((error) =>
                    reportError(error, "새 창을 열지 못했습니다"),
                  );
                }}
              >
                <SquareArrowOutUpRight size={14} aria-hidden="true" />
                새 창으로 열기
              </button>
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  setDialog("addPeople", id);
                }}
              >
                <UserPlus size={14} aria-hidden="true" />
                사람 추가
              </button>
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  setDialog("channelSettings", id);
                }}
              >
                <Settings size={14} aria-hidden="true" />
                채널 설정
              </button>
              <div className="menu__sep" />
              <button
                type="button"
                className="menu__item menu__item--danger"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  setDialog("leaveChannel", id);
                }}
              >
                <LogOut size={14} aria-hidden="true" />
                방 나가기
              </button>
            </Menu>
          ) : null}
        </section>

        <section className="rail__group" aria-label="직접 메시지">
          <div className="rail__groupline">
            <span className="rail__grouptitle">직접 메시지</span>
            <button
              type="button"
              className="rail__add"
              aria-label="새 직접 메시지"
              onClick={() => setDialog("newDm")}
            >
              <UserPlus size={14} aria-hidden="true" />
            </button>
          </div>

          {dms.length === 0 ? (
            <p className="u-px-2 u-py-1 u-small u-muted">
              아직 대화가 없습니다.
            </p>
          ) : null}

          {dms.map((channel) => {
            const other = channel.dm_user;
            const unread = channel.unread_count > 0;
            const beside = besideRoom && activeId === channel.id;
            return (
              <button
                key={channel.id}
                type="button"
                className={`row${unread ? " row--unread" : ""}${beside ? " row--beside" : ""}`}
                aria-current={chatFocused && activeId === channel.id ? "true" : undefined}
                onClick={() => void openChannel(channel.id)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  setRowMenu({ id: channel.id, x: event.clientX, y: event.clientY });
                }}
              >
                <Avatar
                  user={other ?? { id: channel.id, name: channel.name, avatar_color: null }}
                  size="sm"
                  presence={other ? presence[other.id] ?? other.presence : null}
                />
                <span className="row__name">{other?.name ?? channel.name}</span>
                {unread ? (
                  <span className="row__count" aria-label={`읽지 않은 메시지 ${channel.unread_count}개`}>
                    {channel.unread_count}
                  </span>
                ) : null}
              </button>
            );
          })}

          {rowMenu && menuTarget?.kind === "dm" ? (
            <Menu
              anchor={null}
              at={{ x: rowMenu.x, y: rowMenu.y }}
              onClose={() => setRowMenu(null)}
              width={210}
            >
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  void openChannel(id);
                }}
              >
                <MessageSquare size={14} aria-hidden="true" />
                대화 열기
              </button>
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const target = menuTarget;
                  setRowMenu(null);
                  if (!target) return;
                  void openRoomWindow(target).catch((error) =>
                    reportError(error, "새 창을 열지 못했습니다"),
                  );
                }}
              >
                <SquareArrowOutUpRight size={14} aria-hidden="true" />
                새 창으로 열기
              </button>
              <button
                type="button"
                className="menu__item"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  void openChannel(id);
                  setDialog("channelSettings", id);
                }}
              >
                <Settings size={14} aria-hidden="true" />
                대화 정보
              </button>
              <div className="menu__sep" />
              <button
                type="button"
                className="menu__item menu__item--danger"
                onClick={() => {
                  const id = rowMenu.id;
                  setRowMenu(null);
                  setDialog("deleteDm", id);
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                대화 삭제
              </button>
            </Menu>
          ) : null}
        </section>

        <section className="rail__group" aria-label="멤버">
          <div className="rail__groupline">
            <span className="rail__grouptitle">멤버 {members.length}</span>
            <button
              type="button"
              className="rail__add"
              aria-label="멤버 목록"
              onClick={() => setDialog("people")}
            >
              <Users size={14} aria-hidden="true" />
            </button>
          </div>
        </section>
      </div>

      <div className="rail__foot">
        <button
          type="button"
          className="me"
          onClick={(event) => {
            // The same button that opened the menu closes it again.
            if (meAnchor) {
              setMeAnchor(null);
              setPresenceOpen(false);
              return;
            }
            setMeAnchor(event.currentTarget);
          }}
          aria-haspopup="menu"
          aria-expanded={Boolean(meAnchor)}
        >
          <Avatar user={user ?? { id: "me", name: "나", avatar_color: null }} size="sm" presence={user?.presence} />
          <span className="me__text">
            <span className="me__name">{user?.name ?? "내 이름"}</span>
            <span className="me__status">
              {user?.title ?? presenceLabel(user?.presence)}
            </span>
          </span>
          <ChevronDown size={13} className="wkey__chev" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="iconbtn rail__gear"
          aria-label="설정"
          title="설정"
          onClick={() => setDialog("settings")}
        >
          <Settings size={16} aria-hidden="true" />
        </button>
      </div>

      {workspaceAnchor ? (
        <Menu anchor={workspaceAnchor} onClose={() => setWorkspaceAnchor(null)} width={232}>
          <div className="menu__label">워크스페이스</div>
          {workspaces.map((workspace) => (
            <button
              key={workspace.id}
              type="button"
              className="menu__item"
              onClick={() => {
                setWorkspaceAnchor(null);
                if (workspace.id !== workspaceId) void loadWorkspace(workspace.id);
              }}
            >
              <span className="wkey__mark" aria-hidden="true">
                {workspace.name.slice(0, 1)}
              </span>
              {workspace.name}
            </button>
          ))}
          <div className="menu__sep" />
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setWorkspaceAnchor(null);
              setDialog("invite");
            }}
          >
            <UserPlus size={14} aria-hidden="true" />
            팀원 초대
          </button>
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setWorkspaceAnchor(null);
              setDialog("settings");
            }}
          >
            <Settings size={14} aria-hidden="true" />
            설정
          </button>
        </Menu>
      ) : null}

      {meAnchor ? (
        <Menu
          anchor={meAnchor}
          onClose={() => {
            setMeAnchor(null);
            setPresenceOpen(false);
          }}
          align="left"
          width={232}
        >
          <button
            type="button"
            className="menu__item"
            onMouseEnter={() => setPresenceOpen(false)}
            onClick={() => {
              setMeAnchor(null);
              setDialog("settings", "account");
            }}
          >
            <Settings size={14} aria-hidden="true" />
            프로필과 설정
          </button>
          <button
            type="button"
            className="menu__item menu__item--sub"
            ref={statusItemRef}
            aria-haspopup="menu"
            aria-expanded={presenceOpen}
            onMouseEnter={() => setPresenceOpen(true)}
            onClick={() => setPresenceOpen((open) => !open)}
          >
            <span
              className={`presence presence--dot presence--${user?.presence ?? "offline"}`}
              aria-hidden="true"
            />
            <span className="u-grow">{presenceLabel(user?.presence)}</span>
            <ChevronRight size={13} aria-hidden="true" />
          </button>
          <MenuSub open={presenceOpen} anchor={statusItemRef.current} width={208}>
            {PRESENCE_STATES.map((state) => (
              <button
                key={state.value}
                type="button"
                className="menu__item"
                role="menuitemradio"
                aria-checked={user?.presence === state.value}
                onClick={() => {
                  setMeAnchor(null);
                  setPresenceOpen(false);
                  void updateProfile({ presence: state.value });
                }}
              >
                <span className={`presence presence--dot presence--${state.value}`} aria-hidden="true" />
                <span className="u-grow">{state.label}</span>
                {user?.presence === state.value ? <Check size={14} aria-hidden="true" /> : null}
              </button>
            ))}
          </MenuSub>
          <div className="menu__sep" />
          <button
            type="button"
            className="menu__item menu__item--danger"
            onMouseEnter={() => setPresenceOpen(false)}
            onClick={() => {
              setMeAnchor(null);
              setPresenceOpen(false);
              signOut();
            }}
          >
            <LogOut size={14} aria-hidden="true" />
            로그아웃
          </button>
        </Menu>
      ) : null}
    </nav>
  );
}
