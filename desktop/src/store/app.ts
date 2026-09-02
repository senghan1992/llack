/**
 * The single application store.
 *
 * Deliberately one store rather than several: almost every interaction touches
 * more than one slice (opening a channel clears its unread count, which changes
 * the sidebar and the badge), and splitting that across stores turns each of
 * those into cross-store coordination.
 *
 * Messages are held per channel in a Map keyed by message id, so a realtime
 * update replaces one entry rather than rebuilding a list.
 */

import { create } from "zustand";

import { api, asCommandError } from "@/lib/ipc";
import { canonicaliseMentions } from "@/lib/markdown";
import type {
  AppInstallation,
  Channel,
  CommandError,
  ConnectionStatus,
  Id,
  Message,
  PendingMessage,
  ServerFrame,
  Presence,
  User,
  UserBrief,
  Workspace,
} from "@/lib/types";

export type Screen = "loading" | "signin" | "workspace";

/**
 * A toast waiting in the bottom-right stack.
 *
 * `kind` decides whether it carries the signal edge: something addressed to
 * you (a mention, a direct message) does; a busy channel does not.
 */
export interface Notice {
  id: string;
  title: string;
  body: string;
  channelId: Id | null;
  messageId: Id | null;
  kind: "mention" | "dm" | "message";
  at: number;
}

/** At most this many toasts are on screen; the oldest leaves first. */
export const MAX_NOTICES = 3;

export interface TypingEntry {
  userId: Id;
  at: number;
}

interface AppStateShape {
  // ── Shell ─────────────────────────────────────────────────────────────
  screen: Screen;
  serverUrl: string;
  version: string;
  connection: ConnectionStatus | null;
  banner: { kind: "error" | "info"; message: string } | null;

  // ── Identity ──────────────────────────────────────────────────────────
  me: User | null;

  // ── Workspaces ────────────────────────────────────────────────────────
  workspaces: Workspace[];
  activeWorkspaceId: Id | null;

  // ── Directory ─────────────────────────────────────────────────────────
  /** Everyone in the active workspace, for mentions and the DM picker. */
  people: Map<Id, User>;
  /**
   * Where you had read up to when you opened each channel, kept for as long as
   * the channel stays open.
   *
   * Captured *before* `markRead` runs, because opening a channel marks it read
   * and would otherwise erase the only record of where you stopped. Held for
   * the session rather than derived on every render so the divider does not
   * jump to the bottom the moment a new message arrives while you are reading.
   */
  unreadMarkers: Map<Id, Id>;
  presence: Map<Id, Presence>;

  // ── Channels ──────────────────────────────────────────────────────────
  channels: Channel[];
  activeChannelId: Id | null;
  /** Message id -> message, per channel. */
  messages: Map<Id, Map<Id, Message>>;
  pending: Map<Id, PendingMessage[]>;
  loadingChannels: Set<Id>;
  hasOlder: Map<Id, boolean>;
  typing: Map<Id, TypingEntry[]>;

  // ── Threads ───────────────────────────────────────────────────────────
  openThreadId: Id | null;
  threadReplies: Map<Id, Message[]>;

  // ── Mini-apps ─────────────────────────────────────────────────────────
  installations: AppInstallation[];
  openPanelInstallationId: Id | null;

  // ── UI ────────────────────────────────────────────────────────────────
  paletteOpen: boolean;
  badge: number;
  /** Bottom-right toast stack, newest last. */
  notices: Notice[];
  /** Ids of recently arrived messages that mention me — see `noteIncomingFrame`. */
  mentionedMessageIds: Id[];
}

interface AppActions {
  setScreen: (screen: Screen) => void;
  setServerUrl: (url: string) => void;
  showBanner: (kind: "error" | "info", message: string) => void;
  dismissBanner: () => void;
  reportError: (error: unknown, fallback?: string) => CommandError;

  bootstrap: (serverUrl: string) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  signOut: () => Promise<void>;

  loadWorkspaces: () => Promise<void>;
  selectWorkspace: (workspaceId: Id) => Promise<void>;

