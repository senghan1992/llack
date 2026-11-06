import { useState } from "react";
import { Flag, Pencil, Plus, Trash2 } from "lucide-react";
import { ConfirmDialog } from "./ConfirmDialog";
import { useStore } from "../store/useStore";
import { dateRange } from "../lib/format";
import type { Milestone, Project, Task } from "../lib/types";

/** Empty lists are one object, not one per render. */
const NO_MILESTONES: Milestone[] = [];
const NO_TASKS: Task[] = [];

/**
 * The milestone panel — the board's other face. A milestone is not a lane
 * and not a column: it is a period with a colour, a progress and the cards
 * that belong to it.
 */
export function MilestonePanel({ project }: { project: Project }) {
  const milestoneList = useStore((s) => s.milestones[project.id]);
  const taskList = useStore((s) => s.tasks[project.id]);
  const loading = useStore((s) => s.milestonesLoading);
  const error = useStore((s) => s.milestonesError);
  const loadMilestones = useStore((s) => s.loadMilestones);
  const deleteMilestone = useStore((s) => s.deleteMilestone);
  const setDialog = useStore((s) => s.setDialog);
  const reportError = useStore((s) => s.reportError);
  /** The milestone that is about to be deleted — it asks first. */
  const [pending, setPending] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const milestones = milestoneList ?? NO_MILESTONES;
  const tasks = taskList ?? NO_TASKS;
  const pendingTitle = milestones.find((item) => item.id === pending)?.title ?? "";

  /** The modal asks first; the milestone goes only when the answer is yes. */
  const confirmDelete = async () => {
    if (!pending) return;
    setDeleting(true);
    try {
      await deleteMilestone(pending);
      setPending(null);
    } catch (error) {
      reportError(error, "마일스톤을 삭제하지 못했습니다");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="mspanel">
      <header className="mspanel__head">
        {/* The panel says what a milestone is — the word alone is jargon. */}
        <p className="mspanel__hint">
          기한이 있는 목표입니다. 기간과 진행률, 거기에 붙은 할 일이 함께 보입니다.
        </p>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={() => setDialog("milestone", null)}
        >
          <Plus size={13} aria-hidden="true" />
          마일스톤 추가
        </button>
      </header>

      {error ? (
        <div className="errorstate">
          <p className="errorstate__title">마일스톤을 불러오지 못했습니다</p>
          <p className="errorstate__text">{error}</p>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => void loadMilestones(project.id)}
          >
            다시 시도
          </button>
        </div>
      ) : null}

      {!error && loading && milestones.length === 0 ? (
        <div className="u-col u-gap-3" aria-hidden="true">
          {[0, 1, 2].map((row) => (
            <span key={row} className="skel u-h-12 u-full" />
          ))}
        </div>
      ) : null}

      {!error && !loading && milestones.length === 0 ? (
        <div className="empty">
          <span className="empty__mark" aria-hidden="true">
            <Flag size={20} />
          </span>
          <p className="empty__title">이 프로젝트에는 마일스톤이 없습니다</p>
          <p className="empty__text">
            기한이 있는 목표를 마일스톤으로 만들고, 그에 닿는 할 일을 연결해 보세요.
          </p>
        </div>
      ) : null}

      {milestones.length ? (
        <ul className="mspanel__list">
          {milestones.map((milestone) => {
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
                  <span className="mscard__title u-truncate">{milestone.title}</span>
                  <span className="mscard__dates">
                    {dateRange(milestone.start_at, milestone.end_at)}
                  </span>
                  <span className="u-grow" />
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label={`${milestone.title} 마일스톤 수정`}
                    onClick={() => setDialog("milestone", milestone.id)}
                  >
                    <Pencil size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label={`${milestone.title} 마일스톤 삭제`}
                    onClick={() => setPending(milestone.id)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>

                <div className="mscard__row">
                  <span className="msbar">
                    <span
                      className="msbar__fill"
                      style={{ width: `${Math.max(0, Math.min(100, milestone.progress))}%` }}
                    />
                  </span>
                  <span className="mscard__count">
                    {milestone.auto_progress
                      ? `${milestone.done_count}/${milestone.task_count}`
                      : `${milestone.progress}%`}
                  </span>
                </div>

                {milestone.description ? (
                  <p className="mscard__desc">{milestone.description}</p>
                ) : null}

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

      {pending ? (
        <ConfirmDialog
          title="마일스톤 삭제"
          message={
            <>
              <strong>{pendingTitle}</strong> 마일스톤을 삭제할까요?
            </>
          }
          detail="연결된 할 일은 그대로 남습니다. 마일스톤만 사라집니다."
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onClose={() => setPending(null)}
        />
      ) : null}
    </div>
  );
}
