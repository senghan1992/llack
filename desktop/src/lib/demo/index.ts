/**
 * Demo runtime — the whole product, no server.
 *
 * ## Why this exists
 *
 * Browser mode (`src/lib/web.ts`) already runs the real UI in a tab, but it
 * needs the FastAPI backend and therefore a tunnel or a deployment. That is
 * still too much setup for the only question a reviewer usually has: *what does
 * it look like so far?* This module answers the same HTTP calls `web.ts` makes,
 * from memory, so a single static HTML file is a working walkthrough.
 *
 * ## Why the data is a dump, not a fixture someone wrote
 *
 * `fixture.json` is a recording of the live API's actual responses (see
 * `scripts/dump-demo-fixture.py`). Hand-written fixtures drift from the API
 * they imitate, and the first symptom is a demo rendering a shape the server
 * never returns — which makes the demo actively misleading rather than merely
 * incomplete. Re-record it instead of editing it.
 *
 * ## Where it plugs in
 *
 * One branch at the top of `web.ts`'s single `request()` chokepoint, and one
 * early return in `connectSocket`. Everything else — auth handling, the
 * outbox, cursor pages, error envelopes — is the same code the real browser
 * mode runs, which is what makes this a preview of the product rather than a
 * separate mock of it.
 *
 * ## What it deliberately cannot do
 *
 * Uploads, mini-app panels and the model round-trip all need something outside
 * the page. Each returns its real refusal so the UI shows its real error state,
 * because a demo that silently omits a failure path teaches the wrong thing
 * about the product.
 */

import { commandError } from "@/lib/errors";
import type { Id, Message, User } from "@/lib/types";

import fixture from "./fixture.json";

/** Set at build time by `vite.demo.config.ts`. */
declare const __LLACK_DEMO__: boolean | undefined;

export function isDemoBuild(): boolean {
  return typeof __LLACK_DEMO__ !== "undefined" && __LLACK_DEMO__ === true;
}

interface Fixture {
  me: User;
  workspace_id: Id;
  responses: Record<string, unknown>;
}

const data = fixture as unknown as Fixture;

/** The account the demo is signed in as. */
export const demoUser = data.me;
export const demoWorkspaceId = data.workspace_id;

interface CursorPage<T> {
  items: T[];
  next_cursor?: string | null;
  has_more?: boolean;
}

/*
 * ── Mutable state ────────────────────────────────────────────────────────
 *
 * Messages are copied out of the fixture on first touch so sending, editing and
 * reacting all work for the session. Nothing persists: a reload is a fresh
 * demo, which is the right default for a link that gets passed around.
 */
const channelMessages = new Map<Id, Message[]>();
const threadReplies = new Map<Id, Message[]>();
let sequence = 0;

/**
 * A real ULID, not a readable stand-in.
 *
 * The transcript orders messages by `id.localeCompare(id)` — ULIDs sort
 * lexicographically by time, so the id *is* the ordering. A friendlier id like
 * `01DEMO…` sorts before every seeded `01M1…` one, which put a just-sent
 * message near the top of the channel. The demo has to honour the same
 * invariant the server does.
 */
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function nextId(): string {
  let time = Date.now();
  let out = "";
  for (let index = 0; index < 10; index += 1) {
    out = CROCKFORD[time % 32] + out;
    time = Math.floor(time / 32);
  }
  // The random half only has to be unique within one page, and a counter in
  // the low bits keeps two messages sent in the same millisecond ordered.
  sequence += 1;
  for (let index = 0; index < 16; index += 1) {
    out += CROCKFORD[Math.floor(Math.random() * 32)];
  }
  return out.slice(0, 26 - 2) + CROCKFORD[(sequence >> 5) % 32] + CROCKFORD[sequence % 32];
}

