import { useEffect, useMemo, useState } from "react";
import { Maximize2, PanelRight, X } from "lucide-react";
import { Rail } from "./components/Rail";
import { ChannelHead } from "./components/ChannelHead";
import { EmptyRoom } from "./components/EmptyRoom";
import { MessageList } from "./components/MessageList";
import { Composer } from "./components/Composer";
import { ThreadPane } from "./components/ThreadPane";
import { ScheduleHead, ScheduleView } from "./components/ScheduleView";
import { EventDialog } from "./components/ScheduleDialogs";
import { ProjectsHead, ProjectsView } from "./components/ProjectsView";
import { ProjectDialog, TaskDialog } from "./components/ProjectDialogs";
import { MilestoneDialog } from "./components/MilestoneDialog";
import { ProjectChartDialog } from "./components/ProjectChartDialog";
import { OrgHead, OrgView } from "./components/OrgView";
import { OrgUnitDialog } from "./components/OrgDialogs";
import { Toasts } from "./components/Toasts";
import { Gate } from "./components/Gate";
import {
  AddPeopleDialog,
  ChannelSettingsDialog,
  DeleteDmDialog,
  InviteDialog,
  LeaveChannelDialog,
  NewChannelDialog,
  NewDmDialog,
  PaletteDialog,
  PeopleDialog,
  PinsDialog,
  SearchDialog,
} from "./components/Dialogs";
import { SettingsDialog } from "./components/SettingsDialog";
import { watchTheme } from "./lib/theme";
import { currentRoomId, roomTitle, setRoomTitle } from "./lib/popout";
import { useStore } from "./store/useStore";
import type { Message } from "./lib/types";

/**
 * The width from which the window holds two panes: the conversation on the
 * left, the board (calendar, work) on the right. Below it there is only
 * room for one surface, so the board takes the place of the conversation
 * instead of sitting beside it.
 */
const SPLIT_WIDTH = 1152;

