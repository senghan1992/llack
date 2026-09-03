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

import { searchEmoji, replaceShortcodes, type EmojiEntry } from "@/lib/emoji";
import { asCommandError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { api, isDesktopShell, shell } from "@/lib/ipc";
import type { Id } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { EmojiPicker } from "./EmojiPicker";
import { IconClose, IconPaperclip, IconSmile, IconTemplate } from "./Icon";

/** A row in the mention picker: a person, or `@channel`/`@here`. */
interface MentionCandidate {
  id: string;
  handle: string;
  display_name: string;
  avatar_url?: string | null;
  is_bot?: boolean;
  broadcast?: boolean;
  hint?: string;
}

/** An upload in flight: the bar the file used to lack. */
interface UploadProgress {
  key: string;
  filename: string;
  sent: number;
  total: number;
}

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
  const [uploads, setUploads] = useState<UploadProgress[]>([]);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [emojiQuery, setEmojiQuery] = useState<string | null>(null);
  const [emojiIndex, setEmojiIndex] = useState(0);
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

  const mentionCandidates = useMemo<MentionCandidate[]>(() => {
    if (mentionQuery === null) return [];
    const needle = mentionQuery.toLowerCase();
    // `@channel` reaches everyone, `@here` only those present — offered as
    // rows beside people so nobody has to know the syntax by heart. DMs have
    // no crowd to address, so they are left out there.
    const broadcast: MentionCandidate[] =
      channel && channel.kind !== "dm" && channel.kind !== "group_dm"
        ? [
            { id: "@channel", handle: "channel", display_name: "채널 전원", hint: "모두에게 알림", broadcast: true },
            { id: "@here", handle: "here", display_name: "지금 접속 중인 사람", hint: "자리에 있는 사람만", broadcast: true },
          ].filter(
            (entry) =>
              entry.handle.startsWith(needle) || entry.display_name.toLowerCase().includes(needle),
          )
        : [];
    const found = [...people.values()]
      .filter(
        (person) =>
          person.handle.toLowerCase().includes(needle) ||
          person.display_name.toLowerCase().includes(needle),
      )
      .slice(0, 6)
      .map<MentionCandidate>((person) => ({
        id: person.id,
        handle: person.handle,
        display_name: person.display_name,
        avatar_url: person.avatar_url ?? null,
        is_bot: person.is_bot ?? false,
      }));
    return [...found, ...(needle.length > 0 ? broadcast : broadcast.slice(0, 0))].slice(0, 8);
  }, [mentionQuery, people, channel]);

  // ── Slash commands: `/rem` at the start of the draft lists what fits ─────
  const commands = useApp((state) => state.commands);
  const loadCommands = useApp((state) => state.loadCommands);
  const pushEphemeral = useApp((state) => state.pushEphemeral);
  const [commandIndex, setCommandIndex] = useState(0);
  useEffect(() => {
    if (commands.length === 0) void loadCommands();
  }, [commands.length, loadCommands]);
  const commandQuery = useMemo(() => {
    const match = /^\/([a-z0-9_-]*)$/i.exec(body);
    return match ? (match[1] ?? "").toLowerCase() : null;
  }, [body]);
  const commandCandidates = useMemo(
    () =>
      commandQuery === null
        ? []
        : commands.filter((entry) => entry.command.slice(1).toLowerCase().startsWith(commandQuery)).slice(0, 8),
    [commandQuery, commands],
  );
  const applyCommand = (command: string) => {
    setBody(`${command} `);
    requestAnimationFrame(() => {
      const element = textareaRef.current;
      element?.focus();
      element?.setSelectionRange(command.length + 1, command.length + 1);
    });
  };

  const maybeNotifyTyping = useCallback(() => {
    if (!channelId) return;
    const now = Date.now();
    if (now - lastTypingSentAt.current < TYPING_THROTTLE_MS) return;
    lastTypingSentAt.current = now;
    notifyTyping(channelId, parentId);
  }, [channelId, notifyTyping, parentId]);

  /** Track a trailing `@word` (mention) or `:word` (emoji) at the caret. */
  const updateMentionQuery = (value: string, caret: number) => {
    const upToCaret = value.slice(0, caret);
    // Anything up to whitespace, so `@김앨` keeps the picker open — the
    // ASCII-only pattern closed it on the first Hangul syllable, and people
    // shipped `@김앨리스` as plain text believing they had mentioned someone.
    const match = /(?:^|\s)@([^\s@]*)$/.exec(upToCaret);
    setMentionQuery(match ? (match[1] ?? "") : null);
    setMentionIndex(0);
    // `:ta` → 🎉 suggestions. Two characters before anything shows, so a
    // time like `10:3` does not open a picker.
    const emoji = /(?:^|\s):([a-z0-9_+-]{2,})$/i.exec(upToCaret);
    setEmojiQuery(emoji ? (emoji[1] ?? "") : null);
    setEmojiIndex(0);
  };

  const emojiCandidates = useMemo<EmojiEntry[]>(
    () => (emojiQuery ? searchEmoji(emojiQuery, 6) : []),
    [emojiQuery],
  );

  /** Replace the `:query` being typed with the chosen emoji. */
  const applyEmojiShortcode = (char: string) => {
    const element = textareaRef.current;
    if (!element) return;
    const caret = element.selectionStart;
    const before = body.slice(0, caret).replace(/:([a-z0-9_+-]*)$/i, `${char} `);
    const next = before + body.slice(caret);
    setBody(next);
    setEmojiQuery(null);
    requestAnimationFrame(() => {
      element.focus();
      element.setSelectionRange(before.length, before.length);
    });
  };

  /** Insert an emoji from the picker at the caret. */
  const insertEmoji = (char: string) => {
    const element = textareaRef.current;
    const caret = element?.selectionStart ?? body.length;
    const before = body.slice(0, caret) + char;
    setBody(before + body.slice(caret));
    setEmojiOpen(false);
    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(before.length, before.length);
    });
  };

  /** Progress bookkeeping shared by the picker, drops and pastes. */
  const trackProgress = (key: string, filename: string) => (sent: number, total: number) => {
    setUploads((current) => {
      const rest = current.filter((entry) => entry.key !== key);
      return [...rest, { key, filename, sent, total }];
    });
  };
  const untrack = (key: string) =>
    setUploads((current) => current.filter((entry) => entry.key !== key));

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
    // `:tada:` typed in full (no picker) still becomes 🎉.
    const text = replaceShortcodes(body.trim());
    if (!text && attachments.length === 0) return;

    // A slash command is an instruction, not a message. Known commands go to
    // the server; an unknown `/word` is sent as text (people do start lines
    // with slashes: "/etc/hosts 확인").
    const slash = /^\/([a-z0-9_-]+)(?:\s|$)/i.exec(text);
    if (slash && channelId && attachments.length === 0) {
      const known = commands.some((entry) => entry.command.toLowerCase() === `/${slash[1]?.toLowerCase()}`);
      if (known) {
        setBody("");
        draftsRef.current.delete(draftKey);
        try {
          const result = await api.runCommand(channelId, text);
          if (result.response?.text && (result.response.ephemeral || !result.handled)) {
            pushEphemeral(channelId, result.response.text);
          }
          if (!result.handled && !result.response) {
            pushEphemeral(channelId, `${slash[0].trim()} 명령을 처리하지 못했습니다.`);
          }
        } catch (error) {
          reportError(error, "명령을 실행하지 못했습니다.");
          setBody(text);
        }
        return;
      }
    }
    setBody("");
    draftsRef.current.delete(draftKey);
    const fileIds = attachments.map((file) => file.id);
    setAttachments([]);
    setMentionQuery(null);
    setEmojiQuery(null);

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
      await shell.pickAndUploadFiles(
        workspaceId,
        (file) => {
          untrack(`pick:${file.filename}`);
          setAttachments((current) => [...current, { id: file.id, filename: file.filename }]);
        },
        (filename, sent, total) => trackProgress(`pick:${filename}`, filename)(sent, total),
      );
    } catch (error) {
      reportError(error, uploadFailureMessage(error));
    } finally {
      setUploads([]);
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
            for (const [index, source] of sources.entries()) {
              const name =
                typeof source === "string" ? (source.split(/[\\/]/).pop() ?? source) : source.name;
              const key = `drop:${index}:${name}`;
              trackProgress(key, name)(0, typeof source === "string" ? 0 : source.size);
              const file = await api.uploadFile(workspaceId, source, trackProgress(key, name));
              untrack(key);
              setAttachments((current) => [
                ...current,
                { id: file.id, filename: file.filename },
              ]);
            }
          } catch (error) {
            reportError(error, uploadFailureMessage(error));
          } finally {
            setUploads([]);
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
          const key = `paste:${index}:${named.name}`;
          trackProgress(key, named.name)(0, named.size);
          const uploaded = await api.uploadFile(workspaceId, named, trackProgress(key, named.name));
          untrack(key);
          setAttachments((current) => [
            ...current,
            { id: uploaded.id, filename: uploaded.filename },
          ]);
        }
      } catch (error) {
        reportError(error, uploadFailureMessage(error));
      } finally {
        setUploads([]);
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
                {person.broadcast ? (
                  <span className="mention-broadcast-mark" aria-hidden="true">
                    @
                  </span>
                ) : (
                  <Avatar
                    id={person.id}
                    name={person.display_name}
                    avatarUrl={person.avatar_url}
                    size={22}
                    presence={presence.get(person.id)}
                    isBot={person.is_bot}
                  />
                )}
                <strong>{person.display_name}</strong>
                <span>{person.broadcast ? `@${person.handle} · ${person.hint ?? ""}` : `@${person.handle}`}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {commandQuery !== null && commandCandidates.length > 0 ? (
        <ul className="mention-picker command-picker" role="listbox" aria-label="명령 제안">
          {commandCandidates.map((entry, index) => (
            <li key={entry.command}>
              <button
                type="button"
                className={index === commandIndex ? "is-active" : ""}
                onMouseEnter={() => setCommandIndex(index)}
                onClick={() => applyCommand(entry.command)}
                role="option"
                aria-selected={index === commandIndex}
              >
                <strong>{entry.command}</strong>
                <span>
                  {entry.usage ? `${entry.usage} · ` : ""}
                  {entry.description ?? ""}
                  {entry.app ? ` · ${entry.app.name}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {emojiQuery !== null && emojiCandidates.length > 0 ? (
        <ul className="mention-picker emoji-suggest" role="listbox" aria-label="이모지 제안">
          {emojiCandidates.map((entry, index) => (
            <li key={entry.char}>
              <button
                type="button"
                className={index === emojiIndex ? "is-active" : ""}
                onMouseEnter={() => setEmojiIndex(index)}
                onClick={() => applyEmojiShortcode(entry.char)}
                role="option"
                aria-selected={index === emojiIndex}
              >
                <span className="emoji-suggest-char">{entry.char}</span>
                <strong>:{entry.code}:</strong>
                <span>{entry.keywords.slice(0, 2).join(" · ")}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {emojiOpen ? (
        <div className="emoji-anchor composer-emoji">
          <EmojiPicker onClose={() => setEmojiOpen(false)} onPick={insertEmoji} />
        </div>
      ) : null}

      {uploads.length > 0 ? (
        <ul className="composer-uploads" aria-label="업로드 진행">
          {uploads.map((entry) => {
            const percent = entry.total > 0 ? Math.round((entry.sent / entry.total) * 100) : null;
            return (
              <li key={entry.key}>
                <span className="composer-upload-name">{entry.filename}</span>
                <progress
                  value={percent ?? undefined}
                  max={100}
                  aria-label={`${entry.filename} 업로드 ${percent ?? 0}%`}
                />
                <span className="composer-upload-pct">
                  {percent === null ? "업로드 중" : percent >= 100 ? "처리 중…" : `${percent}%`}
                </span>
              </li>
            );
          })}
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
            // Command, emoji and mention pickers take precedence over sending.
            if (commandQuery !== null && commandCandidates.length > 0) {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setCommandIndex((index) => (index + 1) % commandCandidates.length);
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setCommandIndex((index) => (index - 1 + commandCandidates.length) % commandCandidates.length);
                return;
              }
              if (event.key === "Tab" || (event.key === "Enter" && commandQuery !== commandCandidates[commandIndex]?.command.slice(1))) {
                const chosen = commandCandidates[commandIndex];
                if (chosen) {
                  event.preventDefault();
                  applyCommand(chosen.command);
                  return;
                }
              }
            }
            if (emojiQuery !== null && emojiCandidates.length > 0) {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setEmojiIndex((index) => (index + 1) % emojiCandidates.length);
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setEmojiIndex(
                  (index) => (index - 1 + emojiCandidates.length) % emojiCandidates.length,
                );
                return;
              }
              if (event.key === "Enter" || event.key === "Tab") {
                const chosen = emojiCandidates[emojiIndex];
                if (chosen) {
                  event.preventDefault();
                  applyEmojiShortcode(chosen.char);
                  return;
                }
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setEmojiQuery(null);
                return;
              }
            }
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
            onClick={() => setEmojiOpen((open) => !open)}
            disabled={disabled}
            title="이모지"
            aria-label="이모지"
            aria-expanded={emojiOpen}
          >
            <IconSmile size={15} />
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
          <kbd>@이름</kbd> 멘션 · <kbd>:</kbd> 이모지 · <kbd>⌘V</kbd> 이미지 붙여넣기 · <kbd>```</kbd> 코드
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