function messagesFor(channelId: Id): Message[] {
  const existing = channelMessages.get(channelId);
  if (existing) return existing;
  const recorded = data.responses[
    `GET /channels/${channelId}/messages?limit=80`
  ] as CursorPage<Message> | undefined;
  // Newest-first from the API, and `web.ts` reverses it. Kept in the API's
  // order here so this module answers exactly what the server would.
  const copy = recorded ? recorded.items.map((m) => ({ ...m })) : [];
  channelMessages.set(channelId, copy);
  return copy;
}

function repliesFor(parentId: Id): Message[] {
  const existing = threadReplies.get(parentId);
  if (existing) return existing;
  const recorded = data.responses[`GET /messages/${parentId}/replies?limit=200`] as
    | CursorPage<Message>
    | undefined;
  const copy = recorded ? recorded.items.map((m) => ({ ...m })) : [];
  threadReplies.set(parentId, copy);
  return copy;
}

/** Every channel in the workspace, from the recording. */
function allChannels(): Array<{ id: Id; name: string }> {
  return (data.responses[`GET /workspaces/${demoWorkspaceId}/channels`] ??
    []) as Array<{ id: Id; name: string }>;
}

/**
 * States the recording did not happen to capture.
 *
 * The dump is one moment, and in that moment the account had read every
 * channel that has history — so the demo could never show an unread run or
 * the "여기까지 읽으셨습니다" line, which is a state the product has and a
 * reviewer should see. This applies it at read time rather than editing
 * `fixture.json`, so the recording stays a recording.
 *
 * Only ever *adds* a state to a channel the recording left neutral; it never
 * contradicts what the server said.
 */
const DEMO_UNREAD = 3;

function withDemoStates(channels: unknown[]): unknown[] {
  return channels.map((entry) => {
    const channel = entry as {
      id: Id;
      name?: string | null;
      membership?: { unread_count: number; last_read_message_id?: Id | null } | null;
    };
    if (channel.name !== "개발" || !channel.membership) return entry;
    if (channel.membership.unread_count > 0) return entry;

    /*
     * The count and the read cursor have to agree.
     *
     * Setting only `unread_count` left `last_read_message_id` pointing at the
     * newest message — which is what the recording captured, because the
     * account had read everything — and the line then landed below the last
     * message, marking nothing. Both fields move together: the cursor goes
     * back `DEMO_UNREAD` messages, which is the state it would actually be in.
     */
    const page = messagesFor(channel.id);
    const cursor = page[DEMO_UNREAD]?.id ?? null;
    if (!cursor) return entry;
    return {
      ...channel,
      membership: {
        ...channel.membership,
        unread_count: DEMO_UNREAD,
        last_read_message_id: cursor,
      },
    };
  });
}

function findMessage(messageId: Id): Message | null {
  for (const list of channelMessages.values()) {
    const hit = list.find((m) => m.id === messageId);
    if (hit) return hit;
  }
  for (const list of threadReplies.values()) {
    const hit = list.find((m) => m.id === messageId);
    if (hit) return hit;
  }
  // Not yet materialised: walk the recording.
  for (const channel of allChannels()) {
    const hit = messagesFor(channel.id).find((m) => m.id === messageId);
    if (hit) return hit;
  }
  return null;
}

function newMessage(channelId: Id, body: string, parentId: Id | null): Message {
  return {
    id: nextId(),
    channel_id: channelId,
    kind: "user",
    body,
    blocks: null,
    client_msg_id: null,
    author: {
      id: demoUser.id,
      handle: demoUser.handle,
      display_name: demoUser.display_name,
      avatar_url: demoUser.avatar_url ?? null,
      is_bot: false,
    },
    app_id: null,
    parent_id: parentId,
    reply_count: 0,
    last_reply_at: null,
    also_sent_to_channel: false,
    mentioned_user_ids: [],
    mentions_everyone: false,
    attachments: [],
    reactions: [],
    is_pinned: false,
    edited_at: null,
    deleted_at: null,
    created_at: new Date().toISOString(),
  } as unknown as Message;
}

