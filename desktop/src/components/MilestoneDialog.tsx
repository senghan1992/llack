import { useEffect, useMemo, useRef, useState } from "react";
import { Dialog } from "./Dialogs";
import { useStore } from "../store/useStore";
import { toDateInput } from "../lib/calendar";
import type { Milestone, MilestoneInput, Task, TaskStatus } from "../lib/types";

/**
 * The colours a milestone may wear. They are data, not theme colours: the
 * company picks one, and the milestone keeps it.
 */
const PRESET_COLORS = ["#4f6cff", "#10b981", "#f43f5e", "#f59e0b", "#8b5cf6", "#06b6d4"];

const STATUS_LABEL: Record<TaskStatus, string> = {
  request: "요청",
  todo: "할 일",
  "in-progress": "진행 중",
  done: "완료",
};

/**
 * The inverse of `toDateInput`: a day of the reader's own calendar as an
 * instant the server can store. A period opens at the first moment of its
 * first day and closes at the last moment of its last day.
 */
function dateToIso(day: string, endOfDay: boolean): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(
    year,
    month - 1,
    date,
    endOfDay ? 23 : 0,
    endOfDay ? 59 : 0,
    0,
    0,
  ).toISOString();
}

/** A milestone, wherever it lives. */
function findMilestone(
  milestones: Record<string, Milestone[]>,
  milestoneId: string,
): Milestone | null {
  for (const list of Object.values(milestones)) {
    const found = list.find((milestone) => milestone.id === milestoneId);
    if (found) return found;
  }
  return null;
}

/**
 * The milestone dialog — the same one for making and for changing. A
 * milestone is a period with a colour, a progress and the cards that
 * belong to it.
 */
