/**
 * The thread pane.
 *
 * Docked beside the transcript rather than floating over it — one of the
 * concrete annoyances with Slack's overlay is that it hides the channel you
 * were reading. Here both stay visible.
 */

import { orderedMessages, useApp } from "@/store/app";

import { Composer } from "./Composer";
import { MessageRow } from "./MessageRow";

export function ThreadPane() {
  const threadId = useApp((state) => state.openThreadId);
  const openThread = useApp((state) => state.openThread);
  const replies = useApp((state) => (threadId ? state.threadReplies.get(threadId) : undefined));
  const root = useApp((state) => {
    if (!threadId) return undefined;
    const bucket = state.messages.get(state.activeChannelId ?? "");
    return bucket?.get(threadId) ?? orderedMessages(state, state.activeChannelId)
      .find((message) => message.id === threadId);
  });

  if (!threadId) return null;

  return (
    <aside className="thread-pane" aria-label="스레드">
      <header className="thread-header">
        <h2>스레드</h2>
        <button
          type="button"
          onClick={() => void openThread(null)}
          aria-label="스레드 닫기"
        >
          ×
        </button>
      </header>

      <div className="thread-scroll">
        {root ? <MessageRow message={root} grouped={false} inThread /> : null}
        <div className="thread-divider">
          <span>{replies?.length ?? 0}개의 답글</span>
        </div>
        {(replies ?? []).map((reply, index) => (
          <MessageRow
            key={reply.id}
            message={reply}
            grouped={
              index > 0 &&
              replies?.[index - 1]?.author?.id === reply.author?.id
            }
            inThread
          />
        ))}
      </div>

      <Composer parentId={threadId} placeholder="스레드에 답글 달기" />
    </aside>
  );
}
