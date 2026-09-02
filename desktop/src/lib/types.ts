/**
 * Types mirroring the Rust command surface in `src-tauri/src/commands.rs`.
 *
 * Hand-maintained rather than generated, so the compile error when the Rust
 * side changes shape lands here rather than at runtime in the UI.
 */

export type Id = string;

export type Presence = "active" | "away" | "dnd" | "offline";
export type ChannelKind = "public" | "private" | "dm" | "group_dm";
export type NotificationLevel = "all" | "mentions" | "nothing";
export type MessageKind = "user" | "system" | "app";
export type WorkspaceRole = "owner" | "admin" | "member" | "guest";

export interface UserBrief {
  id: Id;
  handle: string;
  display_name: string;
  avatar_url?: string | null;
  is_bot?: boolean;
}

export interface User extends UserBrief {
  email: string;
  title?: string | null;
  timezone: string;
  locale: string;
  status_emoji?: string | null;
  status_text?: string | null;
  presence: Presence;
  is_active: boolean;
}

export interface Workspace {
  id: Id;
  slug: string;
  name: string;
  description?: string | null;
  icon_url?: string | null;
  my_role?: WorkspaceRole | null;
  member_count: number;
}

export interface ChannelMembership {
  /** "admin" or "member". Decides which channel-settings controls to show;
   *  the server re-checks every privileged change. */
  role?: "admin" | "member" | null;
  last_read_message_id?: Id | null;
  unread_count: number;
  mention_count: number;
  notification_level?: NotificationLevel | null;
  is_muted: boolean;
  is_starred: boolean;
  section?: string | null;
  sort_order: number;
}

export interface Channel {
  id: Id;
  workspace_id: Id;
  kind: ChannelKind;
  slug?: string | null;
  name?: string | null;
  topic?: string | null;
  purpose?: string | null;
  is_archived: boolean;
  last_message_at?: string | null;
  message_count: number;
  member_count: number;
  peers: UserBrief[];
  membership?: ChannelMembership | null;
}

export interface Reaction {
  emoji: string;
  count: number;
  user_ids: Id[];
  me: boolean;
}

/** One row of the channel member list. */
export interface ChannelMemberEntry {
  id: Id;
  user: UserBrief;
  role?: "admin" | "member" | null;
  joined_at?: string | null;
}

export interface FileRef {
  id: Id;
  filename: string;
  mime_type: string;
  size_bytes: number;
  download_url?: string | null;
  thumbnail_url?: string | null;
  uploader?: UserBrief | null;
}

export interface Message {
  id: Id;
  channel_id: Id;
  kind: MessageKind;
  body: string;
  blocks?: unknown;
  client_msg_id?: string | null;
  author?: UserBrief | null;
  app_id?: Id | null;
  parent_id?: Id | null;
  reply_count: number;
  last_reply_at?: string | null;
  also_sent_to_channel: boolean;
  mentioned_user_ids: Id[];
  mentions_everyone: boolean;
  attachments: FileRef[];
  reactions: Reaction[];
  is_pinned: boolean;
  edited_at?: string | null;
  deleted_at?: string | null;
  created_at: string;
}

/** A message that exists only locally until the server confirms it. */
export interface PendingMessage {
  id: string;
  channel_id: Id;
  client_msg_id: string;
  payload: {
    body: string;
    parent_id?: Id | null;
    also_send_to_channel?: boolean;
    file_ids?: Id[];
  };
  state: "pending" | "sending" | "failed";
  attempts: number;
  last_error?: string | null;
  created_at_ms: number;
}

export interface AppSummary {
  id: Id;
  slug: string;
  name: string;
  tagline?: string | null;
  icon_url?: string | null;
  accent_color?: string | null;
  panel_url?: string | null;
  sidebar_url?: string | null;
  default_width: number;
  requested_scopes: string[];
}

export interface AppInstallation {
  id: Id;
  workspace_id: Id;
  app: AppSummary;
  granted_scopes: string[];
  config: Record<string, unknown>;
  bot_user_id?: Id | null;
  is_enabled: boolean;
  is_pinned: boolean;
  sort_order: number;
}

export interface PanelSession {
  installation_id: Id;
  app_id: Id;
  panel_url: string;
  bridge_token: string;
  expires_at: string;
  granted_scopes: string[];
  config: Record<string, unknown>;
  context: Record<string, unknown>;
}

export interface SendResult {
  message: Message | null;
  client_msg_id: string;
  queued: boolean;
  error?: string | null;
}

export interface BootstrapResult {
  server_url: string | null;
  user: User | null;
  resumed: boolean;
}

export interface DrainReport {
  sent: number;
  still_pending: number;
  failed: number;
}

export interface SearchResult {
  query: string;
  took_ms?: number;
  channels: Array<{
    id: Id;
    name: string;
    slug?: string | null;
    kind: ChannelKind;
    topic?: string | null;
    member_count: number;
  }>;
  people: Array<{
    id: Id;
    display_name: string;
    handle: string;
    title?: string | null;
    avatar_url?: string | null;
    is_bot: boolean;
  }>;
  apps: Array<{
    installation_id: Id;
    app_id: Id;
    name: string;
    tagline?: string | null;
    icon_url?: string | null;
    has_panel: boolean;
  }>;
  messages: Array<{
    message: Message;
    channel_id: Id;
    channel_name?: string | null;
    highlight?: string | null;
  }>;
  /** Absent on servers older than the files-in-search release. */
  files?: Array<{
    id: Id;
    filename: string;
    mime_type?: string | null;
    size_bytes: number;
    created_at?: string | null;
    uploader_name?: string | null;
  }>;
}

/** The error shape every failed command rejects with. */
export interface CommandError {
  code: string;
  message: string;
  status?: number | null;
  requires_reauth: boolean;
}

// ── Realtime events emitted by the shell ────────────────────────────────────

export type ConnectionStatus =
  | { status: "connected"; session_id: string; workspace_ids: Id[] }
  | { status: "disconnected"; reason: string; will_retry_in_ms: number | null }
  | { status: "resyncing"; expected: number; received: number };

export type SyncEffect =
  | { kind: "channel_changed"; channel_id: Id }
  | { kind: "thread_changed"; channel_id: Id; parent_id: Id }
  | { kind: "sidebar_changed" }
  | {
      kind: "notify";
      title: string;
      body: string;
      channel_id?: Id | null;
      message_id?: Id | null;
    }
  | { kind: "typing"; channel_id: Id; user_id: Id }
  | { kind: "presence"; user_id: Id; presence: Presence }
  | { kind: "ignored" };

export interface ServerFrame {
  type: string;
  seq?: number | null;
  ts?: string | null;
  workspace_id?: Id | null;
  data: Record<string, unknown>;
}