export function MilestoneDialog() {
  const target = useStore((s) => s.dialogTarget);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const milestones = useStore((s) => s.milestones);
  const tasks = useStore((s) => s.tasks);
  const createMilestone = useStore((s) => s.createMilestone);
  const updateMilestone = useStore((s) => s.updateMilestone);
  const setDialog = useStore((s) => s.setDialog);

  const existing = useMemo(
    () => (target ? findMilestone(milestones, target) : null),
    [milestones, target],
  );

  const projectId = existing?.project_id ?? activeProjectId;
  const projectTasks: Task[] = useMemo(
    () => (projectId ? (tasks[projectId] ?? []) : []),
    [tasks, projectId],
  );
  const projectMilestones: Milestone[] = useMemo(
    () => (projectId ? (milestones[projectId] ?? []) : []),
    [milestones, projectId],
  );

  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [color, setColor] = useState(PRESET_COLORS[0]);
  const [progress, setProgress] = useState(0);
  const [description, setDescription] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The dialog opens on the milestone it is about — or on an empty one.
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = existing?.id ?? "new";
    if (loadedFor.current === key) return;
    loadedFor.current = key;
    if (existing) {
      setTitle(existing.title);
      setStartDate(toDateInput(existing.start_at));
      setEndDate(toDateInput(existing.end_at));
      setColor(existing.color || PRESET_COLORS[0]);
      setProgress(existing.manual_progress);
      setDescription(existing.description);
      // The cards that hang on it: the server's list, or the cards of the
      // project that carry it.
      const fromTasks = projectTasks
        .filter((task) => task.milestone_id === existing.id)
        .map((task) => task.id);
      setPicked(existing.task_ids?.length ? existing.task_ids : fromTasks);
    } else {
      setTitle("");
      setStartDate("");
      setEndDate("");
      setColor(PRESET_COLORS[0]);
      setProgress(0);
      setDescription("");
      setPicked([]);
    }
    setError(null);
    setBusy(false);
  }, [existing, projectTasks]);

  /** The cards that are picked, and how many of them are done. */
  const linked = useMemo(
    () => projectTasks.filter((task) => picked.includes(task.id)),
    [projectTasks, picked],
  );
  const total = linked.length === picked.length && picked.length > 0
    ? linked.length
    : (existing?.task_count ?? 0);
  const done = linked.length === picked.length && picked.length > 0
    ? linked.filter((task) => task.status === "done").length
    : (existing?.done_count ?? 0);
  const auto = picked.length > 0;
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;

  const toggleTask = (taskId: string) => {
    setPicked((current) =>
      current.includes(taskId)
        ? current.filter((id) => id !== taskId)
        : [...current, taskId],
    );
  };

  const submit = async () => {
    const trimmed = title.trim();
    if (!trimmed) {
      setError("마일스톤 제목을 입력해 주세요");
      return;
    }
    if (!startDate || !endDate) {
      setError("시작일과 종료일을 입력해 주세요");
      return;
    }
    if (endDate < startDate) {
      setError("종료일은 시작일보다 빠를 수 없습니다");
      return;
    }
    if (!projectId) {
      setError("프로젝트를 먼저 골라 주세요");
      return;
    }
    setBusy(true);
    setError(null);
    const input: MilestoneInput = {
      title: trimmed,
      start_at: dateToIso(startDate, false),
      end_at: dateToIso(endDate, true),
      color,
      progress,
      description: description.trim(),
      task_ids: picked,
    };
    try {
      if (existing) await updateMilestone(existing.id, input);
      else await createMilestone(projectId, input);
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "마일스톤을 저장하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={existing ? "마일스톤" : "새 마일스톤"}
      onClose={() => setDialog(null)}
      wide
      footer={
        <>
          <span className="u-grow" />
          <button
            type="button"
            className="btn"
            onClick={() => setDialog(null)}
            disabled={busy}
          >
            취소
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? "저장 중…" : existing ? "수정" : "추가"}
          </button>
        </>
      }
    >
      <div className="dialog__body u-col u-gap-4">
        {error ? <p className="field__error">{error}</p> : null}

        <div className="field">
          <label className="field__label" htmlFor="ms-title">
            제목
          </label>
          <input
            id="ms-title"
            className="field__input"
            autoFocus
            value={title}
            placeholder="마일스톤 이름을 입력해 주세요"
            maxLength={120}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        <div className="field">
          <span className="field__label">기간</span>
          <div className="msdlg__dates">
            <label className="msdlg__date">
              <span className="msdlg__datelabel">시작일</span>
              <input
                type="date"
                className="field__input"
                value={startDate}
                required
                onChange={(event) => {
                  setStartDate(event.target.value);
                  // The period may not end before it opens.
                  if (endDate && endDate < event.target.value) setEndDate(event.target.value);
                }}
              />
            </label>
            <label className="msdlg__date">
              <span className="msdlg__datelabel">종료일</span>
              <input
                type="date"
                className="field__input"
                value={endDate}
                min={startDate || undefined}
                required
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
          </div>
        </div>

        <div className="field">
          <span className="field__label">색상</span>
          <div className="swatches">
            {PRESET_COLORS.map((value) => (
              <button
                key={value}
                type="button"
                className={`swatch${value === color ? " swatch--on" : ""}`}
                style={{ ["--swatch" as string]: value }}
                onClick={() => setColor(value)}
                aria-label={`색상 ${value}`}
                aria-pressed={value === color}
              />
            ))}
            <span
              className="swatch swatch--free msdlg__free"
              style={{ ["--swatch" as string]: color }}
            >
              <input
                type="color"
                value={color}
                onChange={(event) => setColor(event.target.value)}
                aria-label="직접 고른 색상"
              />
            </span>
            <span className="swatches__hex">{color}</span>
          </div>
        </div>

        <div className="field">
          <div className="u-row u-row--center u-gap-2">
            <span className="field__label u-grow">진행률</span>
            <span className="msdlg__percent">{auto ? `${percent}%` : `${progress}%`}</span>
          </div>
          {auto ? (
            <p className="msdlg__auto">
              ✓ 연결된 태스크 기반 자동 계산 ({done}/{total} 완료)
            </p>
          ) : (
            <input
              type="range"
              className="msrange"
              min={0}
              max={100}
              step={5}
              value={progress}
              onChange={(event) => setProgress(Number(event.target.value))}
              aria-label="진행률"
            />
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="ms-desc">
            설명
          </label>
          <textarea
            id="ms-desc"
            className="field__input u-h-auto u-minh-72 u-full u-py-2"
            value={description}
            placeholder="마일스톤에 대한 간단한 설명"
            maxLength={4000}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        {projectTasks.length ? (
          <div className="field">
            <div className="u-row u-row--center u-gap-2">
              <span className="field__label u-grow">태스크 연결</span>
              {picked.length ? (
                <span className="msdlg__count">{picked.length}개 선택됨</span>
              ) : null}
            </div>
            <div className="msdlg__tasks">
              {projectTasks.map((task) => {
                const isPicked = picked.includes(task.id);
                const other =
                  task.milestone_id && task.milestone_id !== target
                    ? projectMilestones.find(
                        (milestone) => milestone.id === task.milestone_id,
                      )
                    : null;
                return (
                  <label
                    key={task.id}
                    className={`msdlg__task${task.status === "done" ? " msdlg__task--done" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={isPicked}
                      onChange={() => toggleTask(task.id)}
                    />
                    <span className={`badge badge--${task.status}`}>
                      {STATUS_LABEL[task.status]}
                    </span>
                    <span className="msdlg__tasktitle u-truncate">{task.title}</span>
                    {other ? <span className="mschip">{other.title}</span> : null}
                  </label>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
