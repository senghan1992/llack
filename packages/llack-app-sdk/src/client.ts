/**
 * The client a mini-app actually uses.
 *
 * ```ts
 * import { createClient } from "@llack/app-sdk";
 *
 * const llack = await createClient();
 * const channels = await llack.channels.list();
 * await llack.messages.post({ channelId: channels[0].id, body: "안녕하세요" });
 * ```
 *
 * The bridge token is short-lived. Rather than making every caller handle
 * expiry, the client re-fetches the session from the host and retries once on
 * a 401 — the host always holds a valid session.
 */

import { HostBridge } from "./bridge.js";
import {
  LlackError,
  type ChannelBrief,
  type NotifyOptions,
  type PanelContext,
  type PostMessageOptions,
  type Scope,
  type Session,
} from "./types.js";

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown };
}

export class LlackClient {
  private session: Session;
  private readonly bridge: HostBridge;
  /** Absolute base for bridge calls, derived from the host page's origin. */
  private readonly apiRoot: string;

  constructor(session: Session, bridge: HostBridge, apiRoot: string) {
    this.session = session;
    this.bridge = bridge;
    this.apiRoot = apiRoot;
  }

  // ── Context ─────────────────────────────────────────────────────────

  get context(): PanelContext {
    return this.session.context;
  }

  /** Admin-provided configuration from the install screen. */
  get config(): Record<string, unknown> {
    return this.session.config;
  }

  get scopes(): Scope[] {
    return this.session.granted_scopes;
  }

  hasScope(scope: Scope): boolean {
    return this.session.granted_scopes.includes(scope);
  }

  /** Throw early with a clear message rather than failing at the call site. */
  requireScope(scope: Scope): void {
    if (!this.hasScope(scope)) {
      throw new LlackError(
        "missing_scope",
        `이 앱에는 ${scope} 권한이 없습니다. 매니페스트에 추가하고 다시 설치해주세요.`,
      );
    }
  }

  // ── HTTP ────────────────────────────────────────────────────────────

