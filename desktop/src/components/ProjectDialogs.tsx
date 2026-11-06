import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Hash, Lock, MessageSquare, Trash2, Unlink, UserX, X } from "lucide-react";
import { Dialog } from "./Dialogs";
import { Avatar } from "./Avatar";
import { MemberSelect } from "./MemberSelect";
import { Select } from "./Select";
import { useStore } from "../store/useStore";
import { toDateInput } from "../lib/calendar";
import { dateRange, relativeTime } from "../lib/format";
import type { TaskStatus } from "../lib/types";

const STATUS_LABEL: Record<TaskStatus, string> = {
  request: "요청",
  todo: "할 일",
  "in-progress": "진행 중",
  done: "완료",
};

/** The last moment of a day, in the reader's own timezone. */
function endOfDayIso(dateKey: string): string {
  const [year, month, day] = dateKey.split("-").map(Number);
  return new Date(year, month - 1, day, 23, 59, 0, 0).toISOString();
}

/* ── the project itself ─────────────────────────────────────────────── */

export function ProjectDialog() {
  const target = useStore((s) => s.dialogTarget);
  const projects = useStore((s) => s.projects);
  const members = useStore((s) => s.members);
  const channels = useStore((s) => s.channels);
  const user = useStore((s) => s.user);
  const setDialog = useStore((s) => s.setDialog);
  const createProject = useStore((s) => s.createProject);
  const updateProject = useStore((s) => s.updateProject);
  const deleteProject = useStore((s) => s.deleteProject);
  const removeProjectMember = useStore((s) => s.removeProjectMember);
  const reportError = useStore((s) => s.reportError);

  const existing = useMemo(
    () => (target ? projects.find((project) => project.id === target) ?? null : null),
    [projects, target],
  );

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [channelId, setChannelId] = useState("");
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    const key = existing?.id ?? "new";
    if (loadedFor.current === key) return;
    loadedFor.current = key;
    if (existing) {
      setName(existing.name);
      setDescription(existing.description);
      setChannelId(existing.channel_id ?? "");
      setMemberIds(existing.members.map((member) => member.id));
    } else {
      setName("");
      setDescription("");
      setChannelId("");
      setMemberIds(user ? [user.id] : []);
    }
    setError(null);
    setBusy(false);
  }, [existing, user]);

  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const canManage = Boolean(
    existing && (existing.created_by === user?.id || myRole === "owner" || myRole === "admin"),
  );
  const isNew = !target;
  const vanished = Boolean(target && !existing);
  const readOnly = !isNew && !canManage;

  const roster = members.filter((member) => memberIds.includes(member.user.id));

  const save = async () => {
    if (!name.trim()) {
      setError("프로젝트 이름을 입력해 주세요");
      return;
    }
    setBusy(true);
    setError(null);
    const payload = {
      name: name.trim(),
      description: description.trim(),
      channel_id: channelId || null,
      member_ids: memberIds,
    };
    try {
      if (existing) await updateProject(existing.id, payload);
      else await createProject(payload);
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "프로젝트를 저장하지 못했습니다");
      reportError(err, "프로젝트를 저장하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!existing) return;
    setBusy(true);
    try {
      await deleteProject(existing.id);
      setDialog(null);
    } catch (err) {
      reportError(err, "프로젝트를 삭제하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={isNew ? "프로젝트 등록" : "프로젝트"}
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
            <p className="empty__title">프로젝트가 없어졌습니다</p>
            <p className="empty__text">삭제되었거나 볼 수 없게 된 프로젝트입니다.</p>
          </div>
        ) : null}

        {!vanished ? (
          <>
            <label className="field">
              <span className="field__label">프로젝트 이름</span>
              <input
                className="field__input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="결제 시스템 개편"
                autoFocus
                maxLength={120}
              />
            </label>

            <label className="field">
              <span className="field__label">설명</span>
              <textarea
                className="field__input u-h-auto u-minh-72 u-full u-py-2"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="구독 결제를 다시 만들고, 정산을 한곳에 모읍니다."
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
              <span className="field__hint">
                이 프로젝트에 대한 이야기를 나누는 방입니다. 보드에서 바로 그 방으로 갈 수
                있습니다.
              </span>
            </label>

            <div className="field">
              <span className="field__label">함께하는 사람</span>
              {roster.length ? (
                <div className="proj__roster">
                  {roster.map((member) => (
                    <span key={member.user.id} className="proj__rosteritem">
                      <Avatar user={member.user} size="sm" />
                      <span className="u-truncate">{member.user.name}</span>
                      {canManage && member.user.id !== existing?.created_by ? (
                        <button
                          type="button"
                          className="iconbtn proj__rosterx"
                          aria-label={`${member.user.name}님 빼기`}
                          onClick={() => {
                            const next = memberIds.filter((id) => id !== member.user.id);
                            setMemberIds(next);
                            if (existing) {
                              void removeProjectMember(existing.id, member.user.id);
                            }
                          }}
                        >
                          <X size={12} aria-hidden="true" />
                        </button>
                      ) : null}
                    </span>
                  ))}
                </div>
              ) : null}
              <MemberSelect
                members={members}
                value={memberIds}
                onChange={setMemberIds}
                placeholder="함께하는 사람 선택"
              />
              <span className="field__hint">
                이름이 올라간 사람이 이 프로젝트의 담당자입니다. “내 프로젝트”에서 이
                프로젝트만 볼 수 있습니다.
              </span>
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}

/* ── one task on the board ──────────────────────────────────────────── */

export function TaskDialog() {
  const target = useStore((s) => s.dialogTarget);
  const projects = useStore((s) => s.projects);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const roadmaps = useStore((s) => s.roadmaps);
  const milestones = useStore((s) => s.milestones);
  const loadMilestones = useStore((s) => s.loadMilestones);
  const tasks = useStore((s) => s.tasks);
  const members = useStore((s) => s.members);
  const user = useStore((s) => s.user);
  const setDialog = useStore((s) => s.setDialog);
  const createTask = useStore((s) => s.createTask);
  const updateTask = useStore((s) => s.updateTask);
  const deleteTask = useStore((s) => s.deleteTask);
  const addTaskComment = useStore((s) => s.addTaskComment);
  const deleteTaskComment = useStore((s) => s.deleteTaskComment);
  const reportError = useStore((s) => s.reportError);

  const existing = useMemo(() => {
    if (!target) return null;
    for (const list of Object.values(tasks)) {
      const found = list.find((task) => task.id === target);
      if (found) return found;
    }
    return null;
  }, [tasks, target]);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<TaskStatus>("todo");
  const [assigneeId, setAssigneeId] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [projectId, setProjectId] = useState("");
  const [roadmapId, setRoadmapId] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedFor = useRef<string | null>(null);

  /** The project the task sits in — the one that was picked, or the one it had. */
  const project = projects.find((item) => item.id === projectId) ?? null;

  /** The roadmaps of the project the task is going to sit in. */
  const projectRoadmaps = useMemo(
    () => (projectId ? (roadmaps[projectId] ?? []) : []),
    [roadmaps, projectId],
  );

  /** The milestones of the project the task is going to sit in. */
  const projectMilestones = useMemo(
    () => (projectId ? (milestones[projectId] ?? []) : []),
    [milestones, projectId],
  );

  useEffect(() => {
    const key = existing?.id ?? "new";
    if (loadedFor.current === key) return;
    loadedFor.current = key;
    if (existing) {
      setTitle(existing.title);
      setDescription(existing.description);
      setStatus(existing.status);
      setAssigneeId(existing.assignee_id ?? "");
      setDueDate(existing.due_at ? toDateInput(existing.due_at) : "");
      setProjectId(existing.project_id);
      setRoadmapId(existing.roadmap_id ?? "");
      setMilestoneId(existing.milestone_id ?? "");
    } else {
      setTitle("");
      setDescription("");
      setStatus("todo");
      setAssigneeId(user?.id ?? "");
      setDueDate("");
      setProjectId(activeProjectId ?? projects[0]?.id ?? "");
      setRoadmapId("");
      setMilestoneId("");
    }
    setComment("");
    setError(null);
    setBusy(false);
  }, [existing, user]);

  // A new task lands on the board that is open — or on the first project.
  useEffect(() => {
    if (existing || projectId) return;
    const fallback = activeProjectId ?? projects[0]?.id ?? "";
    if (fallback) setProjectId(fallback);
  }, [existing, projectId, activeProjectId, projects]);

  // The milestones of the project — the list the field picks from.
  useEffect(() => {
    if (!projectId || milestones[projectId]) return;
    void loadMilestones(projectId);
  }, [projectId, milestones, loadMilestones]);

  const isNew = !target;
  const vanished = Boolean(target && !existing);

  // A card is removed by the hand that made it, by the owner of the
  // project, or by an administrator — the same rule the server keeps.
  const myRole = members.find((member) => member.user.id === user?.id)?.role;
  const canDelete = Boolean(
    existing &&
      (existing.created_by === user?.id ||
        project?.created_by === user?.id ||
        myRole === "owner" ||
        myRole === "admin"),
  );

  const save = async () => {
    if (!title.trim()) {
      setError("할 일 제목을 입력해 주세요");
      return;
    }
    if (!projectId) {
      setError("프로젝트를 먼저 골라 주세요");
      return;
    }
    setBusy(true);
    setError(null);
    const payload = {
      title: title.trim(),
      description: description.trim(),
      status,
      assignee_id: assigneeId || null,
      due_at: dueDate ? endOfDayIso(dueDate) : null,
      milestone_id: milestoneId || null,
      roadmap_id: roadmapId || null,
    };
    try {
      if (existing) await updateTask(existing.id, payload);
      else await createTask(projectId, payload);
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "할 일을 저장하지 못했습니다");
      reportError(err, "할 일을 저장하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!existing) return;
    setBusy(true);
    try {
      await deleteTask(existing.id);
      setDialog(null);
    } catch (err) {
      reportError(err, "할 일을 삭제하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const writeComment = async () => {
    if (!existing || !comment.trim()) return;
    try {
      await addTaskComment(existing.id, comment.trim());
      setComment("");
    } catch (err) {
      reportError(err, "의견을 남기지 못했습니다");
    }
  };

  return (
    <Dialog
      title={isNew ? "할 일 추가" : "할 일"}
      onClose={() => setDialog(null)}
      wide
      footer={
        <>
          {existing && canDelete ? (
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
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => void save()}
            disabled={busy || !projectId}
          >
            {busy ? "저장 중" : "저장"}
          </button>
        </>
      }
    >
      <div className="dialog__body u-col u-gap-4">
        {error ? <p className="field__error">{error}</p> : null}

        {vanished ? (
          <div className="empty">
            <p className="empty__title">할 일이 없어졌습니다</p>
            <p className="empty__text">삭제되었거나 다른 사람이 옮긴 할 일입니다.</p>
          </div>
        ) : null}

        {!vanished ? (
          <>
            {existing ? (
              project ? (
                <p className="taskdlg__project">
                  <Lock size={12} aria-hidden="true" />
                  {project.name}
                </p>
              ) : null
            ) : (
              <label className="field">
                <span className="field__label">프로젝트</span>
                <Select
                  value={projectId}
                  onChange={(next) => {
                    setProjectId(next);
                    // The roadmaps of one project do not belong to another.
                    setRoadmapId("");
                  }}
                  placeholder="프로젝트가 없습니다"
                  disabled={projects.length === 0}
                  options={projects.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                />
              </label>
            )}

            {projectRoadmaps.length ? (
              <label className="field">
                <span className="field__label">로드맵</span>
                <Select
                  value={roadmapId}
                  onChange={setRoadmapId}
                  options={[
                    { value: "", label: "로드맵 없음" },
                    ...projectRoadmaps.map((item) => ({
                      value: item.id,
                      label: item.name,
                    })),
                  ]}
                />
              </label>
            ) : null}

            <label className="field">
              <span className="field__label">마일스톤</span>
              <Select
                value={milestoneId}
                onChange={setMilestoneId}
                options={
                  projectMilestones.length
                    ? [
                        { value: "", label: "선택 안 함" },
                        ...projectMilestones.map((item) => ({
                          value: item.id,
                          label: `${item.title} (${dateRange(item.start_at, item.end_at)})`,
                        })),
                      ]
                    : [
                        { value: "", label: "선택 안 함" },
                        { value: "none", label: "등록된 마일스톤이 없습니다", disabled: true },
                      ]
                }
              />
            </label>

            <label className="field">
              <span className="field__label">할 일</span>
              <input
                className="field__input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="PG사 계약 조건 정리"
                autoFocus
                maxLength={200}
              />
            </label>

            <label className="field">
              <span className="field__label">설명</span>
              <textarea
                className="field__input u-h-auto u-minh-72 u-full u-py-2"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="무엇을 해야 하는지, 무엇이 끝나야 하는지"
                maxLength={4000}
              />
            </label>

            <div className="field">
              <span className="field__label">어디까지 했어요</span>
              <div className="u-row u-row--wrap u-gap-2">
                {(Object.keys(STATUS_LABEL) as TaskStatus[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={`btn btn--sm${status === value ? " btn--primary" : ""}`}
                    onClick={() => setStatus(value)}
                  >
                    {STATUS_LABEL[value]}
                  </button>
                ))}
              </div>
            </div>

            <label className="field">
              <span className="field__label">담당자</span>
              <Select
                value={assigneeId}
                onChange={setAssigneeId}
                options={[
                  {
                    value: "",
                    label: "담당 없음",
                    lead: <UserX size={13} aria-hidden="true" />,
                  },
                  ...members.map((member) => ({
                    value: member.user.id,
                    label: member.user.name,
                    lead: <Avatar user={member.user} size="sm" />,
                  })),
                ]}
              />
            </label>

            <label className="field">
              <span className="field__label">마감일</span>
              <input
                type="date"
                className="field__input"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
              />
            </label>

            {existing ? (
              <section className="field">
                <span className="field__label">
                  <MessageSquare size={12} aria-hidden="true" /> 의견 {existing.comment_count}
                </span>
                {existing.comments.length ? (
                  <ul className="taskdlg__comments">
                    {existing.comments.map((item) => (
                      <li key={item.id} className="taskdlg__comment">
                        <Avatar user={item.author} size="sm" />
                        <div className="u-col u-gap-1 u-grow">
                          <span className="taskdlg__commentmeta">
                            {item.author.name}
                            <span className="u-muted"> · {relativeTime(item.created_at)}</span>
                          </span>
                          <p className="taskdlg__commentbody">{item.body}</p>
                        </div>
                        {item.user_id === user?.id ? (
                          <button
                            type="button"
                            className="iconbtn"
                            aria-label="의견 삭제"
                            onClick={() => void deleteTaskComment(item.id)}
                          >
                            <X size={13} aria-hidden="true" />
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="u-small u-muted">아직 의견이 없습니다.</p>
                )}
                <div className="taskdlg__write">
                  <input
                    className="field__input"
                    value={comment}
                    placeholder="의견 남기기"
                    maxLength={2000}
                    onChange={(event) => setComment(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void writeComment();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => void writeComment()}
                    disabled={!comment.trim()}
                  >
                    <Check size={13} aria-hidden="true" />
                    남기기
                  </button>
                </div>
              </section>
            ) : null}
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
