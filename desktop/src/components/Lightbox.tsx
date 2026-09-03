/**
 * The image viewer.
 *
 * One instance for the whole app, driven by the store: any place that shows
 * images (a message, the file browser) hands over the set and an index, and
 * this flips through them. ← → move, Esc closes, a click on the image toggles
 * between "fit the screen" and "actual pixels" — the comparison a designer
 * needs when three comps differ by a few pixels of padding.
 */

import { useEffect, useState } from "react";

import { formatBytes } from "@/lib/format";
import { api } from "@/lib/ipc";
import { loadPreview } from "@/lib/preview";
import { useApp } from "@/store/app";

import { IconChevrons, IconClose } from "./Icon";

export function Lightbox() {
  const lightbox = useApp((state) => state.lightbox);
  const step = useApp((state) => state.stepLightbox);
  const close = useApp((state) => state.closeLightbox);
  const reportError = useApp((state) => state.reportError);

  const [src, setSrc] = useState<string | null>(null);
  const [actualSize, setActualSize] = useState(false);
  const [failed, setFailed] = useState(false);

  const file = lightbox ? lightbox.files[lightbox.index] : undefined;
  const count = lightbox?.files.length ?? 0;

  // Load the current image, and warm the neighbours so ← → feel instant.
  useEffect(() => {
    if (!lightbox || !file) return undefined;
    let alive = true;
    setFailed(false);
    setActualSize(false);
    loadPreview(file.id, file.mime_type).then(
      (url) => {
        if (alive) setSrc(url);
      },
      () => {
        if (alive) {
          setSrc(null);
          setFailed(true);
        }
      },
    );
    for (const delta of [1, -1]) {
      const neighbour = lightbox.files[(lightbox.index + delta + count) % count];
      if (neighbour && neighbour.id !== file.id) {
        void loadPreview(neighbour.id, neighbour.mime_type).catch(() => {});
      }
    }
    return () => {
      alive = false;
    };
  }, [lightbox, file, count]);

  useEffect(() => {
    if (!lightbox) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      else if (event.key === "ArrowRight" && count > 1) step(1);
      else if (event.key === "ArrowLeft" && count > 1) step(-1);
      else if (event.key === "+" || event.key === "=" || event.key === "0") {
        setActualSize((on) => !on);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, count, step, close]);

  if (!lightbox || !file) return null;

  return (
    <div className="lightbox" onClick={close} role="presentation">
      <figure
        role="dialog"
        aria-label={file.filename}
        className={actualSize ? "is-actual" : ""}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="lightbox-stage">
          {src ? (
            <img
              src={src}
              alt={file.filename}
              onClick={() => setActualSize((on) => !on)}
              title={actualSize ? "화면에 맞추기" : "원본 크기로 보기"}
            />
          ) : (
            <div className="lightbox-empty">
              {failed ? "미리보기를 불러오지 못했습니다. 내려받아 확인해주세요." : "불러오는 중…"}
            </div>
          )}
          {count > 1 ? (
            <>
              <button
                type="button"
                className="lightbox-nav is-prev"
                onClick={() => step(-1)}
                aria-label="이전 이미지"
                title="이전 (←)"
              >
                <IconChevrons size={16} />
              </button>
              <button
                type="button"
                className="lightbox-nav is-next"
                onClick={() => step(1)}
                aria-label="다음 이미지"
                title="다음 (→)"
              >
                <IconChevrons size={16} />
              </button>
            </>
          ) : null}
        </div>
        <figcaption>
          <span className="lightbox-name">
            {file.filename}
            <small>
              {formatBytes(file.size_bytes)}
              {count > 1 ? ` · ${lightbox.index + 1} / ${count}` : ""}
            </small>
          </span>
          <button type="button" onClick={() => setActualSize((on) => !on)}>
            {actualSize ? "화면에 맞추기" : "원본 크기"}
          </button>
          <button
            type="button"
            onClick={() => {
              void api
                .downloadFile(file.id, file.filename)
                .catch((error) => reportError(error, "파일을 내려받지 못했습니다."));
            }}
          >
            다운로드
          </button>
          <button type="button" onClick={close} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </figcaption>
      </figure>
    </div>
  );
}
