import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Channel, Message, User } from "../lib/types";

/** localStorage 가 없는 환경(node)에서 도는 테스트라 흉내를 낸다. */
function stubStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  });
}

let useStore: typeof import("./useStore").useStore;
let handleRealtimeEvent: typeof import("./useStore").handleRealtimeEvent;
let resetRealtimeTimers: typeof import("./useStore").resetRealtimeTimers;

beforeAll(async () => {
  stubStorage();
  ({ useStore, handleRealtimeEvent, resetRealtimeTimers } = await import("./useStore"));
});

function channel(id: string, over: Partial<Channel> = {}): Channel {
  return {
    id,
    workspace_id: "w",
    name: id,
    topic: null,
    purpose: null,
    kind: "channel",
    is_private: false,
    created_by: "u",
    created_at: "",
    member_count: 0,
    unread_count: 0,
    last_message_at: null,
    dm_user: null,
    members: null,
    is_member: true,
    ...over,
  };
}

beforeEach(() => {
  resetRealtimeTimers();
  useStore.setState({
    user: null,
    channels: [],
    activeId: null,
    recentRooms: [],
    drafts: {},
    messages: {},
    typing: {},
    enteringIds: {},
    // The rooms of this test are not on a server: the network is not the
    // test's business.
    loadMessages: vi.fn(async () => undefined),
    markRead: vi.fn(),
  });
});

afterEach(() => {
  resetRealtimeTimers();
  vi.useRealTimers();
});

describe("stepRoom", () => {
  it("walks in the order the rail lists the rooms", async () => {
    useStore.setState({
      channels: [
        channel("general"),
        channel("dm-1", { kind: "dm", name: "지현" }),
        channel("random"),
      ],
      activeId: "general",
    });

    await useStore.getState().stepRoom(1);
    // The rail lists the channels first and the messages after them.
    expect(useStore.getState().activeId).toBe("random");

    await useStore.getState().stepRoom(1);
    expect(useStore.getState().activeId).toBe("dm-1");

    await useStore.getState().stepRoom(-1);
    expect(useStore.getState().activeId).toBe("random");
  });

  it("stops at the ends instead of wrapping around", async () => {
    useStore.setState({
      channels: [channel("general"), channel("random")],
      activeId: "random",
    });

    await useStore.getState().stepRoom(1);
    expect(useStore.getState().activeId).toBe("random");

    await useStore.getState().stepRoom(-1);
    expect(useStore.getState().activeId).toBe("general");

    await useStore.getState().stepRoom(-1);
    expect(useStore.getState().activeId).toBe("general");
  });

  it("walks the unread rooms only", async () => {
    useStore.setState({
      channels: [
        channel("general"),
        channel("random", { unread_count: 3 }),
        channel("dm-1", { kind: "dm", name: "지현", unread_count: 1 }),
      ],
      activeId: "general",
    });

    await useStore.getState().stepRoom(1, true);
    expect(useStore.getState().activeId).toBe("random");

    await useStore.getState().stepRoom(1, true);
    expect(useStore.getState().activeId).toBe("dm-1");

    // There is no unread room after this one.
    await useStore.getState().stepRoom(1, true);
    expect(useStore.getState().activeId).toBe("dm-1");
  });

  it("does nothing when no room is unread", async () => {
    useStore.setState({
      channels: [channel("general"), channel("random")],
      activeId: "general",
    });

    await useStore.getState().stepRoom(1, true);
    expect(useStore.getState().activeId).toBe("general");
  });

  it("walks the rooms you are in, and skips the ones you left", async () => {
    useStore.setState({
      channels: [
        channel("general"),
        channel("left", { is_member: false }),
        channel("random"),
      ],
      activeId: "general",
    });

    await useStore.getState().stepRoom(1);
    expect(useStore.getState().activeId).toBe("random");
  });
});

describe("recentRooms", () => {
  it("puts the room you opened at the top, without a repeat", async () => {
    useStore.setState({ channels: [channel("general"), channel("random")] });

    await useStore.getState().openChannel("general");
    await useStore.getState().openChannel("random");
    expect(useStore.getState().recentRooms).toEqual(["random", "general"]);

    await useStore.getState().openChannel("general");
    expect(useStore.getState().recentRooms).toEqual(["general", "random"]);
  });

  it("keeps eight rooms", async () => {
    const channels = Array.from({ length: 10 }, (_, index) => channel(`room-${index}`));
    useStore.setState({ channels });

    for (const room of channels) await useStore.getState().openChannel(room.id);

    const recent = useStore.getState().recentRooms;
    expect(recent).toHaveLength(8);
    expect(recent[0]).toBe("room-9");
    expect(recent).not.toContain("room-0");
  });
});

