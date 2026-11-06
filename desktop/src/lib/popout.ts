import { inDesktop } from "./desktop";
import type { Channel } from "./types";

/**
 * A room opened on its own, in a window of its own — the way a chat client
 * lets you pull one conversation out of the workspace and keep it beside it.
 *
 * The window is the same app; what makes it a room window is its *label*:
 * `room-<id>`. The label is all the app can read about itself without being
 * told, so the room id is written next to it (in this origin's storage) and
 * read back when the window boots.
 */

const ROOM_PREFIX = "room-";
const MAP_PREFIX = "llack.room.";

/** The label a room's own window carries. */
export function roomLabel(channelId: string): string {
  return `${ROOM_PREFIX}${channelId.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

function mapKey(label: string): string {
  return `${MAP_PREFIX}${label}`;
}

/** The page a room window opens. The dev server is a URL; the app is a file. */
function roomWindowUrl(): string {
  const here = window.location;
  if (here.protocol === "http:" || here.protocol === "https:") {
    return here.origin + here.pathname;
  }
  return "index.html";
}

/** The name a room's window wears in the title bar. */
export function roomTitle(channel: Channel): string {
  if (channel.kind === "dm") return channel.dm_user?.name ?? channel.name;
  return `#${channel.name}`;
}

/**
 * Open a room in a window of its own.
 *
 * A room that is already open in its own window is brought forward instead of
 * opened twice — the same conversation should not live in two windows.
 */
export async function openRoomWindow(channel: Channel): Promise<void> {
  const label = roomLabel(channel.id);
  const title = roomTitle(channel);

  if (!(await inDesktop())) {
    // A browser has its own windows: a popup is the same idea, smaller.
    const url = `${window.location.pathname}?room=${encodeURIComponent(channel.id)}`;
    window.open(url, label, "width=560,height=760");
    return;
  }

  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const existing = await WebviewWindow.getByLabel(label);
  if (existing) {
    await existing.setFocus();
    return;
  }

  window.localStorage.setItem(mapKey(label), channel.id);
  await new Promise<void>((resolve, reject) => {
    const win = new WebviewWindow(label, {
      url: roomWindowUrl(),
      title,
      width: 560,
      height: 760,
      minWidth: 380,
      minHeight: 460,
      center: true,
      resizable: true,
    });
    win.once("tauri://created", () => resolve());
    win.once("tauri://error", (event) => reject(new Error(String(event.payload))));
  });
}

/**
 * The room this window is for, or null when this is the workspace window.
 */
export async function currentRoomId(): Promise<string | null> {
  if (!(await inDesktop())) {
    return new URLSearchParams(window.location.search).get("room");
  }
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const label = getCurrentWindow().label;
  if (!label.startsWith(ROOM_PREFIX)) return null;
  return window.localStorage.getItem(mapKey(label));
}

/** Put the room's name on the window's title bar. */
export async function setRoomTitle(title: string): Promise<void> {
  if (!(await inDesktop())) {
    document.title = title;
    return;
  }
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTitle(title);
  } catch {
    /* a title bar that keeps its old name is not worth a failure */
  }
}