  openChannel: (channelId: Id) => Promise<void>;
  refreshChannel: (channelId: Id) => Promise<void>;
  loadOlder: (channelId: Id) => Promise<void>;
  refreshSidebar: () => Promise<void>;
  createChannel: (name: string, kind: "public" | "private") => Promise<Channel | null>;
  openDm: (userIds: Id[]) => Promise<Channel | null>;
  joinChannel: (channelId: Id) => Promise<void>;
  leaveChannel: (channelId: Id) => Promise<void>;
  toggleMute: (channelId: Id) => Promise<void>;

  send: (body: string, options?: { parentId?: Id; alsoSendToChannel?: boolean; fileIds?: Id[] }) => Promise<void>;
  editMessage: (messageId: Id, body: string) => Promise<void>;
  deleteMessage: (messageId: Id) => Promise<void>;
  toggleReaction: (messageId: Id, emoji: string) => Promise<void>;
  notifyTyping: (channelId: Id, parentId?: Id) => void;

  openThread: (messageId: Id | null) => Promise<void>;

  loadInstallations: () => Promise<void>;
  openAppPanel: (installationId: Id | null) => void;

  setPalette: (open: boolean) => void;
  setPresence: (presence: Presence) => Promise<void>;

  // Realtime hooks, called by the event bridge.
  onConnection: (status: ConnectionStatus) => void;
  applyChannelChanged: (channelId: Id) => Promise<void>;
  applyThreadChanged: (parentId: Id) => Promise<void>;
  applyTyping: (channelId: Id, userId: Id) => void;
  applyPresence: (userId: Id, presence: Presence) => void;
  setBadge: (count: number) => void;
  pushNotice: (effect: {
    title: string;
    body: string;
    channel_id?: Id | null;
    message_id?: Id | null;
  }) => void;
  dismissNotice: (id: string) => void;
  noteIncomingFrame: (frame: ServerFrame) => void;
  handleAuthLost: (message: string) => void;
}

export type AppStore = AppStateShape & AppActions;

export const TYPING_TTL_MS = 6_000;

