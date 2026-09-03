import { useMemo, useState } from "react";

import { formatBytes, formatTime } from "@/lib/format";
import { api } from "@/lib/ipc";
import { renderMessage } from "@/lib/markdown";
import type { Message } from "@/lib/types";
import { useApp } from "@/store/app";

import { AttachmentImage, isPreviewableImage } from "./AttachmentImage";
import { Avatar } from "./Avatar";
import { EmojiPicker } from "./EmojiPicker";
import { MessageBlocks, isInlineVideo } from "./MessageBlocks";
import { SaveMenu } from "./SaveMenu";
import { VideoAttachment } from "./VideoAttachment";
import {
  IconBookmark,
  IconEdit,
  IconFile,
  IconImage,
  IconPin,
  IconReply,
  IconShare,
  IconSmile,
  IconTrash,
} from "./Icon";
import { ShareMessage } from "./ShareMessage";

const QUICK_REACTIONS = ["👍", "🎉", "👀", "✅"];

interface MessageRowProps {
  message: Message;
  grouped: boolean;
  /** Thread replies render slightly tighter and without the reply affordance. */
  inThread?: boolean;
}

export function MessageRow({ message, grouped, inThread = false }: MessageRowProps) {
  const me = useApp((state) => state.me);
  const people = useApp((state) => state.people);
  const channels = useApp((state) => state.channels);
  const presence = useApp((state) => state.presence);
  const toggleReaction = useApp((state) => state.toggleReaction);
  const openThread = useApp((state) => state.openThread);
  const editMessage = useApp((state) => state.editMessage);
  const deleteMessage = useApp((state) => state.deleteMessage);
  const openChannel = useApp((state) => state.openChannel);
  const revealMessage = useApp((state) => state.revealMessage);

  const [editing, setEditing] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [pickingEmoji, setPickingEmoji] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(message.body);
  const refreshChannel = useApp((state) => state.refreshChannel);
  const reportError = useApp((state) => state.reportError);

  const togglePin = async () => {
    try {
      await api.setPinned(message.id, !message.is_pinned);
      await refreshChannel(message.channel_id);
    } catch (error) {
      reportError(error, "고정 상태를 바꾸지 못했습니다.");
    }
  };

  const html = useMemo(
    () =>
      renderMessage(message.body, {
        userName: (id) => people.get(id)?.display_name,
        channelName: (id) =>
          channels.find((channel) => channel.id === id)?.name ?? undefined,
        viewerId: me?.id,
      }),
    [message.body, people, channels, me?.id],
  );

  const author = message.author;
  const isMine = author?.id === me?.id;
  const mentionsMe = me
    ? message.mentions_everyone || message.mentioned_user_ids.includes(me.id)
    : false;

  // "김앨리스 님이 참여했습니다" — a line of context, not a person speaking.
  if (message.kind === "system") {
    return (
      <article className="message message-system" data-message-id={message.id}>
        <div className="message-gutter" />
        <div className="message-content">
          <span>{message.body}</span>
          <time dateTime={message.created_at}>
            {formatTime(message.created_at, me?.timezone)}
          </time>
        </div>
      </article>
    );
  }

  if (message.deleted_at) {
    return (
      <article className="message message-deleted" data-message-id={message.id}>
        <div className="message-gutter" />
        <div className="message-content">
          <em>삭제된 메시지입니다.</em>
          {/* The replies outlive their root. Without this the thread was
              unreachable — the data stayed, the door vanished. */}
          {!inThread && message.reply_count > 0 ? (
            <button
              type="button"
              className="thread-summary"
              onClick={() => void openThread(message.id)}
            >
              답글 {message.reply_count}개
            </button>
          ) : null}
        </div>
      </article>
    );
  }

  const submitEdit = async (event: React.FormEvent) => {
    event.preventDefault();
    const next = draft.trim();
    setEditing(false);
    if (next && next !== message.body) {
      await editMessage(message.id, next);
    } else {
      setDraft(message.body);
    }
  };

  return (
    <article
      className={[
        "message",
        grouped ? "is-grouped" : "",
        mentionsMe ? "is-mention" : "",
        message.kind === "app" ? "is-app" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-message-id={message.id}
    >
      <div className="message-gutter">
        {grouped ? (
          <time className="message-hover-time" dateTime={message.created_at}>
            {formatTime(message.created_at, me?.timezone)}
          </time>
        ) : author ? (
          <Avatar
            id={author.id}
            name={author.display_name}
            avatarUrl={author.avatar_url}
            size={28}
            presence={author.is_bot ? undefined : presence.get(author.id)}
            isBot={author.is_bot}
          />
        ) : (
          <Avatar id={message.id} name="?" size={28} />
        )}
      </div>

      <div className="message-content">
        {!grouped ? (
          <header className="message-header">
            <strong>{author?.display_name ?? "알 수 없는 사용자"}</strong>
            {author?.is_bot ? <span className="tag-bot">앱</span> : null}
            <time dateTime={message.created_at}>
              {formatTime(message.created_at, me?.timezone)}
            </time>
            {message.is_pinned ? (
              <span className="tag-pin">
                <IconPin size={11} />
                고정
              </span>
            ) : null}
          </header>
        ) : null}

        {editing ? (
          <form className="message-edit" onSubmit={submitEdit}>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={Math.min(10, draft.split("\n").length + 1)}
              autoFocus
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setEditing(false);
                  setDraft(message.body);
                }
                // Same contract as the composer: Enter saves, Shift+Enter
                // newlines. Enter-as-newline here while Enter-sends there
                // meant every edit ended with a stray blank line.
                if (event.key === "Enter" && !event.shiftKey) {
                  void submitEdit(event);
                }
              }}
            />
            <div className="message-edit-actions">
              <button type="submit">저장</button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setDraft(message.body);
                }}
              >
                취소
              </button>
              <span className="hint">Enter 로 저장 · Shift+Enter 줄바꿈 · Esc 취소</span>
            </div>
          </form>
        ) : (
          <div
            className="message-body"
            // Safe: `renderMessage` escapes all user input before building tags.
            dangerouslySetInnerHTML={{ __html: html }}
            onClick={(event) => {
              const target = event.target as HTMLElement;
              if (target.classList.contains("code-copy")) {
                const code = target.parentElement?.querySelector("pre")?.textContent ?? "";
                void navigator.clipboard?.writeText(code).then(() => {
                  target.textContent = "복사됨";
                  window.setTimeout(() => {
                    target.textContent = "복사";
                  }, 1_500);
                });
                return;
              }
              const channelId = target.dataset.channelId;
              const messageId = target.dataset.messageId;
              if (channelId) {
                event.preventDefault();
                if (messageId) void revealMessage(channelId, messageId);
                else void openChannel(channelId);
              }
            }}
          />
        )}

        {message.edited_at ? <span className="message-edited">(수정됨)</span> : null}

        <MessageBlocks message={message} />

        {message.attachments.length > 0 ? (
          <ul className="attachments">
            {message.attachments.map((file) => (
              <li key={file.id}>
                {/* The image, when it loads, sits above the chip; the chip
                    stays as the download affordance and as the whole story
                    when the preview cannot load. */}
                {isPreviewableImage(file) ? (
                  <AttachmentImage
                    file={file}
                    gallery={message.attachments.filter(isPreviewableImage)}
                  />
                ) : null}
                {isInlineVideo(file) && file.scan_status !== "infected" ? (
                  <VideoAttachment file={file} />
                ) : null}
                <button
                  type="button"
                  className="attachment"
                  onClick={() => {
                    void api.downloadFile(file.id, file.filename).catch(() => {
                      /* surfaced by the store's banner on the next action */
                    });
                  }}
                  title={`${file.filename} 내려받기`}
                >
                  <span className="attachment-icon">
                    {file.mime_type.startsWith("image/") ? (
                      <IconImage size={14} />
                    ) : (
                      <IconFile size={14} />
                    )}
                  </span>
                  <span className="attachment-name">{file.filename}</span>
                  <span className="attachment-size">{formatBytes(file.size_bytes)}</span>
                  {file.scan_status === "pending" ? (
                    <span className="attachment-scan is-pending" title="바이러스 검사 중">
                      검사 중
                    </span>
                  ) : file.scan_status === "infected" ? (
                    <span className="attachment-scan is-infected" title="악성 코드가 발견되어 차단됨">
                      차단됨
                    </span>
                  ) : file.scan_status === "clean" ? (
                    <span className="attachment-scan is-clean" title="바이러스 검사 통과">
                      안전
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {message.reactions.length > 0 ? (
          <ul className="reactions">
            {message.reactions.map((reaction) => (
              <li key={reaction.emoji}>
                <button
                  type="button"
                  className={reaction.me ? "reaction is-mine" : "reaction"}
                  onClick={() => void toggleReaction(message.id, reaction.emoji)}
                  title={reaction.user_ids
                    .map((id) => people.get(id)?.display_name ?? "사용자")
                    .join(", ")}
                >
                  <span>{reaction.emoji}</span>
                  <span>{reaction.count}</span>
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="reaction reaction-add"
                onClick={() => setPickingEmoji(true)}
                title="다른 반응 추가"
                aria-label="다른 반응 추가"
              >
                <IconSmile size={13} />
              </button>
            </li>
          </ul>
        ) : null}

        {saving ? (
          <div className="emoji-anchor">
            <SaveMenu message={message} onClose={() => setSaving(false)} />
          </div>
        ) : null}

        {pickingEmoji ? (
          <div className="emoji-anchor">
            <EmojiPicker
              label="반응 추가"
              onClose={() => setPickingEmoji(false)}
              onPick={(emoji) => {
                setPickingEmoji(false);
                void toggleReaction(message.id, emoji);
              }}
            />
          </div>
        ) : null}

        {!inThread && message.reply_count > 0 ? (
          <button
            type="button"
            className="thread-summary"
            onClick={() => void openThread(message.id)}
          >
            답글 {message.reply_count}개
          </button>
        ) : null}
      </div>

      <div className="message-actions" role="group" aria-label="메시지 작업">
        {QUICK_REACTIONS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            onClick={() => void toggleReaction(message.id, emoji)}
            title={`${emoji} 반응`}
          >
            {emoji}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setPickingEmoji((open) => !open)}
          title="다른 이모지로 반응"
          aria-label="다른 이모지로 반응"
          aria-expanded={pickingEmoji}
        >
          <IconSmile size={13} />
        </button>
        {!inThread ? (
          <button
            type="button"
            onClick={() => void openThread(message.id)}
            title="스레드에서 답글"
            aria-label="스레드에서 답글"
          >
            <IconReply size={13} />
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => setSharing(true)}
          title="다른 대화로 공유"
          aria-label="다른 대화로 공유"
        >
          <IconShare size={13} />
        </button>
        <button
          type="button"
          onClick={() => setSaving((open) => !open)}
          title={message.is_saved ? "나중에 볼 항목에서 빼기" : "나중에 보기 (리마인더 설정 가능)"}
          aria-label={message.is_saved ? "저장 해제" : "나중에 보기"}
          aria-expanded={saving}
          className={message.is_saved ? "is-on" : ""}
        >
          <IconBookmark size={13} />
        </button>
        <button
          type="button"
          onClick={() => void togglePin()}
          title={message.is_pinned ? "고정 해제" : "채널에 고정"}
          aria-label={message.is_pinned ? "고정 해제" : "채널에 고정"}
          className={message.is_pinned ? "is-on" : ""}
        >
          <IconPin size={13} />
        </button>
        {isMine ? (
          <>
            <button
              type="button"
              onClick={() => setEditing(true)}
              title="수정"
              aria-label="수정"
            >
              <IconEdit size={13} />
            </button>
            {/*
              Two clicks to delete, no dialog: the first click turns the
              button into its own confirmation, and looking away resets it.
              The trash sits one slot from edit, and there is no undo.
            */}
            {confirmingDelete ? (
              <button
                type="button"
                className="is-confirm-delete"
                onClick={() => void deleteMessage(message.id)}
                onMouseLeave={() => setConfirmingDelete(false)}
                onBlur={() => setConfirmingDelete(false)}
                title="한 번 더 누르면 삭제됩니다"
                aria-label="삭제 확인"
              >
                삭제?
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                title="삭제"
                aria-label="삭제"
              >
                <IconTrash size={13} />
              </button>
            )}
          </>
        ) : null}
      </div>

      {sharing ? (
        <ShareMessage message={message} onClose={() => setSharing(false)} />
      ) : null}
    </article>
  );
}
