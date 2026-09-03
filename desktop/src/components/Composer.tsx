/**
 * The message composer.
 *
 * Behaviours that matter in daily use:
 * - Enter sends, Shift+Enter newlines (the convention people expect).
 * - `@` opens an inline mention picker filtered as you type.
 * - Typing notifications are throttled rather than sent per keystroke.
 * - Drafts survive switching channels, because losing a half-written message
 *   is a genuinely infuriating bug.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { asCommandError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { api, isDesktopShell, shell } from "@/lib/ipc";
import type { Id } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { IconClose, IconPaperclip, IconTemplate } from "./Icon";

const TYPING_THROTTLE_MS = 2_500;

/** Say *why* an upload failed. "파일을 업로드하지 못했습니다" for a 110 MB file
 *  hid the one fact the person needed — the limit. */
function uploadFailureMessage(error: unknown): string {
  const parsed = asCommandError(error);
  if (parsed.code === "payload_too_large") {
    const max = Number(
      (parsed.details as { max_upload_bytes?: number } | null | undefined)?.max_upload_bytes,
    );
    return max > 0
      ? `파일이 너무 큽니다. 한 파일은 ${formatBytes(max)} 까지 올릴 수 있습니다.`
      : "파일이 너무 큽니다. 워크스페이스 업로드 한도를 넘었습니다.";
  }
  if (parsed.code === "network_error" || parsed.code === "offline") {
    return "연결이 끊겨 업로드하지 못했습니다. 연결되면 다시 시도해주세요.";
  }
  return "파일을 업로드하지 못했습니다.";
}

/**
 * Message templates: the shares people make all day, pre-shaped.
 *
 * Deliberately just text. A schedule or a task shared here is a message —
 * searchable, quotable, thread-able — not a record in a calendar this product
 * does not have. The template's value is that nobody has to re-invent the
 * fields, and the reader always finds 일시/담당/기한 in the same place.
 */