export const useApp = create<AppStore>((set, get) => ({
  screen: "loading",
  serverUrl: "",
  version: "0.1.0",
  connection: null,
  banner: null,

  me: null,

  workspaces: [],
  activeWorkspaceId: null,

  people: new Map(),
  unreadMarkers: new Map(),
  presence: new Map(),

  channels: [],
  activeChannelId: null,
  messages: new Map(),
  pending: new Map(),
  loadingChannels: new Set(),
  hasOlder: new Map(),
  typing: new Map(),
  notices: [],
  mentionedMessageIds: [],

  openThreadId: null,
  threadReplies: new Map(),

  installations: [],
  openPanelInstallationId: null,

  paletteOpen: false,
  badge: 0,

  // ── Shell ─────────────────────────────────────────────────────────────

  setScreen: (screen) => set({ screen }),
  setServerUrl: (serverUrl) => set({ serverUrl }),
  showBanner: (kind, message) => set({ banner: { kind, message } }),
  dismissBanner: () => set({ banner: null }),

  reportError: (error, fallback) => {
    const parsed = asCommandError(error);
    if (parsed.requires_reauth) {
      get().handleAuthLost(parsed.message);
    } else {
      set({ banner: { kind: "error", message: fallback ?? parsed.message } });
    }
    return parsed;
  },

  bootstrap: async (serverUrl) => {
    set({ screen: "loading", serverUrl });
    try {
      const result = await api.bootstrap(serverUrl);
      if (result.resumed && result.user) {
        set({ me: result.user, screen: "workspace" });
        await get().loadWorkspaces();
      } else {
        set({ screen: "signin" });
      }
    } catch (error) {
      get().reportError(error, "서버에 연결할 수 없습니다. 주소를 확인해주세요.");
      set({ screen: "signin" });
    }
  },

  signIn: async (email, password) => {
    const user = await api.login(email, password);
    set({ me: user, screen: "workspace", banner: null });
    await get().loadWorkspaces();
  },

  signUp: async (email, password, displayName) => {
    const user = await api.register(email, password, displayName);
    set({ me: user, screen: "workspace", banner: null });
    await get().loadWorkspaces();
  },

  signOut: async () => {
    try {
      await api.logout();
    } finally {
      set({
        screen: "signin",
        me: null,
        workspaces: [],
        activeWorkspaceId: null,
        channels: [],
        activeChannelId: null,
        messages: new Map(),
        pending: new Map(),
        people: new Map(),
        unreadMarkers: new Map(),
        presence: new Map(),
        installations: [],
        openPanelInstallationId: null,
        openThreadId: null,
        threadReplies: new Map(),
        badge: 0,
        connection: null,
      });
    }
  },

  // ── Workspaces ────────────────────────────────────────────────────────

  loadWorkspaces: async () => {
    try {
      const workspaces = await api.listWorkspaces();
      set({ workspaces });
      const first = workspaces[0];
      if (first && !get().activeWorkspaceId) {
        await get().selectWorkspace(first.id);
      }
    } catch (error) {
      get().reportError(error, "워크스페이스를 불러오지 못했습니다.");
    }
  },

  selectWorkspace: async (workspaceId) => {
    set({
      activeWorkspaceId: workspaceId,
      activeChannelId: null,
      openThreadId: null,
      openPanelInstallationId: null,
    });

    // Cached first so the sidebar paints immediately, then authoritative.
    try {
      const cached = await api.cachedChannels(workspaceId);
      if (cached.length > 0) set({ channels: sortChannels(cached) });
    } catch {
      // A cold cache is not an error.
    }

    try {
      const channels = await api.selectWorkspace(workspaceId);
      set({ channels: sortChannels(channels) });

      const [people, installations] = await Promise.all([
        api.listWorkspaceUsers(workspaceId),
        api.listInstalledApps(workspaceId),
      ]);
      set({
        people: new Map(people.map((person) => [person.id, person])),
        presence: new Map(people.map((person) => [person.id, person.presence])),
        installations,
      });

      // Land the user somewhere useful rather than on an empty pane.
      const firstChannel =
        channels.find((channel) => channel.name === "general") ?? channels[0];
      if (firstChannel) await get().openChannel(firstChannel.id);
    } catch (error) {
      get().reportError(error, "워크스페이스를 열지 못했습니다.");
    }
  },

  // ── Channels ──────────────────────────────────────────────────────────

  openChannel: async (channelId) => {
    // Opening the channel is the answer to its toast.
    set((state) => ({
      notices: state.notices.filter((notice) => notice.channelId !== channelId),
    }));
    set({ activeChannelId: channelId, openThreadId: null });

    // Paint from cache, then refresh.
    try {
      const cached = await api.cachedHistory(channelId);
      if (cached.length > 0) {
        set((state) => ({
          messages: withMessages(state.messages, channelId, cached),
        }));
      }
    } catch {
      // Ignore: the refresh below is authoritative.
    }

    await get().refreshChannel(channelId);
    void get().openThread(null);

    /*
     * Remember where the reader stopped, then mark the channel read.
     *
     * Order matters and it is the whole reason this exists: `markRead` moves
     * `last_read_message_id` to the newest message, so after it runs there is
     * nothing left to say "you had read up to here". The marker is only set if
     * there was actually something unread and it is not already set for this
     * channel — coming back to a channel you have already been in this session
     * must not move the line you were using.
     */
    const state = get();
    const channel = state.channels.find((candidate) => candidate.id === channelId);
    const lastRead = channel?.membership?.last_read_message_id ?? null;
    const unread = channel?.membership?.unread_count ?? 0;
    if (lastRead && unread > 0 && !state.unreadMarkers.has(channelId)) {
      set((current) => ({
        unreadMarkers: new Map(current.unreadMarkers).set(channelId, lastRead),
      }));
    }

    const latest = latestMessageId(get().messages.get(channelId));
    try {
      const membership = await api.markRead(channelId, latest ?? undefined);
      set((state) => ({
        channels: state.channels.map((channel) =>
          channel.id === channelId ? { ...channel, membership } : channel,
        ),
      }));
    } catch (error) {
      // Failing to mark read is not worth interrupting the user for.
      asCommandError(error);
    }

    try {
      const pending = await api.pendingMessages(channelId);
      set((state) => ({ pending: new Map(state.pending).set(channelId, pending) }));
    } catch {
      // No outbox entries is the common case.
    }
  },

  refreshChannel: async (channelId) => {
    set((state) => ({
      loadingChannels: new Set(state.loadingChannels).add(channelId),
    }));
    try {
      const messages = await api.refreshHistory(channelId);
      set((state) => ({
        messages: withMessages(state.messages, channelId, messages),
        hasOlder: new Map(state.hasOlder).set(channelId, messages.length >= 80),
      }));
    } catch (error) {
      const parsed = asCommandError(error);
      // Offline is expected; the cached transcript stays on screen.
      if (parsed.code !== "network_error") {
        get().reportError(error, "메시지를 불러오지 못했습니다.");
      }
    } finally {
      set((state) => {
        const loading = new Set(state.loadingChannels);
        loading.delete(channelId);
        return { loadingChannels: loading };
      });
    }
  },

  loadOlder: async (channelId) => {
    const existing = get().messages.get(channelId);
    const oldest = oldestMessageId(existing);
    if (!oldest) return;

    try {
      const older = await api.loadOlderMessages(channelId, oldest);
      set((state) => ({
        messages: withMessages(state.messages, channelId, older, { merge: true }),
        hasOlder: new Map(state.hasOlder).set(channelId, older.length > 0),
      }));
    } catch (error) {
      get().reportError(error, "이전 메시지를 불러오지 못했습니다.");
    }
  },

  refreshSidebar: async () => {
    const workspaceId = get().activeWorkspaceId;
    if (!workspaceId) return;
    try {
      const channels = await api.refreshChannels(workspaceId);
      set({ channels: sortChannels(channels) });
    } catch (error) {
      asCommandError(error);
    }
  },

  createChannel: async (name, kind) => {
    const workspaceId = get().activeWorkspaceId;
    if (!workspaceId) return null;
    try {
      const channel = await api.createChannel(workspaceId, name, kind);
      set((state) => ({ channels: sortChannels([...state.channels, channel]) }));
      await get().openChannel(channel.id);
      return channel;
    } catch (error) {
      get().reportError(error, "채널을 만들지 못했습니다.");
      return null;
    }
  },

  openDm: async (userIds) => {
    const workspaceId = get().activeWorkspaceId;
    if (!workspaceId) return null;
    try {
      const channel = await api.openDm(workspaceId, userIds);
      set((state) => ({
        channels: sortChannels(
          state.channels.some((existing) => existing.id === channel.id)
            ? state.channels.map((existing) =>
                existing.id === channel.id ? channel : existing,
              )
            : [...state.channels, channel],
        ),
      }));
      await get().openChannel(channel.id);
      return channel;
    } catch (error) {
      get().reportError(error, "대화를 열지 못했습니다.");
      return null;
    }
  },

  joinChannel: async (channelId) => {
    try {
      const channel = await api.joinChannel(channelId);
      set((state) => ({
        channels: sortChannels(
          state.channels.some((existing) => existing.id === channel.id)
            ? state.channels.map((existing) =>
                existing.id === channel.id ? channel : existing,
              )
            : [...state.channels, channel],
        ),
      }));
      await get().openChannel(channelId);
    } catch (error) {
      get().reportError(error, "채널에 참여하지 못했습니다.");
    }
  },

  leaveChannel: async (channelId) => {
    try {
      await api.leaveChannel(channelId);
      set((state) => ({
        channels: state.channels.filter((channel) => channel.id !== channelId),
        activeChannelId:
          state.activeChannelId === channelId ? null : state.activeChannelId,
      }));
    } catch (error) {
      get().reportError(error, "채널에서 나가지 못했습니다.");
    }
  },

  toggleMute: async (channelId) => {
    const channel = get().channels.find((candidate) => candidate.id === channelId);
    if (!channel) return;
    const nextMuted = !(channel.membership?.is_muted ?? false);
    try {
      const membership = await api.updateMembership(channelId, { is_muted: nextMuted });
      set((state) => ({
        channels: state.channels.map((candidate) =>
          candidate.id === channelId ? { ...candidate, membership } : candidate,
        ),
      }));
    } catch (error) {
      get().reportError(error, "알림 설정을 변경하지 못했습니다.");
    }
  },

  // ── Messages ──────────────────────────────────────────────────────────

  send: async (body, options) => {
    const state = get();
    const channelId = state.activeChannelId;
    if (!channelId || !body.trim()) return;

    // Turn `@handle` into `<@id>` before sending, matching what the server
    // would do — this way the optimistic bubble renders the same text the
    // server will echo back.
    const handleToId = new Map(
      [...state.people.values()].map((person) => [person.handle.toLowerCase(), person.id]),
    );
    const canonical = canonicaliseMentions(body.trim(), handleToId);

    try {
      const result = await api.sendMessage({
        channelId,
        body: canonical,
        parentId: options?.parentId ?? null,
        alsoSendToChannel: options?.alsoSendToChannel ?? false,
        fileIds: options?.fileIds ?? [],
      });

      if (result.message) {
        const message = result.message;
        if (message.parent_id) {
          await get().openThread(message.parent_id);
        } else {
          set((current) => ({
            messages: withMessages(current.messages, channelId, [message], { merge: true }),
          }));
        }
      }

      if (result.queued) {
        set({
          banner: {
            kind: "info",
            message: "오프라인 상태입니다. 연결되면 자동으로 전송됩니다.",
          },
        });
        const pending = await api.pendingMessages(channelId);
        set((current) => ({ pending: new Map(current.pending).set(channelId, pending) }));
      }
    } catch (error) {
      get().reportError(error, "메시지를 보내지 못했습니다.");
    }
  },

  editMessage: async (messageId, body) => {
    try {
      const message = await api.editMessage(messageId, body);
      set((state) => ({
        messages: withMessages(state.messages, message.channel_id, [message], {
          merge: true,
        }),
      }));
    } catch (error) {
      get().reportError(error, "메시지를 수정하지 못했습니다.");
    }
  },

  deleteMessage: async (messageId) => {
    const channelId = get().activeChannelId;
    try {
      await api.deleteMessage(messageId);
      if (channelId) {
        set((state) => {
          const perChannel = new Map(state.messages);
          const bucket = new Map(perChannel.get(channelId) ?? []);
          bucket.delete(messageId);
          perChannel.set(channelId, bucket);
          return { messages: perChannel };
        });
      }
    } catch (error) {
      get().reportError(error, "메시지를 삭제하지 못했습니다.");
    }
  },

  toggleReaction: async (messageId, emoji) => {
    const state = get();
    const channelId = state.activeChannelId;
    if (!channelId) return;

    const message = state.messages.get(channelId)?.get(messageId);
    const mine = message?.reactions.find((reaction) => reaction.emoji === emoji)?.me ?? false;

    // Optimistic: reacting should feel instant.
    if (message) {
      set((current) => ({
        messages: withMessages(
          current.messages,
          channelId,
          [applyReactionLocally(message, emoji, !mine, current.me?.id)],
          { merge: true },
        ),
      }));
    }

    try {
      await api.toggleReaction(messageId, emoji, !mine);
    } catch (error) {
      // Roll back by re-fetching the channel rather than guessing.
      get().reportError(error, "반응을 변경하지 못했습니다.");
      await get().refreshChannel(channelId);
    }
  },

  notifyTyping: (channelId, parentId) => {
    void api.typing(channelId, parentId).catch(() => {
      // Typing indicators are best-effort by nature.
    });
  },

  // ── Threads ───────────────────────────────────────────────────────────

  openThread: async (messageId) => {
    set({ openThreadId: messageId });
    if (!messageId) return;
    try {
      const replies = await api.threadReplies(messageId);
      set((state) => ({
        threadReplies: new Map(state.threadReplies).set(messageId, replies),
      }));
    } catch (error) {
      get().reportError(error, "스레드를 불러오지 못했습니다.");
    }
  },

  // ── Mini-apps ─────────────────────────────────────────────────────────

  loadInstallations: async () => {
    const workspaceId = get().activeWorkspaceId;
    if (!workspaceId) return;
    try {
      set({ installations: await api.listInstalledApps(workspaceId) });
    } catch (error) {
      asCommandError(error);
    }
  },

  openAppPanel: (installationId) => set({ openPanelInstallationId: installationId }),

  // ── UI ────────────────────────────────────────────────────────────────

  setPalette: (paletteOpen) => set({ paletteOpen }),

  setPresence: async (presence) => {
    try {
      await api.setPresence(presence);
      const me = get().me;
      if (me) set({ me: { ...me, presence } });
    } catch (error) {
      asCommandError(error);
    }
  },

  // ── Realtime ──────────────────────────────────────────────────────────

  onConnection: (connection) => {
    set({ connection });
    if (connection.status === "connected") {
      set((state) => ({
        banner:
          state.banner?.kind === "error" && state.banner.message.includes("연결")
            ? null
            : state.banner,
      }));
    }
  },

  applyChannelChanged: async (channelId) => {
    // Only re-fetch what the user can see; other channels are updated lazily
    // through the sidebar refresh.
    if (get().activeChannelId === channelId) {
      await get().refreshChannel(channelId);
      const latest = latestMessageId(get().messages.get(channelId));
      if (latest) {
        try {
          await api.markRead(channelId, latest);
        } catch {
          // Not worth surfacing.
        }
      }
    }
    await get().refreshSidebar();
  },

  applyThreadChanged: async (parentId) => {
    if (get().openThreadId === parentId) {
      await get().openThread(parentId);
    }
    await get().refreshSidebar();
  },

  applyTyping: (channelId, userId) => {
    set((state) => {
      const now = Date.now();
      const existing = (state.typing.get(channelId) ?? []).filter(
        (entry) => now - entry.at < TYPING_TTL_MS && entry.userId !== userId,
      );
      return {
        typing: new Map(state.typing).set(channelId, [...existing, { userId, at: now }]),
      };
    });
  },

  applyPresence: (userId, presence) =>
    set((state) => ({ presence: new Map(state.presence).set(userId, presence) })),

  setBadge: (badge) => set({ badge }),

  /**
   * Remember which arriving messages are addressed to me.
   *
   * The gateway sends `message.created` before the matching `notification`,
   * and only the former carries the mention targets — the notification payload
   * is shared by every recipient, so it cannot say "this one is for you".
   * Recording the id here lets the toast know. If the order ever changed the
   * toast simply renders neutral, which is a downgrade rather than a break.
   */
  noteIncomingFrame: (frame) => {
    if (frame.type !== "message.created") return;
    const me = get().me;
    if (!me) return;
    const message = frame.data?.message as Message | undefined;
    if (!message) return;
    const forMe =
      message.mentions_everyone || message.mentioned_user_ids.includes(me.id);
    if (!forMe) return;
    const seen = new Set(get().mentionedMessageIds);
    seen.add(message.id);
    // Bounded: this only has to survive the gap between two frames.
    while (seen.size > 50) seen.delete(seen.values().next().value as string);
    set({ mentionedMessageIds: [...seen] });
  },

  pushNotice: (effect) => {
    const state = get();
    const channelId = effect.channel_id ?? null;

    // The channel already on screen needs no toast: the message is visible.
    if (channelId && channelId === state.activeChannelId) return;

    const channel = state.channels.find((candidate) => candidate.id === channelId);
    const isDm = channel?.kind === "dm" || channel?.kind === "group_dm";
    const isMention = effect.message_id
      ? state.mentionedMessageIds.includes(effect.message_id)
      : false;

    const notice: Notice = {
      id: effect.message_id ?? `notice-${Date.now()}-${state.notices.length}`,
      title: effect.title,
      body: effect.body,
      channelId,
      messageId: effect.message_id ?? null,
      kind: isMention ? "mention" : isDm ? "dm" : "message",
      at: Date.now(),
    };

    set({
      notices: [
        ...state.notices.filter((existing) => existing.id !== notice.id),
        notice,
      ].slice(-MAX_NOTICES),
    });
  },

  dismissNotice: (id) =>
    set((state) => ({
      notices: state.notices.filter((notice) => notice.id !== id),
    })),

  handleAuthLost: (message) =>
    set({
      screen: "signin",
      me: null,
      banner: { kind: "error", message: message || "다시 로그인해주세요." },
    }),
}));

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Starred first, then most recent activity — matching the server's ordering. */
function sortChannels(channels: Channel[]): Channel[] {
  return [...channels].sort((a, b) => {
    const starred = Number(b.membership?.is_starred ?? false) - Number(a.membership?.is_starred ?? false);
    if (starred !== 0) return starred;
    const at = (b.last_message_at ?? "").localeCompare(a.last_message_at ?? "");
    if (at !== 0) return at;
    return (a.name ?? "").localeCompare(b.name ?? "", "ko");
  });
}

