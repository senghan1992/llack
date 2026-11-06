import { useEffect, useMemo, useState } from "react";
import { ChartNoAxesGantt } from "lucide-react";
import { Dialog } from "./Dialogs";
import { api } from "../lib/api";
import { useStore } from "../store/useStore";
import { dateRange, formatDate } from "../lib/format";
import { dayStart, monthCells, monthStartOf, nextDay, ratio } from "../lib/gantt";
import type { Milestone, ScheduleEvent, Task } from "../lib/types";

/** The status of a card on the timeline — the same four the board has. */
const STATUS_TONE: Record<Task["status"], string> = {
  request: "var(--color-muted)",
  todo: "var(--color-ink-2)",
  "in-progress": "var(--color-warn)",
  done: "var(--color-accent)",
};

/**
 * The project chart — the Gantt view of one project's work.
 *
 * It answers one question at a glance: when is what due, and how far
 * along is it. The bars are the milestones, the dots are the cards that
 * carry their own deadline, the notches are the team's calendar, and the
 * list under the chart says the same thing in words.
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

  const inSpan = useMemo(() => {
    if (!span) return [];
    return events.filter((event) => {
      const start = dayStart(event.starts_at);
      const end = nextDay(event.ends_at);
      return end > span.start && start < span.end;
    });
  }, [events, span]);

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
                    boundaries and today run through every row at once. */}
                <div className="chart__overlay" aria-hidden="true">
                  {span.cells.slice(1).map((cell) => (
                    <span
                      key={cell.key}
                      className="chart__gridline"
                      style={{
                        left: `${ratio(cell.start, span.start, span.end) * 100}%`,
                      }}
                    />
                  ))}
                  {today >= span.start && today <= span.end ? (
                    <span
                      className="chart__today"
                      style={{
                        left: `${ratio(today, span.start, span.end) * 100}%`,
                      }}
                    />
                  ) : null}
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
                  return (
                    <div key={milestone.id} className="chart__row">
                      <span className="chart__label u-truncate">
                        <span
                          className="chart__dot"
                          style={{ ["--ms-color" as string]: milestone.color }}
                          aria-hidden="true"
                        />
                        {milestone.title}
                      </span>
                      <div className="chart__track">
                        <span
                          className="chart__bar"
                          style={{
                            left: `${left * 100}%`,
                            width: `${Math.max(right - left, 0.006) * 100}%`,
                            ["--ms-color" as string]: milestone.color,
                          }}
                        >
                          <span
                            className="chart__barfill"
                            style={{
                              width: `${Math.max(0, Math.min(100, milestone.progress))}%`,
                            }}
                          />
                        </span>
                      </div>
                    </div>
                  );
                })}

                {dated.length ? (
                  <div className="chart__row">
                    <span className="chart__label chart__label--quiet">
                      카드 마감일
                    </span>
                    <div className="chart__track chart__track--dots">
                      {dated.map((task) => (
                        <span
                          key={task.id}
                          className="chart__dotmark"
                          style={{
                            left: `${ratio(dayStart(task.due_at), span.start, span.end) * 100}%`,
                            ["--dot-tone" as string]: STATUS_TONE[task.status],
                          }}
                          title={`${task.title} · ${formatDate(task.due_at)} 마감`}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}

                {inSpan.length ? (
                  <div className="chart__row">
                    <span className="chart__label chart__label--quiet">
                      팀 일정
                    </span>
                    <div className="chart__track chart__track--dots">
                      {inSpan.map((event) => (
                        <span
                          key={event.id}
                          className="chart__notch"
                          style={{
                            left: `${ratio(dayStart(event.starts_at), span.start, span.end) * 100}%`,
                          }}
                          title={`${event.title} · ${formatDate(event.starts_at)}`}
                        />
                      ))}
                    </div>
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
                  <span className="chart__legendnotch" aria-hidden="true" />
                  팀 일정
                </span>
              ) : null}
              <span className="chart__legenditem">
                <span className="chart__legendtoday" aria-hidden="true" />
                오늘
              </span>
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
    </Dialog>
  );
}
