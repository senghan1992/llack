import { X } from "lucide-react";
import { MessageRow } from "./MessageRow";
import { Composer } from "./Composer";
import type { Channel, Message } from "../lib/types";

interface Props {
  channel: Channel | null;
  root: Message | null;
  replies: Message[];
  ownId: string | null;
  onClose: () => void;
  onSend: (body: string) => Promise<void> | void;
  onTyping: (on: boolean) => void;
  onReact: (message: Message, emoji: string) => void;
  onEdit: (message: Message, body: string) => void;
  onDelete: (message: Message) => void;
  onPin: (message: Message) => void;
}

export function ThreadPane({
  channel,
  root,
  replies,
  ownId,
  onClose,
  onSend,
  onTyping,
  onReact,
  onEdit,
  onDelete,
  onPin,
}: Props) {
  if (!root) return null;

  return (
    <aside className="thread" aria-label="스레드">
      <header className="thread__head">
        <div className="u-grow">
          <p className="thread__title">스레드</p>
          <p className="thread__sub">
            {channel?.kind === "dm" ? channel.name : `#${channel?.name ?? ""}`}
          </p>
        </div>
        <button type="button" className="iconbtn" aria-label="스레드 닫기" onClick={onClose}>
          <X size={16} aria-hidden="true" />
        </button>
      </header>

      <div className="scroll thread__body">
        <MessageRow
          message={root}
          grouped={false}
          own={root.user_id === ownId}
          onOpenThread={() => undefined}
          onReact={onReact}
          onEdit={onEdit}
          onDelete={onDelete}
          onPin={onPin}
          replyScope="thread"
          hideThread
          flat
        />
        <p className="thread__count">
          {replies.length ? `${replies.length}개의 답글` : "아직 답글이 없습니다"}
        </p>
        {replies.map((reply) => (
          <MessageRow
            key={reply.id}
            message={reply}
            grouped={false}
            own={reply.user_id === ownId}
            onOpenThread={() => undefined}
            onReact={onReact}
            onEdit={onEdit}
            onDelete={onDelete}
            onPin={onPin}
            replyScope="thread"
            flat
          />
        ))}
      </div>

      <Composer
        channel={channel}
        threadRoot={root}
        onSend={onSend}
        onTyping={onTyping}
        onCancelThread={onClose}
      />
    </aside>
  );
}
