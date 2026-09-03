/**
 * 활동 — the threads I am part of and the messages that named me.
 *
 * A question asked in a channel gets its answer in a thread, and the only
 * trace used to be a "답글 1개" link under the original and a badge on the
 * channel. This gathers those: threads newest-reply-first with how many
 * replies arrived since I last spoke, and mentions of me across every channel.
 * Click → the exact message, thread open.
 */

import { useCallback, useEffect, useState } from "react";

import { formatRelative } from "@/lib/format";
import { api } from "@/lib/ipc";
import { previewText } from "@/lib/markdown";
import type { ChannelRef, MentionActivity, ThreadActivity } from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";
import { ChannelMark, IconClose } from "./Icon";

type Tab = "threads" | "mentions";

export function ActivityView() {
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const people = useApp((state) => state.people);
  const channels = useApp((state) => state.channels);
  const me = useApp((state) => state.me);
  const setMainView = useApp((state) => state.setMainView);
  const revealMessage = useApp((state) => state.revealMessage);
  const openThread = useApp((state) => state.openThread);
  const reportError = useApp((state) => state.reportError);

  const [tab, setTab] = useState<Tab>("threads");
  const [threads, setThreads] = useState<ThreadActivity[] | null>(null);
  const [mentions, setMentions] = useState<MentionActivity[] | null>(null);
  const [more, setMore] = useState<{ threads: boolean; mentions: boolean }>({
    threads: false,
    mentions: false,
  });
  const [next, setNext] = useState<{ threads: string | null; mentions: string | null }>({
    threads: null,
    mentions: null,
  });
  const [busy, setBusy] = useState(false);

  const context = useCallback(
    () => ({
      userName: (id: string) => people.get(id)?.display_name,
      channelName: (id: string) => channels.find((channel) => channel.id === id)?.name ?? undefined,
    }),
    [people, channels],
  );

  const load = useCallback(
    async (which: Tab, before: string | null) => {
      if (!workspaceId) return;
      setBusy(true);
      try {
        if (which === "threads") {
          const page = await api.activityThreads(workspaceId, before);
          setThreads((current) => (before ? [...(current ?? []), ...page.items] : page.items));
          setMore((current) => ({ ...current, threads: page.has_more }));
          setNext((current) => ({
            ...current,
            threads: page.next_before ?? page.items[page.items.length - 1]?.root.id ?? null,
          }));
        } else {
          const page = await api.activityMentions(workspaceId, before);
          setMentions((current) => (before ? [...(current ?? []), ...page.items] : page.items));
          setMore((current) => ({ ...current, mentions: page.has_more }));
          setNext((current) => ({
            ...current,
            mentions: page.next_before ?? page.items[page.items.length - 1]?.message.id ?? null,
          }));
        }
      } catch (error) {
        if (which === "threads") setThreads((current) => current ?? []);
        else setMentions((current) => current ?? []);
        reportError(error, "활동을 불러오지 못했습니다.");
      } finally {
        setBusy(false);
      }
    },
    [workspaceId, reportError],
  );

  useEffect(() => {
    void load("threads", null);
    void load("mentions", null);
  }, [load]);

  const channelLabel = (channel: ChannelRef): string => {
    if (channel.kind === "dm" || channel.kind === "group_dm") {
      const names = channel.peers.map((peer) => peer.display_name).join(", ");
      return names || "나와의 대화";
    }
    return `#${channel.name ?? "채널"}`;
  };

  const openThreadItem = async (item: ThreadActivity) => {
    await revealMessage(item.channel.id, item.root.id);
    await openThread(item.root.id);
  };

  const openMention = async (item: MentionActivity) => {
    await revealMessage(item.channel.id, item.message.id, item.message.parent_id ?? null);
  };

  const list = tab === "threads" ? threads : mentions;
  const hasMore = tab === "threads" ? more.threads : more.mentions;
  const cursor = tab === "threads" ? next.threads : next.mentions;

  return (
    <div className="activity-view">
      <header className="channel-header">
        <div className="channel-title">
          <h1>활동</h1>
          <span className="channel-meta">내가 낀 스레드와 나를 부른 메시지</span>
        </div>
        <div className="channel-header-right">
          <button
            type="button"
            className="header-button"
            onClick={() => setMainView("channel")}
            title="닫고 대화로 돌아가기"
            aria-label="닫기"
          >
            <IconClose size={13} />
          </button>
        </div>
      </header>

      <div className="file-toolbar">
        <div className="file-filters" role="tablist" aria-label="활동 종류">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "threads"}
            className={tab === "threads" ? "is-active" : ""}
            onClick={() => setTab("threads")}
          >
            스레드
            {threads && threads.some((item) => item.unread_replies > 0) ? (
              <span className="badge badge-mention">
                {threads.reduce((sum, item) => sum + (item.unread_replies > 0 ? 1 : 0), 0)}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "mentions"}
            className={tab === "mentions" ? "is-active" : ""}
            onClick={() => setTab("mentions")}
          >
            멘션
          </button>
        </div>
      </div>

      <div className="file-list-scroll">
        {list === null ? (
          <p className="file-empty">불러오는 중…</p>
        ) : list.length === 0 ? (
          <div className="file-empty">
            <strong>{tab === "threads" ? "참여한 스레드가 없습니다." : "나를 부른 메시지가 없습니다."}</strong>
            <p>
              {tab === "threads"
                ? "메시지의 답글 버튼으로 스레드를 열거나, 누군가 내 메시지에 답하면 여기에 모입니다."
                : "@이름 으로 나를 부른 메시지와 @channel 공지가 여기에 모입니다."}
            </p>
          </div>
        ) : tab === "threads" ? (
          <ul className="activity-list">
            {(threads ?? []).map((item) => (
              <li key={item.root.id}>
                <button type="button" className="activity-row" onClick={() => void openThreadItem(item)}>
                  <div className="activity-head">
                    <ChannelMark kind={item.channel.kind as "public"} />
                    <span className="activity-where">{channelLabel(item.channel)}</span>
                    <span className="activity-time">
                      {formatRelative(item.last_reply?.created_at ?? item.root.created_at)}
                    </span>
                  </div>
                  <p className="activity-root">
                    <strong>{item.root.author?.display_name ?? "알 수 없는 사용자"}</strong>{" "}
                    {previewText(item.root.body, context(), 140) ||
                      (item.root.attachments.length > 0 ? `첨부 ${item.root.attachments.length}개` : "")}
                  </p>
                  {item.last_reply ? (
                    <p className="activity-reply">
                      <span className="activity-reply-author">
                        {item.last_reply.author?.id === me?.id
                          ? "나"
                          : item.last_reply.author?.display_name ?? "알 수 없는 사용자"}
                      </span>
                      {previewText(item.last_reply.body, context(), 120)}
                    </p>
                  ) : null}
                  <div className="activity-foot">
                    <span className="activity-avatars">
                      {item.participants.slice(0, 5).map((person) => (
                        <Avatar
                          key={person.id}
                          id={person.id}
                          name={person.display_name}
                          avatarUrl={person.avatar_url}
                          size={18}
                          isBot={person.is_bot}
                        />
                      ))}
                    </span>
                    <span className="activity-count">답글 {item.root.reply_count}개</span>
                    {item.unread_replies > 0 ? (
                      <span className="badge badge-mention">새 답글 {item.unread_replies}</span>
                    ) : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <ul className="activity-list">
            {(mentions ?? []).map((item) => (
              <li key={item.message.id}>
                <button type="button" className="activity-row" onClick={() => void openMention(item)}>
                  <div className="activity-head">
                    <ChannelMark kind={item.channel.kind as "public"} />
                    <span className="activity-where">
                      {channelLabel(item.channel)}
                      {item.message.parent_id ? " · 스레드" : ""}
                    </span>
                    <span className="activity-time">{formatRelative(item.message.created_at)}</span>
                  </div>
                  <p className="activity-root">
                    <strong>{item.message.author?.display_name ?? "알 수 없는 사용자"}</strong>{" "}
                    {previewText(item.message.body, context(), 160)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
        {list && hasMore ? (
          <button
            type="button"
            className="file-more"
            onClick={() => void load(tab, cursor)}
            disabled={busy}
          >
            {busy ? "불러오는 중…" : "더 보기"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
