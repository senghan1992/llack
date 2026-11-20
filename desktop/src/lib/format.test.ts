import { beforeAll, describe, expect, it, vi } from "vitest";

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

let formatTyping: typeof import("./format").formatTyping;

beforeAll(async () => {
  stubStorage();
  ({ formatTyping } = await import("./format"));
});

describe("formatTyping", () => {
  it("formats zero, one, two, and three-plus typers in Korean", () => {
    expect(formatTyping([])).toBe("");
    expect(formatTyping(["김현진"])).toBe("김현진님이 입력 중입니다");
    expect(formatTyping(["김현진", "박지민"])).toBe("김현진, 박지민님이 입력 중입니다");
    expect(formatTyping(["김현진", "박지민", "이채원"])).toBe(
      "김현진, 박지민 외 1명이 입력 중입니다",
    );
    expect(formatTyping(["김현진", "박지민", "이채원", "최수아", "정우진"])).toBe(
      "김현진, 박지민 외 3명이 입력 중입니다",
    );
  });
});
