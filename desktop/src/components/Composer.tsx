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

import { open as openFileDialog } from "@tauri-apps/plugin-dialog";

import { api } from "@/lib/ipc";
import type { Id } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";

const TYPING_THROTTLE_MS = 2_500;

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

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastTypingSentAt = useRef(0);

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
    const match = /(?:^|\s)@([a-zA-Z0-9._-]*)$/.exec(upToCaret);
    setMentionQuery(match ? (match[1] ?? "") : null);
    setMentionIndex(0);
  };

  const applyMention = (handle: string) => {
    const element = textareaRef.current;
    if (!element) return;
    const caret = element.selectionStart;
    const before = body.slice(0, caret).replace(/@([a-zA-Z0-9._-]*)$/, `@${handle} `);
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
      const selected = await openFileDialog({ multiple: true });
      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      setUploading(true);
      for (const path of paths) {
        const file = await api.uploadFile(workspaceId, path);
        setAttachments((current) => [...current, { id: file.id, filename: file.filename }]);
      }
    } catch (error) {
      reportError(error, "파일을 업로드하지 못했습니다.");
    } finally {
      setUploading(false);
    }
  };

  const disabled = !channelId || channel?.is_archived;

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
              📎 {file.filename}
              <button
                type="button"
                onClick={() =>
                  setAttachments((current) =>
                    current.filter((candidate) => candidate.id !== file.id),
                  )
                }
                aria-label="첨부 제거"
              >
                ×
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
              ? "보관된 채널에는 메시지를 보낼 수 없습니다."
              : placeholder ??
                (channel?.name ? `#${channel.name} 에 메시지 보내기` : "메시지 보내기")
          }
          rows={Math.min(12, body.split("\n").length)}
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
            onClick={() => void attachFiles()}
            disabled={disabled || uploading}
            title="파일 첨부"
            aria-label="파일 첨부"
          >
            {uploading ? "…" : "📎"}
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
          <kbd>@</kbd> 멘션 · <kbd>```</kbd> 코드 블록
        </p>
      )}
    </div>
  );
}
