import { API_BASE } from "./api";
import type { WsEvent } from "./types";

/** A reconnecting WebSocket client. Backoff is capped, and a rejected token never retries. */
export class Realtime {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private token: string | null = null;
  private closed = false;

  onEvent: (event: WsEvent) => void = () => {};
  onOpen: () => void = () => {};
  onClose: () => void = () => {};

  get connected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  connect(token: string): void {
    this.token = token;
    this.closed = false;
    this.open();
  }

  private open(): void {
    if (!this.token || this.closed) return;
    const url = `${API_BASE.replace(/^http/, "ws")}/api/v1/ws?token=${encodeURIComponent(this.token)}`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.attempt = 0;
      this.onOpen();
    };

    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data as string) as WsEvent;
        this.onEvent(parsed);
      } catch {
        /* a frame that is not our protocol is not worth crashing over */
      }
    };

    socket.onclose = (event) => {
      this.socket = null;
      this.onClose();
      if (this.closed || event.code === 4401) return;
      const delay = Math.min(800 * 2 ** this.attempt, 10000);
      this.attempt += 1;
      this.timer = setTimeout(() => this.open(), delay);
    };

    socket.onerror = () => socket.close();
  }

  send(payload: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  close(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.socket?.close();
    this.socket = null;
  }
}
