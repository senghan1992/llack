/**
 * The channel's pinned messages — the notice board behind the 📌 in the
 * header. Clicking a row jumps the transcript to the message itself, because
 * a pin is a pointer, not a copy.
 */

import { useEffect, useState } from "react";

import { formatTime } from "@/lib/format";
import { api } from "@/lib/ipc";
import { previewText } from "@/lib/markdown";
import type { Id, Message } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { IconClose } from "./Icon";

export function PinnedMessages({
  channelId,
  onClose,
}: {
  channelId: Id;
  onClose: () => void;
}) {
  const people = useApp((state) => state.people);
  const revealMessage = useApp((state) => state.revealMessage);
  const reportError = useApp((state) => state.reportError);

  const [pins, setPins] = useState<Message[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .channelPins(channelId)
      .then((rows) => {
        if (alive) setPins(rows);
      })
      .catch((error) => {
        if (alive) {
          setPins([]);
          reportError(error, "고정된 메시지를 불러오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, [channelId, reportError]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal pinned-list"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="고정된 메시지"
      >
        <header className="modal-header">
          <h2>고정된 메시지</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body">
          {pins === null ? <p className="modal-empty">불러오는 중…</p> : null}
          {pins !== null && pins.length === 0 ? (
            <p className="modal-empty">
              아직 고정된 메시지가 없습니다. 메시지에 마우스를 올려 📌 버튼으로
              고정할 수 있습니다.
            </p>
          ) : null}
          <ul className="pinned-rows">
            {(pins ?? []).map((message) => (
              <li key={message.id}>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    void revealMessage(channelId, message.id);
                  }}
                  title="메시지 위치로 이동"
                >
                  <Avatar
                    id={message.author?.id ?? message.id}
                    name={message.author?.display_name ?? "알 수 없는 사용자"}
                    avatarUrl={message.author?.avatar_url}
                    size={22}
                    isBot={message.author?.is_bot}
                  />
                  <div>
                    <strong>
                      {message.author?.display_name ?? "알 수 없는 사용자"}
                      <span>{formatTime(message.created_at)}</span>
                    </strong>
                    <p>
                      {previewText(message.body, {
                        userName: (id) => people.get(id)?.display_name,
                        channelName: () => undefined,
                      })}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