describe("drafts", () => {
  it("keeps each room's line apart", () => {
    useStore.getState().setDraft("general", "안녕하세요");
    useStore.getState().setDraft("random", "내일 회의");

    expect(useStore.getState().drafts.general).toBe("안녕하세요");
    expect(useStore.getState().drafts.random).toBe("내일 회의");
  });

  it("forgets a line that was emptied", () => {
    useStore.getState().setDraft("general", "안녕하세요");
    useStore.getState().setDraft("general", "");

    expect(useStore.getState().drafts.general).toBeUndefined();
  });
});

function makeUser(id: string, name: string): User {
  return {
    id,
    email: `${id}@hanbit.co.kr`,
    name,
    title: null,
    avatar_color: null,
    avatar_url: null,
    presence: "online",
    last_seen_at: null,
    created_at: "",
  };
}

function makeMessage(id: string, channelId: string, user: User): Message {
  return {
    id,
    channel_id: channelId,
    user_id: user.id,
    author: user,
    body: `message ${id}`,
    kind: "text",
    parent_id: null,
    reply_to_id: null,
    reply_to: null,
    inline: false,
    created_at: "2026-11-20T09:00:00Z",
    edited_at: null,
    deleted_at: null,
    reply_count: 0,
    last_reply_at: null,
    pinned: false,
    reactions: [],
    attachments: [],
  };
}

describe("typing and entering messages", () => {
  it("tracks typing users, ignores self, and expires after 5 seconds", () => {
    vi.useFakeTimers();
    const me = makeUser("me", "나");
    useStore.setState({ user: me, activeId: "general" });

    handleRealtimeEvent({
      type: "typing",
      channel_id: "general",
      user_id: "me",
      name: "나",
      on: true,
    });
    expect(useStore.getState().typing.general).toBeUndefined();

    handleRealtimeEvent({
      type: "typing",
      channel_id: "general",
      user_id: "u2",
      name: "김현진",
      on: true,
    });
    expect(useStore.getState().typing.general).toEqual([{ user_id: "u2", name: "김현진" }]);

    vi.advanceTimersByTime(4999);
    expect(useStore.getState().typing.general).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useStore.getState().typing.general).toEqual([]);
  });

  it("clears typing on message.created and marks active-channel live messages as entering", () => {
    vi.useFakeTimers();
    const me = makeUser("me", "나");
    const other = makeUser("u2", "김현진");
    useStore.setState({
      user: me,
      activeId: "general",
      channels: [channel("general"), channel("random")],
      messages: { general: [], random: [] },
    });

    handleRealtimeEvent({
      type: "typing",
      channel_id: "general",
      user_id: other.id,
      name: other.name,
      on: true,
    });
    expect(useStore.getState().typing.general).toHaveLength(1);

    handleRealtimeEvent({
      type: "message.created",
      message: makeMessage("m1", "general", other),
    });
    expect(useStore.getState().typing.general).toEqual([]);
    expect(useStore.getState().enteringIds.m1).toBe(true);

    // Inactive channel messages do not animate on arrival.
    handleRealtimeEvent({
      type: "message.created",
      message: makeMessage("m2", "random", other),
    });
    expect(useStore.getState().enteringIds.m2).toBeUndefined();

    vi.advanceTimersByTime(600);
    expect(useStore.getState().enteringIds.m1).toBeUndefined();
  });

  it("clears typing across channels when a user goes offline and clears entering on channel switch", async () => {
    const me = makeUser("me", "나");
    const other = makeUser("u2", "김현진");
    useStore.setState({
      user: me,
      activeId: "general",
      channels: [channel("general"), channel("random")],
      messages: { general: [], random: [] },
    });

    handleRealtimeEvent({
      type: "typing",
      channel_id: "general",
      user_id: other.id,
      name: other.name,
      on: true,
    });
    handleRealtimeEvent({
      type: "typing",
      channel_id: "random",
      user_id: other.id,
      name: other.name,
      on: true,
    });

    handleRealtimeEvent({
      type: "presence",
      user_id: other.id,
      presence: "offline",
    });
    expect(useStore.getState().typing.general).toEqual([]);
    expect(useStore.getState().typing.random).toEqual([]);

    handleRealtimeEvent({
      type: "message.created",
      message: makeMessage("m3", "general", other),
    });
    expect(useStore.getState().enteringIds.m3).toBe(true);

    await useStore.getState().openChannel("random");
    expect(useStore.getState().enteringIds).toEqual({});
  });
});
