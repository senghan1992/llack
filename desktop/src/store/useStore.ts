import { create } from "zustand";
import { api, ApiError, friendlyMessage, NETWORK_MESSAGE, tokens } from "../lib/api";
import { notify } from "../lib/desktop";
import { formatDateLong, formatTime, mentionsUser } from "../lib/format";
import { dateKey, monthKey, parseMonthKey } from "../lib/calendar";
import { Realtime } from "../lib/ws";
import { getSettings, setSettings, subscribeSettings } from "../lib/settings";
import type {
  Bootstrap,
  Channel,
  EventInput,
  Invite,
  Member,
  Message,
  Milestone,
  MilestoneInput,
  OrgUnit,
  OrgUnitInput,
  Presence,
  Project,
  ProjectInput,
  Reaction,
  Role,
  RsvpResponse,
  ScheduleEvent,
  Session,
  Roadmap,
  Task,
  TaskInput,
  TaskStatus,
  User,
  WsEvent,
  Workspace,
} from "../lib/types";

/** Where an answer is written: in the room, or inside a thread. */
export type ReplyScope = "channel" | "thread";

export type DialogKind =
  | "palette"
  | "search"
  | "channels"
  | "people"
  | "settings"
  | "newChannel"
  | "newDm"
  | "pins"
  | "invite"
  | "channelSettings"
  | "addPeople"
  | "leaveChannel"
  | "deleteDm"
  | "event"
  | "project"
  | "task"
  | "newOrgUnit"
  | "milestone"
  | "projectChart"
  | null;

export interface Toast {
  id: number;
  text: string;
  action?: { label: string; run: () => void };
}

interface TypingEntry {
  user_id: string;
  name: string;
}

interface StoreState {
  status: "boot" | "anon" | "ready";
  bootError: string | null;
  session: Session | null;
  user: User | null;
  workspaceId: string | null;
  workspaceName: string;
  channels: Channel[];
  members: Member[];
  /** The roster of each room, by channel id. */
  channelMembers: Record<string, Member[]>;
  activeId: string | null;
  /** Which surface the main pane shows: a room, the team calendar, the
      board of work, or the organization. */
  view: "channel" | "schedule" | "projects" | "org";
  /** The surface that sits *beside* the conversation, when the window is
      wide enough to hold two panes. Null while there is no side pane. */
  board: "schedule" | "projects" | null;
  /** True when the window is wide enough to show the conversation and the
      board side by side. The app decides; the store only remembers. */
  wide: boolean;
  /** True when this device is willing to split the screen at all — the
      reader's own setting. The width is the app's answer, this one is the
      reader's. */
  splitEnabled: boolean;
  /** True when the rail is folded to a strip of icons. The conversation
      takes the room, and the rail comes back over it on hover. */
  railCollapsed: boolean;
  /** True when the main pane holds nothing: the reader cleared the screen
      for a meeting. Nothing is selected in the rail, and the pane shows an
      empty state instead of a conversation. */
  idle: boolean;
  /** The rooms you were in lately, newest first. The palette opens on
      them, and it forgets the ones that are gone. */
  recentRooms: string[];
  /** The half-written line of each room, by room id. It lives here, so it
      stays when the room changes, when the composer goes away, and when
      the window is closed with the sentence still in it. */
  drafts: Record<string, string>;
  messages: Record<string, Message[]>;
  hasMore: Record<string, boolean>;
  loading: Record<string, boolean>;
  loadingMore: Record<string, boolean>;
  errors: Record<string, string>;
  threadRoot: Message | null;
  replies: Message[];
  /** The message being answered, and the surface the answer is written in. */
  replyTo: { message: Message; scope: ReplyScope } | null;
  typing: Record<string, TypingEntry[]>;
  dialog: DialogKind;
  /** The channel a dialog acts on, when it is not the open one. */
  dialogTarget: string | null;
  toasts: Toast[];
  connected: boolean;
  presence: Record<string, Presence>;
  muted: Record<string, boolean>;
  invites: Invite[];
  events: ScheduleEvent[];
  eventsLoading: boolean;
  eventsError: string | null;
  /** The month the calendar shows, as `YYYY-MM`. */
  eventMonth: string;
  /** The day the calendar has selected, as `YYYY-MM-DD`. */
  eventDay: string;

  /* ── projects and their board ────────────────────────────────────────── */
  projects: Project[];
  projectsLoading: boolean;
  projectsError: string | null;
  /** The project the board is showing. */
  activeProjectId: string | null;
  /** The tasks of each project, by project id. */
  tasks: Record<string, Task[]>;
  /** The roadmaps of each project, by project id. */
  roadmaps: Record<string, Roadmap[]>;
  /** The roadmap the board shows — null means the whole board. */
  activeRoadmapId: string | null;
  /** The tasks of the whole workspace that are mine and not finished. */
  myTasks: Task[];
  /** Which projects the list shows: all of them, or the ones I am on. */
  projectFilter: "all" | "mine";
  /** The milestones of each project, by project id. */
  milestones: Record<string, Milestone[]>;
  /** Whether the milestone list is on its way. */
  milestonesLoading: boolean;
  /** Why the milestone list could not be read. */
  milestonesError: string | null;
  /** Which surface the project board shows: the four columns, or the
      milestones of the project. */
  boardMode: "board" | "milestones";

  /* ── organization ────────────────────────────────────────────────────── */
  /** The units of the organization, as a flat list. */
  orgUnits: OrgUnit[];
  /** The owners and admins of the workspace. */
  orgAdmins: Member[];
  /** My own role in this workspace, as the server sees it. */
  orgMyRole: Role | undefined;
  /** Whether I may appoint and remove workspace admins. */
  orgCanManageAdmins: boolean;
  orgLoading: boolean;
  orgError: string | null;
  /** The unit the page is showing. */
  activeOrgUnitId: string | null;
  /** The units I manage — the rail shows the organization when it is not
      empty. */
  orgManagedUnitIds: string[];

  boot: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (input: {
    email: string;
    password: string;
    name: string;
    workspace_name: string;
  }) => Promise<void>;
  signOut: () => void;
  loadWorkspace: (workspaceId: string) => Promise<void>;

  openChannel: (channelId: string) => Promise<void>;
  /** Open a room — a public one you are not in yet takes you in. */
  enterChannel: (channelId: string) => Promise<void>;
  /** Walk to the next or the previous room, in the order the rail lists
   *  them. With `onlyUnread`, only the rooms that have something unread in
   *  them are walked. The walk stops at the ends — it never wraps around. */
  stepRoom: (direction: 1 | -1, onlyUnread?: boolean) => Promise<void>;
  /** Keep the half-written line of a room. */
  setDraft: (channelId: string, body: string) => void;
  /** Leave the workspace with nothing selected: no room, no board, no
      thread. The rail stays; the main pane shows an empty state. */
  clearScreen: () => void;
  /** Say how wide the window is — the app measures it. */
  setWide: (wide: boolean) => void;
  /** Fold the rail to a strip of icons, or open it again. The reader's
      own choice, and it stays the next time the app opens. */
  setRailCollapsed: (collapsed: boolean) => void;
  /** Put the side pane away and go back to the conversation. */
  closeBoard: () => void;
  /** Give the side pane the whole main pane. */
  expandBoard: () => void;
  /** Move the full-width board back beside the conversation. */
  besideBoard: () => void;
  openSchedule: () => Promise<void>;
  loadEvents: (month?: string) => Promise<void>;
  setEventDay: (day: string) => void;
  setEventMonth: (month: string) => Promise<void>;
  createEvent: (input: EventInput) => Promise<void>;
  updateEvent: (eventId: string, input: Partial<EventInput>) => Promise<void>;
  deleteEvent: (eventId: string) => Promise<void>;
  rsvpEvent: (eventId: string, response: RsvpResponse) => Promise<void>;
  openProjects: () => Promise<void>;
  /** Load the projects and make sure one of them is on the board. */
  ensureProjects: () => Promise<void>;
  openProject: (projectId: string) => Promise<void>;
  loadProjects: () => Promise<void>;
  loadProjectTasks: (projectId: string) => Promise<void>;
  loadMyTasks: () => Promise<void>;
  selectProject: (projectId: string | null) => Promise<void>;
  setProjectFilter: (filter: "all" | "mine") => void;