/**
 * Split a recorded path into its segments and its query.
 *
 * `seg(n)` returns `""` past the end rather than `undefined`, so route matching
 * reads as a series of plain equality checks. `tsconfig` has
 * `noUncheckedIndexedAccess`, and threading `?? ""` through thirty comparisons
 * would bury the routing table in noise.
 */
function parse(path: string): {
  seg: (index: number) => string;
  length: number;
  params: URLSearchParams;
} {
  const rawPath = path.split("?")[0] ?? path;
  const rawQuery = path.split("?")[1] ?? "";
  const parts = rawPath.split("/").filter(Boolean);
  return {
    seg: (index) => parts[index] ?? "",
    length: parts.length,
    params: new URLSearchParams(rawQuery),
  };
}

const unsupported = (what: string) =>
  commandError("unsupported_in_demo", `${what} 은(는) 데모에서 동작하지 않습니다.`);

/**
 * Answer one API call from memory.
 *
 * Ordering is deliberate: mutations first, then the recording, then a 404. A
 * recording that shadowed a mutation would make a sent message vanish on the
 * next read, which is the single most obvious way a demo like this breaks.
 */
export async function demoRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  // A little latency, so the UI's loading states are visible rather than
  // skipped. Fast enough not to feel broken, slow enough to be honest about
  // the fact that this is a network-shaped boundary.
  await new Promise((resolve) => setTimeout(resolve, 90));

  const { seg, length, params } = parse(path);
  const ok = <R,>(value: R) => value as unknown as T;

  // ── Auth ─────────────────────────────────────────────────────────────
  if (seg(0) === "auth") {
    if (seg(1) === "login" || seg(1) === "register") {
      // Any credentials are accepted. There is nothing to protect: the whole
      // dataset is already inside the page the visitor downloaded.
      return ok({
        user: demoUser,
        tokens: {
          access_token: "demo",
          refresh_token: "demo",
          expires_at: new Date(Date.now() + 864e5).toISOString(),
        },
      });
    }
    if (seg(1) === "refresh") {
      return ok({
        access_token: "demo",
        refresh_token: "demo",
        expires_at: new Date(Date.now() + 864e5).toISOString(),
      });
    }
    if (seg(1) === "logout") return ok(undefined);
  }

  if (path === "/me") return ok(demoUser);

  // ── Messages ─────────────────────────────────────────────────────────
  if (seg(0) === "channels" && seg(2) === "messages" && method === "POST") {
    const channelId = seg(1);
    const payload = (body ?? {}) as { body?: string; parent_id?: Id | null };
    const message = newMessage(channelId, payload.body ?? "", payload.parent_id ?? null);
    if (payload.parent_id) {
      repliesFor(payload.parent_id).push(message);
      const parent = findMessage(payload.parent_id);
      if (parent) {
        (parent as { reply_count: number }).reply_count += 1;
        (parent as { last_reply_at: string }).last_reply_at = message.created_at;
      }
    } else {
      messagesFor(channelId).unshift(message);
    }
    return ok(message);
  }

  if (seg(0) === "channels" && seg(2) === "messages" && method === "GET") {
    const items = messagesFor(seg(1));
    const before = params.get("before");
    // `before` is answered honestly — with nothing. The recording holds one
    // page per channel, so "load older" correctly reports the start of history
    // instead of looping the same page forever.
    return ok<CursorPage<Message>>({
      items: before ? [] : items,
      next_cursor: null,
      has_more: false,
    });
  }

  if (seg(0) === "messages" && seg(2) === "replies") {
    return ok<CursorPage<Message>>({
      items: repliesFor(seg(1)),
      next_cursor: null,
      has_more: false,
    });
  }

  if (seg(0) === "messages" && length === 2) {
    const message = findMessage(seg(1));
    if (!message) throw commandError("not_found", "메시지를 찾을 수 없습니다.");
    if (method === "PATCH") {
      const payload = (body ?? {}) as { body?: string };
      (message as { body: string }).body = payload.body ?? message.body;
      (message as { edited_at: string }).edited_at = new Date().toISOString();
      return ok(message);
    }
    if (method === "DELETE") {
      (message as { deleted_at: string }).deleted_at = new Date().toISOString();
      (message as { body: string }).body = "";
      return ok(undefined);
    }
  }

  if (seg(0) === "messages" && seg(2) === "reactions") {
    const message = findMessage(seg(1));
    if (!message) throw commandError("not_found", "메시지를 찾을 수 없습니다.");
    const emoji =
      method === "PUT"
        ? ((body ?? {}) as { emoji?: string }).emoji
        : params.get("emoji");
    if (emoji) toggleReaction(message, emoji, method === "PUT");
    return ok(undefined);
  }

  // ── Channels & membership ────────────────────────────────────────────
  if (seg(0) === "channels" && (seg(2) === "read" || seg(2) === "join" || seg(2) === "leave")) {
    return ok(undefined);
  }
  if (seg(0) === "channels" && seg(2) === "membership") return ok(undefined);

  if (seg(0) === "workspaces" && seg(2) === "channels" && method === "POST") {
    const payload = (body ?? {}) as { name?: string; kind?: string };
    const created = {
      id: nextId(),
      workspace_id: demoWorkspaceId,
      name: payload.name ?? "새-채널",
      kind: payload.kind ?? "public",
      topic: null,
      purpose: null,
      is_archived: false,
      member_count: 1,
      unread_count: 0,
      mention_count: 0,
      last_message_at: null,
      membership: { notification_level: "all", is_muted: false, is_starred: false },
      created_at: new Date().toISOString(),
    };
    const channels = allChannels() as unknown[];
    channels.push(created);
    channelMessages.set(created.id, []);
    return ok(created);
  }

  if (seg(0) === "workspaces" && seg(3) === "dm") {
    // The recording has DMs already; returning an existing one is more useful
    // than inventing an empty conversation with someone.
    const existing = allChannels().find(
      (channel) => (channel as { kind?: string }).kind === "dm",
    );
    if (existing) return ok(existing);
    throw unsupported("새 DM");
  }

  // ── Search: computed, not recorded ───────────────────────────────────
  //
  // Two different endpoints, two different shapes. `/search` is the ⌘K palette
  // (channels + people + apps + messages); `/search/messages` is the message-only
  // one. Answering the palette with the message shape is not a smaller result —
  // it is `undefined.map`, and the app unmounts.
  if (seg(0) === "workspaces" && seg(2) === "search" && seg(3) === "messages") {
    return ok(searchMessages(params.get("q") ?? ""));
  }
  if (seg(0) === "workspaces" && seg(2) === "search") {
    return ok(searchUnified(params.get("q") ?? ""));
  }

  // ── Not possible inside a single page ────────────────────────────────
  if (seg(0) === "workspaces" && seg(2) === "files") throw unsupported("파일 업로드");
  if (seg(0) === "files") throw unsupported("파일 업로드");
  if (seg(0) === "app-installations" && seg(2) === "panel-session") {
    throw unsupported("미니앱 패널");
  }
  if (seg(0) === "app-installations" && method === "DELETE") return ok(undefined);
  if (seg(0) === "workspaces" && seg(3) === "install") throw unsupported("앱 설치");

  if (seg(0) === "workspaces" && seg(2) === "channels" && length === 3) {
    return ok(withDemoStates(allChannels() as unknown[]));
  }

  // ── Everything else: the recording ───────────────────────────────────
  const recorded = data.responses[`${method} ${path}`];
  if (recorded !== undefined) return ok(recorded);

  // Same path, different query — the app varies `limit` and `q`.
  const bare = path.split("?")[0];
  for (const key of Object.keys(data.responses)) {
    const recordedMethod = key.split(" ")[0];
    const recordedPath = key.split(" ")[1] ?? "";
    if (recordedMethod === method && recordedPath.split("?")[0] === bare) {
      return ok(data.responses[key]);
    }
  }

  throw commandError(
    "unsupported_in_demo",
    "이 화면은 데모에 포함되지 않았습니다.",
  );
}

