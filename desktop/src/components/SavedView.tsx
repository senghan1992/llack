/**
 * 나중에 — messages I kept, with optional reminders.
 *
 * "이거 나중에 봐야 해" used to mean a screenshot or a self-DM. A saved message
 * stays here until I mark it done; a reminder time turns it into a toast at
 * that moment. Click opens the exact message; done moves it to the 완료 tab
 * where it can be reopened.
 */

import { useCallback, useEffect, useState } from "react";

import { formatRelative } from "@/lib/format";
import { api } from "@/lib/ipc";
import { previewText } from "@/lib/markdown";
import type { ChannelRef, SavedItem } from "@/lib/types";
import { useApp } from "@/store/app";

import { ChannelMark, IconClose } from "./Icon";

type Tab = "open" | "done";

export function SavedView() {
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const people = useApp((state) => state.people);
  const channels = useApp((state) => state.channels);
  const setMainView = useApp((state) => state.setMainView);
  const revealMessage = useApp((state) => state.revealMessage);
  const reportError = useApp((state) => state.reportError);
  const showBanner = useApp((state) => state.showBanner);

  const [tab, setTab] = useState<Tab>("open");
  const [items, setItems] = useState<SavedItem[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(
    async (which: Tab, before: string | null) => {
      if (!workspaceId) return;
      try {
        const page = await api.listSaved(workspaceId, { done: which === "done", before });
        setItems((current) => (before ? [...(current ?? []), ...page.items] : page.items));
        setHasMore(page.has_more);
        setNext(page.next_before ?? page.items[page.items.length - 1]?.id ?? null);
      } catch (error) {
        setItems((current) => current ?? []);
        reportError(error, "저장한 항목을 불러오지 못했습니다.");
      }
    },
    [workspaceId, reportError],
  );

  useEffect(() => {
    setItems(null);
    void load(tab, null);
  }, [tab, load]);

  const context = {
    userName: (id: string) => people.get(id)?.display_name,
    channelName: (id: string) => channels.find((channel) => channel.id === id)?.name ?? undefined,
  };

  const channelLabel = (channel: ChannelRef): string => {
    if (channel.kind === "dm" || channel.kind === "group_dm") {
      return channel.peers.map((peer) => peer.display_name).join(", ") || "나와의 대화";
    }
    return `#${channel.name ?? "채널"}`;
  };

  const toggleDone = async (item: SavedItem) => {
    setBusy(item.id);
    try {
      if (item.done_at) await api.reopenSaved(item.id);
      else await api.markSavedDone(item.id);
      setItems((current) => (current ?? []).filter((entry) => entry.id !== item.id));
      showBanner("info", item.done_at ? "다시 나중에 볼 항목으로 옮겼습니다." : "완료로 표시했습니다.");
    } catch (error) {
      reportError(error, "상태를 바꾸지 못했습니다.");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (item: SavedItem) => {
    setBusy(item.id);
    try {
      await api.unsaveMessage(item.message.id);
      setItems((current) => (current ?? []).filter((entry) => entry.id !== item.id));
    } catch (error) {
      reportError(error, "저장을 해제하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="activity-view saved-view">
      <header className="channel-header">
        <div className="channel-title">
          <h1>나중에</h1>
          <span className="channel-meta">저장한 메시지와 리마인더</span>
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
        <div className="file-filters" role="tablist" aria-label="저장 항목">
          <button type="button" role="tab" aria-selected={tab === "open"} className={tab === "open" ? "is-active" : ""} onClick={() => setTab("open")}>
            할 것
          </button>
          <button type="button" role="tab" aria-selected={tab === "done"} className={tab === "done" ? "is-active" : ""} onClick={() => setTab("done")}>
            완료
          </button>
        </div>
      </div>

      <div className="file-list-scroll">
        {items === null ? (
          <p className="file-empty">불러오는 중…</p>
        ) : items.length === 0 ? (
          <div className="file-empty">
            <strong>{tab === "open" ? "나중에 볼 항목이 없습니다." : "완료한 항목이 없습니다."}</strong>
            <p>메시지에 마우스를 올리고 책갈피 버튼을 누르면 여기에 모입니다. 시간을 정하면 그때 알려드립니다.</p>
          </div>
        ) : (
          <ul className="activity-list">
            {items.map((item) => {
              const due = item.remind_at ? new Date(item.remind_at) : null;
              const overdue = due !== null && due.getTime() < Date.now() && !item.done_at;
              return (
                <li key={item.id}>
                  <div className="saved-row">
                    <button
                      type="button"
                      className="activity-row"
                      onClick={() =>
                        void revealMessage(item.channel.id, item.message.id, item.message.parent_id ?? null)
                      }
                    >
                      <div className="activity-head">
                        <ChannelMark kind={item.channel.kind} />
                        <span className="activity-where">{channelLabel(item.channel)}</span>
                        <span className="activity-time">저장 {formatRelative(item.created_at)}</span>
                      </div>
                      <p className="activity-root">
                        <strong>{item.message.author?.display_name ?? "알 수 없는 사용자"}</strong>{" "}
                        {previewText(item.message.body, context, 160) ||
                          (item.message.attachments.length > 0 ? `첨부 ${item.message.attachments.length}개` : "")}
                      </p>
                      {item.note ? <p className="saved-note">메모: {item.note}</p> : null}
                      {due ? (
                        <p className={`saved-remind ${overdue ? "is-overdue" : ""}`}>
                          {item.reminded_at ? "알림 완료" : "알림"} · {due.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </p>
                      ) : null}
                    </button>
                    <div className="saved-actions">
                      <button
                        type="button"
                        className="member-action is-primary"
                        onClick={() => void toggleDone(item)}
                        disabled={busy === item.id}
                      >
                        {item.done_at ? "다시 열기" : "완료"}
                      </button>
                      <button
                        type="button"
                        className="member-action"
                        onClick={() => void remove(item)}
                        disabled={busy === item.id}
                        title="저장 해제"
                      >
                        해제
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {items && hasMore ? (
          <button type="button" className="file-more" onClick={() => void load(tab, next)}>
            더 보기
          </button>
        ) : null}
      </div>
    </div>
  );
}
