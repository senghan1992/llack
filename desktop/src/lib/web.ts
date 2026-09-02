/**
 * Browser runtime — the Tauri command surface reimplemented over plain
 * HTTP + WebSocket.
 *
 * The UI only ever talks to the shell through the `api` / `events` objects in
 * `ipc.ts`, which makes that boundary swappable. This module fills the same
 * contract from a browser tab, so the real product can be clicked through
 * without a Rust toolchain — `npm run web`, one URL, no install.
 *
 * What a tab cannot provide, and this therefore does not pretend to:
 * - **No local cache.** `cached*` reads go to the network, so the desktop
 *   app's paint-from-disk-then-refresh behaviour is absent (it feels slower).
 * - **The outbox is in memory.** A reload drops queued messages; the desktop
 *   app persists them in SQLite.
 * - **Tokens live in `localStorage`**, not the OS keychain. Fine for a review
 *   build against a dev server; not a production posture.
 * - No OS notifications, tray badge or `llack://` deep links.
 */

import type {
  AgentEvent,
  AgentProviderStatus,
  AgentToolResult,
  AgentToolSpec,
} from "./agent/types";
import { demoRequest, isDemoBuild } from "@/lib/demo";
import { asCommandError, commandError } from "./errors";
import type {
  AppInstallation,
  AppSummary,
  BootstrapResult,
  Channel,
  ChannelKind,
  ChannelMemberEntry,
  ChannelMembership,
  ConnectionStatus,
  DrainReport,
  FileRef,
  Id,
  InviteOut,
  Message,
  PanelSession,
  PendingMessage,
  Presence,
  SearchResult,
  SendResult,
  ServerFrame,
  SyncEffect,
  User,
  Workspace,
} from "./types";

const API_PREFIX = "/api/v1";
const SESSION_KEY = "llack.web.session";
const REFRESH_SKEW_MS = 60_000;
const MAX_BACKOFF_MS = 15_000;

interface StoredSession {
  accessToken: string;
  refreshToken: string;
  /** ISO timestamp; the access token is refreshed before this. */
  expiresAt: string;
}

interface CursorPage<T> {
  items: T[];
  next_cursor?: string | null;
  prev_cursor?: string | null;
  has_more?: boolean;
}

// ── Mutable runtime state ───────────────────────────────────────────────────

let serverUrl = defaultServerUrl();
let session = loadSession();
let me: User | null = null;
let activeWorkspaceId: Id | null = null;

/**
 * The server the tab talks to.
 *
 * Same-origin by default: `npm run web` proxies `/api` to the backend, which
 * keeps cookies, CORS and the WebSocket origin check out of the picture. A
 * `?server=` query parameter overrides it for pointing at a remote backend.
 */
function defaultServerUrl(): string {
  const override = new URLSearchParams(window.location.search).get("server");
  return (override ?? window.location.origin).replace(/\/+$/, "");
}

function apiRoot(): string {
  return serverUrl + API_PREFIX;
}

function loadSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    // Private browsing or blocked site data: run without a resumable session.
    return null;
  }
}

function saveSession(next: StoredSession | null): void {
  session = next;
  try {
    if (next) {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    } else {
      window.localStorage.removeItem(SESSION_KEY);
    }
  } catch {
    // Keep the in-memory session; it just will not survive a reload.
  }
}

// ── Event emitter ───────────────────────────────────────────────────────────

type Handler = (payload: unknown) => void;

const listeners = new Map<string, Set<Handler>>();

function on<T>(name: string, handler: (payload: T) => void): Promise<() => void> {
  const set = listeners.get(name) ?? new Set<Handler>();
  set.add(handler as Handler);
  listeners.set(name, set);
  return Promise.resolve(() => {
    set.delete(handler as Handler);
  });
}

function emit<T>(name: string, payload: T): void {
  for (const handler of listeners.get(name) ?? []) {
    try {
      (handler as (value: T) => void)(payload);
    } catch (error) {
      console.error(`[web] listener for ${name} threw`, error);
    }
  }
}

// ── HTTP ────────────────────────────────────────────────────────────────────

/** ULID-shaped id, so `client_msg_id` sorts and validates like the real thing. */
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function ulid(): string {
  let time = Date.now();
  let stamp = "";
  for (let i = 0; i < 10; i += 1) {
    stamp = CROCKFORD.charAt(time % 32) + stamp;
    time = Math.floor(time / 32);
  }
  let random = "";
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  for (const byte of bytes) {
    random += CROCKFORD.charAt(byte % 32);
  }
  return stamp + random;
}

async function errorFromResponse(response: Response): Promise<never> {
  let code = `http_${response.status}`;
  let message = `요청이 실패했습니다 (HTTP ${response.status}).`;
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string };
      detail?: string;
    };
    if (body.error?.code) code = body.error.code;
    if (body.error?.message) message = body.error.message;
    else if (body.detail) message = body.detail;
  } catch {
    // Non-JSON error body; the status-derived defaults stand.
  }
  throw commandError(code, message, {
    status: response.status,
    requiresReauth: response.status === 401,
  });
}

