/**
 * An image attachment, shown as the image instead of as a chip with an icon.
 *
 * The bytes come through the shell (`api.filePreview`) because the transcript
 * has no bearer token to put on an `<img src>` — the desktop keeps the session
 * in Rust, and that is a feature, not an obstacle to work around.
 *
 * Failure is silent by design: the chip underneath this component never goes
 * away, so a preview that cannot load (demo build, file too large, server
 * hiccup) degrades to exactly what the transcript showed before this feature
 * existed. An error banner for a decoration would be louder than the feature.
 */

import { useEffect, useState } from "react";

import { api } from "@/lib/ipc";
import type { FileRef } from "@/lib/types";

import { IconClose } from "./Icon";

/** Matches the shell-side cap; bigger files never even ask. */
const PREVIEW_BYTE_CAP = 10 * 1024 * 1024;

/**
 * One in-flight or resolved fetch per file id, shared across every render of
 * every row that shows it. A failed fetch is evicted so a transient error is
 * not remembered for the rest of the session.
 */
const previews = new Map<string, Promise<string>>();

function loadPreview(fileId: string, mime: string): Promise<string> {
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

export function AttachmentImage({ file }: { file: FileRef }) {
  const [src, setSrc] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    let alive = true;
    loadPreview(file.id, file.mime_type).then(
      (url) => {
        if (alive) setSrc(url);
      },
      () => {
        /* the chip below stays; nothing to say */
      },
    );
    return () => {
      alive = false;
    };
  }, [file.id, file.mime_type]);

  useEffect(() => {
    if (!zoomed) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setZoomed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  if (!src) return null;

  return (
    <>
      <button
        type="button"
        className="attachment-preview"
        onClick={() => setZoomed(true)}
        title={`${file.filename} 크게 보기`}
        aria-label={`${file.filename} 크게 보기`}
      >
        <img src={src} alt={file.filename} loading="lazy" />
      </button>

      {zoomed ? (
        <div
          className="lightbox"
          onClick={() => setZoomed(false)}
          role="presentation"
        >
          <figure
            role="dialog"
            aria-label={file.filename}
            onClick={(event) => event.stopPropagation()}
          >
            <img src={src} alt={file.filename} />
            <figcaption>
              <span>{file.filename}</span>
              <button
                type="button"
                onClick={() => {
                  void api.downloadFile(file.id, file.filename).catch(() => {
                    /* surfaced by the store's banner on the next action */
                  });
                }}
              >
                다운로드
              </button>
              <button
                type="button"
                onClick={() => setZoomed(false)}
                aria-label="닫기"
              >
                <IconClose size={13} />
              </button>
            </figcaption>
          </figure>
        </div>
      ) : null}
    </>
  );
}
