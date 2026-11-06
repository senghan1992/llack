import type {
  Bootstrap,
  Channel,
  EventInput,
  FileRef,
  Invite,
  Member,
  Message,
  Milestone,
  MilestoneInput,
  OrgOverview,
  OrgUnit,
  OrgUnitInput,
  Presence,
  Project,
  Roadmap,
  ProjectInput,
  RsvpResponse,
  ScheduleEvent,
  SearchResult,
  Session,
  Task,
  TaskComment,
  TaskInput,
  Tokens,
  User,
  Workspace,
} from "./types";

const RAW_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";
export const API_BASE = RAW_BASE.replace(/\/$/, "");
export const API = `${API_BASE}/api/v1`;

const ACCESS_KEY = "llack.access";
const REFRESH_KEY = "llack.refresh";

export const tokens = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  code: string;
  field: string | null;
  status: number;

  constructor(status: number, code: string, message: string, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

/**
 * The API could not be reached at all — the server is not running, or the
 * address points nowhere. The browser says "Failed to fetch" (WebKit says
 * "Load failed"), which tells the person in front of the screen nothing, so
 * it is turned into a sentence they can act on.
 */
export const NETWORK_CODE = "network";

export const NETWORK_MESSAGE =
  "서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요. (백엔드 실행: `make dev`)";

function networkError(): ApiError {
  return new ApiError(0, NETWORK_CODE, NETWORK_MESSAGE);
}

/**
 * A sentence the person in front of the screen can act on.
 *
 * The API answers in English ("invalid email or password"); the app speaks
 * Korean, and the difference between "the password is wrong" and "the server
 * is not running" is the whole difference between a one-line fix and a lost
 * afternoon. So the codes are translated here, and only here.
 */
export function friendlyMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.code === NETWORK_CODE) return error.message;
    if (error.status === 401) return "이메일 또는 비밀번호가 맞지 않습니다.";
    if (error.status === 409) return "이미 등록된 이메일입니다.";
    if (error.status >= 500) return "서버에서 문제가 발생했습니다. 잠시 뒤 다시 시도해 주세요.";
    return error.message;
  }
  return fallback;
}

let refreshing: Promise<Tokens | null> | null = null;