function withMessages(
  current: Map<Id, Map<Id, Message>>,
  channelId: Id,
  incoming: Message[],
  options: { merge?: boolean } = {},
): Map<Id, Map<Id, Message>> {
  const next = new Map(current);
  const bucket = options.merge
    ? new Map(next.get(channelId) ?? [])
    : new Map<Id, Message>();
  for (const message of incoming) {
    bucket.set(message.id, message);
  }
  next.set(channelId, bucket);
  return next;
}

/** Messages for a channel, in ULID order (which is chronological order). */
export function orderedMessages(
  store: Pick<AppStore, "messages">,
  channelId: Id | null,
): Message[] {
  if (!channelId) return [];
  const bucket = store.messages.get(channelId);
  if (!bucket) return [];
  return [...bucket.values()].sort((a, b) => a.id.localeCompare(b.id));
}

function latestMessageId(bucket: Map<Id, Message> | undefined): Id | null {
  if (!bucket || bucket.size === 0) return null;
  let latest: Id | null = null;
  for (const id of bucket.keys()) {
    if (latest === null || id > latest) latest = id;
  }
  return latest;
}

function oldestMessageId(bucket: Map<Id, Message> | undefined): Id | null {
  if (!bucket || bucket.size === 0) return null;
  let oldest: Id | null = null;
  for (const id of bucket.keys()) {
    if (oldest === null || id < oldest) oldest = id;
  }
  return oldest;
}

