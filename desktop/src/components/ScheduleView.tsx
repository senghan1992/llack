import { useEffect, useMemo, type ReactNode } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock,
  Lock,
  MapPin,
  Menu as MenuIcon,
  Plus,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { useStore } from "../store/useStore";
import {
  addMonths,
  dateKey,
  dayOf,
  isSameMonth,
  monthGrid,
  parseMonthKey,
} from "../lib/calendar";
import { formatDateLong, formatTime, weekday } from "../lib/format";
import type { ScheduleEvent } from "../lib/types";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function rangeLabel(event: ScheduleEvent): string {
  if (event.all_day) return "하루 종일";
  const start = formatTime(event.starts_at);
  const end = formatTime(event.ends_at);
  return start === end ? start : `${start} – ${end}`;
}

export function ScheduleHead({
  onToggleRail,
  actions,
}: {
  onToggleRail: () => void;
  /** Extra keys at the edge of the bar — the board's own move and close. */
  actions?: ReactNode;
}) {
  const setDialog = useStore((s) => s.setDialog);

  return (
    <header className="head">
      <div className="head__inner">
        <button
          type="button"
          className="iconbtn head__menu"
          aria-label="채널 목록 열기"
          onClick={onToggleRail}
        >
          <MenuIcon size={17} aria-hidden="true" />
        </button>
        <CalendarDays size={17} className="u-muted" aria-hidden="true" />
        <div className="head__id">
          <span className="head__name">일정</span>
        </div>
        <span className="head__topic">팀 일정과 회의를 한곳에서 봅니다</span>
        <div className="head__actions">
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => setDialog("event", null)}
          >
            <Plus size={13} aria-hidden="true" />
            일정 추가
          </button>
          {actions}
        </div>
      </div>
    </header>
  );
}