  openOrg: () => Promise<void>;
  loadOrg: () => Promise<void>;
  selectOrgUnit: (unitId: string | null) => void;
  /** Make a unit. It answers whether the unit was made — the dialog keeps
      its words when the server refuses. */
  createOrgUnit: (input: OrgUnitInput) => Promise<boolean>;
  updateOrgUnit: (unitId: string, input: Partial<OrgUnitInput>) => Promise<void>;
  deleteOrgUnit: (unitId: string) => Promise<void>;
  addOrgUnitMember: (unitId: string, userId: string) => Promise<void>;
  removeOrgUnitMember: (unitId: string, userId: string) => Promise<void>;
  addOrgUnitManager: (unitId: string, userId: string) => Promise<void>;
  removeOrgUnitManager: (unitId: string, userId: string) => Promise<void>;
  createProject: (input: ProjectInput) => Promise<void>;
  updateProject: (
    projectId: string,
    input: Partial<ProjectInput> & { is_archived?: boolean },
  ) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  addProjectMember: (projectId: string, userId: string) => Promise<void>;
  removeProjectMember: (projectId: string, userId: string) => Promise<void>;
  createTask: (projectId: string, input: TaskInput) => Promise<void>;
  loadRoadmaps: (projectId: string) => Promise<void>;
  deleteRoadmap: (projectId: string, roadmapId: string) => Promise<void>;
  setActiveRoadmap: (roadmapId: string | null) => void;
  loadMilestones: (projectId: string) => Promise<void>;
  createMilestone: (projectId: string, input: MilestoneInput) => Promise<void>;
  updateMilestone: (milestoneId: string, input: Partial<MilestoneInput>) => Promise<void>;
  deleteMilestone: (milestoneId: string) => Promise<void>;
  /** Which surface the project board shows: the cards, or the milestones. */
  setBoardMode: (mode: "board" | "milestones") => void;
  updateTask: (
    taskId: string,
    input: Partial<TaskInput> & { position?: number },
  ) => Promise<void>;
  moveTask: (taskId: string, status: TaskStatus, position?: number) => Promise<void>;
  deleteTask: (taskId: string) => Promise<void>;
  addTaskComment: (taskId: string, body: string) => Promise<void>;
  deleteTaskComment: (commentId: string) => Promise<void>;
  loadMessages: (channelId: string, older?: boolean) => Promise<void>;
  sendMessage: (body: string, parentId?: string, attachmentIds?: string[]) => Promise<void>;
  editMessage: (messageId: string, body: string) => Promise<void>;
  deleteMessage: (messageId: string) => Promise<void>;
  toggleReaction: (message: Message, emoji: string) => Promise<void>;
  togglePin: (message: Message) => Promise<void>;
  markRead: (channelId: string) => void;
  setTyping: (channelId: string, on: boolean) => void;

  openThread: (message: Message) => Promise<void>;
  closeThread: () => void;
  setReplyTo: (message: Message | null, scope?: ReplyScope) => void;

  createChannel: (input: {
    name: string;
    topic?: string;
    is_private?: boolean;
    member_ids?: string[];
  }) => Promise<void>;
  updateChannel: (channelId: string, input: { name?: string; topic?: string }) => Promise<void>;
  updateMemberRole: (userId: string, role: Role) => Promise<void>;
  loadChannelMembers: (channelId: string) => Promise<void>;
  addChannelMember: (channelId: string, userId: string) => Promise<void>;
  removeMember: (userId: string) => Promise<void>;
  joinChannel: (channelId: string) => Promise<void>;
  leaveChannel: (channelId: string) => Promise<void>;
  deleteDm: (channelId: string) => Promise<void>;
  startDm: (userId: string) => Promise<void>;
  updateProfile: (input: {
    name?: string;
    title?: string;
    status_text?: string;
    avatar_color?: string;
    presence?: Presence;
  }) => Promise<void>;

  loadInvites: () => Promise<void>;
  createInvite: (email: string, role?: string) => Promise<Invite>;
  revokeInvite: (inviteId: string) => Promise<void>;
  acceptInvite: (token: string) => Promise<Workspace>;

  setDialog: (dialog: DialogKind, target?: string | null) => void;
  toast: (text: string, action?: Toast["action"]) => void;
  dismissToast: (id: number) => void;
  reportError: (error: unknown, fallback?: string) => string;
}

const realtime = new Realtime();

/** A roster with one person's profile replaced — the one who changed it. */
function replaceUser(members: Member[], user: User): Member[] {
  if (!members.some((member) => member.user.id === user.id)) return members;
  return members.map((member) =>
    member.user.id === user.id ? { ...member, user } : member,
  );
}

function upsertMessage(list: Message[] | undefined, message: Message): Message[] {
  const current = list ?? [];
  const index = current.findIndex((m) => m.id === message.id);
  if (index === -1) return [...current, message];
  const next = current.slice();
  next[index] = message;
  return next;
}

function upsertEvent(list: ScheduleEvent[], event: ScheduleEvent): ScheduleEvent[] {
  const index = list.findIndex((item) => item.id === event.id);
  if (index === -1) return [...list, event];
  const next = list.slice();
  next[index] = event;
  return next;
}

function upsertProject(list: Project[], project: Project): Project[] {
  const index = list.findIndex((item) => item.id === project.id);
  if (index === -1) return [...list, project];
  const next = list.slice();
  next[index] = project;
  return next;
}

/** The tasks of every project, with one of them changed. */function withTask(
  tasks: Record<string, Task[]>,
  task: Task,
): Record<string, Task[]> {
  const list = tasks[task.project_id] ?? [];
  const index = list.findIndex((item) => item.id === task.id);
  if (index === -1) return { ...tasks, [task.project_id]: [...list, task] };
  const next = list.slice();
  next[index] = task;
  return { ...tasks, [task.project_id]: next };
}

/** A milestone, wherever it lives — the milestones of every project are one
 *  flat map, and a change has to find its own way home. */
function findMilestone(
  milestones: Record<string, Milestone[]>,
  milestoneId: string,
): Milestone | null {
  for (const list of Object.values(milestones)) {
    const found = list.find((milestone) => milestone.id === milestoneId);
    if (found) return found;
  }
  return null;
}

function replaceMessage(list: Message[] | undefined, message: Message): Message[] {
  const current = list ?? [];
  return current.map((m) => (m.id === message.id ? message : m));
}

/** The reaction set as it looks the moment a finger lands on it: ours is
 *  flipped, nobody else's is touched. */
function withMyReaction(message: Message, emoji: string, userId: string): Reaction[] {
  const current = message.reactions.find((reaction) => reaction.emoji === emoji);
  if (!current) {
    return [...message.reactions, { emoji, count: 1, user_ids: [userId], me: true }];
  }
  if (current.me) {
    const userIds = current.user_ids.filter((id) => id !== userId);
    if (!userIds.length) {
      return message.reactions.filter((reaction) => reaction.emoji !== emoji);
    }
    return message.reactions.map((reaction) =>
      reaction.emoji === emoji
        ? { ...reaction, count: userIds.length, user_ids: userIds, me: false }
        : reaction,
    );
  }
  const userIds = [...current.user_ids, userId];
  return message.reactions.map((reaction) =>
    reaction.emoji === emoji
      ? { ...reaction, count: userIds.length, user_ids: userIds, me: true }
      : reaction,
  );
}

/** The message as the store holds it now, wherever it is shown. */
function findMessage(state: StoreState, messageId: string): Message | null {
  for (const list of Object.values(state.messages)) {
    const found = list.find((message) => message.id === messageId);
    if (found) return found;
  }
  const reply = state.replies.find((message) => message.id === messageId);
  if (reply) return reply;
  return state.threadRoot?.id === messageId ? state.threadRoot : null;
}

/** Whether the main pane can hold two surfaces: the conversation on the
 *  left and the board on the right. It needs a wide window, this device's
 *  own permission to split, and a conversation to sit beside. */
