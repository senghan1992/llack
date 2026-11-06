import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Clock, Hash, Lock, MapPin, Trash2, Unlink, Users } from "lucide-react";
import { Dialog } from "./Dialogs";
import { Avatar } from "./Avatar";
import { Select } from "./Select";
import { useStore } from "../store/useStore";
import { toDateInput, toLocalInput, fromDateTimeInput } from "../lib/calendar";
import { formatDateLong } from "../lib/format";
import type { ScheduleEvent } from "../lib/types";

const RESPONSE_LABEL: Record<string, string> = {
  accepted: "참석",
  declined: "불참",
  tentative: "미정",
};

export function EventDialog() {
  const target = useStore((s) => s.dialogTarget);
  const events = useStore((s) => s.events);
  const members = useStore((s) => s.members);
  const channels = useStore((s) => s.channels);
  const user = useStore((s) => s.user);
  const setDialog = useStore((s) => s.setDialog);
  const createEvent = useStore((s) => s.createEvent);
  const updateEvent = useStore((s) => s.updateEvent);
  const deleteEvent = useStore((s) => s.deleteEvent);
  const rsvpEvent = useStore((s) => s.rsvpEvent);
  const reportError = useStore((s) => s.reportError);

  const existing = useMemo(
    () => (target ? events.find((event) => event.id === target) ?? null : null),
    [events, target],
  );

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [allDay, setAllDay] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endDate, setEndDate] = useState("");
  const [endTime, setEndTime] = useState("10:00");
  const [isPrivate, setIsPrivate] = useState(false);
  const [channelId, setChannelId] = useState<string>("");
  const [attendeeIds, setAttendeeIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The form is filled once per opened event. A live update for the same
  // event must not wipe what the person is typing.
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    const key = existing?.id ?? "new";
    if (loadedFor.current === key) return;
    loadedFor.current = key;
    if (existing) {
      setTitle(existing.title);
      setDescription(existing.description);
      setLocation(existing.location);
      setAllDay(existing.all_day);
      setStartDate(toDateInput(existing.starts_at));
      setStartTime(toLocalInput(existing.starts_at).slice(11));
      setEndDate(toDateInput(existing.ends_at));
      setEndTime(toLocalInput(existing.ends_at).slice(11));
      setIsPrivate(existing.is_private);
      setChannelId(existing.channel_id ?? "");
      setAttendeeIds(existing.attendees.map((attendee) => attendee.user.id));
    } else {
      const now = new Date();
      const start = new Date(now.getTime() + 60 * 60 * 1000);
      start.setMinutes(0, 0, 0);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      setTitle("");
      setDescription("");
      setLocation("");
      setAllDay(false);
      setStartDate(toDateInput(start.toISOString()));
      setStartTime(toLocalInput(start.toISOString()).slice(11));
      setEndDate(toDateInput(end.toISOString()));
      setEndTime(toLocalInput(end.toISOString()).slice(11));
      setIsPrivate(false);
      setChannelId("");
      setAttendeeIds(user ? [user.id] : []);
    }
    setError(null);
    setBusy(false);
  }, [existing, user]);

  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const canManage = Boolean(
    existing &&
      (existing.created_by === user?.id || myRole === "owner" || myRole === "admin"),
  );
  // "New" is decided by the request, not by the record: an event that
  // vanished while the dialog was open is not a new event.
  const isNew = !target;
  const vanished = Boolean(target && !existing);

  const save = async () => {
    if (!title.trim()) {
      setError("일정 제목을 입력해 주세요");
      return;
    }
    const startsAt = fromDateTimeInput(startDate, allDay ? "00:00" : startTime);
    const endsAt = fromDateTimeInput(endDate, allDay ? "23:59" : endTime);
    if (new Date(endsAt).getTime() < new Date(startsAt).getTime()) {
      setError("종료 시각이 시작 시각보다 빠릅니다");
      return;
    }

    setBusy(true);
    setError(null);
    const payload = {
      title: title.trim(),
      description: description.trim(),
      location: location.trim(),
      starts_at: startsAt,
      ends_at: endsAt,
      all_day: allDay,
      is_private: isPrivate,
      channel_id: channelId || null,
      attendee_ids: attendeeIds,
    };
    try {
      if (existing) await updateEvent(existing.id, payload);
      else await createEvent(payload);
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "일정을 저장하지 못했습니다");
      reportError(err, "일정을 저장하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!existing) return;
    setBusy(true);
    try {
      await deleteEvent(existing.id);
      setDialog(null);
    } catch (err) {
      reportError(err, "일정을 삭제하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const answer = async (response: "accepted" | "declined" | "tentative") => {
    if (!existing) return;
    try {
      await rsvpEvent(existing.id, response);
    } catch (err) {
      reportError(err, "답변을 남기지 못했습니다");
    }
  };

  const readOnly = !isNew && !canManage;

  return (
    <Dialog
      title={isNew ? "일정 추가" : "일정"}
      onClose={() => setDialog(null)}
      wide
      footer={
        <>
          {existing && canManage ? (
            <button
              type="button"
              className="btn btn--danger btn--sm"
              onClick={() => void remove()}
              disabled={busy}
            >
              <Trash2 size={13} aria-hidden="true" />
              삭제
            </button>
          ) : null}
          <span className="u-grow" />
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => setDialog(null)}
            disabled={busy}
          >
            취소
          </button>
          {readOnly ? null : (
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => void save()}
              disabled={busy}
            >
              {busy ? "저장 중" : "저장"}
            </button>
          )}
        </>
      }
    >
      <div className="dialog__body u-col u-gap-4">
        {error ? <p className="field__error">{error}</p> : null}

        {vanished ? (
          <div className="empty">
            <p className="empty__title">일정이 없어졌습니다</p>
            <p className="empty__text">삭제되었거나 볼 수 없게 된 일정입니다.</p>
          </div>
        ) : null}

        {!vanished && readOnly ? (
          <EventReadOnly event={existing as ScheduleEvent} onAnswer={answer} />
        ) : !vanished ? (
          <>
            <label className="field">
              <span className="field__label">제목</span>
              <input
                className="field__input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="주간 회의"
                autoFocus
                maxLength={200}
              />
            </label>

            <div className="field">
              <span className="field__label">날짜와 시간</span>
              <div className="sched__when">
                <span className="sched__whenlabel">시작</span>
                <input
                  type="date"
                  className="field__input"
                  value={startDate}
                  onChange={(event) => {
                    setStartDate(event.target.value);
                    if (!endDate || endDate < event.target.value) setEndDate(event.target.value);
                  }}
                  aria-label="시작 날짜"
                />
                <input
                  type="time"
                  className="field__input"
                  value={startTime}
                  onChange={(event) => setStartTime(event.target.value)}
                  disabled={allDay}
                  aria-label="시작 시간"
                />
                <span className="sched__whenlabel">종료</span>
                <input
                  type="date"
                  className="field__input"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  aria-label="종료 날짜"
                />
                <input
                  type="time"
                  className="field__input"
                  value={endTime}
                  onChange={(event) => setEndTime(event.target.value)}
                  disabled={allDay}
                  aria-label="종료 시간"
                />
              </div>
              <label className="sched__check">
                <input
                  type="checkbox"
                  checked={allDay}
                  onChange={(event) => setAllDay(event.target.checked)}
                />
                하루 종일
              </label>
            </div>

            <label className="field">
              <span className="field__label">장소</span>
              <input
                className="field__input"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="3층 회의실"
                maxLength={200}
              />
            </label>

            <label className="field">
              <span className="field__label">설명</span>
              <textarea
                className="field__input u-h-auto u-minh-72 u-full u-py-2"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="준비할 것, 안건"
                maxLength={4000}
              />
            </label>

            <label className="field">
              <span className="field__label">연결할 채널</span>
              <Select
                value={channelId}
                onChange={setChannelId}
                options={[
                  {
                    value: "",
                    label: "연결 없음",
                    lead: <Unlink size={13} aria-hidden="true" />,
                  },
                  ...channels
                    .filter((channel) => channel.kind === "channel")
                    .map((channel) => ({
                      value: channel.id,
                      label: channel.name,
                      lead: <Hash size={13} aria-hidden="true" />,
                    })),
                ]}
              />
              <span className="field__hint">일정에서 바로 그 방으로 갈 수 있습니다.</span>
            </label>

            <div className="field">
              <span className="field__label">참석자</span>
              <div className="sched__people">
                {members.map((member) => {
                  const on = attendeeIds.includes(member.user.id);
                  return (
                    <button
                      key={member.user.id}
                      type="button"
                      className={`sched__person${on ? " sched__person--on" : ""}`}
                      aria-pressed={on}
                      onClick={() =>
                        setAttendeeIds((current) =>
                          on
                            ? current.filter((id) => id !== member.user.id)
                            : [...current, member.user.id],
                        )
                      }
                    >
                      <Avatar user={member.user} size="sm" />
                      <span className="u-truncate">{member.user.name}</span>
                      {on ? <Check size={13} aria-hidden="true" /> : null}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="sched__check">
              <input
                type="checkbox"
                checked={isPrivate}
                onChange={(event) => setIsPrivate(event.target.checked)}
              />
              비공개 — 나와 참석자만 볼 수 있습니다
            </label>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}

function EventReadOnly({
  event,
  onAnswer,
}: {
  event: ScheduleEvent;
  onAnswer: (response: "accepted" | "declined" | "tentative") => Promise<void>;
}) {
  return (
    <div className="u-col u-gap-4">
      <div className="u-col u-gap-1">
        <h3 className="sched__viewtitle">{event.title}</h3>
        <p className="sched__viewmeta">
          <Clock size={12} aria-hidden="true" />
          {formatDateLong(event.starts_at)}
          {event.all_day ? " · 하루 종일" : ` · ${toLocalInput(event.starts_at).slice(11)}`}
        </p>
        {event.location ? (
          <p className="sched__viewmeta">
            <MapPin size={12} aria-hidden="true" />
            {event.location}
          </p>
        ) : null}
        {event.is_private ? (
          <p className="sched__viewmeta">
            <Lock size={12} aria-hidden="true" />
            비공개 일정
          </p>
        ) : null}
      </div>

      {event.description ? (
        <p className="sched__viewtext">{event.description}</p>
      ) : null}

      <div className="field">
        <span className="field__label">
          <Users size={12} aria-hidden="true" /> 참석자 {event.attendees.length}명
        </span>
        <div className="sched__people">
          {event.attendees.map((attendee) => (
            <span key={attendee.user.id} className="sched__person sched__person--on">
              <Avatar user={attendee.user} size="sm" />
              <span className="u-truncate">{attendee.user.name}</span>
              <span className="sched__response">
                {RESPONSE_LABEL[attendee.response] ?? "미정"}
              </span>
            </span>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label">내 답변</span>
        <div className="u-row u-row--wrap u-gap-2">
          {(["accepted", "tentative", "declined"] as const).map((response) => (
            <button
              key={response}
              type="button"
              className={`btn btn--sm${event.my_response === response ? " btn--primary" : ""}`}
              onClick={() => void onAnswer(response)}
            >
              {RESPONSE_LABEL[response]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