async function refreshTokens(): Promise<Tokens | null> {
  if (!refreshing) {
    const body = JSON.stringify({ refresh_token: tokens.refresh });
    refreshing = fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const data = (await res.json()) as Tokens;
        tokens.set(data.access_token, data.refresh_token);
        return data;
      })
      .catch(() => {
        // The server did not answer at all — that is a different problem
        // from "this refresh token is no longer valid".
        throw networkError();
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

async function parse(res: Response) {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  const access = tokens.access;
  if (access) headers.set("authorization", `Bearer ${access}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("content-type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    // The server is not there. Everything else (a wrong password, a missing
    // table) comes back as an answer; this one never arrives.
    throw networkError();
  }

  if (res.status === 401 && retry && tokens.refresh) {
    const fresh = await refreshTokens();
    if (fresh) return request<T>(path, init, false);
  }

  if (!res.ok) {
    const payload = (await parse(res)) as { error?: { code?: string; message?: string; field?: string } } | null;
    throw new ApiError(
      res.status,
      payload?.error?.code ?? "internal",
      payload?.error?.message ?? `요청이 실패했습니다 (${res.status})`,
      payload?.error?.field ?? null,
    );
  }

  if (res.status === 204) return undefined as T;
  return (await parse(res)) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });

export const api = {
  signup(input: { email: string; password: string; name: string; workspace_name: string }) {
    return post<Session>("/auth/signup", input);
  },
  login(input: { email: string; password: string }) {
    return post<Session>("/auth/login", input);
  },
  me() {
    return get<User>("/me");
  },
  updateMe(input: {
    name?: string;
    title?: string;
    avatar_color?: string;
    status_text?: string;
    presence?: Presence;
  }) {
    return patch<User>("/me", input);
  },
  workspaces() {
    return get<Workspace[]>("/workspaces");
  },
  bootstrap(workspaceId: string) {
    return get<Bootstrap>(`/workspaces/${workspaceId}/bootstrap`);
  },
  channels(workspaceId: string) {
    return get<Channel[]>(`/workspaces/${workspaceId}/channels`);
  },
  createChannel(
    workspaceId: string,
    input: { name: string; topic?: string; is_private?: boolean; member_ids?: string[] },
  ) {
    return post<Channel>(`/workspaces/${workspaceId}/channels`, input);
  },
  channel(channelId: string) {
    return get<Channel>(`/channels/${channelId}`);
  },
  updateChannel(channelId: string, input: { name?: string; topic?: string; purpose?: string }) {
    return patch<Channel>(`/channels/${channelId}`, input);
  },
  joinChannel(channelId: string) {
    return post<Channel>(`/channels/${channelId}/join`);
  },
  leaveChannel(channelId: string) {
    // The route is a POST — leaving is a state change, not a resource.
    return post<void>(`/channels/${channelId}/leave`);
  },
  channelMembers(channelId: string) {
    return get<Member[]>(`/channels/${channelId}/members`);
  },
  addChannelMember(channelId: string, userId: string) {
    return post<void>(`/channels/${channelId}/members`, { user_id: userId });
  },
  pins(channelId: string) {
    return get<Message[]>(`/channels/${channelId}/pins`);
  },
  markRead(channelId: string, messageId?: string) {
    return post<void>(`/channels/${channelId}/read`, messageId ? { message_id: messageId } : {});
  },
  messages(channelId: string, params: { limit?: number; before?: string } = {}) {
    const query = new URLSearchParams();
    if (params.limit) query.set("limit", String(params.limit));
    if (params.before) query.set("before", params.before);
    const qs = query.toString();
    return get<{ messages: Message[]; has_more: boolean }>(
      `/channels/${channelId}/messages${qs ? `?${qs}` : ""}`,
    );
  },
  sendMessage(
    channelId: string,
    input: {
      body: string;
      parent_id?: string;
      reply_to_id?: string;
      inline?: boolean;
      attachment_ids?: string[];
    },
  ) {
    return post<Message>(`/channels/${channelId}/messages`, input);
  },
  replies(messageId: string, limit = 100) {
    return get<Message[]>(`/messages/${messageId}/replies?limit=${limit}`);
  },
  editMessage(messageId: string, body: string) {
    return patch<Message>(`/messages/${messageId}`, { body });
  },
  deleteMessage(messageId: string) {
    return del<void>(`/messages/${messageId}`);
  },
  react(messageId: string, emoji: string) {
    return post<Message>(`/messages/${messageId}/reactions`, { emoji });
  },
  unreact(messageId: string, emoji: string) {
    return del<Message>(`/messages/${messageId}/reactions/${encodeURIComponent(emoji)}`);
  },
  pin(messageId: string) {
    return post<Message>(`/messages/${messageId}/pin`);
  },
  unpin(messageId: string) {
    return del<Message>(`/messages/${messageId}/pin`);
  },
  dms(workspaceId: string) {
    return get<Channel[]>(`/workspaces/${workspaceId}/dms`);
  },
  openDm(workspaceId: string, userId: string) {
    return post<Channel>(`/workspaces/${workspaceId}/dms`, { user_id: userId });
  },
  members(workspaceId: string) {
    return get<Member[]>(`/workspaces/${workspaceId}/members`);
  },
  updateMember(workspaceId: string, userId: string, role: string) {
    return patch<Member>(`/workspaces/${workspaceId}/members/${userId}`, { role });
  },
  removeMember(workspaceId: string, userId: string) {
    return del<void>(`/workspaces/${workspaceId}/members/${userId}`);
  },
  search(workspaceId: string, q: string, limit = 30) {
    return get<SearchResult[]>(
      `/workspaces/${workspaceId}/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    );
  },
  users(q = "") {
    return get<User[]>(`/users?q=${encodeURIComponent(q)}`);
  },
  invites(workspaceId: string) {
    return get<Invite[]>(`/workspaces/${workspaceId}/invites`);
  },
  createInvite(workspaceId: string, input: { email: string; role?: string }) {
    return post<Invite>(`/workspaces/${workspaceId}/invites`, input);
  },
  revokeInvite(workspaceId: string, inviteId: string) {
    return del<void>(`/workspaces/${workspaceId}/invites/${inviteId}`);
  },
  acceptInvite(token: string) {
    return post<Workspace>("/invites/accept", { token });
  },
  events(workspaceId: string, from?: string, to?: string) {
    const query = new URLSearchParams();
    if (from) query.set("from", from);
    if (to) query.set("to", to);
    const qs = query.toString();
    return get<ScheduleEvent[]>(`/workspaces/${workspaceId}/events${qs ? `?${qs}` : ""}`);
  },
  createEvent(workspaceId: string, input: EventInput) {
    return post<ScheduleEvent>(`/workspaces/${workspaceId}/events`, input);
  },
  updateEvent(eventId: string, input: Partial<EventInput>) {
    return patch<ScheduleEvent>(`/events/${eventId}`, input);
  },
  deleteEvent(eventId: string) {
    return del<void>(`/events/${eventId}`);
  },
  rsvpEvent(eventId: string, response: RsvpResponse) {
    return post<ScheduleEvent>(`/events/${eventId}/rsvp`, { response });
  },
  upload(file: File, workspaceId: string): Promise<FileRef> {
    const form = new FormData();
    form.append("file", file);
    // The workspace owns the file: it decides where it is kept and how much
    // room it may take.
    return request<FileRef>(`/files?workspace_id=${encodeURIComponent(workspaceId)}`, {
      method: "POST",
      body: form,
    });
  },

  /* ── organization ───────────────────────────────────────────────────── */

  orgOverview(workspaceId: string) {
    return get<OrgOverview>(`/workspaces/${workspaceId}/org`);
  },
  createOrgUnit(workspaceId: string, input: OrgUnitInput) {
    return post<OrgUnit>(`/workspaces/${workspaceId}/org/units`, input);
  },
  updateOrgUnit(unitId: string, input: Partial<OrgUnitInput>) {
    return patch<OrgUnit>(`/org/units/${unitId}`, input);
  },
  deleteOrgUnit(unitId: string) {
    return del<void>(`/org/units/${unitId}`);
  },
  addOrgUnitMember(unitId: string, userId: string) {
    return post<void>(`/org/units/${unitId}/members`, { user_id: userId });
  },
  removeOrgUnitMember(unitId: string, userId: string) {
    return del<void>(`/org/units/${unitId}/members/${userId}`);
  },
  addOrgUnitManager(unitId: string, userId: string) {
    return post<void>(`/org/units/${unitId}/managers`, { user_id: userId });
  },
  removeOrgUnitManager(unitId: string, userId: string) {
    return del<void>(`/org/units/${unitId}/managers/${userId}`);
  },

  /* ── projects and their board ────────────────────────────────────────── */

  projects(workspaceId: string) {
    return get<Project[]>(`/workspaces/${workspaceId}/projects`);
  },
  createProject(workspaceId: string, input: ProjectInput) {
    return post<Project>(`/workspaces/${workspaceId}/projects`, input);
  },
  updateProject(projectId: string, input: Partial<ProjectInput> & { is_archived?: boolean }) {
    return patch<Project>(`/projects/${projectId}`, input);
  },
  deleteProject(projectId: string) {
    return del<void>(`/projects/${projectId}`);
  },
  addProjectMember(projectId: string, userId: string) {
    return post<Project>(`/projects/${projectId}/members`, { user_id: userId });
  },
  removeProjectMember(projectId: string, userId: string) {
    return del<void>(`/projects/${projectId}/members/${userId}`);
  },
  myTasks(workspaceId: string) {
    return get<Task[]>(`/workspaces/${workspaceId}/tasks`);
  },
  projectTasks(projectId: string) {
    return get<Task[]>(`/projects/${projectId}/tasks`);
  },
  createTask(projectId: string, input: TaskInput) {
    return post<Task>(`/projects/${projectId}/tasks`, input);
  },
  updateTask(taskId: string, input: Partial<TaskInput> & { position?: number }) {
    return patch<Task>(`/tasks/${taskId}`, input);
  },
  deleteTask(taskId: string) {
    return del<void>(`/tasks/${taskId}`);
  },
  addTaskComment(taskId: string, body: string) {
    return post<TaskComment>(`/tasks/${taskId}/comments`, { body });
  },
  deleteTaskComment(commentId: string) {
    return del<void>(`/task-comments/${commentId}`);
  },

  /* ── milestones ───────────────────────────────────────────────────────── */

  roadmaps(projectId: string) {
    return get<Roadmap[]>(`/projects/${projectId}/roadmaps`);
  },
  deleteRoadmap(roadmapId: string) {
    return del<void>(`/roadmaps/${roadmapId}`);
  },

  milestones(projectId: string) {
    return get<Milestone[]>(`/projects/${projectId}/milestones`);
  },
  createMilestone(projectId: string, input: MilestoneInput) {
    return post<Milestone>(`/projects/${projectId}/milestones`, input);
  },
  updateMilestone(milestoneId: string, input: Partial<MilestoneInput>) {
    return patch<Milestone>(`/milestones/${milestoneId}`, input);
  },
  deleteMilestone(milestoneId: string) {
    return del<void>(`/milestones/${milestoneId}`);
  },
  deleteChannel(channelId: string) {
    return del<void>(`/channels/${channelId}`);
  },
};

/**
 * A file's address. The download route wants a bearer token, and an <img>
 * cannot send a header, so the token rides in the query string — the way the
 * websocket already takes it.
 */
export function fileUrl(path: string): string {
  const base = /^https?:/.test(path)
    ? path
    : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const token = tokens.access;
  if (!token) return base;
  return `${base}${base.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}