function toggleReaction(message: Message, emoji: string, add: boolean): void {
  const reactions = (message as unknown as {
    reactions: Array<{ emoji: string; count: number; user_ids: Id[]; me: boolean }>;
  }).reactions;
  const existing = reactions.find((r) => r.emoji === emoji);
  if (add) {
    if (existing) {
      if (existing.me) return;
      existing.count += 1;
      existing.me = true;
      existing.user_ids = [...existing.user_ids, demoUser.id];
    } else {
      reactions.push({ emoji, count: 1, user_ids: [demoUser.id], me: true });
    }
    return;
  }
  if (!existing) return;
  existing.count -= 1;
  existing.me = false;
  existing.user_ids = existing.user_ids.filter((id) => id !== demoUser.id);
  if (existing.count <= 0) {
    reactions.splice(reactions.indexOf(existing), 1);
  }
}

/**
 * Search, computed rather than replayed.
 *
 * The dump holds one canned query. A search box that only answers one word is
 * worse than no search box: it looks broken for every other input, which is the
 * opposite of what a walkthrough should teach.
 *
 * The return shape must be `SearchResult` exactly — the palette maps over
 * `channels`, `people`, `apps` and `messages` unconditionally, so a missing key
 * is a crash, not a smaller result set. (It was, once.)
 */
