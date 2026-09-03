/**
 * A video attachment that plays where it was shared.
 *
 * `<video src>` cannot carry a bearer token, so the shell mints a ten-minute
 * media URL for the file and the browser streams it with Range requests —
 * seeking works, and a 200 MB recording is not pulled into memory as a blob.
 * The chip underneath stays as the download affordance.
 */

import { useEffect, useState } from "react";

import { api } from "@/lib/ipc";
import type { FileRef } from "@/lib/types";

export function VideoAttachment({ file }: { file: FileRef }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api.mediaToken(file.id).then(
      (token) => {
        if (alive) setSrc(token.url);
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [file.id]);

  if (failed || !src) return null;
  return (
    <video
      className="attachment-video"
      src={src}
      controls
      preload="metadata"
      playsInline
      // A token expires after ten minutes; a stalled player asks for a new one.
      onError={() => {
        void api.mediaToken(file.id).then((token) => setSrc(token.url)).catch(() => setFailed(true));
      }}
    >
      {file.filename}
    </video>
  );
}
