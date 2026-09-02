/**
 * A `fetch` for the Anthropic SDK that never sees the API key.
 *
 * The SDK accepts a custom `fetch`. This one does not open a socket: it hands
 * the request to Rust, which vets the URL, attaches the key from the OS
 * keychain, and streams the raw response bytes back over a Tauri channel. Rust
 * does not parse the response — it does not know what an `event: ` line is —
 * so the SDK keeps owning every piece of API drift while the credential stays
 * somewhere the webview cannot read it.
 *
 * What that actually buys, stated plainly: script running in this webview can
 * *use* the key while the app is open, but cannot read it, cannot persist it,
 * and cannot use it after the window closes. That is a much smaller prize than
 * a key in `localStorage`, which is stolen once and used forever.
 *
 * ## Why the body is base64
 *
 * A Tauri channel payload is JSON. A JSON array of integers costs several
 * characters per byte; base64 costs 1.33. The alternative is Tauri's raw-bytes
 * response path, which would be cheaper still and is a reasonable later change
 * — but it would put a byte-layout assumption in the one file whose job is to
 * have no opinion about the bytes.
 */

import { Channel, invoke } from "@tauri-apps/api/core";

/** What the Rust side sends over the channel. Mirrors `ProxyEvent`. */
type ProxyEvent =
  | { kind: "head"; status: number; headers: Array<[string, string]> }
  | { kind: "chunk"; b64: string }
  | { kind: "done" }
  | { kind: "failed"; message: string };

/** Base64 to bytes, without pulling in a dependency for eight lines. */
function decode(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function requestId(): string {
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Collect a `RequestInit` body into a string.
 *
 * The SDK sends JSON, so a string is the whole of the real case. The other
 * branches exist so an unexpected shape becomes a clear error here rather than
 * an empty body the provider rejects with a confusing 400.
 */
async function bodyToString(body: BodyInit | null | undefined): Promise<string | null> {
  if (body == null) return null;
  if (typeof body === "string") return body;
  if (body instanceof Uint8Array) return new TextDecoder().decode(body);
  if (body instanceof ArrayBuffer) return new TextDecoder().decode(body);
  if (body instanceof Blob) return body.text();
  throw new Error("에이전트 요청 본문 형식을 지원하지 않습니다.");
}

function headerPairs(init: RequestInit | undefined, input: RequestInfo | URL): Array<[string, string]> {
  const pairs: Array<[string, string]> = [];
  const push = (headers: HeadersInit) => {
    new Headers(headers).forEach((value, name) => pairs.push([name, value]));
  };
  if (input instanceof Request) push(input.headers);
  if (init?.headers) push(init.headers);
  return pairs;
}

export function createIpcFetch(): typeof fetch {
  const ipcFetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = input instanceof Request ? input.url : input.toString();
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const body = await bodyToString(
      init?.body ?? (input instanceof Request ? await input.clone().text() : null),
    );

    const id = requestId();
    const channel = new Channel<ProxyEvent>();

    /**
     * The response head, delivered through the promise rather than through a
     * closure variable. TypeScript cannot see that `channel.onmessage` assigned
     * a captured `let`, so reading it back always needs a cast — resolving with
     * the value keeps the type honest instead.
     */
    interface Head {
      status: number;
      headers: Headers;
    }
    let resolveHead: ((head: Head) => void) | null = null;
    let rejectHead: ((error: Error) => void) | null = null;
    let headSeen = false;
    const headArrived = new Promise<Head>((resolve, reject) => {
      resolveHead = resolve;
      rejectHead = reject;
    });

    let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
    // Chunks can arrive before the consumer starts pulling, so they queue here
    // until the stream exists. Without this, the first tokens of a fast
    // response are dropped.
    const queued: Uint8Array[] = [];
    let ended: "done" | { message: string } | null = null;

    const stream = new ReadableStream<Uint8Array>({
      start(streamController) {
        controller = streamController;
        for (const chunk of queued) streamController.enqueue(chunk);
        queued.length = 0;
        if (ended === "done") streamController.close();
        else if (ended) streamController.error(new Error(ended.message));
      },
      cancel() {
        // The consumer stopped reading. Tell Rust, so the upstream request is
        // dropped rather than billed to completion into nothing.
        void invoke("agent_provider_abort", { requestId: id }).catch(() => {});
      },
    });

    channel.onmessage = (event) => {
      switch (event.kind) {
        case "head":
          headSeen = true;
          resolveHead?.({
            status: event.status,
            headers: new Headers(event.headers),
          });
          break;
        case "chunk": {
          const bytes = decode(event.b64);
          if (controller) controller.enqueue(bytes);
          else queued.push(bytes);
          break;
        }
        case "done":
          ended = "done";
          controller?.close();
          break;
        case "failed":
          ended = { message: event.message };
          if (controller) controller.error(new Error(event.message));
          // A failure before the head means there is no Response to return.
          // After it, the stream already carries the error and rejecting the
          // (settled) head promise is a no-op.
          rejectHead?.(new Error(event.message));
          break;
      }
    };

    // Aborting from the SDK's own signal has to reach Rust too — otherwise
    // `runner.abort()` stops the reader and leaves the request running.
    init?.signal?.addEventListener("abort", () => {
      void invoke("agent_provider_abort", { requestId: id }).catch(() => {});
    });

    const sending = invoke<void>("agent_provider_request", {
      requestId: id,
      url,
      method,
      headers: headerPairs(init, input),
      body,
      channel,
    });

    /*
     * Waiting for the head needs both signals, not a race between them.
     *
     * A vetting refusal never sends a head at all, so awaiting `headArrived`
     * alone would hang forever on exactly the case the vetting exists for. But
     * `invoke` resolving is *not* proof that no head is coming: the command
     * returns only after the relay finishes, and its channel messages travel a
     * different IPC path, so on a very short response the resolve can land
     * before the head does. Racing them would then reject a request that
     * actually succeeded.
     *
     * So: a rejection rejects the head immediately, and a *resolve* only
     * rejects it after giving the channel a macrotask to deliver what is
     * already queued.
     */
    void sending
      .then(() => {
        if (headSeen) return;
        setTimeout(() => {
          if (!headSeen) {
            rejectHead?.(new Error("프로바이더 응답을 받지 못했습니다."));
          }
        }, 50);
      })
      .catch((error: unknown) => {
        rejectHead?.(
          error instanceof Error
            ? error
            : new Error("프로바이더 요청이 거부되었습니다."),
        );
      });

    const head = await headArrived;

    // 204 and 304 must not carry a body, and constructing one with a stream
    // throws.
    const bodyless = head.status === 204 || head.status === 304;
    return new Response(bodyless ? null : stream, {
      status: head.status,
      headers: head.headers,
    });
  };

  return ipcFetch as typeof fetch;
}
