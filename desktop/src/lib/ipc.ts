/**
 * Typed wrappers around the Tauri command surface.
 *
 * One place where every `invoke` name and argument shape is written down, so a
 * rename on the Rust side produces one compile error here rather than silent
 * runtime failures scattered across components.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  AppInstallation,
  AppSummary,
  BootstrapResult,
  Channel,
  ChannelKind,
  ChannelMembership,
  CommandError,
  ConnectionStatus,
  DrainReport,
  FileRef,
  Id,
  Message,
  PanelSession,
  PendingMessage,
  SearchResult,
  SendResult,
  ServerFrame,
  SyncEffect,
  User,
  Workspace,
} from "./types";

/** Narrow an unknown rejection into the error envelope the shell returns. */
export function asCommandError(error: unknown): CommandError {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error
  ) {
    return error as CommandError;
  }
  return {
    code: "unknown_error",
    message: typeof error === "string" ? error : "알 수 없는 오류가 발생했습니다.",
    requires_reauth: false,
  };
}

async function call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw asCommandError(error);
  }
}

// ── Connection & auth ───────────────────────────────────────────────────────

export const api = {
  bootstrap: (serverUrl: string) =>
    call<BootstrapResult>("bootstrap", { serverUrl }),

  login: (email: string, password: string) =>
    call<User>("login", { email, password }),

  register: (email: string, password: string, displayName: string) =>
    call<User>("register", { email, password, displayName }),

  logout: () => call<void>("logout"),

  currentUser: () => call<User | null>("current_user"),

  // ── Workspaces ────────────────────────────────────────────────────────

  listWorkspaces: () => call<Workspace[]>("list_workspaces"),

  /** Switch workspaces: resubscribes the socket and returns its channels. */
  selectWorkspace: (workspaceId: Id) =>
    call<Channel[]>("select_workspace", { workspaceId }),

  listWorkspaceUsers: (workspaceId: Id, query?: string) =>
    call<User[]>("list_workspace_users", { workspaceId, query: query ?? null }),

  // ── Channels ──────────────────────────────────────────────────────────

  /** Cached list — resolves without a network round-trip. */
  cachedChannels: (workspaceId: Id) =>
    call<Channel[]>("cached_channels", { workspaceId }),

  refreshChannels: (workspaceId: Id) =>
    call<Channel[]>("refresh_channels", { workspaceId }),

  browseChannels: (workspaceId: Id, query?: string) =>
    call<Channel[]>("browse_channels", { workspaceId, query: query ?? null }),

  createChannel: (
    workspaceId: Id,
    name: string,
    kind: ChannelKind,
    memberIds: Id[] = [],
  ) => call<Channel>("create_channel", { workspaceId, name, kind, memberIds }),

  openDm: (workspaceId: Id, userIds: Id[]) =>
    call<Channel>("open_dm", { workspaceId, userIds }),

  joinChannel: (channelId: Id) => call<Channel>("join_channel", { channelId }),

  leaveChannel: (channelId: Id) => call<void>("leave_channel", { channelId }),

  updateMembership: (channelId: Id, patch: Record<string, unknown>) =>
    call<ChannelMembership>("update_membership", { channelId, patch }),

  markRead: (channelId: Id, messageId?: Id) =>
    call<ChannelMembership>("mark_read", {
      channelId,
      messageId: messageId ?? null,
    }),

  // ── Messages ──────────────────────────────────────────────────────────

  cachedHistory: (channelId: Id, limit = 80) =>
    call<Message[]>("cached_history", { channelId, limit }),

  refreshHistory: (channelId: Id, limit = 80) =>
    call<Message[]>("refresh_history", { channelId, limit }),

  loadOlderMessages: (channelId: Id, before: Id, limit = 50) =>
    call<Message[]>("load_older_messages", { channelId, before, limit }),

  threadReplies: (messageId: Id) =>
    call<Message[]>("thread_replies", { messageId }),

  sendMessage: (options: {
    channelId: Id;
    body: string;
    parentId?: Id | null;
    alsoSendToChannel?: boolean;
    fileIds?: Id[];
  }) =>
    call<SendResult>("send_message", {
      channelId: options.channelId,
      body: options.body,
      parentId: options.parentId ?? null,
      alsoSendToChannel: options.alsoSendToChannel ?? false,
      fileIds: options.fileIds ?? [],
    }),

  editMessage: (messageId: Id, body: string) =>
    call<Message>("edit_message", { messageId, body }),

  deleteMessage: (messageId: Id) => call<void>("delete_message", { messageId }),

  toggleReaction: (messageId: Id, emoji: string, add: boolean) =>
    call<void>("toggle_reaction", { messageId, emoji, add }),

  typing: (channelId: Id, parentId?: Id | null) =>
    call<void>("typing", { channelId, parentId: parentId ?? null }),

  // ── Outbox ────────────────────────────────────────────────────────────

  pendingMessages: (channelId: Id) =>
    call<PendingMessage[]>("pending_messages", { channelId }),

  drainOutbox: () => call<DrainReport>("drain_outbox"),

  retryFailedMessages: () => call<number>("retry_failed_messages"),

  discardPendingMessage: (entryId: string) =>
    call<void>("discard_pending_message", { entryId }),

  // ── Search ────────────────────────────────────────────────────────────

  search: (workspaceId: Id, query: string) =>
    call<SearchResult>("search", { workspaceId, query }),

  // ── Files ─────────────────────────────────────────────────────────────

  uploadFile: (workspaceId: Id, path: string) =>
    call<FileRef>("upload_file", { workspaceId, path }),

  downloadFile: (fileId: Id, filename: string) =>
    call<string>("download_file", { fileId, filename }),

  // ── Mini-apps ─────────────────────────────────────────────────────────

  listInstalledApps: (workspaceId: Id) =>
    call<AppInstallation[]>("list_installed_apps", { workspaceId }),

  listAvailableApps: (workspaceId: Id) =>
    call<AppSummary[]>("list_available_apps", { workspaceId }),

  installApp: (workspaceId: Id, appId: Id, grantedScopes?: string[]) =>
    call<AppInstallation>("install_app", {
      workspaceId,
      appId,
      grantedScopes: grantedScopes ?? null,
    }),

  uninstallApp: (installationId: Id) =>
    call<void>("uninstall_app", { installationId }),

  /** Mint a scoped session for a panel webview. */
  openAppPanel: (installationId: Id, channelId?: Id) =>
    call<PanelSession>("open_app_panel", {
      installationId,
      channelId: channelId ?? null,
    }),

  // ── Shell ─────────────────────────────────────────────────────────────

  setPresence: (presence: string) => call<void>("set_presence", { presence }),
  reconnect: () => call<void>("reconnect"),
  cacheStats: () => call<Record<string, unknown>>("cache_stats"),
  pruneCache: (keepPerChannel = 500) =>
    call<number>("prune_cache", { keepPerChannel }),
};

