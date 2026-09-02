/**
 * Share a message into another conversation.
 *
 * The daily move this exists for: a decision lands in one channel and the
 * people who need it live in another. Before this, the route was copy → switch
 * channel → paste → re-type the attribution — four steps that lose the source.
 *
 * The share is a quoted message, not a new message kind: the quote carries the
 * text, and the attribution line carries a `<#channel>` reference that renders
 * as a real channel link, so the reader can jump to the source. Attachments are
 * named in the quote rather than re-attached — re-using file ids would let a
 * share smuggle a private channel's file past that channel's membership.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { previewText } from "@/lib/markdown";
import { api } from "@/lib/ipc";
import type { Channel, Id, Message } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { ChannelMark, IconClose, IconSearch } from "./Icon";

export function ShareMessage({
  message,
  onClose,
}: {
  message: Message;
  onClose: () => void;
}) {
  const channels = useApp((state) => state.channels);
  const people = useApp((state) => state.people);
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const [query, setQuery] = useState("");
  const [targetId, setTargetId] = useState<Id | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /*
   * Everywhere I can post, except where the message already is. Archived
   * channels are out — the composer refuses them, and this dialog must not be
   * a way around that.
   */
  const candidates = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return channels
      .filter(
        (channel) =>
          channel.id !== message.channel_id &&
          !channel.is_archived &&
          shareTargetName(channel, me?.display_name).toLowerCase().includes(needle),
      )
      .slice(0, 30);
  }, [channels, query, message.channel_id, me?.display_name]);

  function shareTargetName(channel: Channel, myName?: string): string {
    if (channel.name) return channel.name;
    if (channel.peers.length > 0) {
      return channel.peers.map((peer) => peer.display_name).join(", ");
    }
    return myName ? `${myName} (나)` : "대화";
  }

  const share = async () => {
    if (!targetId || busy) return;
    setBusy(true);
    try {
      const quoted = message.body
        .split("\n")
        .map((line) => `> ${line}`)
        .join("\n");
      const files =
        message.attachments.length > 0
          ? `\n> 첨부: ${message.attachments.map((file) => file.filename).join(", ")}`
          : "";
      const author = message.author?.display_name ?? "알 수 없는 사용자";
      const body = [
        comment.trim(),
        `${quoted}${files}\n> — <#${message.channel_id}> 에서 ${author}`,
      ]
        .filter(Boolean)
        .join("\n");

      await api.sendMessage({ channelId: targetId, body });
      const target = channels.find((channel) => channel.id === targetId);
      showBanner(
        "info",
        `공유했습니다: ${target ? shareTargetName(target, me?.display_name) : "선택한 대화"}`,
      );
      onClose();
    } catch (error) {
      reportError(error, "메시지를 공유하지 못했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal share-message"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="다른 대화로 공유"
      >
        <header className="modal-header">
          <h2>다른 대화로 공유</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body share-body">
          <blockquote className="share-preview">
            <strong>{message.author?.display_name ?? "알 수 없는 사용자"}</strong>
            <span>
              {previewText(message.body, {
                userName: (id) => people.get(id)?.display_name,
                channelName: (id) =>
                  channels.find((channel) => channel.id === id)?.name ?? undefined,
              }) ||
                (message.attachments.length > 0
                  ? `첨부 ${message.attachments.length}개`
                  : "")}
            </span>
          </blockquote>

          <div className="share-field">
            <IconSearch size={14} />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="채널 또는 대화 찾기"
              aria-label="공유할 곳 찾기"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  onClose();
                }
                if (event.key === "Enter" && candidates.length > 0) {
                  event.preventDefault();
                  setTargetId(candidates[0]?.id ?? null);
                }
              }}
            />
          </div>

          <ul className="share-list" role="listbox" aria-label="공유할 곳">
            {candidates.length === 0 ? (
              <li className="modal-empty">공유할 수 있는 대화가 없습니다.</li>
            ) : (
              candidates.map((channel) => {
                const isDm = channel.kind === "dm" || channel.kind === "group_dm";
                const peer = isDm ? channel.peers[0] : undefined;
                return (
                  <li key={channel.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={targetId === channel.id}
                      className={targetId === channel.id ? "is-picked" : ""}
                      onClick={() => setTargetId(channel.id)}
                    >
                      {isDm && peer ? (
                        <Avatar
                          id={peer.id}
                          name={peer.display_name}
                          avatarUrl={peer.avatar_url}
                          size={20}
                          isBot={peer.is_bot}
                        />
                      ) : (
                        <ChannelMark kind={channel.kind} />
                      )}
                      <span>{shareTargetName(channel, me?.display_name)}</span>
                    </button>
                  </li>
                );
              })
            )}
          </ul>

          <textarea
            className="share-comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="함께 보낼 말 (선택)"
            rows={2}
          />
        </div>

        <footer className="share-footer">
          <button
            type="button"
            className="share-send"
            onClick={() => void share()}
            disabled={!targetId || busy}
          >
            {busy ? "보내는 중…" : "공유"}
          </button>
        </footer>
      </div>
    </div>
  );
}