  private async fetchJson<T>(
    path: string,
    init: RequestInit = {},
    retrying = false,
  ): Promise<T> {
    const response = await fetch(`${this.apiRoot}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
        Authorization: `Bearer ${this.session.bridge_token}`,
      },
    });

    if (response.status === 401 && !retrying) {
      // The token aged out mid-session; ask the host for a fresh one.
      this.session = await this.bridge.getSession();
      return this.fetchJson<T>(path, init, true);
    }

    if (!response.ok) {
      let envelope: ErrorEnvelope = {};
      try {
        envelope = (await response.json()) as ErrorEnvelope;
      } catch {
        // A non-JSON error body means a proxy answered, not the API.
      }
      throw new LlackError(
        envelope.error?.code ?? "http_error",
        envelope.error?.message ?? `요청이 실패했습니다 (HTTP ${response.status})`,
        response.status,
        envelope.error?.details,
      );
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  // ── Channels ────────────────────────────────────────────────────────

  readonly channels = {
    /** Channels in this workspace. DMs are never included. */
    list: async (): Promise<ChannelBrief[]> => {
      this.requireScope("channels:read");
      return this.fetchJson<ChannelBrief[]>("/channels");
    },
  };

  // ── Messages ────────────────────────────────────────────────────────

  readonly messages = {
    /** Post as the app's bot user. */
    post: async (options: PostMessageOptions): Promise<{ created: boolean }> => {
      this.requireScope("messages:write");
      const result = await this.fetchJson<{ created: boolean }>("/messages", {
        method: "POST",
        body: JSON.stringify({
          channel_id: options.channelId,
          body: options.body ?? "",
          blocks: options.blocks ?? null,
          parent_id: options.parentId ?? null,
          client_msg_id: options.clientMsgId ?? null,
        }),
      });
      return result;
    },
  };

  // ── Notifications ───────────────────────────────────────────────────

  readonly notifications = {
    send: async (options: NotifyOptions): Promise<void> => {
      this.requireScope("notify");
      await this.fetchJson<void>("/notify", {
        method: "POST",
        body: JSON.stringify({
          user_ids: options.userIds,
          title: options.title,
          body: options.body ?? "",
          deep_link: options.deepLink ?? null,
        }),
      });
    },
  };

  // ── Storage ─────────────────────────────────────────────────────────

  /**
   * Per-installation key/value store.
   *
   * The reason it exists: a small internal tool should not have to stand up a
   * database to remember a handful of settings.
   *
   * `scope` picks the namespace — `"workspace"` is shared by everyone,
   * `{ user: id }` or `{ channel: id }` is private to that user or channel.
   */
  readonly storage = {
    get: async <T = unknown>(
      key: string,
      scope: StorageScope = "workspace",
    ): Promise<T | null> => {
      this.requireScope("storage");
      try {
        const item = await this.fetchJson<{ value: T }>(
          `/storage/${encodeURIComponent(key)}?scope_key=${encodeURIComponent(
            scopeKey(scope),
          )}`,
        );
        return item.value;
      } catch (error) {
        // A missing key is an absent value, not an error condition.
        if (error instanceof LlackError && error.code === "storage_key_not_found") {
          return null;
        }
        throw error;
      }
    },

    set: async <T = unknown>(
      key: string,
      value: T,
      scope: StorageScope = "workspace",
    ): Promise<void> => {
      this.requireScope("storage");
      await this.fetchJson<unknown>(`/storage/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify({ value, scope_key: scopeKey(scope) }),
      });
    },

    list: async (
      prefix?: string,
      scope: StorageScope = "workspace",
    ): Promise<Array<{ key: string; value: unknown }>> => {
      this.requireScope("storage");
      const params = new URLSearchParams({ scope_key: scopeKey(scope) });
      if (prefix) params.set("prefix", prefix);
      return this.fetchJson<Array<{ key: string; value: unknown }>>(
        `/storage?${params.toString()}`,
      );
    },

    delete: async (key: string, scope: StorageScope = "workspace"): Promise<void> => {
      this.requireScope("storage");
      await this.fetchJson<unknown>(
        `/storage/${encodeURIComponent(key)}?scope_key=${encodeURIComponent(
          scopeKey(scope),
        )}`,
        { method: "DELETE" },
      );
    },
  };

  // ── Panel UI ────────────────────────────────────────────────────────

  /** Ask the host to change the panel's chrome or navigate the app. */
  readonly ui = {
    setTitle: (title: string): void => {
      this.requireScope("panel:ui");
      this.bridge.notify("llack:set-title", { title });
    },

    /** Navigate the main pane to a channel the user is already in. */
    openChannel: (channelId: string): void => {
      this.requireScope("panel:ui");
      this.bridge.notify("llack:open-channel", { channelId });
    },

    close: (): void => {
      this.bridge.notify("llack:close");
    },
  };

  dispose(): void {
    this.bridge.dispose();
  }
}

export type StorageScope = "workspace" | { user: string } | { channel: string };

function scopeKey(scope: StorageScope): string {
  if (scope === "workspace") return "workspace";
  if ("user" in scope) return `user:${scope.user}`;
  return `channel:${scope.channel}`;
}

/**
 * Handshake with the host and return a ready client.
 *
 * Call this once when the panel loads.
 */
export async function createClient(options: { apiRoot?: string } = {}): Promise<LlackClient> {
  const bridge = new HostBridge();
  const session = await bridge.getSession();

  // The session carries a relative base (`/api/v1/app-bridge`). Resolve it
  // against the server the panel was served from, unless the app overrides it
  // (useful when the panel is served from its own domain).
  const apiRoot =
    options.apiRoot ??
    (session.api_base.startsWith("http")
      ? session.api_base
      : new URL(session.api_base, inferServerOrigin()).toString().replace(/\/$/, ""));

  return new LlackClient(session, bridge, apiRoot);
}

/**
 * Best guess at the Llack server's origin.
 *
 * A sandboxed frame cannot read the host's location, so an app served from its
 * own domain must pass `apiRoot` explicitly. Apps served by the Llack server
 * itself get the right answer from their own origin.
 */
function inferServerOrigin(): string {
  if (typeof window === "undefined") return "http://localhost:8000";
  return window.location.origin;
}
