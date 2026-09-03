/**
 * "나중에 보기" — keep a message, optionally with a reminder.
 *
 * Presets cover what people actually pick (an hour, this afternoon, tomorrow
 * morning, next Monday); a custom time is there for the rest. Saving without
 * a time is a plain bookmark that lives in 나중에 until marked done.
 */

import { useState } from "react";

import { api } from "@/lib/ipc";
import type { Message } from "@/lib/types";
import { useApp } from "@/store/app";

function preset(label: string, when: () => Date): { label: string; at: () => string } {
  return { label, at: () => when().toISOString() };
}

const PRESETS = [
  preset("1시간 뒤", () => new Date(Date.now() + 60 * 60 * 1000)),
  preset("3시간 뒤", () => new Date(Date.now() + 3 * 60 * 60 * 1000)),
  preset("내일 오전 9시", () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return d;
  }),
  preset("다음 월요일 9시", () => {
    const d = new Date();
    const day = d.getDay();
    const delta = ((8 - day) % 7) || 7;
    d.setDate(d.getDate() + delta);
    d.setHours(9, 0, 0, 0);
    return d;
  }),
];

export function SaveMenu({ message, onClose }: { message: Message; onClose: () => void }) {
  const refreshChannel = useApp((state) => state.refreshChannel);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);
  const [note, setNote] = useState("");
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async (remindAt: string | null) => {
    setBusy(true);
    try {
      await api.saveMessage(message.id, { note: note.trim() || null, remind_at: remindAt });
      await refreshChannel(message.channel_id);
      showBanner(
        "info",
        remindAt
          ? `저장했습니다. ${new Date(remindAt).toLocaleString("ko-KR", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })} 에 알려드립니다.`
          : "나중에 볼 항목에 저장했습니다. 사이드바 '나중에'에서 봅니다.",
      );
      onClose();
    } catch (error) {
      reportError(error, "저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const unsave = async () => {
    setBusy(true);
    try {
      await api.unsaveMessage(message.id);
      await refreshChannel(message.channel_id);
      showBanner("info", "나중에 볼 항목에서 뺐습니다.");
      onClose();
    } catch (error) {
      reportError(error, "해제하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="save-menu" role="dialog" aria-label="나중에 보기" onClick={(event) => event.stopPropagation()}>
      {message.is_saved ? (
        <button type="button" className="save-row is-remove" onClick={() => void unsave()} disabled={busy}>
          저장 해제
        </button>
      ) : null}
      <button type="button" className="save-row" onClick={() => void save(null)} disabled={busy}>
        <strong>저장만</strong>
        <span>알림 없이 '나중에'에 보관</span>
      </button>
      <div className="save-presets">
        {PRESETS.map((entry) => (
          <button key={entry.label} type="button" onClick={() => void save(entry.at())} disabled={busy}>
            {entry.label}
          </button>
        ))}
      </div>
      <label className="save-custom">
        <span>직접 정하기</span>
        <input
          type="datetime-local"
          value={custom}
          onChange={(event) => setCustom(event.target.value)}
          aria-label="알림 시각"
        />
        <button
          type="button"
          className="settings-primary"
          onClick={() => {
            if (!custom) return;
            void save(new Date(custom).toISOString());
          }}
          disabled={busy || !custom}
        >
          알림
        </button>
      </label>
      <input
        className="save-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="메모 (선택)"
        maxLength={500}
        aria-label="메모"
      />
    </div>
  );
}
