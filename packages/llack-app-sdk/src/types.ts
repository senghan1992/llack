/** Public types for the Llack mini-app SDK. */

/** Capabilities an app may request in its manifest. */
export type Scope =
  | "identity:read"
  | "channels:read"
  | "messages:read"
  | "messages:write"
  | "files:read"
  | "files:write"
  | "users:read"
  | "notify"
  | "storage"
  | "panel:ui";

export interface UserBrief {
  id: string;
  handle: string;
  display_name: string;
  avatar_url?: string | null;
  is_bot?: boolean;
}

/** Where the panel is running: which workspace, which channel, for whom. */
export interface PanelContext {
  workspace_id: string;
  channel_id: string | null;
  user: UserBrief;
  locale: string;
  timezone: string;
  default_width: number;
  accent_color?: string | null;
}

export interface Session {
  /** Short-lived token scoped to this installation. Refreshed by the host. */
  bridge_token: string;
  expires_at: string;
  granted_scopes: Scope[];
  /** Admin-provided configuration from the install screen. */
  config: Record<string, unknown>;
  context: PanelContext;
  api_base: string;
}

export interface ChannelBrief {
  id: string;
  name: string | null;
  slug: string | null;
  kind: "public" | "private";
  topic: string | null;
}

export interface PostMessageOptions {
  channelId: string;
  body?: string;
  /** Rich layout, when plain Markdown is not enough. */
  blocks?: unknown[];
  parentId?: string;
  /** Supply your own idempotency key to make a retry safe. */
  clientMsgId?: string;
}

export interface NotifyOptions {
  userIds: string[];
  title: string;
  body?: string;
  deepLink?: string;
}

export class LlackError extends Error {
  readonly code: string;
  readonly status?: number;
  readonly details?: unknown;

  constructor(code: string, message: string, status?: number, details?: unknown) {
    super(message);
    this.name = "LlackError";
    this.code = code;
    if (status !== undefined) this.status = status;
    if (details !== undefined) this.details = details;
  }

  /** True when the app asked for something outside its granted scopes. */
  get isMissingScope(): boolean {
    return this.code === "missing_scope";
  }
}