export default function App() {
  const status = useStore((s) => s.status);
  const boot = useStore((s) => s.boot);
  const errors = useStore((s) => s.errors);
  const dialog = useStore((s) => s.dialog);
  const setDialog = useStore((s) => s.setDialog);
  const channels = useStore((s) => s.channels);
  const activeId = useStore((s) => s.activeId);
  const view = useStore((s) => s.view);
  const messages = useStore((s) => s.messages);
  const loading = useStore((s) => s.loading);
  const hasMore = useStore((s) => s.hasMore);
  const members = useStore((s) => s.members);
  const presence = useStore((s) => s.presence);
  const user = useStore((s) => s.user);
  const typing = useStore((s) => s.typing);
  const threadRoot = useStore((s) => s.threadRoot);
  const replies = useStore((s) => s.replies);
  const projects = useStore((s) => s.projects);
  const openProject = useStore((s) => s.openProject);
  const board = useStore((s) => s.board);
  const idle = useStore((s) => s.idle);
  const wide = useStore((s) => s.wide);
  const splitEnabled = useStore((s) => s.splitEnabled);
  const setWide = useStore((s) => s.setWide);
  const closeBoard = useStore((s) => s.closeBoard);
  const expandBoard = useStore((s) => s.expandBoard);
  const besideBoard = useStore((s) => s.besideBoard);

  const loadMessages = useStore((s) => s.loadMessages);
  const sendMessage = useStore((s) => s.sendMessage);
  const editMessage = useStore((s) => s.editMessage);
  const deleteMessage = useStore((s) => s.deleteMessage);
  const toggleReaction = useStore((s) => s.toggleReaction);
  const togglePin = useStore((s) => s.togglePin);
  const openThread = useStore((s) => s.openThread);
  const closeThread = useStore((s) => s.closeThread);
  const clearScreen = useStore((s) => s.clearScreen);
  const openChannel = useStore((s) => s.openChannel);
  const setTyping = useStore((s) => s.setTyping);
  const reportError = useStore((s) => s.reportError);
  const toast = useStore((s) => s.toast);
  const [railOpen, setRailOpen] = useState(false);
  /** The room this window was opened for — null in the workspace window. */
  const [roomId, setRoomId] = useState<string | null>(null);

  useEffect(() => {
    // 화면 모드는 설정이 정한다 — OS 설정을 따라가기도 한다.
    watchTheme();
    void boot();
  }, [boot]);

  // The window's width decides whether the board can sit beside the chat.
  // The width alone says nothing: this device's own setting decides
  // whether the screen is split at all.
  useEffect(() => {
    const measure = () => setWide(window.innerWidth >= SPLIT_WIDTH);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [setWide]);

  // A window that was opened for one room knows it by its own label.
  useEffect(() => {
    let alive = true;
    void currentRoomId().then((id) => {
      if (alive) setRoomId(id);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setDialog("palette");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setDialog]);

  const channel = useMemo(
    () => channels.find((c) => c.id === activeId) ?? null,
    [channels, activeId],
  );

  const list = activeId ? messages[activeId] ?? [] : [];
  const typingHere = activeId ? typing[activeId] ?? [] : [];

  // A room that belongs to a project says so in its header — the board is
  // one step away from the conversation it belongs to.
  const linkedProject = useMemo(
    () => (channel ? (projects.find((p) => p.channel_id === channel.id) ?? null) : null),
    [projects, channel],
  );

  // A window opened for one room opens that room, and wears its name.
  useEffect(() => {
    if (status !== "ready" || !roomId) return;
    void openChannel(roomId);
  }, [status, roomId, openChannel]);

  useEffect(() => {
    if (!roomId || !channel) return;
    void setRoomTitle(roomTitle(channel));
  }, [roomId, channel]);

  if (status === "boot") {
    return (
      <div className="u-col u-minh-screen u-place-center u-frame">
        <div className="u-col u-center u-gap-3">
          <span className="gate__mark" aria-hidden="true">
            L
          </span>
          <p className="u-small u-muted">워크스페이스를 여는 중</p>
        </div>
      </div>
    );
  }

  if (status === "anon") {
    return (
      <>
        <Gate />
        <Toasts />
      </>
    );
  }

  const onSend = async (body: string, attachmentIds?: string[]) => {
    try {
      await sendMessage(body, undefined, attachmentIds);
    } catch (error) {
      reportError(error, "메시지를 보내지 못했습니다");
    }
  };

  const onReply = async (body: string) => {
    if (!threadRoot) return;
    try {
      await sendMessage(body, threadRoot.id);
    } catch (error) {
      reportError(error, "답글을 보내지 못했습니다");
    }
  };

  const onEdit = (message: Message, body: string) => {
    void editMessage(message.id, body).catch((error) => reportError(error));
  };

  const onDelete = (message: Message) => {
    void deleteMessage(message.id)
      .then(() => toast("메시지를 삭제했습니다"))
      .catch((error) => reportError(error));
  };

  const onReact = (message: Message, emoji: string) => {
    void toggleReaction(message, emoji).catch((error) => reportError(error));
  };

  const onPin = (message: Message) => {
    void togglePin(message).catch((error) => reportError(error));
  };

  // The conversation — always the same, whether it fills the window or sits
  // in the left half of it.
  const chat = (
    <>
      <ChannelHead
        channel={channel}
        members={members}
        presence={presence}
        project={linkedProject}
        compact={Boolean(board) || Boolean(roomId)}
        onOpenProject={() => {
          if (linkedProject) void openProject(linkedProject.id);
        }}
        onOpenSearch={() => setDialog("search")}
        onOpenPeople={() => setDialog("people")}
        onAddPeople={() => setDialog("addPeople", activeId)}
        onOpenPins={() => setDialog("pins")}
        onToggleRail={() => setRailOpen((open) => !open)}
        onOpenSettings={() => setDialog("channelSettings")}
        onClearScreen={roomId ? undefined : clearScreen}
      />

      <div className="conversation">
        <div className="canvas">
          <MessageList
            channel={channel}
            messages={list}
            loading={Boolean(activeId && loading[activeId])}
            hasMore={Boolean(activeId && hasMore[activeId])}
            error={activeId ? errors[activeId] ?? null : null}
            onLoadMore={() => {
              if (activeId) void loadMessages(activeId, true);
            }}
            onOpenThread={(message) => void openThread(message)}
            onReact={onReact}
            onEdit={onEdit}
            onDelete={onDelete}
            onPin={onPin}
            ownId={user?.id ?? null}
          />
        </div>

        <div className="conversation__foot">
          <div className="typing" aria-live="polite">
            {typingHere.length ? `${typingHere.map((t) => t.name).join(", ")} 입력 중` : ""}
          </div>
          <Composer
            channel={channel}
            onSend={onSend}
            onTyping={(on) => {
              if (activeId) setTyping(activeId, on);
            }}
          />
        </div>
      </div>
    </>
  );

  // The board — the calendar or the work — with the two keys that move it
  // between the side pane and the whole main pane.
  const boardActions = (kind: "side" | "full") => (
    <>
      {kind === "side" ? (
        <button
          type="button"
          className="iconbtn"
          aria-label="보드를 전체 화면으로"
          onClick={expandBoard}
        >
          <Maximize2 size={16} aria-hidden="true" />
        </button>
      ) : wide && splitEnabled ? (
        <button
          type="button"
          className="iconbtn"
          aria-label="보드를 대화 옆에 놓기"
          onClick={besideBoard}
        >
          <PanelRight size={16} aria-hidden="true" />
        </button>
      ) : null}
      <button
        type="button"
        className="iconbtn"
        aria-label="보드 닫고 대화로 돌아가기"
        onClick={closeBoard}
      >
        <X size={16} aria-hidden="true" />
      </button>
    </>
  );

  const calendar = (
    <>
      <ScheduleHead
        onToggleRail={() => setRailOpen((open) => !open)}
        actions={boardActions(board ? "side" : "full")}
      />
      <ScheduleView />
    </>
  );

  const work = (
    <>
      <ProjectsHead
        onToggleRail={() => setRailOpen((open) => !open)}
        actions={boardActions(board ? "side" : "full")}
      />
      <ProjectsView />
    </>
  );

  // The organization is a page of its own — it never sits beside the
  // conversation, so it carries no board keys.
  const org = (
    <>
      <OrgHead onToggleRail={() => setRailOpen((open) => !open)} />
      <OrgView />
    </>
  );

  return (
    <div
      className={`app${threadRoot ? " app--thread" : ""}${railOpen ? " app--rail" : ""}${
        board ? " app--split" : ""
      }${roomId ? " app--room" : ""}`}
    >
      {roomId ? null : <Rail />}

      <div className="app__main">
        {idle ? (
          <section className="pane pane--chat pane--empty">
            <div className="canvas">
              <EmptyRoom onOpenRail={roomId ? undefined : () => setRailOpen(true)} />
            </div>
          </section>
        ) : board ? (
          <>
            <section className="pane pane--chat">{chat}</section>
            <section className="pane pane--board">
              {board === "schedule" ? calendar : work}
            </section>
          </>
        ) : view === "schedule" ? (
          <section className="pane pane--full">{calendar}</section>
        ) : view === "projects" ? (
          <section className="pane pane--full">{work}</section>
        ) : view === "org" ? (
          <section className="pane pane--full">{org}</section>
        ) : (
          <section className="pane pane--chat">{chat}</section>
        )}
      </div>

      {threadRoot ? (
        <ThreadPane
          channel={channel}
          root={threadRoot}
          replies={replies}
          ownId={user?.id ?? null}
          onClose={closeThread}
          onSend={onReply}
          onTyping={(on) => {
            if (activeId) setTyping(activeId, on);
          }}
          onReact={onReact}
          onEdit={onEdit}
          onDelete={onDelete}
          onPin={onPin}
        />
      ) : null}

      {dialog === "palette" ? <PaletteDialog /> : null}
      {dialog === "search" ? <SearchDialog /> : null}
      {dialog === "newChannel" ? <NewChannelDialog /> : null}
      {dialog === "newDm" ? <NewDmDialog /> : null}
      {dialog === "people" ? <PeopleDialog /> : null}
      {dialog === "pins" ? <PinsDialog /> : null}
      {dialog === "settings" ? <SettingsDialog /> : null}
      {dialog === "invite" ? <InviteDialog /> : null}
      {dialog === "channelSettings" ? <ChannelSettingsDialog /> : null}
      {dialog === "addPeople" ? <AddPeopleDialog /> : null}
      {dialog === "leaveChannel" ? <LeaveChannelDialog /> : null}
      {dialog === "deleteDm" ? <DeleteDmDialog /> : null}
      {dialog === "event" ? <EventDialog /> : null}
      {dialog === "project" ? <ProjectDialog /> : null}
      {dialog === "task" ? <TaskDialog /> : null}
      {dialog === "newOrgUnit" ? <OrgUnitDialog /> : null}
      {dialog === "milestone" ? <MilestoneDialog /> : null}
      {dialog === "projectChart" ? <ProjectChartDialog /> : null}

      <Toasts />
    </div>
  );
}