export function ScheduleView() {
  const events = useStore((s) => s.events);
  const loading = useStore((s) => s.eventsLoading);
  const error = useStore((s) => s.eventsError);
  const month = useStore((s) => s.eventMonth);
  const selectedDay = useStore((s) => s.eventDay);
  const members = useStore((s) => s.members);
  const setEventDay = useStore((s) => s.setEventDay);
  const setEventMonth = useStore((s) => s.setEventMonth);
  const loadEvents = useStore((s) => s.loadEvents);
  const setDialog = useStore((s) => s.setDialog);

  // The calendar loads its month; where it sits on the screen is the rail's
  // business, not the calendar's.
  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  const anchor = useMemo(() => parseMonthKey(month), [month]);
  const cells = useMemo(() => monthGrid(anchor), [anchor]);
  const today = dateKey(new Date());

  const byDay = useMemo(() => {
    const map = new Map<string, ScheduleEvent[]>();
    for (const event of events) {
      const key = dayOf(event.starts_at);
      const bucket = map.get(key);
      if (bucket) bucket.push(event);
      else map.set(key, [event]);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    }
    return map;
  }, [events]);

  const dayEvents = byDay.get(selectedDay) ?? [];

  // What each day carries: how many events, and how many of them I am in.
  // The month says the first with a mark; the mark's colour says the second.
  const marks = useMemo(() => {
    const map = new Map<string, { count: number; mine: number }>();
    for (const [key, list] of byDay) {
      map.set(key, {
        count: list.length,
        mine: list.filter((event) => event.my_response !== null).length,
      });
    }
    return map;
  }, [byDay]);

  // The next things on the board, so the list is never an empty page.
  // Only the ones I am in: my_response is set when I am an attendee, and
  // empty when I am not.
  const upcoming = useMemo(() => {
    const now = Date.now();
    return events
      .filter((event) => event.my_response !== null)
      .filter((event) => new Date(event.ends_at).getTime() >= now)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      .slice(0, 6);
  }, [events]);

  // The days ahead, without the day that is already on screen.
  const nextUp = useMemo(
    () => upcoming.filter((event) => dayOf(event.starts_at) !== selectedDay),
    [upcoming, selectedDay],
  );

  const shiftMonth = (count: number) => {
    const next = addMonths(anchor, count);
    const key = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
    // Keep today selected when the month still holds it; otherwise open on
    // the first of the new month.
    setEventDay(today.startsWith(key) ? today : `${key}-01`);
    void setEventMonth(key);
  };

  return (
    <div className="sched">
      <div className="sched__cal">
        <div className="sched__calhead">
          <span className="sched__month">
            {anchor.getFullYear()}년 {anchor.getMonth() + 1}월
          </span>
          <span className="sched__nav">
            <button
              type="button"
              className="iconbtn"
              aria-label="이전 달"
              onClick={() => shiftMonth(-1)}
            >
              <ChevronLeft size={15} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="iconbtn"
              aria-label="다음 달"
              onClick={() => shiftMonth(1)}
            >
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          </span>
        </div>

        <div className="sched__weekdays" aria-hidden="true">
          {WEEKDAYS.map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>

        <div className="sched__grid" role="grid" aria-label="월간 일정">
          {cells.map((cell) => {
            const key = dateKey(cell);
            const outside = !isSameMonth(cell, anchor);
            const mark = marks.get(key);
            const count = mark?.count ?? 0;
            const mine = mark?.mine ?? 0;
            const classes = ["calday"];
            if (outside) classes.push("calday--out");
            if (key === today) classes.push("calday--today");
            if (key === selectedDay) classes.push("calday--sel");
            const label = count
              ? mine
                ? `${cell.getMonth() + 1}월 ${cell.getDate()}일, 일정 ${count}개, 내 일정 ${mine}개`
                : `${cell.getMonth() + 1}월 ${cell.getDate()}일, 팀 일정 ${count}개`
              : `${cell.getMonth() + 1}월 ${cell.getDate()}일, 일정 없음`;
            return (
              <button
                key={key}
                type="button"
                className={classes.join(" ")}
                aria-current={key === selectedDay ? "date" : undefined}
                aria-label={label}
                onClick={() => setEventDay(key)}
              >
                <span className="calday__num">{cell.getDate()}</span>
                {count ? (
                  <span
                    className={`dotmark${mine ? "" : " dotmark--team"}`}
                    aria-hidden="true"
                  />
                ) : null}
              </button>
            );
          })}
        </div>

        {/* The mark on a day says whose it is, so the month says it too. */}
        <ul className="sched__legend">
          <li className="sched__legenditem">
            <span className="dotmark" aria-hidden="true" />
            내 일정
          </li>
          <li className="sched__legenditem">
            <span className="dotmark dotmark--team" aria-hidden="true" />
            팀 일정
          </li>
        </ul>

        <button
          type="button"
          className="btn btn--sm btn--block sched__today"
          onClick={() => {
            setEventDay(today);
            void setEventMonth(today.slice(0, 7));
          }}
        >
          오늘
        </button>
      </div>

      <div className="sched__list">
        <header className="sched__listhead">
          <div className="u-col">
            <h2 className="sched__daytitle">
              {selectedDay === today ? "오늘" : formatDateLong(`${selectedDay}T00:00:00`)}
              <span className="sched__daymeta">
                {weekday(`${selectedDay}T00:00:00`)} · {dayEvents.length}개
              </span>
            </h2>
          </div>
        </header>

        <div className="sched__scroll">
          <div className="sched__day">
            {error ? (
              <div className="errorstate">
                <p className="empty__title">일정을 불러오지 못했습니다</p>
                <p className="empty__text">{error}</p>
                <button
                  type="button"
                  className="btn btn--sm empty__action"
                  onClick={() => void loadEvents()}
                >
                  다시 시도
                </button>
              </div>
            ) : null}

            {!error && loading && events.length === 0 ? (
              <div className="sched__loading">
                <span className="u-small u-muted">일정을 불러오는 중</span>
              </div>
            ) : null}

            {!error && !loading && dayEvents.length === 0 ? (
              <div className="empty">
                <span className="empty__mark" aria-hidden="true">
                  <CalendarDays size={20} />
                </span>
                <p className="empty__title">이 날은 비어 있습니다</p>
                <p className="empty__text">
                  {formatDateLong(`${selectedDay}T00:00:00`)}에 등록된 일정이 없습니다.
                </p>
                <button
                  type="button"
                  className="btn btn--sm empty__action"
                  onClick={() => setDialog("event", null)}
                >
                  일정 추가
                </button>
              </div>
            ) : null}

            {dayEvents.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                members={members}
                onOpen={() => setDialog("event", event.id)}
              />
            ))}
          </div>

          <section className="sched__next">
            <h3 className="sched__nexttitle">내 앞으로</h3>
            {nextUp.length ? (
              nextUp.map((event) => (
                <button
                  key={event.id}
                  type="button"
                  className="sched__nextrow"
                  onClick={() => setDialog("event", event.id)}
                >
                  <span className="sched__nextwhen">
                    {new Date(event.starts_at).getMonth() + 1}월 {new Date(event.starts_at).getDate()}일
                  </span>
                  <span className="sched__nextname u-truncate">{event.title}</span>
                  {event.is_private ? <Lock size={12} aria-hidden="true" /> : null}
                </button>
              ))
            ) : (
              <p className="sched__nextempty">내게 예정된 일정이 없습니다.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function EventCard({
  event,
  members,
  onOpen,
}: {
  event: ScheduleEvent;
  members: { user: { id: string; name: string; avatar_color: string | null } }[];
  onOpen: () => void;
}) {
  const accepted = event.attendees.filter((a) => a.response === "accepted").length;
  const names = new Map(members.map((member) => [member.user.id, member.user.name]));
  const who = event.attendees
    .map((attendee) => names.get(attendee.user.id) ?? attendee.user.name)
    .slice(0, 4)
    .join(", ");

  return (
    <article className="event">
      <div className="event__time">
        <Clock size={13} aria-hidden="true" />
        <span>{rangeLabel(event)}</span>
      </div>
      <div className="event__body">
        <button type="button" className="event__title" onClick={onOpen}>
          {event.title}
          {event.is_private ? (
            <Lock size={12} className="event__lock" aria-label="비공개" />
          ) : null}
        </button>
        {event.location ? (
          <p className="event__meta">
            <MapPin size={12} aria-hidden="true" />
            {event.location}
          </p>
        ) : null}
        <div className="event__foot">
          {who ? (
            <p className="event__who">
              {who}
              {event.attendees.length > 4 ? ` 외 ${event.attendees.length - 4}명` : ""}
              {event.attendees.length ? ` · 참석 ${accepted}/${event.attendees.length}` : ""}
            </p>
          ) : null}
          {event.my_response && event.my_response !== "pending" ? (
            <p
              className={`event__mine${event.my_response === "accepted" ? " event__mine--on" : ""}`}
            >
              {event.my_response === "accepted"
                ? "참석"
                : event.my_response === "declined"
                  ? "불참"
                  : "미정"}
            </p>
          ) : null}
          <div className="event__faces" aria-hidden="true">
            {event.attendees.slice(0, 3).map((attendee) => (
              <Avatar key={attendee.user.id} user={attendee.user} size="sm" />
            ))}
          </div>
        </div>
      </div>
    </article>
  );
}