function canSplit(state: StoreState): boolean {
  return state.wide && state.splitEnabled && Boolean(state.activeId);
}

/** Where the board goes when the rail asks for it.
 *
 *  Beside the conversation when the window holds two panes — and out of the
 *  way when it is already there, so the same rail item twice leaves the
 *  conversation alone. One surface only: the board takes the conversation's
 *  place, and asking again brings the conversation back.
 */
function toggleBoard(
  state: StoreState,
  kind: "schedule" | "projects",
): { view: StoreState["view"]; board: StoreState["board"] } {
  if (canSplit(state)) {
    if (state.board === kind) return { view: "channel", board: null };
    return { view: "channel", board: kind };
  }
  if (state.view === kind) return { view: "channel", board: null };
  return { view: kind, board: null };
}

/** How many rooms the recent list keeps. */
const RECENT_LIMIT = 8;

/** The rooms the rail lists, in the order it lists them: the channels you
 *  are in first, then the direct messages. */
function railRooms(channels: Channel[]): Channel[] {
  return [
    ...channels.filter((c) => c.kind === "channel" && c.is_member !== false),
    ...channels.filter((c) => c.kind === "dm"),
  ];
}

/** The room the walk lands on: the next one in the rail's order, or the
 *  previous one. The walk stops at the ends — it never wraps around. */
function pickNeighbour(
  rooms: Channel[],
  activeId: string | null,
  direction: 1 | -1,
): Channel | null {
  if (!rooms.length) return null;
  const index = rooms.findIndex((room) => room.id === activeId);
  if (index === -1) {
    // The room that is open is not on the list — the walk starts at the
    // near end of it.
    return direction === 1 ? rooms[0] : rooms[rooms.length - 1];
  }
  const next = index + direction;
  if (next < 0 || next >= rooms.length) return null;
  return rooms[next];
}

/** The unread room the walk lands on — the next unread one after the room
 *  that is open, or the previous unread one before it. */
function pickUnread(
  rooms: Channel[],
  activeId: string | null,
  direction: 1 | -1,
): Channel | null {
  if (!rooms.length) return null;
  const index = rooms.findIndex((room) => room.id === activeId);
  if (index === -1) {
    const unread = rooms.filter((room) => room.unread_count > 0);
    if (!unread.length) return null;
    return direction === 1 ? unread[0] : unread[unread.length - 1];
  }
  for (let i = index + direction; i >= 0 && i < rooms.length; i += direction) {
    const room = rooms[i];
    if (room.unread_count > 0) return room;
  }
  return null;
}

let toastId = 0;

