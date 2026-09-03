/**
 * An image attachment, shown as the image instead of as a chip with an icon.
 *
 * Clicking opens the shared lightbox over *every* image on the message, so
 * three design comps can be flipped through with ← → instead of closing and
 * re-opening. Failure is silent by design: the chip underneath this component
 * never goes away, so a preview that cannot load degrades to exactly what the
 * transcript showed before this feature existed.
 */

import { useEffect, useState } from "react";

import { loadPreview } from "@/lib/preview";
import type { FileRef } from "@/lib/types";
import { useApp } from "@/store/app";

export { isPreviewableImage } from "@/lib/preview";

export function AttachmentImage({
  file,
  gallery,
}: {
  file: FileRef;
  /** The message's previewable images, in order; defaults to just this one. */
  gallery?: FileRef[];
}) {
  const openLightbox = useApp((state) => state.openLightbox);
  const [src, setSrc] = useState<string | null>(null);

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

  if (!src) return null;

  const set = gallery && gallery.length > 0 ? gallery : [file];
  const index = Math.max(0, set.findIndex((candidate) => candidate.id === file.id));

  return (
    <button
      type="button"
      className="attachment-preview"
      onClick={() => openLightbox(set, index)}
      title={`${file.filename} 크게 보기`}
      aria-label={`${file.filename} 크게 보기`}
    >
      <img src={src} alt={file.filename} loading="lazy" />
    </button>
  );
}
