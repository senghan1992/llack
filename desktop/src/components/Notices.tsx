/**
 * The bottom-right toast stack.
 *
 * The gateway has always sent a `notification` frame for every message the
 * recipient's settings ask for; until now the UI received it and threw it away,
 * leaving the OS toast as the only signal — and that one is suppressed while
 * the window is focused, so somebody reading #공지 got nothing at all when they
 * were mentioned in #개발. This is the in-app half of that pair.
 *
 * Rules that matter in daily use:
 * - The channel already on screen never toasts (the store drops those); a
 *   message you can see does not need announcing.
 * - Clicking a toast opens its channel and closes it. That is the only action,
 *   so the whole card is the target rather than a button inside it.
 * - Five seconds, paused while the pointer is over the stack — reading the
 *   second toast must not lose the third.
 * - Mentions and DMs carry the signal edge; a busy channel does not.
 * - The stack sits above the composer rather than on top of it. The composer
 *   grows with a multi-line draft, so its height is measured rather than
 *   guessed, and the transcript's own jump-to-latest button is stepped over
 *   when it is showing.
 */

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/store/app";

import { IconClose } from "./Icon";

const DISMISS_AFTER_MS = 5_000;
const EDGE_GAP = 14;

/**
 * How far off the bottom the stack must sit to clear the composer, and the
 * jump-to-latest button when the transcript is scrolled up.
 */
function useBottomOffset(active: boolean): number {
  const [offset, setOffset] = useState(EDGE_GAP);

  useEffect(() => {
    if (!active) return;
    const composer = document.querySelector(".main-transcript .composer");
    if (!composer) return;

    const measure = () => {
      const composerHeight = composer.getBoundingClientRect().height;
      const jump = document.querySelector(".jump-to-latest");
      const jumpHeight = jump ? jump.getBoundingClientRect().height + 10 : 0;
      setOffset(Math.round(composerHeight + jumpHeight + EDGE_GAP));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(composer);
    return () => observer.disconnect();
  }, [active]);

  return offset;
}

export function Notices() {
  const notices = useApp((state) => state.notices);
  const dismissNotice = useApp((state) => state.dismissNotice);
  const openChannel = useApp((state) => state.openChannel);
  const revealMessage = useApp((state) => state.revealMessage);

  const [paused, setPaused] = useState(false);
  const bottom = useBottomOffset(notices.length > 0);

  // One timer per notice, rebuilt when the stack changes or the pointer
  // leaves. Hovering must hold every visible toast, not just the one under
  // the cursor, or the stack shifts out from under the pointer.
  const timers = useRef<number[]>([]);
  useEffect(() => {
    for (const timer of timers.current) window.clearTimeout(timer);
    timers.current = [];
    if (paused) return;

    for (const notice of notices) {
      const elapsed = Date.now() - notice.at;
      const remaining = Math.max(600, DISMISS_AFTER_MS - elapsed);
      timers.current.push(
        window.setTimeout(() => dismissNotice(notice.id), remaining),
      );
    }
    return () => {
      for (const timer of timers.current) window.clearTimeout(timer);
      timers.current = [];
    };
  }, [notices, paused, dismissNotice]);

  if (notices.length === 0) return null;

  return (
    <div
      className="notices"
      style={{ bottom }}
      role="region"
      aria-label="알림"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {notices.map((notice) => (
        <article
          key={notice.id}
          className={`notice notice-${notice.kind}`}
          // `alert` would interrupt a screen reader mid-sentence; a message
          // arriving is not that urgent.
          role="status"
        >
          <button
            type="button"
            className="notice-open"
            onClick={() => {
              // The channel, not the thread: `message_id` is the message
              // itself, so treating it as a thread parent would dock an empty
              // pane for anything that is not a reply.
              if (notice.kind === "reminder" && notice.channelId && notice.messageId) {
                // A reminder points at one message: land on it (its thread, if
                // it is a reply) rather than at the bottom of the channel.
                void revealMessage(notice.channelId, notice.messageId, notice.threadId ?? null);
              } else if (notice.channelId) {
                void openChannel(notice.channelId);
              }
              dismissNotice(notice.id);
            }}
          >
            <strong className="notice-title">{notice.title}</strong>
            <span className="notice-body">{notice.body}</span>
          </button>
          <button
            type="button"
            className="notice-dismiss"
            onClick={() => dismissNotice(notice.id)}
            aria-label="알림 닫기"
            title="닫기"
          >
            <IconClose size={12} />
          </button>
        </article>
      ))}
    </div>
  );
}
