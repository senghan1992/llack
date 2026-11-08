import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChartNoAxesGantt } from "lucide-react";
import { ChartTip } from "./ChartTip";
import { Dialog } from "./Dialogs";
import { api } from "../lib/api";
import { useStore } from "../store/useStore";
import { dateRange, dueLabel, formatDate, formatTime } from "../lib/format";
import { dayStart, monthCells, monthStartOf, nextDay, ratio } from "../lib/gantt";
import type { Milestone, ScheduleEvent, Task } from "../lib/types";

/** The status of a card on the timeline — the same four the board has. */
const STATUS_TONE: Record<Task["status"], string> = {
  request: "var(--color-muted)",
  todo: "var(--color-ink-2)",
  "in-progress": "var(--color-warn)",
  done: "var(--color-accent)",
};

/** The same four, named — a card's tip says where the card stands. */
const STATUS_LABEL: Record<Task["status"], string> = {
  request: "요청",
  todo: "할 일",
  "in-progress": "진행 중",
  done: "완료",
};

/** What the open tip is about — one mark of the chart. */
type TipSubject =
  | { kind: "milestone"; id: string }
  | { kind: "task"; id: string }
  | { kind: "event"; id: string };

/**
 * The project chart — the Gantt view of one project's work.
 *
 * It answers one question at a glance: when is what due, and how far
 * along is it. One mark language says it all: a **bar** is a period of
 * work, a **post** is a meeting, a **dot** is a deadline, and the **rule**
 * with its band is today. Every mark sits in the same trough — the time
 * axis — so the rows read as one instrument, and the list under the chart
 * says the same thing in words.
 *
 * Every mark can be asked about: it is a button, and hovering or focusing
 * it opens a card on the ink band that says what the mark is.
 */