function searchUnified(queryText: string): unknown {
  const needle = queryText.trim().toLowerCase();
  const empty = {
    query: queryText,
    took_ms: 2,
    channels: [] as unknown[],
    people: [] as unknown[],
    apps: [] as unknown[],
    messages: [] as unknown[],
  };
  if (!needle) return empty;

  const channels = allChannels()
    .filter((channel) => (channel.name ?? "").toLowerCase().includes(needle))
    .slice(0, 8);

  const users = (data.responses[
    `GET /workspaces/${demoWorkspaceId}/users?limit=200`
  ] ?? []) as Array<{ display_name: string; handle: string }>;
  const people = users
    .filter(
      (person) =>
        person.display_name.toLowerCase().includes(needle) ||
        person.handle.toLowerCase().includes(needle),
    )
    .slice(0, 8);

  const installed = (data.responses[`GET /workspaces/${demoWorkspaceId}/apps`] ??
    []) as Array<{ id: string; app: { id: string; name: string; tagline?: string | null; icon_url?: string | null; panel_url?: string | null } }>;
  const apps = installed
    .filter((entry) => entry.app.name.toLowerCase().includes(needle))
    .slice(0, 8)
    .map((entry) => ({
      installation_id: entry.id,
      app_id: entry.app.id,
      name: entry.app.name,
      tagline: entry.app.tagline ?? null,
      icon_url: entry.app.icon_url ?? null,
      has_panel: Boolean(entry.app.panel_url),
    }));

  return { ...empty, channels, people, apps, messages: messageHits(needle) };
}

/** The message-only endpoint's shape. */
function searchMessages(queryText: string): unknown {
  const needle = queryText.trim().toLowerCase();
  const hits = needle ? messageHits(needle) : [];
  return { query: queryText, hits, total: hits.length, took_ms: 2 };
}

function messageHits(needle: string): unknown[] {
  const hits: unknown[] = [];
  for (const channel of allChannels()) {
    for (const message of messagesFor(channel.id)) {
      if (message.deleted_at) continue;
      if (!message.body.toLowerCase().includes(needle)) continue;
      hits.push({
        message,
        channel_id: channel.id,
        channel_name: channel.name,
        highlight: null,
      });
      if (hits.length >= 30) return hits;
    }
  }
  return hits;
}