/** Exchange the refresh token for a new pair, or give up and force re-auth. */
async function refreshTokens(): Promise<void> {
  const refreshToken = session?.refreshToken;
  if (!refreshToken) {
    throw commandError("unauthorized", "다시 로그인해주세요.", {
      status: 401,
      requiresReauth: true,
    });
  }

  const response = await fetch(`${apiRoot()}/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    saveSession(null);
    me = null;
    throw commandError("unauthorized", "세션이 만료되었습니다. 다시 로그인해주세요.", {
      status: 401,
      requiresReauth: true,
    });
  }

  const tokens = (await response.json()) as {
    access_token: string;
    refresh_token: string;
    expires_at: string;
  };
  saveSession({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt: tokens.expires_at,
  });
}

async function accessToken(): Promise<string> {
  if (!session) {
    throw commandError("unauthorized", "로그인이 필요합니다.", {
      status: 401,
      requiresReauth: true,
    });
  }
  const expiresAt = Date.parse(session.expiresAt);
  if (Number.isFinite(expiresAt) && expiresAt - Date.now() < REFRESH_SKEW_MS) {
    await refreshTokens();
  }
  return session!.accessToken;
}

interface RequestOptions {
  /** Set false for the endpoints that mint tokens rather than consume them. */
  auth?: boolean;
  /** Internal: prevents a refresh loop on a second 401. */
  retry?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  { auth = true, retry = true }: RequestOptions = {},
): Promise<T> {
  // The demo build answers from memory. One branch, at the single chokepoint,
  // so everything above it — the adapter, the outbox, the store, the whole UI —
  // is the same code the real browser mode runs. A separate mock app would look
  // like the product without being it.
  if (isDemoBuild()) return demoRequest<T>(method, path, body);

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (auth) headers.authorization = `Bearer ${await accessToken()}`;

  let response: Response;
  try {
    response = await fetch(apiRoot() + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw commandError("network_error", "서버에 연결할 수 없습니다.");
  }

  if (response.status === 401 && auth && retry && session?.refreshToken) {
    await refreshTokens();
    return request<T>(method, path, body, { auth, retry: false });
  }
  if (!response.ok) await errorFromResponse(response);

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

// ── Outbox ──────────────────────────────────────────────────────────────────

/**
 * In-memory only. The desktop app keeps this in SQLite so a crash cannot lose
 * a message; here a reload does, which is the honest cost of the tab.
 */
const outbox = new Map<string, PendingMessage>();

/*
 * The web outbox drains itself.
 *
 * Queueing a message and then waiting for a human to find a retry button is
 * how a rate-limited burst used to die: the entries sat "pending" forever and
 * a reload erased them. Every path that leaves something retryable in the
 * outbox now also schedules a drain, with a backoff that grows with the
 * entries' attempt count. After a drain pass, affected channels get a
 * `channel_changed` sync effect so the store refreshes both the transcript
 * (the echo may have raced the response) and the pending rows.
 */
let drainTimer: number | null = null;

function scheduleDrain(delayMs: number): void {
  if (drainTimer !== null) return;
  drainTimer = window.setTimeout(() => {
    drainTimer = null;
    void runScheduledDrain();
  }, delayMs);
}

async function runScheduledDrain(): Promise<void> {
  const channels = new Set(
    [...outbox.values()]
      .filter((entry) => entry.state !== "failed")
      .map((entry) => entry.channel_id),
  );
  if (channels.size === 0) return;

  const report = await webApi.drainOutbox();
  for (const channelId of channels) {
    emit<SyncEffect>("sync", { kind: "channel_changed", channel_id: channelId });
  }
  if (report.still_pending > 0) {
    const attempts = Math.max(
      1,
      ...[...outbox.values()]
        .filter((entry) => entry.state === "pending")
        .map((entry) => entry.attempts),
    );
    scheduleDrain(Math.min(3_000 * attempts, 20_000));
  }
}

function isRetryable(code: string): boolean {
  return code === "network_error" || code.startsWith("http_5") || code === "rate_limited";
}

async function postMessage(entry: PendingMessage): Promise<Message> {
  return request<Message>("POST", `/channels/${entry.channel_id}/messages`, {
    body: entry.payload.body,
    client_msg_id: entry.client_msg_id,
    parent_id: entry.payload.parent_id ?? null,
    also_send_to_channel: entry.payload.also_send_to_channel ?? false,
    file_ids: entry.payload.file_ids ?? [],
  });
}

// ── Realtime ────────────────────────────────────────────────────────────────

let socket: WebSocket | null = null;
let heartbeat: number | null = null;
let reconnectTimer: number | null = null;
let backoffMs = 1_000;
let closedByUs = false;
const pendingCommands: string[] = [];

/**
 * The server drops a connection's channel subscriptions when it closes, so the
 * set is kept here and replayed on every `hello`.
 */
const subscribedChannels = new Set<Id>();

function socketUrl(token: string, workspaceId: Id | null): string {
  const base = new URL(apiRoot() + "/ws", window.location.href);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.searchParams.set("token", token);
  if (workspaceId) base.searchParams.set("workspace_id", workspaceId);
  return base.toString();
}

function sendCommand(type: string, data: Record<string, unknown> = {}): void {
  const frame = JSON.stringify({ type, data });
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(frame);
  } else {
    // Queue rather than drop: `select_workspace` subscribes immediately after
    // asking for a reconnect, and the socket is not open yet.
    pendingCommands.push(frame);
  }
}

function subscribe(channelIds: Id[]): void {
  for (const id of channelIds) subscribedChannels.add(id);
  if (channelIds.length > 0) sendCommand("subscribe", { channel_ids: channelIds });
}

function unsubscribe(channelIds: Id[]): void {
  for (const id of channelIds) subscribedChannels.delete(id);
  sendCommand("unsubscribe", { channel_ids: channelIds });
}

function stopHeartbeat(): void {
  if (heartbeat !== null) {
    window.clearInterval(heartbeat);
    heartbeat = null;
  }
}

function disconnectSocket(): void {
  closedByUs = true;
  stopHeartbeat();
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket?.close();
  socket = null;
  pendingCommands.length = 0;
}

async function connectSocket(workspaceId: Id | null): Promise<void> {
  if (!session) return;
  activeWorkspaceId = workspaceId ?? activeWorkspaceId;

  if (isDemoBuild()) {
    // No socket to open. Reported as connected rather than left in "연결 중":
    // a permanent connecting spinner is the first thing a reviewer would file
    // as a bug, and in a single page there is genuinely nothing to connect to.
    // What is therefore absent, honestly: typing indicators, presence dots
    // updating, and another person's message arriving while you watch.
    emit<ConnectionStatus>("connection", {
      status: "connected",
      session_id: "demo",
      workspace_ids: activeWorkspaceId ? [activeWorkspaceId] : [],
    });
    return;
  }

  disconnectSocket();
  closedByUs = false;

  let token: string;
  try {
    token = await accessToken();
  } catch {
    return;
  }

  const ws = new WebSocket(socketUrl(token, activeWorkspaceId));
  socket = ws;

  ws.onopen = () => {
    backoffMs = 1_000;
    for (const frame of pendingCommands.splice(0)) ws.send(frame);
  };

  ws.onmessage = (event) => {
    let frame: ServerFrame;
    try {
      frame = JSON.parse(String(event.data)) as ServerFrame;
    } catch {
      return;
    }
    handleFrame(frame);
  };

  ws.onclose = (event) => {
    stopHeartbeat();
    if (socket === ws) socket = null;
    if (closedByUs) return;

    // 4001 is the gateway's "unauthorized" — retrying with the same token
    // would just loop, so ask for a fresh one instead.
    if (event.code === 4001) {
      void refreshTokens()
        .then(() => connectSocket(activeWorkspaceId))
        .catch((error) => {
          emit<ConnectionStatus>("connection", {
            status: "disconnected",
            reason: "unauthorized",
            will_retry_in_ms: null,
          });
          emit("auth-lost", { message: asCommandError(error).message });
        });
      return;
    }

    emit<ConnectionStatus>("connection", {
      status: "disconnected",
      reason: event.reason || "connection closed",
      will_retry_in_ms: backoffMs,
    });
    reconnectTimer = window.setTimeout(() => {
      backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
      void connectSocket(activeWorkspaceId);
    }, backoffMs);
  };
}

function handleFrame(frame: ServerFrame): void {
  emit<ServerFrame>("frame", frame);

  if (frame.type === "hello") {
    const data = frame.data as {
      session_id?: string;
      workspace_ids?: Id[];
      heartbeat_seconds?: number;
    };
    emit<ConnectionStatus>("connection", {
      status: "connected",
      session_id: data.session_id ?? "",
      workspace_ids: data.workspace_ids ?? [],
    });

    const seconds = data.heartbeat_seconds ?? 25;
    stopHeartbeat();
    heartbeat = window.setInterval(() => sendCommand("ping"), seconds * 1_000);

    if (subscribedChannels.size > 0) {
      sendCommand("subscribe", { channel_ids: [...subscribedChannels] });
    }
    // Anything that happened while the socket was down is not replayed, so the
    // sidebar re-reads its counters.
    emit<SyncEffect>("sync", { kind: "sidebar_changed" });
    return;
  }

  if (frame.type === "pong") return;

  const effect = toSyncEffect(frame);
  if (effect.kind !== "ignored") emit<SyncEffect>("sync", effect);
}

/**
 * Frame → UI effect, mirroring `core/src/sync.rs::apply`.
 *
 * The Rust version also writes the frame into the cache; with no cache here,
 * the effect alone drives a re-fetch of the affected channel or thread.
 */
function toSyncEffect(frame: ServerFrame): SyncEffect {
  const data = frame.data ?? {};
  const field = (key: string): string | null => {
    const value = data[key];
    return typeof value === "string" ? value : null;
  };

  switch (frame.type) {
    case "message.created":
    case "message.updated": {
      const message = data.message as Message | undefined;
      if (!message) return { kind: "ignored" };

      // An echo of our own message retires its outbox entry.
      if (message.client_msg_id && message.author?.id === me?.id) {
        for (const [id, entry] of outbox) {
          if (entry.client_msg_id === message.client_msg_id) outbox.delete(id);
        }
      }

      return message.parent_id
        ? {
            kind: "thread_changed",
            channel_id: message.channel_id,
            parent_id: message.parent_id,
          }
        : { kind: "channel_changed", channel_id: message.channel_id };
    }

    case "message.deleted":
    case "reaction.added":
    case "reaction.removed": {
      const channelId = field("channel_id");
      return channelId
        ? { kind: "channel_changed", channel_id: channelId }
        : { kind: "ignored" };
    }

    case "channel.created":
    case "channel.updated":
    case "channel.archived":
    case "channel.member_joined":
    case "channel.member_left":
    case "channel.read":
    case "app.installed":
    case "app.uninstalled":
      return { kind: "sidebar_changed" };

    case "notification":
      return {
        kind: "notify",
        title: field("title") ?? "Llack",
        body: field("body") ?? "",
        channel_id: field("channel_id"),
        message_id: field("message_id"),
      };

    case "typing": {
      const channelId = field("channel_id");
      const userId = field("user_id");
      if (!channelId || !userId || userId === me?.id) return { kind: "ignored" };
      return { kind: "typing", channel_id: channelId, user_id: userId };
    }

    case "presence.updated": {
      const userId = field("user_id");
      const presence = field("presence");
      if (!userId || !presence) return { kind: "ignored" };
      return { kind: "presence", user_id: userId, presence: presence as Presence };
    }

    default:
      return { kind: "ignored" };
  }
}

/** Reads that the desktop app answers from disk; a tab has to try the network. */
async function optional<T>(load: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await load();
  } catch {
    return fallback;
  }
}

// ── The command surface ─────────────────────────────────────────────────────

const device = { device_name: "웹 브라우저", platform: "web", app_version: "0.1.0" };

export const webApi = {
  bootstrap: async (url: string): Promise<BootstrapResult> => {
    serverUrl = url.replace(/\/+$/, "");
    if (!session?.refreshToken) {
      return { server_url: serverUrl, user: null, resumed: false };
    }
    try {
      await refreshTokens();
      me = await request<User>("GET", "/me");
      void connectSocket(null);
      return { server_url: serverUrl, user: me, resumed: true };
    } catch {
      saveSession(null);
      me = null;
      return { server_url: serverUrl, user: null, resumed: false };
    }
  },

  login: async (email: string, password: string): Promise<User> => {
    const auth = await request<{
      user: User;
      tokens: { access_token: string; refresh_token: string; expires_at: string };
    }>("POST", "/auth/login", { email, password, device }, { auth: false });

    saveSession({
      accessToken: auth.tokens.access_token,
      refreshToken: auth.tokens.refresh_token,
      expiresAt: auth.tokens.expires_at,
    });
    me = auth.user;
    void connectSocket(null);
    return auth.user;
  },

  register: async (email: string, password: string, displayName: string): Promise<User> => {
    const auth = await request<{
      user: User;
      tokens: { access_token: string; refresh_token: string; expires_at: string };
    }>(
      "POST",
      "/auth/register",
      { email, password, display_name: displayName, device },
      { auth: false },
    );

    saveSession({
      accessToken: auth.tokens.access_token,
      refreshToken: auth.tokens.refresh_token,
      expiresAt: auth.tokens.expires_at,
    });
    me = auth.user;
    void connectSocket(null);
    return auth.user;
  },

  logout: async (): Promise<void> => {
    try {
      await request<void>("POST", "/auth/logout");
    } finally {
      disconnectSocket();
      saveSession(null);
      me = null;
      activeWorkspaceId = null;
      subscribedChannels.clear();
      outbox.clear();
    }
  },

  currentUser: async (): Promise<User | null> => {
    if (!session) return null;
    me = await optional(() => request<User>("GET", "/me"), null);
    return me;
  },

  updateProfile: async (patch: {
    display_name?: string;
    title?: string;
    avatar_url?: string;
  }): Promise<User> => {
    me = await request<User>("PATCH", "/me", patch);
    return me;
  },

  updateStatus: async (patch: {
    status_emoji?: string | null;
    status_text?: string | null;
  }): Promise<User> => {
    me = await request<User>("PUT", "/me/status", patch);
    return me;
  },

  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("POST", "/auth/password", {
      current_password: currentPassword,
      new_password: newPassword,
    }),

  createInvites: (workspaceId: Id, emails: string[], role = "member") =>
    request<InviteOut[]>("POST", `/workspaces/${workspaceId}/invites`, {
      emails,
      role,
    }),

  acceptInvite: (token: string) =>
    request<Workspace>("POST", "/invites/accept", { token }),

  // ── Workspaces ────────────────────────────────────────────────────────

  listWorkspaces: () => request<Workspace[]>("GET", "/workspaces"),

  selectWorkspace: async (workspaceId: Id): Promise<Channel[]> => {
    activeWorkspaceId = workspaceId;
    await connectSocket(workspaceId);
    const channels = await request<Channel[]>(
      "GET",
      `/workspaces/${workspaceId}/channels`,
    );
    subscribedChannels.clear();
    subscribe(channels.map((channel) => channel.id));
    return channels;
  },

  listWorkspaceUsers: (workspaceId: Id, q?: string) =>
    request<User[]>("GET", `/workspaces/${workspaceId}/users${query({ limit: 200, q })}`),

  // ── Channels ──────────────────────────────────────────────────────────

  cachedChannels: (workspaceId: Id) =>
    optional(
      () => request<Channel[]>("GET", `/workspaces/${workspaceId}/channels`),
      [] as Channel[],
    ),

  refreshChannels: (workspaceId: Id) =>
    request<Channel[]>("GET", `/workspaces/${workspaceId}/channels`),

  browseChannels: (workspaceId: Id, q?: string) =>
    request<Channel[]>("GET", `/workspaces/${workspaceId}/channels/browse${query({ q })}`),

  createChannel: (workspaceId: Id, name: string, kind: ChannelKind, memberIds: Id[] = []) =>
    request<Channel>("POST", `/workspaces/${workspaceId}/channels`, {
      name,
      kind,
      member_ids: memberIds,
    }),

  openDm: (workspaceId: Id, userIds: Id[]) =>
    request<Channel>("POST", `/workspaces/${workspaceId}/channels/dm`, {
      user_ids: userIds,
    }),

  updateChannel: (channelId: Id, patch: { name?: string; topic?: string; is_archived?: boolean }) =>
    request<Channel>("PATCH", `/channels/${channelId}`, patch),

  channelMembers: (channelId: Id) =>
    request<ChannelMemberEntry[]>("GET", `/channels/${channelId}/members`),

  addChannelMembers: (channelId: Id, userIds: Id[]) =>
    request<Id[]>("POST", `/channels/${channelId}/members`, { user_ids: userIds }),

  removeChannelMember: (channelId: Id, userId: Id) =>
    request<void>("DELETE", `/channels/${channelId}/members/${userId}`),

  joinChannel: async (channelId: Id): Promise<Channel> => {
    const channel = await request<Channel>("POST", `/channels/${channelId}/join`);
    subscribe([channelId]);
    return channel;
  },

  leaveChannel: async (channelId: Id): Promise<void> => {
    await request<void>("POST", `/channels/${channelId}/leave`);
    unsubscribe([channelId]);
  },

  updateMembership: (channelId: Id, patch: Record<string, unknown>) =>
    request<ChannelMembership>("PATCH", `/channels/${channelId}/membership`, patch),

  markRead: (channelId: Id, messageId?: Id) =>
    request<ChannelMembership>("POST", `/channels/${channelId}/read`, {
      message_id: messageId ?? null,
    }),

  // ── Messages ──────────────────────────────────────────────────────────

  cachedHistory: (channelId: Id, limit = 80) =>
    optional(() => webApi.refreshHistory(channelId, limit), [] as Message[]),

  refreshHistory: async (channelId: Id, limit = 80): Promise<Message[]> => {
    const page = await request<CursorPage<Message>>(
      "GET",
      `/channels/${channelId}/messages${query({ limit })}`,
    );
    // The API returns newest-first; the UI wants oldest-first.
    return page.items.reverse();
  },

  loadOlderMessages: async (channelId: Id, before: Id, limit = 50): Promise<Message[]> => {
    const page = await request<CursorPage<Message>>(
      "GET",
      `/channels/${channelId}/messages${query({ limit, before })}`,
    );
    return page.items.reverse();
  },

  threadReplies: async (messageId: Id): Promise<Message[]> => {
    const page = await request<CursorPage<Message>>(
      "GET",
      `/messages/${messageId}/replies${query({ limit: 200 })}`,
    );
    return page.items;
  },

  sendMessage: async (options: {
    channelId: Id;
    body: string;
    parentId?: Id | null;
    alsoSendToChannel?: boolean;
    fileIds?: Id[];
  }): Promise<SendResult> => {
    const clientMsgId = ulid();
    const entry: PendingMessage = {
      id: clientMsgId,
      channel_id: options.channelId,
      client_msg_id: clientMsgId,
      payload: {
        body: options.body,
        parent_id: options.parentId ?? null,
        also_send_to_channel: options.alsoSendToChannel ?? false,
        file_ids: options.fileIds ?? [],
      },
      state: "sending",
      attempts: 1,
      created_at_ms: Date.now(),
    };

    // A pending entry ahead of us means order is at stake: sending directly
    // would overtake it. Join the queue instead — the drain sends in order.
    const blocked = [...outbox.values()].some(
      (queued) =>
        queued.channel_id === options.channelId && queued.state !== "failed",
    );
    if (blocked) {
      outbox.set(clientMsgId, { ...entry, state: "pending", attempts: 0 });
      scheduleDrain(300);
      return {
        message: null,
        client_msg_id: clientMsgId,
        queued: true,
        error: "앞의 메시지가 전송되는 대로 함께 전송됩니다.",
        error_code: "queued_in_order",
      };
    }

    try {
      const message = await postMessage(entry);
      return { message, client_msg_id: clientMsgId, queued: false };
    } catch (error) {
      const parsed = asCommandError(error);
      if (!isRetryable(parsed.code)) throw parsed;

      // Queue it, exactly as the desktop outbox would, so the composer clears
      // and the message goes out when the server comes back — and schedule
      // the drain that makes "goes out" true without human help.
      outbox.set(clientMsgId, {
        ...entry,
        state: "pending",
        last_error: parsed.message,
      });
      scheduleDrain(parsed.code === "rate_limited" ? 3_500 : 2_000);
      return {
        message: null,
        client_msg_id: clientMsgId,
        queued: true,
        error: parsed.message,
        error_code: parsed.code,
      };
    }
  },

  editMessage: (messageId: Id, body: string) =>
    request<Message>("PATCH", `/messages/${messageId}`, { body }),

  deleteMessage: (messageId: Id) => request<void>("DELETE", `/messages/${messageId}`),

  setPinned: (messageId: Id, pinned: boolean) =>
    request<Message>("POST", `/messages/${messageId}/pin?pinned=${pinned}`),

  channelPins: (channelId: Id) =>
    request<Message[]>("GET", `/channels/${channelId}/pins`),

  toggleReaction: async (messageId: Id, emoji: string, add: boolean): Promise<void> => {
    if (add) {
      await request<void>("PUT", `/messages/${messageId}/reactions`, { emoji });
    } else {
      await request<void>(
        "DELETE",
        `/messages/${messageId}/reactions${query({ emoji })}`,
      );
    }
  },

  typing: async (channelId: Id, parentId?: Id | null): Promise<void> => {
    sendCommand("typing", { channel_id: channelId, parent_id: parentId ?? null });
  },

  // ── Outbox ────────────────────────────────────────────────────────────

  pendingMessages: async (channelId: Id): Promise<PendingMessage[]> =>
    [...outbox.values()]
      .filter((entry) => entry.channel_id === channelId)
      .sort((a, b) => a.created_at_ms - b.created_at_ms),

  drainOutbox: async (): Promise<DrainReport> => {
    const report: DrainReport = { sent: 0, still_pending: 0, failed: 0 };

    for (const [id, entry] of [...outbox]) {
      if (entry.state === "failed") {
        report.failed += 1;
        continue;
      }
      try {
        await postMessage(entry);
        outbox.delete(id);
        report.sent += 1;
      } catch (error) {
        const parsed = asCommandError(error);
        if (isRetryable(parsed.code)) {
          // Order matters within a channel: stop rather than send past a gap.
          outbox.set(id, {
            ...entry,
            state: "pending",
            attempts: entry.attempts + 1,
            last_error: parsed.message,
          });
          report.still_pending = outbox.size - report.failed;
          return report;
        }
        outbox.set(id, {
          ...entry,
          state: "failed",
          attempts: entry.attempts + 1,
          last_error: parsed.message,
        });
        report.failed += 1;
      }
    }
    return report;
  },

  retryFailedMessages: async (): Promise<number> => {
    let revived = 0;
    for (const [id, entry] of outbox) {
      if (entry.state === "failed") {
        outbox.set(id, { ...entry, state: "pending", last_error: null });
        revived += 1;
      }
    }
    return revived;
  },

  discardPendingMessage: async (entryId: string): Promise<void> => {
    outbox.delete(entryId);
  },

  // ── Search ────────────────────────────────────────────────────────────

  search: (workspaceId: Id, q: string) =>
    request<SearchResult>("GET", `/workspaces/${workspaceId}/search${query({ q })}`),

  // ── Files ─────────────────────────────────────────────────────────────

  /**
   * The desktop shell takes a filesystem path; a tab has a `File` from the
   * picker. Both end at the same two-step upload.
   */
  uploadFile: async (workspaceId: Id, source: string | File): Promise<FileRef> => {
    if (typeof source === "string") {
      throw commandError(
        "unsupported_in_browser",
        "브라우저에서는 파일 경로로 업로드할 수 없습니다.",
      );
    }

    const ticket = await request<{
      file_id: string;
      upload_url: string;
      headers?: Record<string, string>;
    }>("POST", `/workspaces/${workspaceId}/files`, {
      filename: source.name,
      mime_type: source.type || "application/octet-stream",
      size_bytes: source.size,
    });

    const isAbsolute = ticket.upload_url.startsWith("http");
    const url = isAbsolute ? ticket.upload_url : serverUrl + ticket.upload_url;
    const headers: Record<string, string> = { ...(ticket.headers ?? {}) };
    if (!isAbsolute) headers.authorization = `Bearer ${await accessToken()}`;

    const response = await fetch(url, { method: "PUT", headers, body: source });
    if (!response.ok) await errorFromResponse(response);

    if (isAbsolute) {
      return request<FileRef>("POST", `/files/${ticket.file_id}/complete`);
    }
    return (await response.json()) as FileRef;
  },

  /** Hands the bytes to the browser's downloader and returns the filename. */
  downloadFile: async (fileId: Id, filename: string): Promise<string> => {
    const response = await fetch(`${apiRoot()}/files/${fileId}/download`, {
      headers: { authorization: `Bearer ${await accessToken()}` },
    });
    if (!response.ok) await errorFromResponse(response);

    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(href);
    return filename;
  },

  /**
   * Same bytes as the download path, folded into a data URL so the transcript
   * can render the image inline. The `mime` parameter exists for the desktop
   * shell; here the blob already knows its own type.
   */
  filePreview: async (fileId: Id, _mime: string): Promise<string> => {
    const response = await fetch(`${apiRoot()}/files/${fileId}/download`, {
      headers: { authorization: `Bearer ${await accessToken()}` },
    });
    if (!response.ok) await errorFromResponse(response);
    const blob = await response.blob();
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
      reader.readAsDataURL(blob);
    });
  },

  // ── Mini-apps ─────────────────────────────────────────────────────────

  listInstalledApps: (workspaceId: Id) =>
    request<AppInstallation[]>("GET", `/workspaces/${workspaceId}/apps`),

  listAvailableApps: (workspaceId: Id) =>
    request<AppSummary[]>("GET", `/workspaces/${workspaceId}/apps/available`),

  installApp: (workspaceId: Id, appId: Id, grantedScopes?: string[]) =>
    request<AppInstallation>("POST", `/workspaces/${workspaceId}/apps/${appId}/install`, {
      granted_scopes: grantedScopes ?? null,
    }),

  addLinkApp: (workspaceId: Id, name: string, url: string) =>
    request<AppInstallation>("POST", `/workspaces/${workspaceId}/apps/link`, {
      name,
      url,
    }),

  uninstallApp: (installationId: Id) =>
    request<void>("DELETE", `/app-installations/${installationId}`),

  openAppPanel: (installationId: Id, channelId?: Id) =>
    request<PanelSession>(
      "POST",
      `/app-installations/${installationId}/panel-session${query({ channel_id: channelId })}`,
    ),

  // ── Shell ─────────────────────────────────────────────────────────────

  setPresence: async (presence: string): Promise<void> => {
    sendCommand("presence", { presence });
  },

  reconnect: async (): Promise<void> => {
    await connectSocket(activeWorkspaceId);
  },

  cacheStats: async (): Promise<Record<string, unknown>> => ({
    mode: "web",
    cached_messages: 0,
    queued_messages: outbox.size,
  }),

  pruneCache: async (): Promise<number> => 0,
};

export const webEvents = {
  /**
   * The shell's `ready` event has no counterpart here, so it is synthesised on
   * subscribe — after the current task, so the handler is registered when it
   * lands.
   */
  onReady: (
    handler: (payload: {
      default_server_url: string;
      version: string;
      platform: string;
    }) => void,
  ): Promise<() => void> => {
    const timer = window.setTimeout(
      () =>
        handler({
          default_server_url: serverUrl,
          version: "0.1.0-web",
          platform: "web",
        }),
      0,
    );
    return Promise.resolve(() => window.clearTimeout(timer));
  },

  onConnection: (handler: (status: ConnectionStatus) => void) =>
    on<ConnectionStatus>("connection", handler),

  onSync: (handler: (effect: SyncEffect) => void) => on<SyncEffect>("sync", handler),

  onFrame: (handler: (frame: ServerFrame) => void) => on<ServerFrame>("frame", handler),

  onAuthLost: (handler: (payload: { message: string }) => void) =>
    on<{ message: string }>("auth-lost", handler),

  /** No tray icon in a tab; the sidebar's own unread badges stand in. */
  onBadge: (handler: (payload: { count: number }) => void) => {
    void handler;
    return Promise.resolve(() => {});
  },

  onDeepLink: (handler: (payload: { urls: string[] }) => void) => {
    void handler;
    return Promise.resolve(() => {});
  },

  /**
   * Agent events, deliverable from a test.
   *
   * The scripted fake never opens a real approval, so without a way to push one
   * the approval card would be unreachable in a browser — and it is the one
   * piece of this UI where a wrong click runs a command, so it is the piece
   * most worth seeing rendered. `window.__llackAgentEmit` is that way in.
   */
  onAgent: (handler: (event: AgentEvent) => void) => {
    agentHandlers.add(handler);
    installAgentTestHook();
    return Promise.resolve(() => {
      agentHandlers.delete(handler);
    });
  },

  /** The desktop tray drives presence; in a tab, tab visibility does. */
  onPresenceRequest: (handler: (payload: { presence: string }) => void) => {
    const onVisibility = () => {
      handler({ presence: document.hidden ? "away" : "active" });
    };
    document.addEventListener("visibilitychange", onVisibility);
    return Promise.resolve(() => {
      document.removeEventListener("visibilitychange", onVisibility);
    });
  },
};

/** Browser file picker, standing in for the Tauri dialog plugin. */
export function pickFilesInBrowser(multiple: boolean): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = multiple;
    input.onchange = () => resolve([...(input.files ?? [])]);
    // A cancelled picker fires no `change`; resolve empty so the caller's
    // `finally` still runs.
    input.oncancel = () => resolve([]);
    input.click();
  });
}

/* ── The agent, in a browser tab ───────────────────────────────────────── */

/**
 * The browser half of `AgentHostApi`.
 *
 * Two different behaviours, on purpose:
 *
 * - Anything that would touch this machine or the OS keychain **rejects**. Not
 *   a silent no-op: a stub that quietly returns nothing turns "this host cannot
 *   do that" into "the agent mysteriously did nothing", and the tool schemas
 *   are filtered in Rust anyway so a reached stub means a bug worth seeing.
 * - Session bookkeeping and the tool gate are served by a **scripted fake**, so
 *   the panel, the streaming UI and the approval card can be driven end to end
 *   in a headless browser with no API key and no Tauri build. That is what
 *   makes this surface testable in CI at all.
 */
function desktopOnly<T>(what: string): Promise<T> {
  return Promise.reject(
    commandError(
      "unsupported_in_browser",
      `${what}는 데스크톱 앱에서만 사용할 수 있습니다.`,
    ),
  );
}

const agentHandlers = new Set<(event: AgentEvent) => void>();

/**
 * Expose one function a test can call to deliver an agent event.
 *
 * Deliberately not a general-purpose bridge: it takes an already-typed event
 * and fans it out to the same handlers the shell would feed. Nothing about the
 * panel's behaviour is special-cased for tests.
 */
function installAgentTestHook(): void {
  const target = window as unknown as {
    __llackAgentEmit?: (event: AgentEvent) => void;
  };
  if (target.__llackAgentEmit) return;
  target.__llackAgentEmit = (event) => {
    for (const handler of agentHandlers) handler(event);
  };
}

/** The fake provider's state, kept out of the exported surface. */
const fakeAgent = {
  sessionSeq: 0,
  /** Tool calls the fake gate approved, for assertions in tests. */
  calls: [] as Array<{ name: string; args: unknown }>,
};

export const webAgent = {
  agentProviderStatus: async (): Promise<AgentProviderStatus> => ({
    // There is no keychain in a browser, so there is no real provider to
    // connect. The scripted fake stands in, which is what makes the panel
    // testable here — and it says so in the model name rather than pretending.
    connected: true,
    provider_id: "fake",
    model: "fake-provider",
    key_fingerprint: null,
    last_error: null,
  }),

  agentProviderConnect: () =>
    desktopOnly<AgentProviderStatus>("프로바이더 연결"),

  agentProviderSetModel: () =>
    desktopOnly<AgentProviderStatus>("모델 변경"),

  agentProviderDisconnect: () =>
    desktopOnly<AgentProviderStatus>("프로바이더 연결 해제"),

  /**
   * The browser advertises the same catalog minus `host.*`.
   *
   * Hard-coded rather than fetched: there is no Rust here to ask. The names and
   * shapes must match `core/src/agent/tools/`, and the point of listing them is
   * that the scripted fake exercises the same code path the desktop does — the
   * panel does not know it is talking to a fake.
   */
  agentTools: async (): Promise<AgentToolSpec[]> => [
    {
      name: "chat.read_channel",
      description: "채널의 최근 메시지를 읽습니다.",
      input_schema: {
        type: "object",
        properties: {
          channel_id: { type: "string" },
          limit: { type: "integer" },
        },
        required: ["channel_id"],
        additionalProperties: false,
      },
    },
    {
      name: "chat.search",
      description: "워크스페이스에서 메시지를 검색합니다.",
      input_schema: {
        type: "object",
        properties: { query: { type: "string" } },
        required: ["query"],
        additionalProperties: false,
      },
    },
    {
      name: "artifact.query",
      description: "저장된 결과의 일부를 가져옵니다.",
      input_schema: {
        type: "object",
        properties: {
          handle: { type: "string" },
          op: { type: "string" },
        },
        required: ["handle", "op"],
        additionalProperties: false,
      },
    },
  ],

  agentSessions: async (_limit = 20): Promise<never[]> => [],

  agentOpenSession: async (sessionId: string | null): Promise<string> => {
    if (sessionId) return sessionId;
    fakeAgent.sessionSeq += 1;
    return `fake-session-${fakeAgent.sessionSeq}`;
  },

  agentToolCall: async (
    _sessionId: string,
    name: string,
    args: unknown,
  ): Promise<AgentToolResult> => {
    fakeAgent.calls.push({ name, args });
    if (name.startsWith("host.")) {
      // Exactly what the real gate does for a host tool in a browser: refuse,
      // and tell the model rather than throwing.
      return {
        content: { error: "이 호스트에서는 컴퓨터 제어를 사용할 수 없습니다." },
        artifact: null,
        is_error: true,
        taints: false,
        verdict: "refused",
      };
    }
    return {
      content: { note: "브라우저 모드의 가짜 도구 결과입니다.", name },
      artifact: null,
      is_error: false,
      taints: name.startsWith("chat."),
      verdict: "auto",
    };
  },

  agentResolveApproval: async (
    _requestId: string,
    _nonce: string,
    _approve: boolean,
    _remember: boolean,
  ): Promise<void> => {
    // Nothing to answer: the fake gate never opens a request.
  },

  agentCancel: async (_sessionId: string): Promise<void> => {},

  agentFocus: async (_sessionId: string, _channelId: string | null): Promise<void> => {},

  agentPickRoot: () => desktopOnly<string | null>("폴더 선택"),
};