export function ProjectChartDialog() {
  const target = useStore((s) => s.dialogTarget);
  const projects = useStore((s) => s.projects);
  const workspaceId = useStore((s) => s.workspaceId);
  const setDialog = useStore((s) => s.setDialog);

  const project = useMemo(
    () => projects.find((item) => item.id === target) ?? null,
    [projects, target],
  );

  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<ScheduleEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tip, setTip] = useState<{ anchor: HTMLElement; subject: TipSubject } | null>(
    null,
  );

  useEffect(() => {
    if (!target) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.milestones(target), api.projectTasks(target)])
      .then(([milestoneList, taskList]) => {
        if (cancelled) return;
        setMilestones(milestoneList);
        setTasks(taskList);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError("차트를 불러오지 못했습니다. 연결을 확인해 주세요.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [target]);

  /** The chart's own span: from the earliest thing to the latest. */
  const span = useMemo(() => {
    const dates: number[] = [];
    for (const milestone of milestones) {
      dates.push(dayStart(milestone.start_at), nextDay(milestone.end_at));
    }
    for (const task of tasks) {
      if (task.due_at) dates.push(dayStart(task.due_at));
    }
    if (!dates.length) return null;
    const from = monthStartOf(Math.min(...dates));
    const last = new Date(Math.max(...dates));
    const to = new Date(last.getFullYear(), last.getMonth() + 1, 1);
    const cells = monthCells(from, to);
    if (!cells.length) return null;
    return { cells, start: cells[0].start, end: cells[cells.length - 1].end };
  }, [milestones, tasks]);

  /** The team's calendar inside the span — the meetings around the work. */
  useEffect(() => {
    if (!workspaceId || !span) return;
    let cancelled = false;
    api
      .events(
        workspaceId,
        new Date(span.start).toISOString(),
        new Date(span.end).toISOString(),
      )
      .then((list) => {
        if (!cancelled) setEvents(list);
      })
      .catch(() => {
        /* the calendar is a bonus — the chart stands without it */
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, span]);

  const ordered = useMemo(
    () => [...milestones].sort((a, b) => a.start_at.localeCompare(b.start_at)),
    [milestones],
  );

  const dated = useMemo(
    () =>
      tasks.filter(
        (task): task is Task & { due_at: string } =>
          typeof task.due_at === "string" && task.due_at !== "",
      ),
    [tasks],
  );

  const today = useMemo(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  }, []);

  /** Is today inside the span the chart draws? Then it is a mark on it. */
  const todayInSpan = useMemo(
    () => Boolean(span) && today >= span!.start && today <= span!.end,
    [span, today],
  );

  /** The date of today, as the legend names it. */
  const todayLabel = useMemo(() => {
    const date = new Date(today);
    return `${date.getMonth() + 1}월 ${date.getDate()}일`;
  }, [today]);

  const inSpan = useMemo(() => {
    if (!span) return [];
    return events.filter((event) => {
      const start = dayStart(event.starts_at);
      const end = nextDay(event.ends_at);
      return end > span.start && start < span.end;
    });
  }, [events, span]);

  /**
   * Where the project stands, in one line: how far the cards have come,
   * how many milestones are closed, what is left, what is late, and what
   * comes next.
   */
  const summary = useMemo(() => {
    const done = tasks.filter((task) => task.status === "done").length;
    const open = tasks.filter((task) => task.status !== "done").length;
    const late = tasks.filter(
      (task) =>
        task.due_at && task.status !== "done" && dayStart(task.due_at) < today,
    ).length;
    const closed = milestones.filter((milestone) => milestone.progress >= 100).length;
    const next = [...milestones]
      .filter((milestone) => milestone.progress < 100)
      .sort((a, b) => a.start_at.localeCompare(b.start_at))[0];
    return {
      progress: tasks.length ? Math.round((done / tasks.length) * 100) : 0,
      total: tasks.length,
      open,
      late,
      closed,
      milestones: milestones.length,
      next,
    };
  }, [tasks, milestones, today]);

  /** Open the tip on the mark under the pointer or under the keyboard. */
  const showTip = (event: { currentTarget: HTMLElement }, subject: TipSubject) => {
    setTip({ anchor: event.currentTarget, subject });
  };

  /** Close the tip — unless the mark still holds the keyboard's focus. */
  const clearTip = () => {
    setTip((prev) => (prev && document.activeElement === prev.anchor ? prev : null));
  };

  /** The tip of one mark, named by the mark it belongs to. */
  const tipOf = (subject: TipSubject) =>
    tip && tip.subject.kind === subject.kind && tip.subject.id === subject.id
      ? "charttip"
      : undefined;

  /** What the open tip says — the mark it belongs to, in words. */
  const tipBody = useMemo<ReactNode>(() => {
    if (!tip) return null;
    if (tip.subject.kind === "milestone") {
      const milestone = milestones.find((item) => item.id === tip.subject.id);
      return milestone ? <MilestoneTip milestone={milestone} /> : null;
    }
    if (tip.subject.kind === "task") {
      const task = tasks.find((item) => item.id === tip.subject.id);
      return task ? <TaskTip task={task} /> : null;
    }
    const event = events.find((item) => item.id === tip.subject.id);
    return event ? <EventTip event={event} /> : null;
  }, [tip, milestones, tasks, events]);

  return (
    <Dialog
      title={project ? `${project.name} · 차트` : "프로젝트 차트"}
      onClose={() => setDialog(null)}
      chart
    >
      <div className="chart">
        {loading ? (
          <div className="u-col u-gap-3" aria-hidden="true">
            {[0, 1, 2, 3].map((row) => (
              <span key={row} className="skel u-h-12 u-full" />
            ))}
          </div>
        ) : null}

        {!loading && error ? (
          <div className="errorstate">
            <p className="errorstate__title">차트를 불러오지 못했습니다</p>
            <p className="errorstate__text">{error}</p>
          </div>
        ) : null}

        {!loading && !error && !span ? (
          <div className="empty">
            <span className="empty__mark" aria-hidden="true">
              <ChartNoAxesGantt size={20} />
            </span>
            <p className="empty__title">차트에 담을 것이 없습니다</p>
            <p className="empty__text">
              마일스톤을 만들면 기간이 차트에 놓이고, 마감일이 있는 할 일은
              그 날짜에 점으로 표시됩니다.
            </p>
          </div>
        ) : null}

        {!loading && !error && span ? (
          <>
            {/* The chart's own first line: where the project stands,
                before a single mark is read. */}
            <div className="proj__facts chart__summary">
              <span className="proj__fact chart__summarylabel">전체 진행률</span>
              {summary.total ? (
                <>
                  <span className="proj__meter" aria-hidden="true">
                    <span
                      className="proj__meterfill"
                      style={{ width: `${summary.progress}%` }}
                    />
                  </span>
                  <span className="proj__fact proj__fact--num">{summary.progress}%</span>
                </>
              ) : null}
              {summary.milestones ? (
                <span className="proj__fact">
                  마일스톤 {summary.closed}/{summary.milestones} 완료
                </span>
              ) : null}
              {summary.total ? (
                <span className="proj__fact">할 일 {summary.open}개 남음</span>
              ) : null}
              {summary.late > 0 ? (
                <span className="proj__fact chart__fact--late">
                  기한 지남 {summary.late}개
                </span>
              ) : null}
              {summary.next ? (
                <span className="proj__fact">
                  다음 {summary.next.title} · {dueLabel(summary.next.end_at).text}
                </span>
              ) : null}
            </div>

            <div className="chart__grid">
              <div className="chart__headrow">
                <span className="chart__headlabel">마일스톤</span>
                <div className="chart__track">
                  {span.cells.map((cell, index) => (
                    <span
                      key={cell.key}
                      className="chart__month"
                      style={{
                        left: `${ratio(cell.start, span.start, span.end) * 100}%`,
                        width: `${ratio(cell.end, span.start, span.end) * 100}%`,
                      }}
                    >
                      {/* The year is said where it changes — a reader must
                          not mistake next January for this one. */}
                      {cell.year !== span.cells[index - 1]?.year
                        ? `${cell.year}년 ${cell.label}`
                        : cell.label}
                    </span>
                  ))}
                </div>
              </div>

              <div className="chart__body">
                {/* One layer of lines for the whole chart: the month
                    boundaries and today's band run through every row at
                    once. It sits under the marks — the trough they are
                    drawn in. */}
                <div className="chart__overlay" aria-hidden="true">
                  {todayInSpan ? (
                    <span
                      className="chart__todayband"
                      style={{
                        left: `${ratio(today, span.start, span.end) * 100}%`,
                      }}
                    />
                  ) : null}
                  {span.cells.slice(1).map((cell) => (
                    <span
                      key={cell.key}
                      className="chart__gridline"
                      style={{
                        left: `${ratio(cell.start, span.start, span.end) * 100}%`,
                      }}
                    />
                  ))}
                </div>

                {ordered.map((milestone) => {
                  const left = ratio(
                    dayStart(milestone.start_at),
                    span.start,
                    span.end,
                  );
                  const right = ratio(
                    nextDay(milestone.end_at),
                    span.start,
                    span.end,
                  );
                  const subject: TipSubject = {
                    kind: "milestone",
                    id: milestone.id,
                  };
                  return (
                    <div key={milestone.id} className="chart__row">
                      <span className="chart__label">
                        <span
                          className="chart__dot"
                          style={{ ["--ms-color" as string]: milestone.color }}
                          aria-hidden="true"
                        />
                        <span className="chart__labelname u-truncate">
                          {milestone.title}
                        </span>
                        <span className="chart__labelnum">
                          {milestone.progress}%
                        </span>
                      </span>
                      <div className="chart__track">
                        <button
                          type="button"
                          className="chart__mark chart__bar"
                          style={{
                            left: `${left * 100}%`,
                            width: `${Math.max(right - left, 0.006) * 100}%`,
                            ["--ms-color" as string]: milestone.color,
                          }}
                          aria-label={`마일스톤 ${milestone.title}`}
                          aria-describedby={tipOf(subject)}
                          onMouseEnter={(event) => showTip(event, subject)}
                          onMouseLeave={clearTip}
                          onFocus={(event) => showTip(event, subject)}
                          onBlur={clearTip}
                        >
                          <span
                            className="chart__barfill"
                            style={{
                              width: `${Math.max(0, Math.min(100, milestone.progress))}%`,
                            }}
                          />
                        </button>
                      </div>
                    </div>
                  );
                })}

                {dated.length ? (
                  <div className="chart__row">
                    <span className="chart__label chart__label--quiet">
                      <span
                        className="chart__glyph chart__glyph--dot"
                        aria-hidden="true"
                      />
                      <span className="chart__labelname u-truncate">
                        카드 마감일
                      </span>
                      <span className="chart__labelnum">{dated.length}</span>
                    </span>
                    <div className="chart__track">
                      {dated.map((task) => {
                        const subject: TipSubject = { kind: "task", id: task.id };
                        return (
                          <button
                            key={task.id}
                            type="button"
                            className="chart__mark chart__dotmark"
                            style={{
                              left: `${ratio(dayStart(task.due_at), span.start, span.end) * 100}%`,
                              ["--dot-tone" as string]: STATUS_TONE[task.status],
                            }}
                            aria-label={`${task.title} · ${formatDate(task.due_at)} 마감`}
                            aria-describedby={tipOf(subject)}
                            onMouseEnter={(event) => showTip(event, subject)}
                            onMouseLeave={clearTip}
                            onFocus={(event) => showTip(event, subject)}
                            onBlur={clearTip}
                          />
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {inSpan.length ? (
                  <div className="chart__row">
                    <span className="chart__label chart__label--quiet">
                      <span
                        className="chart__glyph chart__glyph--post"
                        aria-hidden="true"
                      />
                      <span className="chart__labelname u-truncate">
                        팀 일정
                      </span>
                      <span className="chart__labelnum">{inSpan.length}</span>
                    </span>
                    <div className="chart__track">
                      {inSpan.map((event) => {
                        const subject: TipSubject = { kind: "event", id: event.id };
                        return (
                          <button
                            key={event.id}
                            type="button"
                            className="chart__mark chart__post"
                            style={{
                              left: `${ratio(dayStart(event.starts_at), span.start, span.end) * 100}%`,
                            }}
                            aria-label={`${event.title} · ${formatDate(event.starts_at)}`}
                            aria-describedby={tipOf(subject)}
                            onMouseEnter={(event) => showTip(event, subject)}
                            onMouseLeave={clearTip}
                            onFocus={(event) => showTip(event, subject)}
                            onBlur={clearTip}
                          />
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {/* today's rule runs over the marks — it is the one thing
                    that cuts through every row at once */}
                {todayInSpan ? (
                  <div className="chart__todaylayer" aria-hidden="true">
                    <span
                      className="chart__today"
                      style={{
                        left: `${ratio(today, span.start, span.end) * 100}%`,
                      }}
                    />
                  </div>
                ) : null}
              </div>
            </div>

            <div className="chart__legend">
              <span className="chart__legenditem">
                <span className="chart__legendbar" aria-hidden="true" />
                기간과 진행률
              </span>
              <span className="chart__legenditem">
                <span
                  className="chart__legenddot"
                  style={{ ["--dot-tone" as string]: "var(--color-ink-2)" }}
                  aria-hidden="true"
                />
                카드 마감일
              </span>
              {inSpan.length ? (
                <span className="chart__legenditem">
                  <span className="chart__legendpost" aria-hidden="true" />
                  팀 일정
                </span>
              ) : null}
              {todayInSpan ? (
                <span className="chart__legenditem">
                  <span className="chart__legendtoday" aria-hidden="true" />
                  오늘
                  <span className="chart__legenddate">{todayLabel}</span>
                </span>
              ) : null}
            </div>

            {ordered.length ? (
              <ul className="chart__list">
                {ordered.map((milestone) => {
                  const linked = tasks.filter(
                    (task) => task.milestone_id === milestone.id,
                  );
                  return (
                    <li
                      key={milestone.id}
                      className="mscard"
                      style={{ ["--ms-color" as string]: milestone.color }}
                    >
                      <div className="mscard__head">
                        <span className="mscard__dot" aria-hidden="true" />
                        <span className="mscard__title u-truncate">
                          {milestone.title}
                        </span>
                        <span className="mscard__dates">
                          {dateRange(milestone.start_at, milestone.end_at)}
                        </span>
                      </div>
                      <div className="mscard__row">
                        <span className="msbar">
                          <span
                            className="msbar__fill"
                            style={{
                              width: `${Math.max(0, Math.min(100, milestone.progress))}%`,
                            }}
                          />
                        </span>
                        <span className="mscard__count">
                          {milestone.auto_progress
                            ? `${milestone.done_count}/${milestone.task_count}`
                            : `${milestone.progress}%`}
                        </span>
                      </div>
                      {linked.length ? (
                        <div className="mscard__chips">
                          {linked.map((task) => (
                            <span key={task.id} className="mschip">
                              {task.title}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : null}

            {inSpan.length ? (
              <ul className="chart__agenda">
                {inSpan.map((event) => (
                  <li key={event.id} className="chart__agendaitem">
                    <span className="chart__agendadate">
                      {formatDate(event.starts_at)}
                    </span>
                    <span className="chart__agendatitle u-truncate">
                      {event.title}
                    </span>
                    {event.location ? (
                      <span className="chart__agendaplace u-truncate">
                        {event.location}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}

            {!ordered.length && dated.length ? (
              <p className="chart__note">
                마일스톤은 아직 없고, 마감일이 있는 카드만 차트에 놓였습니다.
              </p>
            ) : null}
          </>
        ) : null}
      </div>

      {tip ? (
        <ChartTip anchor={tip.anchor}>{tipBody}</ChartTip>
      ) : null}
    </Dialog>
  );
}

/** The card that names a milestone: its period, its progress, its title. */
function MilestoneTip({ milestone }: { milestone: Milestone }) {
  return (
    <>
      <span className="charttip__title">{milestone.title}</span>
      <span className="charttip__meta">
        {dateRange(milestone.start_at, milestone.end_at)} ·{" "}
        {dueLabel(milestone.end_at).text}
      </span>
      <span className="charttip__meta">
        <span className="charttip__num">
          {milestone.auto_progress
            ? `${milestone.done_count}/${milestone.task_count}`
            : `${milestone.progress}%`}
        </span>{" "}
        진행
      </span>
    </>
  );
}

/** The card that names a card's deadline: when it falls and who holds it. */
function TaskTip({ task }: { task: Task }) {
  const due = task.due_at ? dueLabel(task.due_at) : null;
  return (
    <>
      <span className="charttip__title">{task.title}</span>
      <span className="charttip__meta">
        {task.due_at ? `${formatDate(task.due_at)} · ` : ""}
        {STATUS_LABEL[task.status]}
        {task.assignee ? ` · ${task.assignee.name}` : ""}
      </span>
      {due && due.tone === "late" ? (
        <span className="charttip__meta charttip__warn">{due.text}</span>
      ) : null}
    </>
  );
}

/** The card that names a meeting: when it is, where, and who comes. */
function EventTip({ event }: { event: ScheduleEvent }) {
  const people = event.attendees?.length ?? 0;
  return (
    <>
      <span className="charttip__title">{event.title}</span>
      <span className="charttip__meta">
        {formatDate(event.starts_at)} ·{" "}
        {event.all_day ? "종일" : formatTime(event.starts_at)}
      </span>
      {event.location || people ? (
        <span className="charttip__meta">
          {event.location ? `${event.location} · ` : ""}
          {people ? `${people}명` : ""}
        </span>
      ) : null}
    </>
  );
}
