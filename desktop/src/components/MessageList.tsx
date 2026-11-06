import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, Hash, MessageSquare } from "lucide-react";
import { MessageRow } from "./MessageRow";
import { dayLabel, isSameDay } from "../lib/format";
import type { Channel, Message } from "../lib/types";

interface Props {
  channel: Channel | null;
  messages: Message[];
  loading: boolean;
  hasMore: boolean;
  error: string | null;
  onLoadMore: () => void;
  onOpenThread: (message: Message) => void;
  onReact: (message: Message, emoji: string) => void;
  onEdit: (message: Message, body: string) => void;
  onDelete: (message: Message) => void;
  onPin: (message: Message) => void;
  ownId: string | null;
}

const GROUP_WINDOW_MS = 5 * 60 * 1000;

export function MessageList({
  channel,
  messages,
  loading,
  hasMore,
  error,
  onLoadMore,
  onOpenThread,
  onReact,
  onEdit,
  onDelete,
  onPin,
  ownId,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [count, setCount] = useState(0);

  useEffect(() => {
    setCount(messages.length);
  }, [messages.length]);

  useLayoutEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [count, atBottom]);

  const onScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setAtBottom(distance < 80);
    if (node.scrollTop < 60 && hasMore) onLoadMore();
  };

  if (error) {
    return (
      <div className="errorstate">
        <p className="errorstate__title">메시지를 불러오지 못했습니다</p>
        <p className="errorstate__text">{error}</p>
        <button type="button" className="btn" onClick={onLoadMore}>
          다시 시도
        </button>
      </div>
    );
  }

  if (loading && messages.length === 0) {
    return (
      <div className="list u-col u-gap-3 u-px-4" aria-busy="true" aria-label="메시지 불러오는 중">
        {[0, 1, 2, 3, 4].map((row) => (
          <div key={row} className="u-row u-row--start u-gap-3">
            <div className="skel u-h-30 u-w-30 u-r-8" />
            <div className="u-grow u-stack">
              <div className="skel u-h-3 u-w-28" />
              <div className="skel u-h-3 u-w-wide" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!channel) {
    return (
      <div className="empty">
        <span className="empty__mark" aria-hidden="true">
          <MessageSquare size={20} />
        </span>
        <p className="empty__title">대화를 고르세요</p>
        <p className="empty__text">
          왼쪽 목록에서 채널이나 대화를 선택하면 메시지가 여기에 쌓입니다.
        </p>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="empty">
        <span className="empty__mark" aria-hidden="true">
          <Hash size={20} />
        </span>
        <p className="empty__title">
          {channel.kind === "dm" ? `${channel.name}와의 첫 대화` : `#${channel.name}의 첫 대화`}
        </p>
        <p className="empty__text">
          {channel.topic
            ? channel.topic
            : "첫 메시지를 남겨 대화 시작을 알리세요."}
        </p>
      </div>
    );
  }

  return (
    <div className="listpane u-minh-0">
      <div ref={scrollRef} className="scroll u-h-full" onScroll={onScroll}>
        <div className="list">
          {hasMore ? (
            <div className="u-row u-center u-pb-3">
              <button type="button" className="btn btn--sm" onClick={onLoadMore}>
                이전 메시지 불러오기
              </button>
            </div>
          ) : null}

          <div className="msg__intro">
            <p className="msg__intro-name">
              {channel.kind === "dm" ? channel.name : `#${channel.name}`}
            </p>
            {channel.topic ? <p className="msg__intro-topic">{channel.topic}</p> : null}
          </div>

          {messages.map((message, index) => {
            const previous = messages[index - 1];
            const newDay = !previous || !isSameDay(previous.created_at, message.created_at);
            const grouped =
              !newDay &&
              Boolean(previous) &&
              previous.user_id === message.user_id &&
              !previous.deleted_at &&
              new Date(message.created_at).getTime() -
                new Date(previous.created_at).getTime() <
                GROUP_WINDOW_MS;

            return (
              <div key={message.id}>
                {newDay ? (
                  <div className="divider">
                    <span className="divider__label">
                      <span>{dayLabel(message.created_at).rel}</span>
                      <span className="divider__date">{dayLabel(message.created_at).date}</span>
                    </span>
                  </div>
                ) : null}
                <MessageRow
                  message={message}
                  grouped={grouped}
                  own={message.user_id === ownId}
                  onOpenThread={onOpenThread}
                  onReact={onReact}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  onPin={onPin}
                />
              </div>
            );
          })}

          <div ref={bottomRef} />
        </div>
      </div>

      {!atBottom ? (
        <button
          type="button"
          className="jump"
          onClick={() => {
            setAtBottom(true);
            bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
          }}
        >
          <ArrowDown size={14} aria-hidden="true" />
          최신 메시지
        </button>
      ) : null}
    </div>
  );
}
