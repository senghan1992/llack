/**
 * Typed wrappers around the Tauri command surface — and the switch that lets
 * the same UI run without Tauri at all.
 *
 * One place where every `invoke` name and argument shape is written down, so a
 * rename on the Rust side produces one compile error here rather than silent
 * runtime failures scattered across components.
 *
 * The exported `api` / `events` are the desktop shell's when the UI is running
 * inside it, and the browser adapter in `web.ts` otherwise. `ShellApi` is
 * derived from the Tauri implementation, so the adapter is checked against the
 * real contract rather than a hand-copied one.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import { asCommandError } from "./errors";
import type {
  AppInstallation,
  AppSummary,
  BootstrapResult,
  Channel,
  ChannelKind,
  ChannelMembership,
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
import type {
  AgentEvent,
  AgentProviderStatus,
  AgentSessionSummary,
  AgentToolResult,
  AgentToolSpec,
} from "./agent/types";
import { pickFilesInBrowser, webAgent, webApi, webEvents } from "./web";

export { asCommandError };

/**
 * True when the UI is hosted by the Tauri shell.
 *
 * Tauri injects this on the window before the bundle runs; its absence means a
 * plain browser tab, where the HTTP adapter takes over.
 */
export function isDesktopShell(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw asCommandError(error);
  }
}

// ── Connection & auth ───────────────────────────────────────────────────────

const tauriApi = {
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

  /**
   * `source` is a filesystem path in the desktop shell. The browser adapter
   * also accepts a `File`, which is what its picker produces; pick files
   * through `shell.pickAndUploadFiles` so callers need not care which.
   */
  uploadFile: (workspaceId: Id, source: string | File) => {
    if (typeof source !== "string") {
      throw asCommandError("데스크톱 앱에서는 파일 경로로 업로드합니다.");
    }
    return call<FileRef>("upload_file", { workspaceId, path: source });
  },

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

/** The contract both runtimes implement. */
export type ShellApi = typeof tauriApi;

// ── Events ──────────────────────────────────────────────────────────────────

const tauriEvents = {
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

  /**
   * Agent facts other surfaces need: a session opening, an approval waiting.
   *
   * Only these — never the token stream. A broadcast event carries no session
   * scoping, so every listener would have to filter, and a filter you can get
   * wrong is worse than no broadcast. Tokens ride the per-call channel the
   * loop already owns.
   */
  onAgent: (handler: (event: AgentEvent) => void) =>
    listen<AgentEvent>("llack://agent", (event) => handler(event.payload)),
};

/** The contract both runtimes implement. */
export type ShellEvents = typeof tauriEvents;

// ── Runtime selection ───────────────────────────────────────────────────────

// Assigning through the annotations is what checks the browser adapter against
// the desktop contract — a drift on either side fails the typecheck here.
export const api: ShellApi = isDesktopShell() ? tauriApi : webApi;
export const events: ShellEvents = isDesktopShell() ? tauriEvents : webEvents;

/*
 * ── The agent host surface ──────────────────────────────────────────────
 *
 * A second contract rather than more members on `ShellApi`. Nine commands that
 * only the desktop shell can serve would mean nine browser stubs whose only
 * job is to throw, and a reviewer could no longer tell from the type which
 * commands are host-specific. Splitting them keeps that legible.
 *
 * The stubs are the fallback, not the mechanism: the real fix is that the tool
 * schemas sent to the provider are filtered by host capability in Rust
 * (`ToolCatalog::expose`), so a browser session never sees `host.exec` and the
 * model never proposes it. A stub that actually gets hit therefore means a bug,
 * and it will show up in the audit log as one.
 */
const tauriAgent = {
  /** Whether a provider is connected, and which model. Never the key. */
  agentProviderStatus: () => call<AgentProviderStatus>("agent_provider_status"),

  /**
   * Store a provider key in the OS keychain and validate it.
   *
   * The key crosses to Rust once, here, and never comes back — every later
   * request is signed by the byte proxy on the Rust side.
   */
  agentProviderConnect: (providerId: string, apiKey: string, model: string) =>
    call<AgentProviderStatus>("agent_provider_connect", { providerId, apiKey, model }),


  agentProviderDisconnect: () => call<AgentProviderStatus>("agent_provider_disconnect"),

  /** The tools this host advertises. Computed in Rust, filtered by capability. */
  agentTools: () => call<AgentToolSpec[]>("agent_tools"),

  agentSessions: (limit = 20) =>
    call<AgentSessionSummary[]>("agent_sessions", { limit }),

  agentOpenSession: (sessionId: string | null) =>
    call<string>("agent_open_session", { sessionId: sessionId ?? null }),

  /**
   * Run one tool call through the gate.
   *
   * The webview names a tool and its arguments; it cannot name a command to
   * run. Everything about whether this is allowed is decided in Rust.
   */
  agentToolCall: (sessionId: string, name: string, args: unknown, rationale?: string) =>
    call<AgentToolResult>("agent_tool_call", {
      sessionId,
      name,
      args,
      rationale: rationale ?? null,
    }),

  /**
   * Answer a pending approval.
   *
   * Takes a request id and its single-use nonce — never a description of an
   * action. The webview can answer a request Rust created; it can never
   * originate one.
   */
  agentResolveApproval: (
    requestId: string,
    nonce: string,
    approve: boolean,
    remember: boolean,
  ) =>
    call<void>("agent_resolve_approval", { requestId, nonce, approve, remember }),

  /** Deny everything outstanding and stop the turn. */
  agentCancel: (sessionId: string) => call<void>("agent_cancel", { sessionId }),

  /**
   * Tell the engine which channel the panel is looking at, so a tool call with
   * no explicit channel means "this one".
   */
  agentFocus: (sessionId: string, channelId: string | null) =>
    call<void>("agent_focus", { sessionId, channelId }),

  /** Let the user choose a directory the agent may read without asking. */
  agentPickRoot: () => call<string | null>("agent_pick_root"),
};

/** The contract both runtimes implement for the agent. */
export type AgentHostApi = typeof tauriAgent;

export const agentHost: AgentHostApi = isDesktopShell() ? tauriAgent : webAgent;

/**
 * What this host can actually do, in one place.
 *
 * Collected here rather than scattering `isDesktopShell()` through components:
 * a capability is a fact about the host, and the UI should read it rather than
 * re-derive it.
 */
export const capabilities = {
  /** Programs and files on this machine. Desktop only. */
  computerControl: isDesktopShell(),
  /**
   * The agent panel itself. Available in both runtimes: a browser tab gets it
   * driven by the scripted fake provider, which is how the panel is verified
   * without a key.
   */
  agent: true,
};

/**
 * Capabilities that are not commands but still differ per host: anything the
 * platform, rather than the server, has to provide.
 */
export const shell = {
  /**
   * Pick files with the host's picker and upload them, reporting each one as
   * it lands so the composer can show attachments appearing.
   */
  pickAndUploadFiles: async (
    workspaceId: Id,
    onUploaded: (file: FileRef) => void,
  ): Promise<void> => {
    if (isDesktopShell()) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({ multiple: true });
      if (!selected) return;
      for (const path of Array.isArray(selected) ? selected : [selected]) {
        onUploaded(await api.uploadFile(workspaceId, path));
      }
      return;
    }

    for (const file of await pickFilesInBrowser(true)) {
      onUploaded(await api.uploadFile(workspaceId, file));
    }
  },
};

export type { UnlistenFn };
