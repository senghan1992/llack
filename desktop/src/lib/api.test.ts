import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, NETWORK_CODE } from "./api";

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

beforeEach(() => {
  stubStorage();
  vi.restoreAllMocks();
});

describe("login", () => {
  it("says the server is not there instead of 'Failed to fetch'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    const failure = await api.login({ email: "a@b.co", password: "x" }).catch((err) => err);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.status).toBe(0);
    expect(failure.code).toBe(NETWORK_CODE);
    expect(failure.message).toContain("서버에 연결할 수 없습니다");
  });

  it("keeps the answer the server gave", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code: "unauthorized", message: "invalid email or password" } }),
          { status: 401, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    const failure = await api.login({ email: "a@b.co", password: "x" }).catch((err) => err);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.status).toBe(401);
    expect(failure.code).toBe("unauthorized");
  });

  it("hands the session back with both tokens", async () => {
    const session = {
      access_token: "access-token",
      refresh_token: "refresh-token",
      user: { id: "usr_1", email: "a@b.co", name: "김현진" },
      workspace: { id: "wsp_1", name: "한빛", slug: "hanbit" },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(session), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const result = await api.login({ email: "a@b.co", password: "x" });

    expect(result.access_token).toBe("access-token");
    expect(result.refresh_token).toBe("refresh-token");
    expect(result.workspace.id).toBe("wsp_1");
  });
});
