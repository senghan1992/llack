/**
 * The host bridge.
 *
 * A panel runs in a sandboxed iframe with no access to the host's storage or
 * the signed-in user's token. Everything it needs arrives over `postMessage`:
 * a short-lived bridge token, the granted scopes, and the channel context.
 *
 * Requests are correlated by id and time out, so a host that never answers
 * produces a rejected promise rather than a panel stuck on a spinner.
 */

import { LlackError, type Session } from "./types.js";

const REQUEST_TIMEOUT_MS = 10_000;

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export class HostBridge {
  private readonly pending = new Map<string, PendingRequest>();
  private counter = 0;
  private listening = false;

  private onMessage = (event: MessageEvent) => {
    const data = event.data as
      | { id?: string; type?: string; payload?: unknown }
      | undefined;
    if (!data || data.type !== "llack:response" || typeof data.id !== "string") {
      return;
    }
    const request = this.pending.get(data.id);
    if (!request) return;
    this.pending.delete(data.id);
    clearTimeout(request.timer);
    request.resolve(data.payload);
  };

  private ensureListening(): void {
    if (this.listening) return;
    if (typeof window === "undefined") {
      throw new LlackError(
        "no_window",
        "Llack SDK는 브라우저(패널) 환경에서만 동작합니다.",
      );
    }
    window.addEventListener("message", this.onMessage);
    this.listening = true;
  }

  /** Send a request to the host and await its reply. */
  request<T>(type: string, payload: Record<string, unknown> = {}): Promise<T> {
    this.ensureListening();

    if (!window.parent || window.parent === window) {
      return Promise.reject(
        new LlackError(
          "not_in_panel",
          "이 페이지가 Llack 패널 안에서 열리지 않았습니다.",
        ),
      );
    }

    this.counter += 1;
    const id = `req-${Date.now()}-${this.counter}`;

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(
          new LlackError(
            "host_timeout",
            `호스트가 ${REQUEST_TIMEOUT_MS}ms 안에 응답하지 않았습니다: ${type}`,
          ),
        );
      }, REQUEST_TIMEOUT_MS);

      this.pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
      });

      // The host validates our origin; we address it as "*" because a
      // sandboxed frame without allow-same-origin has an opaque origin and
      // cannot know the host's. No secret is ever sent in this direction.
      window.parent.postMessage({ id, type, ...payload }, "*");
    });
  }

  /** Fire-and-forget notification to the host. */
  notify(type: string, payload: Record<string, unknown> = {}): void {
    this.ensureListening();
    if (!window.parent || window.parent === window) return;
    this.counter += 1;
    window.parent.postMessage(
      { id: `evt-${this.counter}`, type, ...payload },
      "*",
    );
  }

  getSession(): Promise<Session> {
    return this.request<Session>("llack:get-session");
  }

  dispose(): void {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new LlackError("disposed", "SDK가 해제되었습니다."));
    }
    this.pending.clear();
    if (this.listening && typeof window !== "undefined") {
      window.removeEventListener("message", this.onMessage);
      this.listening = false;
    }
  }
}
