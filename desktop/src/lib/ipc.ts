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
  SearchResult,
  SendResult,
  ServerFrame,
  SmtpSettings,
  SmtpSettingsInput,
  SyncEffect,
  ActionResult,
  ActivityPage,
  AppToken,
  AuditEvent,
  CommandResult,
  DeveloperApp,
  LinkProbe,
  MediaToken,
  MentionActivity,
  RetentionSettings,
  SavedItem,
  SessionInfo,
  SlashCommand,
  ThreadActivity,
  User,
  WebhookDelivery,
  Workspace,
  WorkspaceFile,
  WorkspaceMember,
  WorkspaceRole,
} from "./types";
import type {
  AgentAuditEntries,
  AgentEvent,
  AgentMemory,
  AgentProviderStatus,
  AgentSessionSummary,
  AgentSkill,
  AgentToolResult,
  AgentToolSpec,
  McpServerView,
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

  register: (email: string, password: string, displayName: string, inviteToken?: string | null) =>
    call<User>("register", { email, password, displayName, inviteToken: inviteToken ?? null }),

  logout: () => call<void>("logout"),

  currentUser: () => call<User | null>("current_user"),

  /** Update my profile; `patch` carries only the fields to change. */
  updateProfile: (patch: { display_name?: string; title?: string; avatar_url?: string }) =>
    call<User>("update_me", { patch }),

  updateStatus: (patch: { status_emoji?: string | null; status_text?: string | null }) =>
    call<User>("update_my_status", { patch }),

  changePassword: (currentPassword: string, newPassword: string) =>
    call<void>("change_password", { currentPassword, newPassword }),

  /** Server-wide SMTP relay (owner-only). Password is write-only. */
  getSmtpSettings: () => call<SmtpSettings>("get_smtp_settings"),

  updateSmtpSettings: (payload: SmtpSettingsInput) =>
    call<SmtpSettings>("update_smtp_settings", { payload }),

  testSmtp: (payload: SmtpSettingsInput) =>
    call<{ ok: boolean; error?: string; sent_to?: string }>("test_smtp", { payload }),

  /** Mail a reset code. Public; the same answer whether the account exists. */
  forgotPassword: (email: string) => call<void>("forgot_password", { email }),

  resetPassword: (email: string, code: string, newPassword: string) =>
    call<void>("reset_password", { email, code, newPassword }),

  /** Issue workspace invitations (admin). URLs are shown once. */
  createInvites: (workspaceId: Id, emails: string[], role = "member") =>
    call<InviteOut[]>("create_invites", { workspaceId, emails, role }),

  acceptInvite: (token: string) => call<Workspace>("accept_invite", { token }),

  /** Outstanding invitations (admin). No invite_url — links are shown once. */
  listInvites: (workspaceId: Id) => call<InviteOut[]>("list_invites", { workspaceId }),

  revokeInvite: (workspaceId: Id, inviteId: string) =>
    call<void>("revoke_invite", { workspaceId, inviteId }),

  /** Admin: one-time temporary password for a locked-out member. */
  resetMemberPassword: (workspaceId: Id, userId: Id) =>
    call<{ temp_password: string }>("reset_member_password", { workspaceId, userId }),

  createWorkspace: (name: string, slug: string) =>
    call<Workspace>("create_workspace", { name, slug }),

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

  updateChannel: (
    channelId: Id,
    patch: { name?: string; topic?: string; is_archived?: boolean; retention_days?: number | null },
  ) => call<Channel>("update_channel", { channelId, patch }),

  channelMembers: (channelId: Id) =>
    call<ChannelMemberEntry[]>("channel_members", { channelId }),

  addChannelMembers: (channelId: Id, userIds: Id[]) =>
    call<Id[]>("add_channel_members", { channelId, userIds }),

  removeChannelMember: (channelId: Id, userId: Id) =>
    call<void>("remove_channel_member", { channelId, userId }),

  setChannelMemberRole: (channelId: Id, userId: Id, role: "admin" | "member") =>
    call<ChannelMemberEntry>("set_channel_member_role", { channelId, userId, role }),

  revokeOtherSessions: () => call<void>("revoke_other_sessions"),

  deleteFile: (fileId: Id) => call<void>("delete_file", { fileId }),

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

  setPinned: (messageId: Id, pinned: boolean) =>
    call<Message>("set_pinned", { messageId, pinned }),

  channelPins: (channelId: Id) => call<Message[]>("channel_pins", { channelId }),

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
  uploadFile: (
    workspaceId: Id,
    source: string | File,
    onProgress?: (sent: number, total: number) => void,
  ) => {
    if (typeof source !== "string") {
      throw asCommandError("데스크톱 앱에서는 파일 경로로 업로드합니다.");
    }
    // The shell uploads in one Rust call; progress is start → done.
    return call<FileRef>("upload_file", { workspaceId, path: source }).then((file) => {
      onProgress?.(file.size_bytes, file.size_bytes);
      return file;
    });
  },

  /** Replace my avatar from a file on disk (the shell reads and PUTs it). */
  uploadAvatar: (source: File | string) => {
    if (typeof source !== "string") {
      throw asCommandError("데스크톱 앱에서는 파일 경로로 업로드합니다.");
    }
    return call<User>("upload_avatar", { path: source });
  },

  removeAvatar: () => call<User>("remove_avatar"),

  listWorkspaceFiles: (
    workspaceId: Id,
    options: {
      q?: string;
      kind?: "image" | "document" | null;
      mine?: boolean;
      cursor?: string | null;
      limit?: number;
    } = {},
  ) =>
    call<WorkspaceFile[]>("list_workspace_files", {
      workspaceId,
      q: options.q ?? null,
      kind: options.kind ?? null,
      mine: options.mine ?? false,
      cursor: options.cursor ?? null,
      limit: options.limit ?? 50,
    }),

  activityThreads: (workspaceId: Id, before?: string | null) =>
    call<ActivityPage<ThreadActivity>>("activity_threads", { workspaceId, before: before ?? null }),

  activityMentions: (workspaceId: Id, before?: string | null) =>
    call<ActivityPage<MentionActivity>>("activity_mentions", { workspaceId, before: before ?? null }),

  listSessions: () => call<SessionInfo[]>("list_sessions"),

  revokeSession: (sessionId: string) => call<void>("revoke_session", { sessionId }),

  listWorkspaceMembers: (workspaceId: Id) =>
    call<WorkspaceMember[]>("list_workspace_members", { workspaceId }),

  updateWorkspaceMemberRole: (workspaceId: Id, memberId: string, role: WorkspaceRole) =>
    call<WorkspaceMember>("update_workspace_member_role", { workspaceId, memberId, role }),

  removeWorkspaceMember: (workspaceId: Id, memberId: string) =>
    call<void>("remove_workspace_member", { workspaceId, memberId }),

  listAudit: (
    workspaceId: Id,
    options: { before?: string | null; action?: string | null; actorId?: string | null } = {},
  ) =>
    call<ActivityPage<AuditEvent>>("list_audit", {
      workspaceId,
      before: options.before ?? null,
      action: options.action ?? null,
      actorId: options.actorId ?? null,
    }),

  downloadAuditCsv: (workspaceId: Id) => call<void>("download_audit_csv", { workspaceId }),

  getRetention: (workspaceId: Id) => call<RetentionSettings>("get_retention", { workspaceId }),

  updateRetention: (workspaceId: Id, patch: Partial<RetentionSettings>) =>
    call<RetentionSettings>("update_retention", { workspaceId, patch }),

  updateNotifications: (patch: {
    dnd_start?: string | null;
    dnd_end?: string | null;
    dnd_days?: number[];
    paused_until?: string | null;
  }) => call<User>("update_notifications", { patch }),

  saveMessage: (messageId: Id, options: { note?: string | null; remind_at?: string | null } = {}) =>
    call<SavedItem>("save_message", { messageId, note: options.note ?? null, remindAt: options.remind_at ?? null }),

  unsaveMessage: (messageId: Id) => call<void>("unsave_message", { messageId }),

  listSaved: (workspaceId: Id, options: { done?: boolean; before?: string | null } = {}) =>
    call<ActivityPage<SavedItem>>("list_saved", {
      workspaceId,
      done: options.done ?? false,
      before: options.before ?? null,
    }),

  markSavedDone: (savedId: string) => call<SavedItem>("mark_saved_done", { savedId }),

  reopenSaved: (savedId: string) => call<SavedItem>("reopen_saved", { savedId }),

  resendInvite: (workspaceId: Id, inviteId: string) =>
    call<InviteOut>("resend_invite", { workspaceId, inviteId }),

  fileThumbnail: (fileId: Id) => call<string>("file_thumbnail", { fileId }),

  mediaToken: (fileId: Id) => call<MediaToken>("media_token", { fileId }),

  listCommands: (workspaceId: Id) => call<SlashCommand[]>("list_commands", { workspaceId }),

  runCommand: (channelId: Id, text: string) => call<CommandResult>("run_command", { channelId, text }),

  messageAction: (messageId: Id, actionId: string, value?: string | null) =>
    call<ActionResult>("message_action", { messageId, actionId, value: value ?? null }),

  openAppHome: (installationId: Id) => call<PanelSession>("open_app_home", { installationId }),

  listMyApps: (workspaceId: Id) => call<DeveloperApp[]>("list_my_apps", { workspaceId }),

  registerApp: (manifest: Record<string, unknown>, workspaceId: Id) =>
    call<DeveloperApp & { secret?: string }>("register_app", { manifest, workspaceId }),

  updateManifest: (appId: Id, manifest: Record<string, unknown>) =>
    call<DeveloperApp>("update_manifest", { appId, manifest }),

  submitApp: (appId: Id) => call<DeveloperApp>("submit_app", { appId }),

  reviewApp: (appId: Id, decision: "approve" | "reject", note?: string | null) =>
    call<DeveloperApp>("review_app", { appId, decision, note: note ?? null }),

  listPendingApps: () => call<DeveloperApp[]>("list_pending_apps"),

  rotateAppSecret: (appId: Id) => call<{ secret: string }>("rotate_app_secret", { appId }),

  testWebhook: (appId: Id) => call<WebhookDelivery>("test_webhook", { appId }),

  listDeliveries: (appId: Id) => call<WebhookDelivery[]>("list_deliveries", { appId }),

  listAppTokens: (appId: Id) => call<AppToken[]>("list_app_tokens", { appId }),

  createAppToken: (appId: Id, name: string) => call<AppToken>("create_app_token", { appId, name }),

  revokeAppToken: (appId: Id, tokenId: string) =>
    call<void>("revoke_app_token", { appId, tokenId }),

  downloadFile: (fileId: Id, filename: string) =>
    call<string>("download_file", { fileId, filename }),

  /**
   * An image attachment as a data URL, for inline rendering. Images only and
   * capped — everything else is a download, not a preview.
   */
  filePreview: (fileId: Id, mime: string) =>
    call<string>("file_preview", { fileId, mime }),

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

  /** Register and pin an external web app from a bare URL (admin). */
  addLinkApp: (workspaceId: Id, name: string, url: string) =>
    call<AppInstallation>("add_link_app", { workspaceId, name, url }),

  uninstallApp: (installationId: Id) =>
    call<void>("uninstall_app", { installationId }),

  updateInstallation: (
    installationId: Id,
    patch: {
      name?: string;
      icon_url?: string | null;
      is_pinned?: boolean;
      sort_order?: number;
      config?: Record<string, unknown>;
    },
  ) => call<AppInstallation>("update_installation", { installationId, patch }),

  probeLinkApp: (workspaceId: Id, url: string) =>
    call<LinkProbe>("probe_link_app", { workspaceId, url }),

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
  agentProviderConnect: (providerId: string, apiKey: string, model: string, baseUrl?: string | null) =>
    call<AgentProviderStatus>("agent_provider_connect", {
      providerId,
      apiKey,
      model,
      baseUrl: baseUrl ?? null,
    }),

  /**
   * Switch models on the already-connected provider. No key crosses: the choice
   * attaches to the key in the keychain, and Rust refuses when there is none.
   */
  agentProviderSetModel: (model: string) =>
    call<AgentProviderStatus>("agent_provider_set_model", { model }),

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

  // ── MCP servers (v2) ─────────────────────────────────────────────────
  agentMcpList: () => call<McpServerView[]>("agent_mcp_list"),
  agentMcpAdd: (input: {
    name: string;
    transport: "http" | "stdio";
    url?: string | null;
    command?: string | null;
    args?: string[];
    token?: string | null;
  }) =>
    call<McpServerView>("agent_mcp_add", {
      name: input.name,
      transport: input.transport,
      url: input.url ?? null,
      command: input.command ?? null,
      args: input.args ?? [],
      token: input.token ?? null,
    }),
  agentMcpRemove: (serverId: string) => call<void>("agent_mcp_remove", { serverId }),
  agentMcpSetEnabled: (serverId: string, enabled: boolean) =>
    call<McpServerView>("agent_mcp_set_enabled", { serverId, enabled }),
  agentMcpTools: (serverId: string) => call<AgentToolSpec[]>("agent_mcp_tools", { serverId }),
  agentMcpRefresh: () => call<McpServerView[]>("agent_mcp_refresh"),

  // ── Artifacts · memory · skills · audit (v2) ─────────────────────────
  agentArtifactPut: (sessionId: string, label: string, text: string) =>
    call<{ handle: string; bytes: number }>("agent_artifact_put", { sessionId, label, text }),
  agentMemoriesList: (limit = 50) => call<AgentMemory[]>("agent_memories_list", { limit }),
  agentMemoryAdd: (text: string, tags: string[] = []) =>
    call<AgentMemory>("agent_memory_add", { text, tags }),
  agentMemoryDelete: (id: string) => call<void>("agent_memory_delete", { id }),
  agentSkillsList: () => call<AgentSkill[]>("agent_skills_list"),
  agentSkillRead: (name: string) => call<string>("agent_skill_read", { name }),
  agentSkillSave: (name: string, body: string) => call<AgentSkill>("agent_skill_save", { name, body }),
  agentSkillDelete: (name: string) => call<void>("agent_skill_delete", { name }),
  agentAuditEntries: (date?: string | null, limit = 200) =>
    call<AgentAuditEntries>("agent_audit_entries", { date: date ?? null, limit }),
  agentNativeDialogs: (enabled: boolean | null) =>
    call<boolean>("agent_native_dialogs", { enabled }),
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
    onProgress?: (filename: string, sent: number, total: number) => void,
  ): Promise<void> => {
    if (isDesktopShell()) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({ multiple: true });
      if (!selected) return;
      for (const path of Array.isArray(selected) ? selected : [selected]) {
        const name = path.split(/[\\/]/).pop() ?? path;
        onProgress?.(name, 0, 0);
        onUploaded(
          await api.uploadFile(workspaceId, path, (sent, total) =>
            onProgress?.(name, sent, total),
          ),
        );
      }
      return;
    }

    for (const file of await pickFilesInBrowser(true)) {
      onProgress?.(file.name, 0, file.size);
      onUploaded(
        await api.uploadFile(workspaceId, file, (sent, total) =>
          onProgress?.(file.name, sent, total),
        ),
      );
    }
  },

  /**
   * Files dragged onto the window.
   *
   * The two hosts report the same gesture through different machinery: the
   * Tauri shell intercepts the OS drag (HTML5 drop never fires there while
   * `dragDropEnabled` is on) and reports filesystem *paths*; a browser tab gets
   * the HTML5 events and reports `File` objects. Both shapes are exactly what
   * each host's `uploadFile` accepts, so the subscriber can pass them through.
   */
  onFileDrop: async (handlers: {
    onOver?: () => void;
    onLeave?: () => void;
    onDrop: (sources: Array<string | File>) => void;
  }): Promise<UnlistenFn> => {
    if (isDesktopShell()) {
      const { getCurrentWebview } = await import("@tauri-apps/api/webview");
      return getCurrentWebview().onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          handlers.onOver?.();
        } else if (event.payload.type === "drop") {
          handlers.onLeave?.();
          if (event.payload.paths.length > 0) handlers.onDrop(event.payload.paths);
        } else {
          handlers.onLeave?.();
        }
      });
    }

    const hasFiles = (event: DragEvent) =>
      Boolean(event.dataTransfer && [...event.dataTransfer.types].includes("Files"));
    const onDragOver = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      // Without this the browser navigates to the dropped file.
      event.preventDefault();
      handlers.onOver?.();
    };
    const onDragLeave = (event: DragEvent) => {
      // Only when the drag actually leaves the window, not an inner element.
      if (event.relatedTarget === null) handlers.onLeave?.();
    };
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      handlers.onLeave?.();
      const files = [...(event.dataTransfer?.files ?? [])];
      if (files.length > 0) handlers.onDrop(files);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  },
};

export type { UnlistenFn };