export const useStore = create<StoreState>((set, get) => ({
  status: "boot",
  bootError: null,
  session: null,
  user: null,
  workspaceId: null,
  workspaceName: "",
  channels: [],
  members: [],
  channelMembers: {},
  activeId: null,
  view: "channel",
  board: null,
  wide: false,
  splitEnabled: getSettings().splitView,
  railCollapsed: getSettings().railCollapsed,
  idle: false,
  recentRooms: [],
  drafts: {},
  messages: {},
  hasMore: {},
  loading: {},
  loadingMore: {},
  errors: {},
  threadRoot: null,
  replies: [],
  replyTo: null,
  typing: {},
  dialog: null,
  dialogTarget: null,
  toasts: [],
  connected: false,
  presence: {},
  muted: {},
  invites: [],
  events: [],
  eventsLoading: false,
  eventsError: null,
  eventMonth: monthKey(new Date()),
  eventDay: dateKey(new Date()),
  projects: [],
  projectsLoading: false,
  projectsError: null,
  activeProjectId: null,
  tasks: {},
  myTasks: [],
  projectFilter: "all",
  roadmaps: {},
  activeRoadmapId: null,
  milestones: {},
  milestonesLoading: false,
  milestonesError: null,
  boardMode: "board",
  orgUnits: [],
  orgAdmins: [],
  orgMyRole: undefined,
  orgCanManageAdmins: false,
  orgLoading: false,
  orgError: null,
  activeOrgUnitId: null,
  orgManagedUnitIds: [],

  async boot() {
    if (!tokens.access && !tokens.refresh) {
      set({ status: "anon" });
      return;
    }
    try {
      const workspaces = await api.workspaces();
      if (!workspaces.length) {
        set({ status: "anon" });
        return;
      }
      const first = workspaces[0];
      const session: Session = {
        access_token: tokens.access ?? "",
        refresh_token: tokens.refresh ?? "",
        user: await api.me(),
        workspace: first,
      };
      set({ session, user: session.user });
      await get().loadWorkspace(first.id);
      set({ status: "ready" });
      realtime.connect(tokens.access ?? "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        tokens.clear();
        set({ status: "anon" });
        return;
      }
      // The login screen shows this. A toast is gone in five seconds; the
      // reason the app came back here stays until it is dealt with.
      set({
        status: "anon",
        bootError: friendlyMessage(error, NETWORK_MESSAGE),
      });
    }
  },

  async signIn(email, password) {
    const session = await api.login({ email, password });
    tokens.set(session.access_token, session.refresh_token);
    set({ session, user: session.user, bootError: null });
    try {
      await get().loadWorkspace(session.workspace.id);
    } catch (error) {
      // The token was refused after all — do not keep a session the server
      // has already rejected.
      if (error instanceof ApiError && error.status === 401) tokens.clear();
      throw error;
    }
    set({ status: "ready" });
    realtime.connect(session.access_token);
  },

  async signUp(input) {
    const session = await api.signup(input);
    tokens.set(session.access_token, session.refresh_token);
    set({ session, user: session.user, bootError: null });
    try {
      await get().loadWorkspace(session.workspace.id);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) tokens.clear();
      throw error;
    }
    set({ status: "ready" });
    realtime.connect(session.access_token);
  },

  signOut() {
    realtime.close();
    tokens.clear();
    set({
      status: "anon",
      session: null,
      user: null,
      bootError: null,
      workspaceId: null,
      channels: [],
      members: [],
      activeId: null,
      messages: {},
      recentRooms: [],
      drafts: {},
      threadRoot: null,
      replies: [],
      view: "channel",
      board: null,
      idle: false,
      events: [],
      projects: [],
      tasks: {},
      myTasks: [],
      activeProjectId: null,
      roadmaps: {},
      activeRoadmapId: null,
      milestones: {},
      boardMode: "board",
      orgUnits: [],
      orgAdmins: [],
      orgMyRole: undefined,
      orgCanManageAdmins: false,
      orgLoading: false,
      orgError: null,
      activeOrgUnitId: null,
      orgManagedUnitIds: [],
    });
  },

  async loadWorkspace(workspaceId) {
    const data: Bootstrap = await api.bootstrap(workspaceId);
    const presence: Record<string, Presence> = {};
    for (const member of data.members) presence[member.user.id] = member.user.presence;
    const switching = get().workspaceId !== null && get().workspaceId !== workspaceId;
    set({
      workspaceId,
      workspaceName: data.workspace.name,
      channels: [...data.channels, ...data.dms],
      members: data.members,
      user: data.me,
      presence,
      // The organization of this workspace, and the units I manage in it.
      orgManagedUnitIds: data.org?.managed_unit_ids ?? [],
      // Another team's rooms are not this one's rooms. Leaving the old
      // channel selected showed an empty pane with a stale channel id.
      ...(switching
        ? {
            activeId: null,
            messages: {},
            recentRooms: [],
            drafts: {},
            hasMore: {},
            loading: {},
            loadingMore: {},
            errors: {},
            typing: {},
            channelMembers: {},
            threadRoot: null,
            replies: [],
            events: [],
            projects: [],
            tasks: {},
            myTasks: [],
            activeProjectId: null,
            roadmaps: {},
            activeRoadmapId: null,
            milestones: {},
            boardMode: "board",
            orgUnits: [],
            orgAdmins: [],
            orgMyRole: undefined,
            orgCanManageAdmins: false,
            orgLoading: false,
            orgError: null,
            activeOrgUnitId: null,
            view: "channel" as const,
            board: null,
            idle: false,
          }
        : {}),
    });
    if (!get().activeId) {
      const first = data.channels[0] ?? data.dms[0];
      if (first) await get().openChannel(first.id);
    }
    // The projects are fetched quietly in the background: a room that
    // belongs to a project says so in its header, so the list has to be
    // there before the reader looks.
    void get().loadProjects();
  },

  async openChannel(channelId) {
    if (get().activeId !== channelId) {
      // A thread reads with the room it belongs to.
      get().closeThread();
    }
    // A wide window keeps the board beside the conversation — opening a room
    // does not throw the calendar away. A narrow one, or a machine that
    // keeps to one surface, has only room for one: the board gives way.
    // The organization is never a side board: it is a page of its own.
    const { wide, splitEnabled, view, board } = get();
    // The room that is already open, pressed again, takes the whole
    // window: the board beside it goes away, and the conversation is read
    // at the width it deserves. The board comes back through its own
    // switch in the rail.
    if (board && get().activeId === channelId) {
      set({ view: "channel", board: null, replyTo: null, idle: false });
      get().markRead(channelId);
      return;
    }
    const beside =
      wide && splitEnabled
        ? board ?? (view === "schedule" || view === "projects" ? view : null)
        : null;
    // The room you were in goes to the top of the recent list. The same
    // room again does not sit there twice.
    const recentRooms = [
      channelId,
      ...get().recentRooms.filter((id) => id !== channelId),
    ].slice(0, RECENT_LIMIT);
    set({
      activeId: channelId,
      view: "channel",
      board: beside,
      replyTo: null,
      idle: false,
      recentRooms,
    });
    if (!get().messages[channelId]) await get().loadMessages(channelId);
    get().markRead(channelId);
  },

  async stepRoom(direction, onlyUnread = false) {
    const state = get();
    const rooms = railRooms(state.channels);
    const room = onlyUnread
      ? pickUnread(rooms, state.activeId, direction)
      : pickNeighbour(rooms, state.activeId, direction);
    // Nothing at this end of the list: the walk stops here.
    if (!room) return;
    await get().openChannel(room.id);
  },

  setDraft(channelId, body) {
    const drafts = { ...get().drafts };
    if (body) drafts[channelId] = body;
    else delete drafts[channelId];
    set({ drafts });
  },

  clearScreen() {
    // Nothing is selected any more: no room, no board, no thread. The rail
    // stays, and the main pane shows an empty state — a screen that can be
    // shared without the conversation behind it.
    set({
      idle: true,
      activeId: null,
      view: "channel",
      board: null,
      threadRoot: null,
      replies: [],
      replyTo: null,
    });
  },

  setWide(wide) {
    const state = get();
    if (state.wide === wide) return;
    if (!wide && state.board) {
      // The window got too small for two panes — the board takes the whole
      // main pane instead of vanishing.
      set({ wide: false, board: null, view: state.board });
      return;
    }
    set({ wide });
  },

  setRailCollapsed(collapsed) {
    if (get().railCollapsed === collapsed) return;
    // The rail's shape is the reader's own: it stays the next time the
    // app opens.
    setSettings({ railCollapsed: collapsed });
    set({ railCollapsed: collapsed });
  },

  closeBoard() {
    set({ board: null, view: "channel" });
  },

  expandBoard() {
    const { board } = get();
    if (!board) return;
    set({ board: null, view: board });
  },

  besideBoard() {
    const { wide, splitEnabled, activeId, view } = get();
    if (!wide || !splitEnabled || !activeId) return;
    if (view !== "schedule" && view !== "projects") return;
    set({ board: view, view: "channel" });
  },

  async openSchedule() {
    get().closeThread();
    // The rail item is a switch: it opens the calendar beside the
    // conversation, and asks it away again.
    set({ ...toggleBoard(get(), "schedule"), idle: false });
    await get().loadEvents();
  },

  async loadEvents(month) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const anchor = parseMonthKey(month ?? get().eventMonth);
    // A month of days, plus a month ahead for the "what is next" list.
    const from = new Date(anchor);
    from.setDate(1 - 7);
    const to = new Date(anchor);
    to.setMonth(to.getMonth() + 1, 0);
    to.setDate(to.getDate() + 7);
    const next = new Date(to);
    next.setMonth(next.getMonth() + 2);

    set({ eventsLoading: true });
    try {
      const list = await api.events(
        workspaceId,
        from.toISOString(),
        next.toISOString(),
      );
      set({
        events: list,
        eventsLoading: false,
        eventsError: null,
      });
    } catch (error) {
      set({
        eventsLoading: false,
        eventsError:
          error instanceof ApiError
            ? error.message
            : "일정을 불러오지 못했습니다. 연결을 확인해 주세요.",
      });
    }
  },

  setEventDay(day) {
    set({ eventDay: day });
  },

  async setEventMonth(month) {
    set({ eventMonth: month });
    await get().loadEvents(month);
  },

  async createEvent(input) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const event = await api.createEvent(workspaceId, input);
    set({ events: upsertEvent(get().events, event) });
    const day = dateKey(new Date(event.starts_at));
    const month = day.slice(0, 7);
    set({ eventDay: day });
    if (month !== get().eventMonth) {
      // The event belongs to another month — go there with it.
      set({ eventMonth: month });
      await get().loadEvents(month);
    }
    get().toast("일정을 등록했습니다");
  },

  async updateEvent(eventId, input) {
    const event = await api.updateEvent(eventId, input);
    set({ events: upsertEvent(get().events, event) });
    get().toast("일정을 수정했습니다");
  },

  async deleteEvent(eventId) {
    await api.deleteEvent(eventId);
    set({ events: get().events.filter((event) => event.id !== eventId) });
    get().toast("일정을 삭제했습니다");
  },

  async rsvpEvent(eventId, response) {
    const event = await api.rsvpEvent(eventId, response);
    set({ events: upsertEvent(get().events, event) });
  },

  async openProjects() {
    get().closeThread();
    // The rail item is a switch here too.
    set({ ...toggleBoard(get(), "projects"), idle: false });
    await get().ensureProjects();
  },

  async ensureProjects() {
    await get().loadProjects();
    // The board follows the list: the first project of the list is open
    // unless the reader has already picked one.
    if (!get().activeProjectId) {
      const first = get().projects[0]?.id ?? null;
      if (first) await get().selectProject(first);
    }
  },

  async openProject(projectId) {
    get().closeThread();
    // A project is a place, not a switch: it opens beside the conversation
    // when the window holds two panes, and takes the whole main pane when
    // it holds one.
    if (canSplit(get())) {
      set({ view: "channel", board: "projects", idle: false });
    } else {
      set({ view: "projects", board: null, idle: false });
    }
    if (!get().projects.length) await get().loadProjects();
    await get().selectProject(projectId);
  },

  async loadProjects() {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    set({ projectsLoading: true });
    try {
      const [projects, myTasks] = await Promise.all([
        api.projects(workspaceId),
        api.myTasks(workspaceId),
      ]);
      set({
        projects,
        myTasks,
        projectsLoading: false,
        projectsError: null,
      });
    } catch (error) {
      set({
        projectsLoading: false,
        projectsError:
          error instanceof ApiError
            ? error.message
            : "프로젝트를 불러오지 못했습니다. 연결을 확인해 주세요.",
      });
    }
  },

  async selectProject(projectId) {
    // Another project means another set of views — the board starts on the
    // cards, on the whole board.
    if (get().activeProjectId !== projectId) {
      set({ activeRoadmapId: null, boardMode: "board" });
    }
    set({ activeProjectId: projectId });
    if (!projectId) return;
    if (!get().roadmaps[projectId]) await get().loadRoadmaps(projectId);
    if (!get().milestones[projectId]) await get().loadMilestones(projectId);
    if (!get().milestones[projectId]) await get().loadMilestones(projectId);
    if (get().tasks[projectId]) return;
    await get().loadProjectTasks(projectId);
  },

  async loadRoadmaps(projectId) {
    try {
      const list = await api.roadmaps(projectId);
      set({ roadmaps: { ...get().roadmaps, [projectId]: list } });
    } catch {
      set({ roadmaps: { ...get().roadmaps, [projectId]: [] } });
    }
  },

  async deleteRoadmap(projectId, roadmapId) {
    await api.deleteRoadmap(roadmapId);
    set({
      roadmaps: {
        ...get().roadmaps,
        [projectId]: (get().roadmaps[projectId] ?? []).filter((item) => item.id !== roadmapId),
      },
      activeRoadmapId: get().activeRoadmapId === roadmapId ? null : get().activeRoadmapId,
    });
    // The tasks stay, but they no longer hang on a roadmap.
    await get().loadProjectTasks(projectId);
    get().toast("로드맵을 삭제했습니다");
  },

  setActiveRoadmap(roadmapId) {
    // A roadmap is a lane of the board — picking one puts the cards back in
    // front of the reader.
    set({ activeRoadmapId: roadmapId, boardMode: "board" });
  },

  /* ── milestones ───────────────────────────────────────────────────────── */

  async loadMilestones(projectId) {
    set({ milestonesLoading: true });
    try {
      const list = await api.milestones(projectId);
      set({
        milestones: { ...get().milestones, [projectId]: list },
        milestonesLoading: false,
        milestonesError: null,
      });
    } catch (error) {
      set({
        milestonesLoading: false,
        milestonesError:
          error instanceof ApiError
            ? error.message
            : "마일스톤을 불러오지 못했습니다. 연결을 확인해 주세요.",
      });
    }
  },

  async createMilestone(projectId, input) {
    await api.createMilestone(projectId, input);
    // The list is read again: the server knows the progress and the count.
    await get().loadMilestones(projectId);
    get().toast("마일스톤을 만들었습니다");
  },

  async updateMilestone(milestoneId, input) {
    const milestone = findMilestone(get().milestones, milestoneId);
    await api.updateMilestone(milestoneId, input);
    if (milestone) await get().loadMilestones(milestone.project_id);
    get().toast("마일스톤을 수정했습니다");
  },

  async deleteMilestone(milestoneId) {
    const milestone = findMilestone(get().milestones, milestoneId);
    await api.deleteMilestone(milestoneId);
    if (milestone) await get().loadMilestones(milestone.project_id);
    get().toast("마일스톤을 삭제했습니다");
  },

  setBoardMode(mode) {
    set({ boardMode: mode });
  },

  async loadProjectTasks(projectId) {
    try {
      const list = await api.projectTasks(projectId);
      set({ tasks: { ...get().tasks, [projectId]: list } });
    } catch {
      set({ tasks: { ...get().tasks, [projectId]: [] } });
    }
  },

  async loadMyTasks() {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    try {
      set({ myTasks: await api.myTasks(workspaceId) });
    } catch {
      /* the list stays as it is */
    }
  },

  setProjectFilter(filter) {
    set({ projectFilter: filter });
    // The board follows the list: when the list no longer holds the open
    // project, the first project of the new list takes its place.
    const visible = get().projects.filter((project) =>
      filter === "mine" ? project.is_member : true,
    );
    const current = get().activeProjectId;
    if (current && !visible.some((project) => project.id === current)) {
      void get().selectProject(visible[0]?.id ?? null);
    }
  },

  async createProject(input) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const project = await api.createProject(workspaceId, input);
    set({
      projects: upsertProject(get().projects, project),
      dialog: null,
    });
    await get().selectProject(project.id);
    get().toast("프로젝트를 등록했습니다");
  },

  async updateProject(projectId, input) {
    const project = await api.updateProject(projectId, input);
    set({
      projects: upsertProject(get().projects, project),
      dialog: null,
    });
    get().toast("프로젝트를 수정했습니다");
  },

  async deleteProject(projectId) {
    await api.deleteProject(projectId);
    const projects = get().projects.filter((project) => project.id !== projectId);
    // Whether the board was showing the project that goes away — asked
    // before the state changes, because after it the board shows nothing.
    const wasActive = get().activeProjectId === projectId;
    const tasks = { ...get().tasks };
    delete tasks[projectId];
    const roadmaps = { ...get().roadmaps };
    delete roadmaps[projectId];
    const milestones = { ...get().milestones };
    delete milestones[projectId];
    set({
      projects,
      tasks,
      roadmaps,
      milestones,
      dialog: null,
      activeProjectId: wasActive ? null : get().activeProjectId,
    });
    // The board does not stay empty: the next project takes its place.
    if (wasActive) {
      await get().selectProject(projects[0]?.id ?? null);
    }
    get().toast("프로젝트를 삭제했습니다");
  },

  async addProjectMember(projectId, userId) {
    const project = await api.addProjectMember(projectId, userId);
    set({ projects: upsertProject(get().projects, project) });
  },

  async removeProjectMember(projectId, userId) {
    await api.removeProjectMember(projectId, userId);
    const project = get().projects.find((item) => item.id === projectId);
    if (!project) return;
    set({
      projects: upsertProject(get().projects, {
        ...project,
        members: project.members.filter((member) => member.id !== userId),
      }),
    });
  },

  async createTask(projectId, input) {
    const task = await api.createTask(projectId, input);
    set({
      tasks: withTask(get().tasks, task),
      dialog: null,
    });
    await get().loadMyTasks();
    // A card that joins a milestone changes its progress — the counts live
    // on the server.
    await get().loadMilestones(projectId);
  },

  async updateTask(taskId, input) {
    const task = await api.updateTask(taskId, input);
    set({
      tasks: withTask(get().tasks, task),
      dialog: null,
    });
    await get().loadMyTasks();
    await get().loadMilestones(task.project_id);
  },

  async moveTask(taskId, status, position) {
    const current = Object.values(get().tasks)
      .flat()
      .find((task) => task.id === taskId);
    if (!current) return;
    // The card is moved right away; the board follows the hand, not the
    // round trip.
    const moved: Task = { ...current, status };
    set({ tasks: withTask(get().tasks, moved) });
    try {
      const task = await api.updateTask(taskId, { status, position });
      set({ tasks: withTask(get().tasks, task) });
      // The column renumbers itself when a card leaves or arrives — the
      // board is read again so the order is the server's.
      await get().loadProjectTasks(task.project_id);
      await get().loadMyTasks();
      // A card that moved may have finished — the milestone counts follow.
      await get().loadMilestones(task.project_id);
    } catch (error) {
      set({ tasks: withTask(get().tasks, current) });
      throw error;
    }
  },

  async deleteTask(taskId) {
    // The project the card belonged to — a card that leaves a milestone
    // changes its count.
    const owner = Object.values(get().tasks)
      .flat()
      .find((task) => task.id === taskId);
    await api.deleteTask(taskId);
    const tasks = { ...get().tasks };
    for (const [projectId, list] of Object.entries(tasks)) {
      if (list.some((task) => task.id === taskId)) {
        tasks[projectId] = list.filter((task) => task.id !== taskId);
      }
    }
    set({
      tasks,
      myTasks: get().myTasks.filter((task) => task.id !== taskId),
      dialog: null,
    });
    if (owner) await get().loadMilestones(owner.project_id);
    get().toast("할 일을 삭제했습니다");
  },

  async addTaskComment(taskId, body) {
    await api.addTaskComment(taskId, body);
    const task = Object.values(get().tasks)
      .flat()
      .find((item) => item.id === taskId);
    if (task) await get().loadProjectTasks(task.project_id);
  },

  async deleteTaskComment(commentId) {
    await api.deleteTaskComment(commentId);
    await get().loadProjects();
  },

  /* ── organization ────────────────────────────────────────────────────── */

  async openOrg() {
    get().closeThread();
    // The organization is a page of its own — it never sits beside the
    // conversation.
    set({ view: "org", board: null, idle: false });
    await get().loadOrg();
  },

  async loadOrg() {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    set({ orgLoading: true });
    try {
      const overview = await api.orgOverview(workspaceId);
      const current = get().activeOrgUnitId;
      const units = overview.units;
      set({
        orgUnits: units,
        orgAdmins: overview.admins,
        orgMyRole: overview.my_role,
        orgCanManageAdmins: overview.can_manage_admins,
        orgManagedUnitIds: overview.managed_unit_ids ?? [],
        orgLoading: false,
        orgError: null,
        // The unit that was open may be gone — the first one takes its place.
        activeOrgUnitId: units.some((unit) => unit.id === current)
          ? current
          : units[0]?.id ?? null,
      });
    } catch (error) {
      set({
        orgLoading: false,
        orgError:
          error instanceof ApiError
            ? error.message
            : "조직을 불러오지 못했습니다. 연결을 확인해 주세요.",
      });
    }
  },

  selectOrgUnit(unitId) {
    set({ activeOrgUnitId: unitId });
  },

  async createOrgUnit(input) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return false;
    try {
      const unit = await api.createOrgUnit(workspaceId, input);
      // The tree is read again, so the new unit sits where the server put it.
      await get().loadOrg();
      set({ activeOrgUnitId: unit.id });
      get().toast("조직을 만들었습니다");
      return true;
    } catch (error) {
      get().reportError(error, "조직을 만들지 못했습니다");
      return false;
    }
  },

  async updateOrgUnit(unitId, input) {
    try {
      await api.updateOrgUnit(unitId, input);
      await get().loadOrg();
      get().toast("조직을 수정했습니다");
    } catch (error) {
      get().reportError(error, "조직을 수정하지 못했습니다");
    }
  },

  async deleteOrgUnit(unitId) {
    try {
      await api.deleteOrgUnit(unitId);
      if (get().activeOrgUnitId === unitId) set({ activeOrgUnitId: null });
      await get().loadOrg();
      get().toast("조직을 삭제했습니다");
    } catch (error) {
      // The server refuses to delete a unit that still holds people or
      // children — its own Korean sentence is the answer.
      get().reportError(error, "조직을 삭제하지 못했습니다");
    }
  },

  async addOrgUnitMember(unitId, userId) {
    try {
      await api.addOrgUnitMember(unitId, userId);
      await get().loadOrg();
      const member = get().members.find((item) => item.user.id === userId);
      get().toast(
        member ? `${member.user.name}님을 추가했습니다` : "구성원을 추가했습니다",
      );
    } catch (error) {
      get().reportError(error, "구성원을 추가하지 못했습니다");
    }
  },

  async removeOrgUnitMember(unitId, userId) {
    try {
      await api.removeOrgUnitMember(unitId, userId);
      await get().loadOrg();
      get().toast("구성원을 내보냈습니다");
    } catch (error) {
      get().reportError(error, "구성원을 내보내지 못했습니다");
    }
  },

  async addOrgUnitManager(unitId, userId) {
    try {
      await api.addOrgUnitManager(unitId, userId);
      await get().loadOrg();
      const member = get().members.find((item) => item.user.id === userId);
      get().toast(
        member
          ? `${member.user.name}님을 관리자로 지정했습니다`
          : "관리자를 지정했습니다",
      );
    } catch (error) {
      get().reportError(error, "관리자를 지정하지 못했습니다");
    }
  },

  async removeOrgUnitManager(unitId, userId) {
    try {
      await api.removeOrgUnitManager(unitId, userId);
      await get().loadOrg();
      get().toast("관리자 지정을 해제했습니다");
    } catch (error) {
      get().reportError(error, "관리자 지정을 해제하지 못했습니다");
    }
  },

  async loadMessages(channelId, older = false) {
    const state = get();
    if (older) {
      if (state.loadingMore[channelId] || !state.hasMore[channelId]) return;
      const list = state.messages[channelId] ?? [];
      const first = list[0];
      if (!first) return;
      set({ loadingMore: { ...state.loadingMore, [channelId]: true } });
      try {
        const res = await api.messages(channelId, { limit: 40, before: first.id });
        set({
          messages: {
            ...state.messages,
            [channelId]: [...res.messages, ...(state.messages[channelId] ?? [])],
          },
          hasMore: { ...state.hasMore, [channelId]: res.has_more },
        });
      } finally {
        set({ loadingMore: { ...get().loadingMore, [channelId]: false } });
      }
      return;
    }

    set({ loading: { ...state.loading, [channelId]: true } });
    try {
      const res = await api.messages(channelId, { limit: 50 });
      const errors = { ...get().errors };
      delete errors[channelId];
      set({
        messages: { ...get().messages, [channelId]: res.messages },
        hasMore: { ...get().hasMore, [channelId]: res.has_more },
        errors,
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "메시지를 불러오지 못했습니다. 연결을 확인해 주세요.";
      set({ errors: { ...get().errors, [channelId]: message } });
    } finally {
      set({ loading: { ...get().loading, [channelId]: false } });
    }
  },

  async sendMessage(body, parentId, attachmentIds) {
    const channelId = get().activeId;
    if (!channelId || (!body.trim() && !attachmentIds?.length)) return;
    // An answer written in the room shows in the room, quoting the message
    // it answers; an answer written in a thread stays in the thread.
    const scope: ReplyScope = parentId ? "thread" : "channel";
    const pending = get().replyTo;
    const target = pending && pending.scope === scope ? pending.message : null;
    const message = await api.sendMessage(channelId, {
      body: body.trim(),
      parent_id: parentId,
      reply_to_id: target?.id,
      inline: scope === "channel" && Boolean(target),
      attachment_ids: attachmentIds,
    });
    if (target) set({ replyTo: null });
    if (parentId) {
      const root = get().threadRoot;
      if (root && root.id === parentId) {
        set({ replies: upsertMessage(get().replies, message) });
      }
    }
  },

  async editMessage(messageId, body) {
    const message = await api.editMessage(messageId, body);
    set({
      messages: { ...get().messages, [message.channel_id]: replaceMessage(get().messages[message.channel_id], message) },
      replies: replaceMessage(get().replies, message),
    });
    if (get().threadRoot?.id === message.id) set({ threadRoot: message });
  },

  async deleteMessage(messageId) {
    await api.deleteMessage(messageId);
    const root = get().threadRoot;
    if (root?.id === messageId) get().closeThread();
  },

  async toggleReaction(message, emoji) {
    const mine = message.reactions.find((r) => r.emoji === emoji)?.me;
    const before = message.reactions;
    const userId = get().user?.id;

    // One message, every place it is shown.
    const show = (target: Message) => {
      set({
        messages: {
          ...get().messages,
          [target.channel_id]: replaceMessage(get().messages[target.channel_id], target),
        },
        replies: replaceMessage(get().replies, target),
      });
      if (get().threadRoot?.id === target.id) set({ threadRoot: target });
    };

    // The change is painted before the round trip, so the chip and the names
    // behind it move together, at once.
    if (userId) {
      const current = findMessage(get(), message.id) ?? message;
      show({ ...current, reactions: withMyReaction(current, emoji, userId) });
    }

    try {
      const updated = mine
        ? await api.unreact(message.id, emoji)
        : await api.react(message.id, emoji);
      show(updated);
    } catch (error) {
      // The server refused: put the reactions back the way they were.
      const current = findMessage(get(), message.id);
      if (current) show({ ...current, reactions: before });
      throw error;
    }
  },

  async togglePin(message) {
    const updated = message.pinned ? await api.unpin(message.id) : await api.pin(message.id);
    set({
      messages: {
        ...get().messages,
        [message.channel_id]: replaceMessage(get().messages[message.channel_id], updated),
      },
      replies: replaceMessage(get().replies, updated),
    });
    get().toast(message.pinned ? "고정 해제했습니다" : "메시지를 고정했습니다");
  },

  markRead(channelId) {
    const list = get().messages[channelId];
    const last = list?.[list.length - 1];
    // One mark, not two: the socket is the fast path, REST the fallback when
    // the socket is not up. Doing both at once made the server race itself.
    if (get().connected) {
      realtime.send({ type: "read", channel_id: channelId, message_id: last?.id });
    } else {
      api.markRead(channelId, last?.id).catch(() => undefined);
    }
    set({
      channels: get().channels.map((c) =>
        c.id === channelId ? { ...c, unread_count: 0 } : c,
      ),
    });
  },

  setTyping(channelId, on) {
    realtime.send({ type: "typing", channel_id: channelId, on });
  },

  async openThread(message) {
    set({ threadRoot: message, replies: [] });
    try {
      const replies = await api.replies(message.id);
      // The user may have opened another thread while this was in flight.
      if (get().threadRoot?.id === message.id) set({ replies });
    } catch {
      /* the root still opens, the replies arrive over the socket */
    }
  },

  closeThread() {
    const replyTo = get().replyTo;
    set({
      threadRoot: null,
      replies: [],
      replyTo: replyTo?.scope === "thread" ? null : replyTo,
    });
  },

  setReplyTo(message, scope = "channel") {
    set({ replyTo: message ? { message, scope } : null });
  },

  async createChannel(input) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const channel = await api.createChannel(workspaceId, input);
    // The room can arrive twice — once over the socket, once in the answer.
    // One room, one row in the rail.
    set((state) => ({
      channels: [...state.channels.filter((c) => c.id !== channel.id), channel],
      dialog: null,
    }));
    await get().openChannel(channel.id);
  },

  async updateChannel(channelId, input) {
    const channel = await api.updateChannel(channelId, input);
    set({
      channels: get().channels.map((c) => (c.id === channelId ? { ...c, ...channel } : c)),
    });
  },

  async loadChannelMembers(channelId) {
    try {
      const roster = await api.channelMembers(channelId);
      set({ channelMembers: { ...get().channelMembers, [channelId]: roster } });
    } catch {
      // Not in this room (or it went away) — leave the roster as it is.
    }
  },

  async addChannelMember(channelId, userId) {
    await api.addChannelMember(channelId, userId);
    await get().loadChannelMembers(channelId);
    const member = get().members.find((m) => m.user.id === userId);
    get().toast(member ? `${member.user.name}님을 초대했습니다` : "초대했습니다");
  },

  async updateMemberRole(userId, role) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const member = await api.updateMember(workspaceId, userId, role);
    set({ members: get().members.map((m) => (m.user.id === userId ? member : m)) });
  },

  async removeMember(userId) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    await api.removeMember(workspaceId, userId);
    set({
      members: get().members.filter((m) => m.user.id !== userId),
      channels: get().channels.filter((c) => c.kind !== "dm" || c.dm_user?.id !== userId),
    });
    get().toast("멤버를 내보냈습니다");
  },

  async enterChannel(channelId) {
    const channel = get().channels.find((c) => c.id === channelId);
    // One rule, wherever the room was opened from: a public room you are not
    // in yet takes you in when you open it. A private one you are not in is
    // simply not yours to open.
    if (channel && channel.kind === "channel" && !channel.is_member) {
      await get().joinChannel(channelId);
      return;
    }
    await get().openChannel(channelId);
  },

  async joinChannel(channelId) {
    const channel = await api.joinChannel(channelId);
    const known = get().channels.some((c) => c.id === channelId);
    set({
      channels: known
        ? get().channels.map((c) => (c.id === channelId ? { ...c, ...channel } : c))
        : [...get().channels, channel],
      dialog: null,
    });
    await get().openChannel(channel.id);
  },

  async leaveChannel(channelId) {
    await api.leaveChannel(channelId);
    // A public room stays in the workspace's directory after you leave it —
    // you can find it again and walk back in. A private one is gone for good:
    // nobody may see a room they are not in.
    const channels = get()
      .channels.filter((c) => c.id !== channelId || !c.is_private)
      .map((c) => (c.id === channelId ? { ...c, is_member: false } : c));
    const messages = { ...get().messages };
    delete messages[channelId];
    set({ channels, messages, dialog: null, dialogTarget: null });
    if (get().activeId === channelId) {
      // Land somewhere the reader can keep working instead of an empty pane.
      const next = channels.find((c) => c.kind === "channel" && c.is_member) ?? null;
      set({ activeId: next ? next.id : null });
      if (next) await get().openChannel(next.id);
    }
    get().toast("채널에서 나왔습니다");
  },

  async deleteDm(channelId: string) {
    await api.deleteChannel(channelId);
    // The conversation and everything in it are gone — for both of us.
    const channels = get().channels.filter((c) => c.id !== channelId);
    const messages = { ...get().messages };
    delete messages[channelId];
    set({ channels, messages, dialog: null, dialogTarget: null });
    if (get().activeId === channelId) {
      // Land somewhere the reader can keep working instead of an empty pane.
      const next = channels.find((c) => c.kind === "channel" && c.is_member) ?? null;
      set({ activeId: next ? next.id : null });
      if (next) await get().openChannel(next.id);
    }
    get().toast("대화를 삭제했습니다");
  },

  async startDm(userId) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    const channel = await api.openDm(workspaceId, userId);
    set({
      channels: [...get().channels.filter((c) => c.id !== channel.id), channel],
      dialog: null,
    });
    await get().openChannel(channel.id);
  },

  async updateProfile(input) {
    const user = await api.updateMe(input);
    const state = get();
    set({
      user,
      session: state.session ? { ...state.session, user } : null,
      // the roster shows the new face too, not only the header
      members: replaceUser(state.members, user),
      // and the presence chip on the faces follows the new state
      presence: { ...state.presence, [user.id]: user.presence },
      channelMembers: Object.fromEntries(
        Object.entries(state.channelMembers).map(([id, list]) => [
          id,
          replaceUser(list, user),
        ]),
      ),
    });
  },

  async loadInvites() {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    try {
      set({ invites: await api.invites(workspaceId) });
    } catch {
      set({ invites: [] });
    }
  },

  async createInvite(email, role) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) throw new Error("워크스페이스가 선택되지 않았습니다");
    const invite = await api.createInvite(workspaceId, { email: email.trim(), role });
    set({ invites: [invite, ...get().invites.filter((i) => i.id !== invite.id)] });
    return invite;
  },

  async revokeInvite(inviteId) {
    const workspaceId = get().workspaceId;
    if (!workspaceId) return;
    await api.revokeInvite(workspaceId, inviteId);
    set({ invites: get().invites.filter((i) => i.id !== inviteId) });
  },

  async acceptInvite(token) {
    const workspace = await api.acceptInvite(token.trim());
    await get().loadWorkspace(workspace.id);
    return workspace;
  },

  setDialog(dialog, target = null) {
    set({ dialog, dialogTarget: dialog ? target : null });
  },

  toast(text, action) {
    toastId += 1;
    const id = toastId;
    set({ toasts: [...get().toasts, { id, text, action }] });
    setTimeout(() => get().dismissToast(id), 5000);
  },

  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },

  reportError(error, fallback = "문제가 생겼습니다. 다시 시도해 주세요.") {
    const message = error instanceof ApiError ? error.message : fallback;
    get().toast(message);
    return message;
  },
}));


