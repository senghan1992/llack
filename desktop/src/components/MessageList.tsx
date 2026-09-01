/**
 * The transcript.
 *
 * Two behaviours worth calling out:
 *
 * - **Stick to bottom.** New messages only auto-scroll when the reader is
 *   already at the bottom. Yanking the viewport while someone reads history is
 *   the single most annoying thing a chat client can do.
 * - **Anchored history loading.** Prepending older messages would otherwise
 *   jump the scroll position, so the scroll offset is restored relative to the
 *   previous first element.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { formatDayHeading, formatTime, shouldGroupWithPrevious } from "@/lib/format";
import { api } from "@/lib/ipc";
import type { Message, PendingMessage } from "@/lib/types";
import { orderedMessages, useApp } from "@/store/app";

import { MessageRow } from "./MessageRow";

const BOTTOM_THRESHOLD_PX = 80;

export function MessageList() {
  const channelId = useApp((state) => state.activeChannelId);
  const messagesByChannel = useApp((state) => state.messages);
  const pendingByChannel = useApp((state) => state.pending);
  const hasOlder = useApp((state) => (channelId ? state.hasOlder.get(channelId) : false));
  const loading = useApp((state) =>
    channelId ? state.loadingChannels.has(channelId) : false,
  );
  const loadOlder = useApp((state) => state.loadOlder);

  const messages = orderedMessages({ messages: messagesByChannel }, channelId);
  const pending = (channelId && pendingByChannel.get(channelId)) || [];

  const scrollRef = useRef<HTMLDivElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const previousCount = useRef(0);
  const previousChannel = useRef<string | null>(null);
  // Set while prepending history, so the effect can restore the offset.
  const anchor = useRef<{ id: string; offset: number } | null>(null);

  const handleScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    setStickToBottom(distanceFromBottom < BOTTOM_THRESHOLD_PX);

    if (element.scrollTop < 120 && hasOlder && !loading && channelId) {
      const first = messages[0];
      if (first) {
        anchor.current = { id: first.id, offset: element.scrollTop };
        void loadOlder(channelId);
      }
    }
  }, [channelId, hasOlder, loading, loadOlder, messages]);

  // Restore position after a prepend, or follow new messages at the bottom.
  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const switchedChannel = previousChannel.current !== channelId;
    previousChannel.current = channelId ?? null;

    if (switchedChannel) {
      element.scrollTop = element.scrollHeight;
      previousCount.current = messages.length;
      setStickToBottom(true);
      return;
    }

    if (anchor.current) {
      const node = element.querySelector<HTMLElement>(
        `[data-message-id="${anchor.current.id}"]`,
      );
      if (node) {
        element.scrollTop = node.offsetTop - anchor.current.offset;
      }
      anchor.current = null;
      previousCount.current = messages.length;
      return;
    }

    const grew = messages.length > previousCount.current;
    previousCount.current = messages.length;
    if (grew && stickToBottom) {
      element.scrollTop = element.scrollHeight;
    }
  }, [channelId, messages.length, stickToBottom, messages]);

  useEffect(() => {
    if (!stickToBottom) return;
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [pending.length, stickToBottom]);

  if (!channelId) {
    return (
      <div className="transcript transcript-empty">
        <p>채널을 선택하세요.</p>
      </div>
    );
  }

  const rows = buildRows(messages, pending);

  return (
    <div className="transcript-wrapper">
      <div className="transcript" ref={scrollRef} onScroll={handleScroll}>
        {hasOlder ? (
          <div className="transcript-loading">
            {loading ? "이전 메시지를 불러오는 중…" : "위로 스크롤하여 더 보기"}
          </div>
        ) : (
          <div className="transcript-start">대화의 시작입니다.</div>
        )}

        {rows.map((row) => {
          if (row.type === "day") {
            return (
              <div className="day-divider" key={`day-${row.key}`}>
                <span>{row.label}</span>
              </div>
            );
          }
          if (row.type === "pending") {
            return <PendingRow key={`pending-${row.entry.id}`} entry={row.entry} />;
          }
          return (
            <MessageRow
              key={row.message.id}
              message={row.message}
              grouped={row.grouped}
            />
          );
        })}
      </div>

      {!stickToBottom ? (
        <button
          type="button"
          className="jump-to-latest"
          onClick={() => {
            const element = scrollRef.current;
            if (element) element.scrollTop = element.scrollHeight;
            setStickToBottom(true);
          }}
        >
          ↓ 최신 메시지로
        </button>
      ) : null}
    </div>
  );
}

function PendingRow({ entry }: { entry: PendingMessage }) {
  const reportError = useApp((state) => state.reportError);
  const channelId = useApp((state) => state.activeChannelId);
  const failed = entry.state === "failed";

  const retry = async () => {
    try {
      await api.retryFailedMessages();
      await api.drainOutbox();
      if (channelId) {
        // Re-read the queue so a message that went out disappears from the
        // transcript rather than lingering as "failed".
        const pending = await api.pendingMessages(channelId);
        useApp.setState((state) => ({
          pending: new Map(state.pending).set(channelId, pending),
        }));
        await useApp.getState().refreshChannel(channelId);
      }
    } catch (error) {
      reportError(error, "다시 전송하지 못했습니다.");
    }
  };

  const discard = async () => {
    try {
      await api.discardPendingMessage(entry.id);
      if (channelId) {
        const pending = await api.pendingMessages(channelId);
        useApp.setState((state) => ({
          pending: new Map(state.pending).set(channelId, pending),
        }));
      }
    } catch (error) {
      reportError(error, "삭제하지 못했습니다.");
    }
  };

  return (
    <article className={`message message-pending ${failed ? "is-failed" : ""}`}>
      <div className="message-gutter" />
      <div className="message-content">
        <p className="message-body">{entry.payload.body}</p>
        <span className="message-status">
          {failed ? (
            <>
              전송 실패 · {entry.last_error ?? "알 수 없는 오류"}
              <button type="button" onClick={() => void retry()}>
                다시 시도
              </button>
              <button type="button" onClick={() => void discard()}>
                삭제
              </button>
            </>
          ) : (
            <>전송 중… ({formatTime(new Date(entry.created_at_ms).toISOString())})</>
          )}
        </span>
      </div>
    </article>
  );
}

type Row =
  | { type: "day"; key: string; label: string }
  | { type: "message"; message: Message; grouped: boolean }
  | { type: "pending"; entry: PendingMessage };

/** Interleave day dividers and pending bubbles into the message sequence. */
function buildRows(messages: Message[], pending: PendingMessage[]): Row[] {
  const rows: Row[] = [];
  let lastDay = "";
  let previous: Message | undefined;

  for (const message of messages) {
    const day = message.created_at.slice(0, 10);
    if (day !== lastDay) {
      rows.push({ type: "day", key: day, label: formatDayHeading(message.created_at) });
      lastDay = day;
      previous = undefined;
    }
    rows.push({
      type: "message",
      message,
      grouped: shouldGroupWithPrevious(message, previous),
    });
    previous = message;
  }

  // Anything unsent belongs at the very bottom, in composition order.
  for (const entry of pending) {
    rows.push({ type: "pending", entry });
  }
  return rows;
}