// ── Events ──────────────────────────────────────────────────────────────────

export const events = {
  onReady: (handler: (payload: { default_server_url: string; version: string; platform: string }) => void) =>
    listen<{ default_server_url: string; version: string; platform: string }>(
      "llack://ready",
      (event) => handler(event.payload),
    ),

  onConnection: (handler: (status: ConnectionStatus) => void) =>
    listen<ConnectionStatus>("llack://connection", (event) => handler(event.payload)),

  onSync: (handler: (effect: SyncEffect) => void) =>
    listen<SyncEffect>("llack://sync", (event) => handler(event.payload)),

  onFrame: (handler: (frame: ServerFrame) => void) =>
    listen<ServerFrame>("llack://frame", (event) => handler(event.payload)),

  onAuthLost: (handler: (payload: { message: string }) => void) =>
    listen<{ message: string }>("llack://auth-lost", (event) => handler(event.payload)),

  onBadge: (handler: (payload: { count: number }) => void) =>
    listen<{ count: number }>("llack://badge", (event) => handler(event.payload)),

  onDeepLink: (handler: (payload: { urls: string[] }) => void) =>
    listen<{ urls: string[] }>("llack://deep-link", (event) => handler(event.payload)),

  onPresenceRequest: (handler: (payload: { presence: string }) => void) =>
    listen<{ presence: string }>("llack://presence-request", (event) =>
      handler(event.payload),
    ),
};

export type { UnlistenFn };