function shareTemplates(): Array<{ id: string; label: string; hint: string; body: string }> {
  let tomorrow = "";
  try {
    tomorrow = new Intl.DateTimeFormat("ko-KR", {
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(new Date(Date.now() + 24 * 60 * 60 * 1000));
  } catch {
    // An exotic runtime without ko-KR data: the field just starts empty.
  }
  return [
    {
      id: "schedule",
      label: "일정 공유",
      hint: "일시·장소·참석",
      body: `**[일정]** 제목\n- 일시: ${tomorrow} 14:00–15:00\n- 장소: \n- 참석: @\n- 안건: `,
    },
    {
      id: "task",
      label: "일 공유",
      hint: "담당·기한",
      body: "**[할 일]** 제목\n- 담당: @\n- 기한: \n- 내용: ",
    },
    {
      id: "decision",
      label: "결정 공유",
      hint: "결론·근거·다음 단계",
      body: "**[결정]** 제목\n- 결론: \n- 근거: \n- 다음 단계: ",
    },
  ];
}

interface ComposerProps {
  /** Set when composing inside a thread. */
  parentId?: Id;
  placeholder?: string;
}

export function Composer({ parentId, placeholder }: ComposerProps) {
  const channelId = useApp((state) => state.activeChannelId);
  const channel = useApp((state) =>
    state.channels.find((candidate) => candidate.id === state.activeChannelId),
  );
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const people = useApp((state) => state.people);
  const presence = useApp((state) => state.presence);
  const send = useApp((state) => state.send);
  const notifyTyping = useApp((state) => state.notifyTyping);
  const reportError = useApp((state) => state.reportError);

  // Drafts are keyed by channel (and thread), so switching away and back keeps
  // whatever was typed.
  const draftsRef = useRef(new Map<string, string>());
  const draftKey = `${channelId ?? ""}:${parentId ?? ""}`;

  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<Array<{ id: Id; filename: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const [alsoSend, setAlsoSend] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [dropping, setDropping] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastTypingSentAt = useRef(0);

  const disabled = !channelId || Boolean(channel?.is_archived);

  // Swap the draft in and out when the target changes.
  useEffect(() => {
    setBody(draftsRef.current.get(draftKey) ?? "");
    setAttachments([]);
    setMentionQuery(null);
  }, [draftKey]);

  useEffect(() => {
    draftsRef.current.set(draftKey, body);
  }, [body, draftKey]);

  const mentionCandidates = useMemo(() => {
    if (mentionQuery === null) return [];
    const needle = mentionQuery.toLowerCase();
    return [...people.values()]
      .filter(
        (person) =>
          person.handle.toLowerCase().includes(needle) ||
          person.display_name.toLowerCase().includes(needle),
      )
      .slice(0, 6);
  }, [mentionQuery, people]);

  const maybeNotifyTyping = useCallback(() => {
    if (!channelId) return;
    const now = Date.now();
    if (now - lastTypingSentAt.current < TYPING_THROTTLE_MS) return;
    lastTypingSentAt.current = now;
    notifyTyping(channelId, parentId);
  }, [channelId, notifyTyping, parentId]);

  /** Track a trailing `@word` at the caret to drive the mention picker. */
  const updateMentionQuery = (value: string, caret: number) => {
    const upToCaret = value.slice(0, caret);
    // Anything up to whitespace, so `@김앨` keeps the picker open — the
    // ASCII-only pattern closed it on the first Hangul syllable, and people
    // shipped `@김앨리스` as plain text believing they had mentioned someone.
    const match = /(?:^|\s)@([^\s@]*)$/.exec(upToCaret);
    setMentionQuery(match ? (match[1] ?? "") : null);
    setMentionIndex(0);
  };

  const applyMention = (handle: string) => {
    const element = textareaRef.current;
    if (!element) return;
    const caret = element.selectionStart;
    const before = body.slice(0, caret).replace(/@([^\s@]*)$/, `@${handle} `);
    const next = before + body.slice(caret);
    setBody(next);
    setMentionQuery(null);
    requestAnimationFrame(() => {
      element.focus();
      element.setSelectionRange(before.length, before.length);
    });
  };

  const submit = async () => {
    const text = body.trim();
    if (!text && attachments.length === 0) return;
    setBody("");
    draftsRef.current.delete(draftKey);
    const fileIds = attachments.map((file) => file.id);
    setAttachments([]);
    setMentionQuery(null);

    await send(text, {
      ...(parentId ? { parentId } : {}),
      alsoSendToChannel: Boolean(parentId) && alsoSend,
      fileIds,
    });
    setAlsoSend(false);
  };

  const attachFiles = async () => {
    if (!workspaceId) return;
    try {
      setUploading(true);
      // The picker differs per host (native dialog vs. file input); the upload
      // that follows does not.
      await shell.pickAndUploadFiles(workspaceId, (file) => {
        setAttachments((current) => [...current, { id: file.id, filename: file.filename }]);
      });
    } catch (error) {
      reportError(error, uploadFailureMessage(error));
    } finally {
      setUploading(false);
    }
  };

  /*
   * Files dragged onto the window attach here.
   *
   * Only the channel composer subscribes — a thread composer subscribing too
   * would mean one drop landing in two places. The sources arrive host-shaped
   * (paths from the shell, `File`s from a tab) and `uploadFile` accepts each
   * host's own shape, so they pass straight through.
   */
  useEffect(() => {
    if (parentId || !workspaceId || disabled) return undefined;

    const unlistenPromise = shell.onFileDrop({
      onOver: () => setDropping(true),
      onLeave: () => setDropping(false),
      onDrop: (sources) => {
        void (async () => {
          setUploading(true);
          try {
            for (const source of sources) {
              const file = await api.uploadFile(workspaceId, source);
              setAttachments((current) => [
                ...current,
                { id: file.id, filename: file.filename },
              ]);
            }
          } catch (error) {
            reportError(error, uploadFailureMessage(error));
          } finally {
            setUploading(false);
          }
        })();
      },
    });

    return () => {
      void unlistenPromise.then((unlisten) => unlisten()).catch(() => {});
    };
  }, [parentId, workspaceId, disabled, reportError]);

  // The template menu closes like every other popover: outside click or Esc.
  useEffect(() => {
    if (!templatesOpen) return undefined;
    const onClick = () => setTemplatesOpen(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setTemplatesOpen(false);
    };
    window.addEventListener("click", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [templatesOpen]);

  /**
   * Screenshots arrive by ⌘V. A pasted image is a file on the clipboard; it
   * attaches like a dropped one. Text pastes fall through untouched. The
   * desktop shell uploads by path and has no path for clipboard bytes, so it
   * keeps the browser default there.
   */
  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!workspaceId || disabled || isDesktopShell()) return;
    const files = Array.from(event.clipboardData?.files ?? []).filter((file) =>
      file.type.startsWith("image/"),
    );
    if (files.length === 0) return;
    event.preventDefault();
    void (async () => {
      setUploading(true);
      try {
        for (const [index, file] of files.entries()) {
          const extension = file.type.split("/")[1] ?? "png";
          const named =
            file.name && file.name !== "image.png"
              ? file
              : new File([file], `스크린샷-${stamp()}${index > 0 ? `-${index + 1}` : ""}.${extension}`, {
                  type: file.type,
                });
          const uploaded = await api.uploadFile(workspaceId, named);
          setAttachments((current) => [
            ...current,
            { id: uploaded.id, filename: uploaded.filename },
          ]);
        }
      } catch (error) {
        reportError(error, uploadFailureMessage(error));
      } finally {
        setUploading(false);
      }
    })();
  };

  /** Insert a template at the caret, on its own line, and put the caret after it. */
  const insertTemplate = (text: string) => {
    const element = textareaRef.current;
    const caret = element?.selectionStart ?? body.length;
    const before = body.slice(0, caret);
    const glue = before && !before.endsWith("\n") ? "\n" : "";
    const inserted = before + glue + text;
    setBody(inserted + body.slice(caret));
    setTemplatesOpen(false);
    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(inserted.length, inserted.length);
    });
  };

  return (
    <div className="composer">
      {mentionQuery !== null && mentionCandidates.length > 0 ? (
        <ul className="mention-picker" role="listbox">
          {mentionCandidates.map((person, index) => (
            <li key={person.id}>
              <button
                type="button"
                className={index === mentionIndex ? "is-active" : ""}
                onMouseEnter={() => setMentionIndex(index)}
                onClick={() => applyMention(person.handle)}
                role="option"
                aria-selected={index === mentionIndex}
              >
                <Avatar
                  id={person.id}
                  name={person.display_name}
                  avatarUrl={person.avatar_url}
                  size={22}
                  presence={presence.get(person.id)}
                  isBot={person.is_bot}
                />
                <strong>{person.display_name}</strong>
                <span>@{person.handle}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {attachments.length > 0 ? (
        <ul className="composer-attachments">
          {attachments.map((file) => (
            <li key={file.id}>
              <IconPaperclip size={12} />
              {file.filename}
              <button
                type="button"
                onClick={() => {
                  setAttachments((current) =>
                    current.filter((candidate) => candidate.id !== file.id),
                  );
                  // Removed before sending: the upload is an orphan. Drop it
                  // so it does not haunt ⌘K's file results.
                  void api.deleteFile(file.id).catch(() => {});
                }}
                aria-label="첨부 제거"
              >
                <IconClose size={11} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {!parentId && dropping && !disabled ? (
        <div className="composer-drop" aria-hidden="true">
          파일을 놓으면 첨부됩니다
        </div>
      ) : null}

      {templatesOpen ? (
        <ul
          className="composer-templates"
          role="menu"
          aria-label="공유 서식"
          onClick={(event) => event.stopPropagation()}
        >
          {shareTemplates().map((template) => (
            <li key={template.id}>
              <button
                type="button"
                role="menuitem"
                onClick={() => insertTemplate(template.body)}
              >
                <strong>{template.label}</strong>
                <span>{template.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className={`composer-box ${disabled ? "is-disabled" : ""}`}>
        <textarea
          ref={textareaRef}
          value={body}
          disabled={disabled}
          placeholder={
            disabled
              ? channel?.is_archived
                ? "보관된 채널에는 메시지를 보낼 수 없습니다."
                : "왼쪽에서 채널을 고르거나 ⌘K 로 대화를 찾아보세요."
              : placeholder ?? composerPlaceholder(channel)
          }
          rows={Math.min(12, body.split("\n").length)}
          onPaste={onPaste}
          onChange={(event) => {
            setBody(event.target.value);
            updateMentionQuery(event.target.value, event.target.selectionStart);
            maybeNotifyTyping();
          }}
          onKeyDown={(event) => {
            // Mention picker navigation takes precedence over sending.
            if (mentionQuery !== null && mentionCandidates.length > 0) {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setMentionIndex((index) => (index + 1) % mentionCandidates.length);
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setMentionIndex(
                  (index) =>
                    (index - 1 + mentionCandidates.length) % mentionCandidates.length,
                );
                return;
              }
              if (event.key === "Enter" || event.key === "Tab") {
                const chosen = mentionCandidates[mentionIndex];
                if (chosen) {
                  event.preventDefault();
                  applyMention(chosen.handle);
                  return;
                }
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setMentionQuery(null);
                return;
              }
            }

            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
        />

        <div className="composer-actions">
          <button
            type="button"
            onClick={(event) => {
              // The window listener that closes the menu must not see this click.
              event.stopPropagation();
              setTemplatesOpen((open) => !open);
            }}
            disabled={disabled}
            title="공유 서식 (일정·할 일·결정)"
            aria-label="공유 서식"
            aria-expanded={templatesOpen}
          >
            <IconTemplate size={15} />
          </button>
          <button
            type="button"
            onClick={() => void attachFiles()}
            disabled={disabled || uploading}
            title="파일 첨부"
            aria-label="파일 첨부"
          >
            {uploading ? (
              <span className="composer-uploading" aria-label="업로드 중" />
            ) : (
              <IconPaperclip size={15} />
            )}
          </button>
          <button
            type="button"
            className="composer-send"
            onClick={() => void submit()}
            disabled={disabled || (!body.trim() && attachments.length === 0)}
          >
            보내기
          </button>
        </div>
      </div>

      {parentId ? (
        <label className="composer-also">
          <input
            type="checkbox"
            checked={alsoSend}
            onChange={(event) => setAlsoSend(event.target.checked)}
          />
          채널에도 보내기
        </label>
      ) : (
        <p className="composer-hint">
          <kbd>Enter</kbd> 전송 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 줄바꿈 ·{" "}
          <kbd>@이름</kbd> 멘션 · <kbd>⌘V</kbd> 이미지 붙여넣기 · <kbd>```</kbd> 코드
        </p>
      )}
    </div>
  );
}

/** `#개발 에 메시지 보내기` for rooms; DMs are people, not hashtags. */
function composerPlaceholder(
  channel: { kind: string; name?: string | null; peers: Array<{ display_name: string }> } | undefined,
): string {
  if (!channel) return "메시지 보내기";
  if (channel.kind === "dm" || channel.kind === "group_dm") {
    const names = channel.peers.map((peer) => peer.display_name).join(", ");
    return names ? `${names} 에게 메시지 보내기` : "나에게 메모 남기기";
  }
  return channel.name ? `#${channel.name} 에 메시지 보내기` : "메시지 보내기";
}

function stamp(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(
    now.getHours(),
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}
