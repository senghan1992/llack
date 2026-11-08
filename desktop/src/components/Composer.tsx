import { useEffect, useRef, useState } from "react";
import { CornerUpLeft, Paperclip, Send, Smile, X } from "lucide-react";
import { api, ApiError, fileUrl } from "../lib/api";
import { QUICK_REACTIONS } from "../lib/markdown";
import { formatBytes } from "../lib/format";
import { Menu } from "./Menu";
import { useStore, type ReplyScope } from "../store/useStore";
import type { Channel, FileRef, Message } from "../lib/types";

interface Props {
  channel: Channel | null;
  threadRoot?: Message | null;
  onSend: (body: string, attachmentIds?: string[]) => Promise<void> | void;
  onTyping: (on: boolean) => void;
  onCancelThread?: () => void;
}

export function Composer({ channel, threadRoot, onSend, onTyping, onCancelThread }: Props) {
  const toast = useStore((s) => s.toast);
  const workspaceId = useStore((s) => s.workspaceId);
  const setDraft = useStore((s) => s.setDraft);
  const [sending, setSending] = useState(false);
  const [emojiAnchor, setEmojiAnchor] = useState<HTMLElement | null>(null);
  const [files, setFiles] = useState<FileRef[]>([]);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (channel?.id) inputRef.current?.focus();
  }, [channel?.id]);

  // The room keeps its half-written line in the store: it belongs to the
  // room, not to this composer, so it stays when the room changes, when
  // the composer goes away (the schedule takes the whole pane), and when
  // the window is closed with the sentence still in it. A thread's answer
  // is its own answer — it does not share the room's line.
  const inThread = Boolean(threadRoot);
  const channelId = channel?.id ?? null;
  const [typed, setTyped] = useState("");
  // Only this room's own line is watched — the composer does not wake up
  // for a half-written sentence in another room.
  const draft = useStore((s) => (channelId ? s.drafts[channelId] ?? "" : ""));
  const value = !inThread && channelId ? draft : typed;
  const write = (next: string) => {
    if (!inThread && channelId) setDraft(channelId, next);
    else setTyped(next);
  };

  useEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
  }, [value]);

  const send = async () => {
    const body = value.trim();
    if ((!body && files.length === 0) || sending) return;
    setSending(true);
    try {
      await onSend(body, files.map((f) => f.id));
      write("");
      setFiles([]);
      onTyping(false);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  const onChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    write(event.target.value);
    onTyping(true);
    if (typingTimer.current) clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => onTyping(false), 2500);
  };

  const pickFiles = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    if (!picked.length) return;
    setUploading(true);
    try {
      if (!workspaceId) throw new Error("no workspace");
      const uploaded = await Promise.all(
        picked.map((file) => api.upload(file, workspaceId)),
      );
      setFiles((current) => [...current, ...uploaded]);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "파일을 올리지 못했습니다. 형식과 크기를 확인해 주세요.";
      toast(message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const insert = (text: string) => {
    const node = inputRef.current;
    if (!node) return;
    const start = node.selectionStart ?? value.length;
    const next = `${value.slice(0, start)}${text}${value.slice(node.selectionEnd ?? start)}`;
    write(next);
    setEmojiAnchor(null);
    requestAnimationFrame(() => {
      node.focus();
      node.selectionStart = node.selectionEnd = start + text.length;
    });
  };

  const placeholder = threadRoot
    ? "스레드에 답글을 남기세요"
    : channel?.kind === "dm"
      ? `${channel.name}에게 메시지를 보내세요`
      : channel
        ? `#${channel.name}에 메시지를 보내세요`
        : "메시지를 입력하세요";

  // The answer being written, if any. Only one answer is open at a time,
  // and only the surface it was opened in shows it.
  const scope: ReplyScope = threadRoot ? "thread" : "channel";
  const pending = useStore((s) => s.replyTo);
  const setReplyTo = useStore((s) => s.setReplyTo);
  const answer = pending && pending.scope === scope ? pending.message : null;

  return (
    <div className="composer">
      {threadRoot ? (
        <div className="composer__thread">
          <span className="u-grow u-truncate">
            <strong>{threadRoot.author.name}</strong>의 메시지에 답글
          </span>
          <button
            type="button"
            className="iconbtn u-h-6 u-w-6"
            aria-label="스레드 닫기"
            onClick={onCancelThread}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      {answer ? (
        <div className="composer__reply">
          <CornerUpLeft size={13} aria-hidden="true" />
          <span className="u-grow u-truncate">
            <strong>{answer.author.name}</strong>의 메시지에 답장
          </span>
          <button
            type="button"
            className="iconbtn u-h-6 u-w-6"
            aria-label="답장 취소"
            onClick={() => setReplyTo(null)}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <div className="composer__box">
        <textarea
          ref={inputRef}
          className="composer__input"
          rows={1}
          value={value}
          placeholder={placeholder}
          aria-label={placeholder}
          onChange={onChange}
          onKeyDown={onKeyDown}
        />

        {files.length ? (
          <div className="u-row u-row--wrap u-gap-2 u-px-3 u-pb-2">
            {files.map((file) => (
              <span
                key={file.id}
                className="u-row u-row--center u-gap-2 u-r-8 u-hairline u-border-t u-px-2 u-py-1 u-tiny"
              >
                {file.mime.startsWith("image/") ? (
                  <img
                    src={fileUrl(file.url)}
                    alt=""
                    width={24}
                    height={24}
                    className="u-h-6 u-w-6 u-r-4 u-cover"
                  />
                ) : null}
                {file.name} · {formatBytes(file.size)}
                <button
                  type="button"
                  className="iconbtn u-h-4 u-w-4"
                  aria-label={`${file.name} 제거`}
                  onClick={() => setFiles((current) => current.filter((f) => f.id !== file.id))}
                >
                  <X size={11} aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="composer__bar">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/*,application/pdf,application/zip,application/gzip,application/rtf,text/plain,text/csv,text/markdown,.txt,.csv,.md,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.hwp,.hwpx,.zip,.gz"
            className="u-hidden"
            onChange={(event) => void pickFiles(event)}
          />
          <button
            type="button"
            className="iconbtn"
            aria-label="파일 첨부"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
          >
            <Paperclip size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="iconbtn"
            aria-label="이모티콘 넣기"
            aria-expanded={Boolean(emojiAnchor)}
            onClick={(event) => setEmojiAnchor(event.currentTarget)}
          >
            <Smile size={15} aria-hidden="true" />
          </button>
          <span className="composer__spacer" />
          {uploading ? <span className="composer__hint">업로드 중</span> : null}
          <span className="composer__hint">Enter로 전송</span>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => void send()}
            disabled={sending || (!value.trim() && files.length === 0)}
          >
            <Send size={13} aria-hidden="true" />
            전송
          </button>
        </div>
      </div>

      {emojiAnchor ? (
        <Menu anchor={emojiAnchor} onClose={() => setEmojiAnchor(null)} className="emoji" width={280}>
          <div className="emoji__grid">
            {QUICK_REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                className="emoji__item"
                onClick={() => insert(emoji)}
              >
                {emoji}
              </button>
            ))}
          </div>
        </Menu>
      ) : null}
    </div>
  );
}