/* ── realtime wiring ─────────────────────────────────────────────────── */

// The screen can be split only when this device says so. The setting is the
// reader's own, so it is followed at once — and the split follows it.
subscribeSettings(() => {
  const state = useStore.getState();
  const next = getSettings().splitView;
  if (state.splitEnabled !== next) {
    if (!next && state.board) {
      // The split is gone — the board takes the whole main pane.
      useStore.setState({ splitEnabled: next, board: null, view: state.board });
    } else {
      useStore.setState({ splitEnabled: next });
    }
  }
  // The rail's shape is the reader's own too, and it is followed at once.
  const rail = getSettings().railCollapsed;
  if (state.railCollapsed !== rail) {
    useStore.setState({ railCollapsed: rail });
  }
});

realtime.onOpen = () => useStore.setState({ connected: true });
realtime.onClose = () => useStore.setState({ connected: false });

realtime.onEvent = (event: WsEvent) => {
  const state = useStore.getState();
  const set = useStore.setState;

  switch (event.type) {
    case "message.created": {
      const message = event.message;
      if (!message) return;
      if (message.parent_id) {
        if (state.threadRoot?.id === message.parent_id) {
          set({ replies: upsertMessage(state.replies, message) });
        }
        const root = state.messages[message.channel_id]?.find((m) => m.id === message.parent_id);
        if (
          root &&
          root.user_id === state.user?.id &&
          message.user_id !== state.user?.id &&
          state.activeId !== message.channel_id
        ) {
          // Someone answered my message in a thread.
          void notify(
            `${message.author.name}님이 답글을 남겼습니다`,
            message.body.length > 120 ? `${message.body.slice(0, 120)}\u2026` : message.body,
          );
        }
        if (root) {
          set({
            messages: {
              ...state.messages,
              [message.channel_id]: replaceMessage(state.messages[message.channel_id], {
                ...root,
                reply_count: root.reply_count + 1,
                last_reply_at: message.created_at,
              }),
            },
          });
        }
        if (message.inline) {
          // An answer written in the room shows in the room too, quoted.
          const list = state.messages[message.channel_id] ?? [];
          if (!list.some((m) => m.id === message.id)) {
            set({
              messages: {
                ...state.messages,
                [message.channel_id]: [...list, message],
              },
            });
          }
        }
        return;
      }

      const list = state.messages[message.channel_id] ?? [];
      if (!list.some((m) => m.id === message.id)) {
        set({ messages: { ...state.messages, [message.channel_id]: [...list, message] } });
      }

      const isActive = state.activeId === message.channel_id;
      if (!isActive && message.user_id !== state.user?.id) {
        set({
          channels: state.channels.map((c) =>
            c.id === message.channel_id ? { ...c, unread_count: c.unread_count + 1 } : c,
          ),
        });
        void notify(
          message.author.name,
          message.body.length > 120 ? `${message.body.slice(0, 120)}\u2026` : message.body,
        );
      } else if (
        message.user_id !== state.user?.id &&
        mentionsUser(message.body, state.user?.name ?? "")
      ) {
        // Being named counts even in the room you are already reading.
        void notify(
          `${message.author.name}님이 불렀습니다`,
          message.body.length > 120 ? `${message.body.slice(0, 120)}\u2026` : message.body,
        );
      }
      return;
    }

    case "message.updated": {
      const message = event.message;
      if (!message) return;
      set({
        messages: {
          ...state.messages,
          [message.channel_id]: replaceMessage(state.messages[message.channel_id], message),
        },
        replies: replaceMessage(state.replies, message),
      });
      return;
    }

    case "message.deleted": {
      const { message_id: messageId, channel_id: channelId } = event;
      if (!messageId || !channelId) return;
      set({
        messages: {
          ...state.messages,
          [channelId]: (state.messages[channelId] ?? []).map((m) =>
            m.id === messageId
              ? { ...m, deleted_at: new Date().toISOString(), body: "", reactions: [] }
              : m,
          ),
        },
      });
      return;
    }

    case "reaction.updated": {
      const message = event.message;
      if (!message) return;
      set({
        messages: {
          ...state.messages,
          [message.channel_id]: replaceMessage(state.messages[message.channel_id], message),
        },
        replies: replaceMessage(state.replies, message),
      });
      return;
    }

    case "typing": {
      const { channel_id: channelId, user_id: userId, name, on } = event;
      if (!channelId || !userId) return;
      const current = (state.typing[channelId] ?? []).filter((t) => t.user_id !== userId);
      set({
        typing: {
          ...state.typing,
          [channelId]: on && name ? [...current, { user_id: userId, name }] : current,
        },
      });
      return;
    }

    case "hello": {
      // The greeting carries the state we are really in — "online", or the
      // status we chose for ourselves before the socket opened.
      const user = event.user;
      if (!user) return;
      const me = state.user && state.user.id === user.id ? user : null;
      set({
        presence: { ...state.presence, [user.id]: user.presence },
        ...(me
          ? {
              user: me,
              session: state.session ? { ...state.session, user: me } : null,
              members: replaceUser(state.members, me),
            }
          : {}),
      });
      return;
    }

    case "presence": {
      const { user_id: userId, presence } = event;
      if (!userId || !presence) return;
      const me = state.user && state.user.id === userId ? { ...state.user, presence } : null;
      set({
        presence: { ...state.presence, [userId]: presence },
        // my own face wears the state too — the rail's own chip and name
        ...(me
          ? {
              user: me,
              session: state.session ? { ...state.session, user: me } : null,
              members: replaceUser(state.members, me),
            }
          : {}),
      });
      return;
    }

    case "user.updated": {
      const user = event.user;
      if (!user) return;
      set({
        members: replaceUser(state.members, user),
        presence: { ...state.presence, [user.id]: user.presence },
        channelMembers: Object.fromEntries(
          Object.entries(state.channelMembers).map(([id, list]) => [
            id,
            replaceUser(list, user),
          ]),
        ),
      });
      return;
    }

    case "channel.created": {
      const channel = event.channel;
      if (!channel || state.channels.some((c) => c.id === channel.id)) return;
      set({ channels: [...state.channels, channel] });
      return;
    }

    case "channel.updated": {
      const channel = event.channel;
      if (!channel) return;
      set({
        channels: state.channels.map((c) => (c.id === channel.id ? { ...c, ...channel } : c)),
      });
      return;
    }

    case "members.changed": {
      const { channel_id: channelId, members } = event;
      if (!channelId || !members) return;
      set({
        channels: state.channels.map((c) =>
          c.id === channelId ? { ...c, members, member_count: members.length } : c,
        ),
      });
      return;
    }

    case "event.created":
    case "event.updated": {
      const scheduleEvent = event.event;
      if (!scheduleEvent) return;
      set({ events: upsertEvent(state.events, scheduleEvent) });
      if (event.type === "event.created" && scheduleEvent.created_by !== state.user?.id) {
        // Somebody booked the team up — say so.
        const when = scheduleEvent.all_day
          ? formatDateLong(scheduleEvent.starts_at)
          : `${formatDateLong(scheduleEvent.starts_at)} ${formatTime(scheduleEvent.starts_at)}`;
        void notify("새 일정", `${scheduleEvent.title} · ${when}`);
      }
      return;
    }

    case "event.deleted": {
      const { event_id: eventId } = event;
      if (!eventId) return;
      set({ events: state.events.filter((item) => item.id !== eventId) });
      return;
    }

    case "unread": {
      const { channel_id: channelId, count } = event;
      if (!channelId || count === undefined) return;
      set({
        channels: state.channels.map((c) => (c.id === channelId ? { ...c, unread_count: count } : c)),
      });
      return;
    }

    case "project.created":
    case "project.updated": {
      const project = event.project;
      if (!project) return;
      set({ projects: upsertProject(state.projects, project) });
      return;
    }

    case "project.deleted": {
      const { project_id: projectId } = event;
      if (!projectId) return;
      const tasks = { ...state.tasks };
      delete tasks[projectId];
      const roadmaps = { ...state.roadmaps };
      delete roadmaps[projectId];
      const milestones = { ...state.milestones };
      delete milestones[projectId];
      set({
        projects: state.projects.filter((project) => project.id !== projectId),
        tasks,
        roadmaps,
        milestones,
        activeRoadmapId:
          state.activeProjectId === projectId ? null : state.activeRoadmapId,
        activeProjectId:
          state.activeProjectId === projectId ? null : state.activeProjectId,
      });
      return;
    }

    case "task.created":
    case "task.updated": {
      const task = event.task;
      if (!task) return;
      set({ tasks: withTask(state.tasks, task) });
      void useStore.getState().loadMyTasks();
      // The milestone counts live on the server — they are read again.
      void useStore.getState().loadMilestones(task.project_id);
      return;
    }

    case "task.deleted": {
      const { task_id: taskId } = event;
      if (!taskId) return;
      // The card may have hung on a milestone — the project it belonged to
      // is the one whose counts change.
      let owner = "";
      const tasks = { ...state.tasks };
      for (const [projectId, list] of Object.entries(tasks)) {
        if (list.some((task) => task.id === taskId)) {
          tasks[projectId] = list.filter((task) => task.id !== taskId);
          owner = projectId;
        }
      }
      set({
        tasks,
        myTasks: state.myTasks.filter((task) => task.id !== taskId),
      });
      if (owner) void useStore.getState().loadMilestones(owner);
      return;
    }

    case "org.changed": {
      // Somebody else changed the organization — the tree is read again, so
      // the page never shows a structure the server has already left behind.
      if (state.view === "org") void useStore.getState().loadOrg();
      return;
    }

    default:
      return;
  }
};
