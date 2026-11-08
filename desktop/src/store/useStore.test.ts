import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Channel } from "../lib/types";

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

beforeAll(async () => {
  stubStorage();
  ({ useStore } = await import("./useStore"));
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
  useStore.setState({
    channels: [],
    activeId: null,
    recentRooms: [],
    drafts: {},
    messages: {},
    // The rooms of this test are not on a server: the network is not the
    // test's business.
    loadMessages: vi.fn(async () => undefined),
    markRead: vi.fn(),
  });
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