/** Apply a reaction toggle locally, for the optimistic update. */
function applyReactionLocally(
  message: Message,
  emoji: string,
  add: boolean,
  viewerId: Id | undefined,
): Message {
  const reactions = [...message.reactions];
  const index = reactions.findIndex((reaction) => reaction.emoji === emoji);

  if (index === -1) {
    if (!add) return message;
    return {
      ...message,
      reactions: [
        ...reactions,
        { emoji, count: 1, user_ids: viewerId ? [viewerId] : [], me: true },
      ],
    };
  }

  const existing = reactions[index];
  if (!existing) return message;
  const count = Math.max(0, existing.count + (add ? 1 : -1));
  if (count === 0) {
    reactions.splice(index, 1);
  } else {
    reactions[index] = {
      ...existing,
      count,
      me: add,
      user_ids: add
        ? [...existing.user_ids, ...(viewerId ? [viewerId] : [])]
        : existing.user_ids.filter((id) => id !== viewerId),
    };
  }
  return { ...message, reactions };
}

/** Users currently typing in a channel, excluding stale entries. */
/**
 * Names to show in the "typing…" indicator.
 *
 * Takes the raw entries rather than the store, because it builds a fresh array:
 * called from inside a zustand selector, that new reference on every snapshot
 * read is an infinite render loop. Callers select `typing.get(channelId)` and
 * `people` — both stable references — and call this in the render body.
 */
export function typingNames(
  entries: TypingEntry[] | undefined,
  people: Map<Id, UserBrief>,
): string[] {
  if (!entries || entries.length === 0) return [];
  const now = Date.now();
  return entries
    .filter((entry) => now - entry.at < TYPING_TTL_MS)
    .map((entry) => people.get(entry.userId)?.display_name)
    .filter((name): name is string => Boolean(name));
}
