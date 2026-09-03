/**
 * Image bytes for inline rendering, shared by the transcript, the file
 * browser and the lightbox.
 *
 * The bytes come through the shell (`api.filePreview`) because an `<img src>`
 * cannot carry the bearer token — the desktop keeps the session in Rust, and
 * that is a feature. One in-flight or resolved fetch per file id, shared by
 * every component that shows it; a failed fetch is evicted so a transient
 * error is not remembered for the rest of the session.
 */

import { api } from "@/lib/ipc";
import type { FileRef } from "@/lib/types";

/** Matches the shell-side cap; bigger files never even ask. */
export const PREVIEW_BYTE_CAP = 10 * 1024 * 1024;

const previews = new Map<string, Promise<string>>();

export function loadPreview(fileId: string, mime: string): Promise<string> {
  let pending = previews.get(fileId);
  if (!pending) {
    pending = api.filePreview(fileId, mime);
    previews.set(fileId, pending);
    pending.catch(() => previews.delete(fileId));
  }
  return pending;
}

export function isPreviewableImage(file: FileRef): boolean {
  return file.mime_type.startsWith("image/") && file.size_bytes <= PREVIEW_BYTE_CAP;
}
