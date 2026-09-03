/**
 * 파일 — every file I may know exists in this workspace, in one place.
 *
 * "그 파일 어디 있지?" used to need the filename and ⌘K. This lists files
 * newest first with where each one was shared, filters by kind, searches by
 * name, previews images in the shared lightbox and jumps to the message a
 * file came from. Visibility is the server's rule (mine, or shared into a
 * channel I am in), so a private channel's files stay private here too.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatBytes, formatRelative } from "@/lib/format";
import { api } from "@/lib/ipc";
import { isPreviewableImage, loadPreview } from "@/lib/preview";
import type { FileRef, WorkspaceFile } from "@/lib/types";
import { useApp } from "@/store/app";

import { IconClose, IconFile, IconImage, IconSearch } from "./Icon";

type Kind = "all" | "image" | "document" | "mine";
const PAGE = 50;
const DEBOUNCE_MS = 250;

const FILTERS: Array<{ id: Kind; label: string }> = [
  { id: "all", label: "전체" },
  { id: "image", label: "이미지" },
  { id: "document", label: "문서" },
  { id: "mine", label: "내 파일" },
];

export function FileBrowser() {
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const channels = useApp((state) => state.channels);
  const me = useApp((state) => state.me);
  const setMainView = useApp((state) => state.setMainView);
  const revealMessage = useApp((state) => state.revealMessage);
  const openLightbox = useApp((state) => state.openLightbox);
  const reportError = useApp((state) => state.reportError);

  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind>("all");
  const [files, setFiles] = useState<WorkspaceFile[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const params = useCallback(
    (cursor: string | null) => ({
      q: query.trim() || undefined,
      kind: kind === "image" || kind === "document" ? kind : null,
      mine: kind === "mine",
      cursor,
      limit: PAGE,
    }),
    [query, kind],
  );

  // First page, debounced on the query so typing does not hammer the server.
  useEffect(() => {
    if (!workspaceId) return undefined;
    let alive = true;
    const timer = setTimeout(() => {
      api
        .listWorkspaceFiles(workspaceId, params(null))
        .then((rows) => {
          if (!alive) return;
          setFiles(rows);
          setHasMore(rows.length >= PAGE);
        })
        .catch((error) => {
          if (!alive) return;
          setFiles([]);
          reportError(error, "파일 목록을 불러오지 못했습니다.");
        });
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [workspaceId, params, reportError]);

  const loadMore = async () => {
    if (!workspaceId || !files || loadingMore) return;
    const last = files[files.length - 1];
    if (!last) return;
    setLoadingMore(true);
    try {
      const rows = await api.listWorkspaceFiles(workspaceId, params(last.id));
      setFiles((current) => [...(current ?? []), ...rows]);
      setHasMore(rows.length >= PAGE);
    } catch (error) {
      reportError(error, "파일 목록을 더 불러오지 못했습니다.");
    } finally {
      setLoadingMore(false);
    }
  };

  const images = useMemo(
    () => (files ?? []).filter((file) => isPreviewableImage(file)),
    [files],
  );

  const whereLabel = (file: WorkspaceFile): string | null => {
    const shared = file.shared_in;
    if (!shared) return null;
    if (shared.channel_kind === "dm" || shared.channel_kind === "group_dm") {
      const local = channels.find((channel) => channel.id === shared.channel_id);
      const names = local?.peers.map((peer) => peer.display_name).join(", ");
      return names ? `${names} 와의 대화` : "다이렉트 메시지";
    }
    return `#${shared.channel_name ?? "채널"}`;
  };

  const open = (file: WorkspaceFile) => {
    if (isPreviewableImage(file)) {
      const index = images.findIndex((candidate) => candidate.id === file.id);
      openLightbox(images as FileRef[], Math.max(0, index));
      return;
    }
    void api
      .downloadFile(file.id, file.filename)
      .catch((error) => reportError(error, "파일을 내려받지 못했습니다."));
  };

  return (
    <div className="file-browser">
      <header className="channel-header">
        <div className="channel-title">
          <h1>파일</h1>
          <span className="channel-meta">
            {files === null ? "불러오는 중…" : `${files.length}${hasMore ? "+" : ""}개`}
          </span>
        </div>
        <div className="channel-header-right">
          <button
            type="button"
            className="header-button"
            onClick={() => setMainView("channel")}
            title="닫고 대화로 돌아가기"
            aria-label="닫기"
          >
            <IconClose size={13} />
          </button>
        </div>
      </header>

      <div className="file-toolbar">
        <div className="share-field file-search">
          <IconSearch size={14} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="파일 이름으로 찾기"
            aria-label="파일 찾기"
          />
        </div>
        <div className="file-filters" role="tablist" aria-label="파일 종류">
          {FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              role="tab"
              aria-selected={kind === filter.id}
              className={kind === filter.id ? "is-active" : ""}
              onClick={() => setKind(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      <div className="file-list-scroll">
        {files === null ? (
          <p className="file-empty">불러오는 중…</p>
        ) : files.length === 0 ? (
          <div className="file-empty">
            <strong>
              {query.trim()
                ? "찾는 파일이 없습니다."
                : kind === "mine"
                  ? "아직 올린 파일이 없습니다."
                  : "아직 볼 수 있는 파일이 없습니다."}
            </strong>
            <p>
              채널이나 대화에 올린 파일이 여기에 모입니다. 내가 속한 대화에 공유된
              파일만 보입니다.
            </p>
          </div>
        ) : (
          <ul className="file-list">
            {files.map((file) => {
              const where = whereLabel(file);
              const image = isPreviewableImage(file);
              return (
                <li key={file.id} className="file-row">
                  <button
                    type="button"
                    className="file-thumb"
                    onClick={() => open(file)}
                    title={image ? "크게 보기" : "내려받기"}
                    aria-label={image ? `${file.filename} 크게 보기` : `${file.filename} 내려받기`}
                  >
                    {image ? (
                      <Thumb file={file} />
                    ) : (
                      <span className="file-thumb-icon">
                        {file.mime_type.startsWith("image/") ? (
                          <IconImage size={18} />
                        ) : (
                          <IconFile size={18} />
                        )}
                        <small>{extensionOf(file.filename)}</small>
                      </span>
                    )}
                  </button>
                  <div className="file-info">
                    <button type="button" className="file-name" onClick={() => open(file)}>
                      {file.filename}
                    </button>
                    <span className="file-meta">
                      {file.scan_status === "infected" ? (
                        <span className="attachment-scan is-infected">차단됨 · </span>
                      ) : file.scan_status === "pending" ? (
                        <span className="attachment-scan is-pending">검사 중 · </span>
                      ) : null}
                      {formatBytes(file.size_bytes)}
                      {file.uploader
                        ? ` · ${file.uploader.id === me?.id ? "나" : file.uploader.display_name}`
                        : ""}
                      {file.created_at ? ` · ${formatRelative(file.created_at)}` : ""}
                    </span>
                    {where && file.shared_in ? (
                      <button
                        type="button"
                        className="file-where"
                        onClick={() =>
                          void revealMessage(file.shared_in!.channel_id, file.shared_in!.message_id)
                        }
                        title="공유된 메시지로 이동"
                      >
                        {where} 에서 공유됨 →
                      </button>
                    ) : (
                      <span className="file-where is-muted">아직 메시지에 첨부되지 않음</span>
                    )}
                  </div>
                  <div className="file-actions">
                    <button
                      type="button"
                      className="member-action"
                      onClick={() =>
                        void api
                          .downloadFile(file.id, file.filename)
                          .catch((error) => reportError(error, "파일을 내려받지 못했습니다."))
                      }
                    >
                      내려받기
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {hasMore ? (
          <button
            type="button"
            className="file-more"
            onClick={() => void loadMore()}
            disabled={loadingMore}
          >
            {loadingMore ? "불러오는 중…" : "더 보기"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Thumb({ file }: { file: FileRef }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    // The server-made 320px thumbnail when it exists (cheap), the full image
    // otherwise (older uploads, or a server without Pillow).
    const source = file.thumbnail_url
      ? api.fileThumbnail(file.id).catch(() => loadPreview(file.id, file.mime_type))
      : loadPreview(file.id, file.mime_type);
    source.then(
      (url) => {
        if (alive) setSrc(url);
      },
      () => {},
    );
    return () => {
      alive = false;
    };
  }, [file.id, file.mime_type]);
  if (!src) {
    return (
      <span className="file-thumb-icon">
        <IconImage size={18} />
      </span>
    );
  }
  return <img src={src} alt="" loading="lazy" />;
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  if (dot <= 0 || dot === filename.length - 1) return "";
  return filename.slice(dot + 1).toUpperCase().slice(0, 5);
}
