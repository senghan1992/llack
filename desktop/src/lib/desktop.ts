import { isTauri } from "@tauri-apps/api/core";
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from "@tauri-apps/plugin-notification";
import { useEffect, useState } from "react";
import { getSettings } from "./settings";

/** True when the app runs inside the Tauri shell rather than a plain browser. */
export async function inDesktop(): Promise<boolean> {
  try {
    return await isTauri();
  } catch {
    return false;
  }
}

/**
 * 셸 안에서 돌고 있는지, 컴포넌트에서 쓸 수 있게.
 * 브라우저에서 열면 OS 알림도, 폴더 고르기도, 파일 저장도 없다 —
 * 그렇다면 고른 것이 아무 일도 하지 않으므로 화면도 그렇게 말해야 한다.
 */
export function useInDesktop(): boolean {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    let alive = true;
    void inDesktop().then((value) => {
      if (alive) setDesktop(value);
    });
    return () => {
      alive = false;
    };
  }, []);
  return desktop;
}

/**
 * A native notification when the shell is present, a no-op in the browser.
 *
 * The settings decide what it says: switched off, nothing is sent at all;
 * with the preview off, only the title (who it is from) is shown.
 */
export async function notify(title: string, body: string): Promise<void> {
  const settings = getSettings();
  if (!settings.notifications) return;
  try {
    if (!(await inDesktop())) return;
    let granted = await isPermissionGranted();
    if (!granted) granted = (await requestPermission()) === "granted";
    if (!granted) return;
    const text = settings.notificationPreview === "preview" ? body : "";
    sendNotification({ title, body: text });
  } catch {
    /* notifications are a nicety, never a failure */
  }
}

/**
 * Pick a folder for downloads. Returns null when the shell is absent or the
 * person changed their mind.
 */
export async function pickFolder(title: string): Promise<string | null> {
  try {
    if (!(await inDesktop())) return null;
    const { open } = await import("@tauri-apps/plugin-dialog");
    const picked = await open({ directory: true, multiple: false, title });
    return typeof picked === "string" && picked ? picked : null;
  } catch {
    return null;
  }
}

/** A path as 16진수 — headers are latin-1, and a folder may hold Hangul. */
function toHex(value: string): string {
  return Array.from(new TextEncoder().encode(value))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Write bytes into a folder. The bytes travel as the raw request body, so a
 * photo does not become a JSON array of numbers on the way.
 */
export async function saveFile(dir: string, name: string, bytes: Uint8Array): Promise<string> {
  const { invoke } = await import("@tauri-apps/api/core");
  return await invoke<string>("save_file", bytes, {
    headers: {
      "X-Llack-Dir": toHex(dir),
      "X-Llack-Name": toHex(name),
    },
  });
}

/**
 * Fetch a file's bytes. The download route wants a bearer token, and the
 * token rides in the query string.
 */
export async function fetchFile(url: string): Promise<Uint8Array> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`파일을 받지 못했습니다 (HTTP ${response.status})`);
  return new Uint8Array(await response.arrayBuffer());
}
