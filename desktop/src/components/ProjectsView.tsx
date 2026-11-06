import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FolderKanban,
  Hash,
  ListChecks,
  Menu as MenuIcon,
  MessageSquare,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { ConfirmDialog } from "./ConfirmDialog";
import { Menu } from "./Menu";
import { MilestonePanel } from "./MilestonePanel";
import { useStore } from "../store/useStore";
import { periodLabel } from "../lib/format";
import type { Task, TaskStatus } from "../lib/types";

/** The four columns of a board, in the order the work moves through them. */
const COLUMNS: { status: TaskStatus; label: string; hint: string }[] = [
  { status: "request", label: "요청", hint: "누군가 요청한 것" },
  { status: "todo", label: "할 일", hint: "맡은 것" },
  { status: "in-progress", label: "진행 중", hint: "지금 하는 것" },
  { status: "done", label: "완료", hint: "끝난 것" },
];

const STATUS_LABEL: Record<TaskStatus, string> = {
  request: "요청",
  todo: "할 일",
  "in-progress": "진행 중",
  done: "완료",
};

/** How many of my tasks the sidebar shows before it says "and the rest". */
const MINE_LIMIT = 8;

export function ProjectsHead({
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
        <FolderKanban size={17} className="u-muted" aria-hidden="true" />
        <div className="head__id">
          <span className="head__name">프로젝트</span>
        </div>
        <span className="head__topic">프로젝트와 할 일을 한곳에서 봅니다</span>
        <div className="head__actions">
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => setDialog("project", null)}
          >
            <Plus size={13} aria-hidden="true" />
            프로젝트 등록
          </button>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => setDialog("task", null)}
          >
            <Plus size={13} aria-hidden="true" />
            할 일 추가
          </button>
          {actions}
        </div>
      </div>
    </header>
  );
}

export function ProjectsView() {
  const projects = useStore((s) => s.projects);
  const loading = useStore((s) => s.projectsLoading);
  const error = useStore((s) => s.projectsError);
  const filter = useStore((s) => s.projectFilter);
  const setFilter = useStore((s) => s.setProjectFilter);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const selectProject = useStore((s) => s.selectProject);
  const tasks = useStore((s) => s.tasks);
  const myTasks = useStore((s) => s.myTasks);
  const boardMode = useStore((s) => s.boardMode);
  const setBoardMode = useStore((s) => s.setBoardMode);
  const ensureProjects = useStore((s) => s.ensureProjects);
  const setDialog = useStore((s) => s.setDialog);
  const openChannel = useStore((s) => s.openChannel);
  const channels = useStore((s) => s.channels);
  const moveTask = useStore((s) => s.moveTask);
  const roadmaps = useStore((s) => s.roadmaps);
  const activeRoadmapId = useStore((s) => s.activeRoadmapId);
  const setActiveRoadmap = useStore((s) => s.setActiveRoadmap);
  const deleteRoadmap = useStore((s) => s.deleteRoadmap);
  const reportError = useStore((s) => s.reportError);

  const [pendingRoadmap, setPendingRoadmap] = useState<string | null>(null);
  const [deletingRoadmap, setDeletingRoadmap] = useState(false);
  const [projectAnchor, setProjectAnchor] = useState<HTMLElement | null>(null);

  // The board loads its work; where it sits on the screen is the rail's
  // business, not the board's.
  useEffect(() => {
    void ensureProjects();
  }, [ensureProjects]);

  const visible = useMemo(
    () => (filter === "mine" ? projects.filter((project) => project.is_member) : projects),
    [projects, filter],
  );

  /** Which project a task belongs to — the list says the title, this says where. */
  const projectNameOf = (projectId: string) =>
    projects.find((item) => item.id === projectId)?.name ?? "";

  /**
   * My tasks, in the order the board moves: 요청 → 할 일 → 진행 중. The
   * list then reads like the board it belongs to.
   */
  const mineRows = useMemo(() => {
    const order = COLUMNS.map((column) => column.status);
    return [...myTasks]
      .sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
      .slice(0, MINE_LIMIT);
  }, [myTasks]);

  const project = useMemo(
    () => projects.find((item) => item.id === activeProjectId) ?? null,
    [projects, activeProjectId],
  );

  /** The milestones of the project on the board — the goals it aims at. */
  const milestoneCount = useStore((s) => (project ? (s.milestones[project.id] ?? []).length : 0));

  /** How far the project has come — the cards that are finished. */
  const progress = useMemo(() => {
    const total = project?.total_tasks ?? 0;
    if (!total) return 0;
    return Math.round(((project?.done_tasks ?? 0) * 100) / total);
  }, [project]);

  /** The roadmaps of the project on the board — the lanes it is planned in. */
  const projectRoadmaps = useMemo(
    () => (project ? (roadmaps[project.id] ?? []) : []),
    [roadmaps, project],
  );

  const board = useMemo(() => {
    const list = project ? (tasks[project.id] ?? []) : [];
    // A lane shows only its own cards; the whole board shows every card.
    const shown = activeRoadmapId
      ? list.filter((task) => task.roadmap_id === activeRoadmapId)
      : list;
    const map = new Map<TaskStatus, Task[]>();
    for (const column of COLUMNS) map.set(column.status, []);
    for (const task of shown) {
      const bucket = map.get(task.status);
      if (bucket) bucket.push(task);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => a.position - b.position);
    }
    return map;
  }, [tasks, project, activeRoadmapId]);

  const room = project?.channel_id
    ? channels.find((channel) => channel.id === project.channel_id) ?? null
    : null;


  /** A roadmap goes away — the tasks on it stay. */
  const removeRoadmap = async (roadmapId: string): Promise<boolean> => {
    if (!project) return false;
    try {
      await deleteRoadmap(project.id, roadmapId);
      return true;
    } catch (error) {
      reportError(error, "로드맵을 삭제하지 못했습니다");
      return false;
    }
  };

  /** The modal asks first; the lane goes only when the answer is yes. */
  const confirmRemoveRoadmap = async () => {
    if (!pendingRoadmap) return;
    setDeletingRoadmap(true);
    const gone = await removeRoadmap(pendingRoadmap);
    setDeletingRoadmap(false);
    if (gone) setPendingRoadmap(null);
  };

  const pendingRoadmapName =
    projectRoadmaps.find((item) => item.id === pendingRoadmap)?.name ?? "";

  return (
    <div className="proj">
      <aside className="proj__list" aria-label="프로젝트 목록">
        <div className="proj__listhead">
          <span className="proj__listtitle">프로젝트</span>
          <button
            type="button"
            className="rail__add"
            aria-label="프로젝트 등록"
            onClick={() => setDialog("project", null)}
          >
            <Plus size={14} aria-hidden="true" />
          </button>
        </div>

        <div className="proj__filters" role="group" aria-label="프로젝트 거르기">
          <button
            type="button"
            className={`proj__filter${filter === "all" ? " proj__filter--on" : ""}`}
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}
          >
            전체
            <span className="proj__filternum">{projects.length}</span>
          </button>
          <button
            type="button"
            className={`proj__filter${filter === "mine" ? " proj__filter--on" : ""}`}
            aria-pressed={filter === "mine"}
            onClick={() => setFilter("mine")}
          >
            내 프로젝트
            <span className="proj__filternum">
              {projects.filter((item) => item.is_member).length}
            </span>
          </button>
        </div>

        <div className="proj__scroll">
          {error ? (
            <div className="errorstate">
              <p className="empty__title">프로젝트를 불러오지 못했습니다</p>
              <p className="empty__text">{error}</p>
              <button
                type="button"
                className="btn btn--sm empty__action"
                onClick={() => void ensureProjects()}
              >
                다시 시도
              </button>
            </div>
          ) : null}

          {!error && loading && projects.length === 0 ? (
            <p className="u-small u-muted u-px-2 u-py-1">프로젝트를 불러오는 중</p>
          ) : null}

          {!error && !loading && visible.length === 0 ? (
            <div className="empty">
              <span className="empty__mark" aria-hidden="true">
                <FolderKanban size={20} />
              </span>
              <p className="empty__title">
                {filter === "mine" ? "내 프로젝트가 없습니다" : "아직 프로젝트가 없습니다"}
              </p>
              <p className="empty__text">
                {filter === "mine"
                  ? "내가 속한 프로젝트를 모아 봅니다. 프로젝트의 사람 목록에 추가해 보세요."
                  : "팀이 하는 일을 프로젝트로 등록해 보세요."}
              </p>
              <button
                type="button"
                className="btn btn--sm empty__action"
                onClick={() => setDialog("project", null)}
              >
                프로젝트 등록
              </button>
            </div>
          ) : null}

          {visible.map((item) => (
            <button
              key={item.id}
              className={`projitem${item.id === activeProjectId ? " projitem--on" : ""}`}
              aria-current={item.id === activeProjectId}
              onClick={() => void selectProject(item.id)}
            >
              <span className="projitem__top">
                <span className="projitem__name u-truncate">{item.name}</span>
                {item.open_tasks > 0 ? (
                  <span className="projitem__count">{item.open_tasks}</span>
                ) : null}
              </span>
              {item.description ? (
                <span className="projitem__purpose u-truncate">{item.description}</span>
              ) : null}
              <span className="projitem__foot">
                {item.members.slice(0, 4).map((member) => (
                  <Avatar key={member.id} user={member} size="sm" />
                ))}
                {item.members.length > 4 ? (
                  <span className="projitem__more">+{item.members.length - 4}</span>
                ) : null}
                {item.my_open_tasks > 0 ? (
                  <span className="projitem__mine">내 할일 {item.my_open_tasks}</span>
                ) : null}
              </span>
            </button>
          ))}

          <section className="proj__mine">
            <h3 className="proj__minetitle">
              내 할일
              {myTasks.length ? (
                <span className="proj__minetitle-n">{myTasks.length}</span>
              ) : null}
            </h3>
            {myTasks.length ? (
              <>
                {mineRows.map((task) => (
                  <button
                    key={task.id}
                    type="button"
                    className="proj__minerow"
                    onClick={() => {
                      // The card may belong to a project whose board is not
                      // open yet — the board is loaded before the card opens.
                      void selectProject(task.project_id).then(() =>
                        setDialog("task", task.id),
                      );
                    }}
                  >
                    <span className="proj__minename u-truncate">{task.title}</span>
                    <span className="proj__minemeta">
                      <span className="proj__mineproject u-truncate">
                        {projectNameOf(task.project_id)}
                      </span>
                      <span className={`badge badge--${task.status}`}>
                        {STATUS_LABEL[task.status]}
                      </span>
                    </span>
                  </button>
                ))}
                {myTasks.length > MINE_LIMIT ? (
                  <p className="proj__minemore">그 밖에 {myTasks.length - MINE_LIMIT}개</p>
                ) : null}
              </>
            ) : (
              <p className="proj__mineempty">내게 맡은 할 일이 없습니다.</p>
            )}
          </section>
        </div>
      </aside>

      <section className="proj__board" aria-label="할 일 보드">
        {!project ? (
          <div className="empty empty--board">
            <span className="empty__mark" aria-hidden="true">
              <ListChecks size={20} />
            </span>
            <p className="empty__title">프로젝트를 골라 주세요</p>
            <p className="empty__text">
              왼쪽에서 고르면 그 프로젝트의 할 일과 마일스톤이 열립니다.
            </p>
          </div>
        ) : (
          <>
            <header className="proj__head">
              <div className="proj__headmain">
                <h2 className="proj__name">
                  {/* The board's own name picks the project — in a side pane
                      the list beside it is gone. */}
                  <button
                    type="button"
                    className="proj__namebtn"
                    aria-haspopup="menu"
                    aria-expanded={Boolean(projectAnchor)}
                    onClick={(event) => setProjectAnchor(event.currentTarget)}
                  >
                    {project.name}
                    <ChevronDown size={14} aria-hidden="true" />
                  </button>
                </h2>
                {project.description ? (
                  <p className="proj__purpose">{project.description}</p>
                ) : null}
                {/* The project's own three facts: how far it has come, how
                    much is left, and the period it runs in. The period is
                    the way into the chart — the chart is that period
                    drawn out. */}
                <p className="proj__facts">
                  <span className="proj__meter" aria-hidden="true">
                    <span
                      className="proj__meterfill"
                      style={{ width: `${progress}%` }}
                    />
                  </span>
                  <span className="proj__fact proj__fact--num">{progress}%</span>
                  <span className="proj__fact">
                    할 일 {project.open_tasks}개 남음
                  </span>
                  {project.start_at && project.end_at ? (
                    <button
                      type="button"
                      className="proj__period"
                      title="차트 보기"
                      aria-label={`차트 보기: ${periodLabel(project.start_at, project.end_at)}`}
                      onClick={() => setDialog("projectChart", project.id)}
                    >
                      {periodLabel(project.start_at, project.end_at)}
                    </button>
                  ) : null}
                </p>
              </div>
              <div className="proj__headtools">
                {room ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => void openChannel(room.id)}
                  >
                    <Hash size={13} aria-hidden="true" />
                    {room.name}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="iconbtn"
                  aria-label="프로젝트 설정"
                  title="프로젝트 설정"
                  onClick={() => setDialog("project", project.id)}
                >
                  <Settings size={15} aria-hidden="true" />
                </button>
              </div>
            </header>

            {projectAnchor ? (
              <Menu
                anchor={projectAnchor}
                onClose={() => setProjectAnchor(null)}
                width={240}
              >
                <div className="menu__label">프로젝트</div>
                {visible.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="menu__item"
                    onClick={() => {
                      setProjectAnchor(null);
                      void selectProject(item.id);
                    }}
                  >
                    <FolderKanban size={14} aria-hidden="true" />
                    <span className="u-grow u-truncate">{item.name}</span>
                    {item.id === activeProjectId ? (
                      <Check size={14} aria-hidden="true" />
                    ) : null}
                  </button>
                ))}
              </Menu>
            ) : null}

            {/* 무엇을 보는지 — 할 일과 마일스톤은 종류가 다른 두 가지다.
                로드맵은 카드의 묶음이고, 마일스톤은 기한이 있는 목표다.
                그래서 하나는 스위치고, 다른 하나는 카드 위의 거르기다. */}
            <div className="proj__views" role="tablist" aria-label="프로젝트에서 볼 것">
              <button
                type="button"
                role="tab"
                aria-selected={boardMode === "board"}
                className={`proj__view${boardMode === "board" ? " proj__view--on" : ""}`}
                onClick={() => setBoardMode("board")}
              >
                할 일
                <span className="proj__viewn">{project.total_tasks}</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={boardMode === "milestones"}
                className={`proj__view${boardMode === "milestones" ? " proj__view--on" : ""}`}
                onClick={() => setBoardMode("milestones")}
              >
                마일스톤
                <span className="proj__viewn">{milestoneCount}</span>
              </button>
            </div>

            <div className="proj__body">
              {boardMode === "milestones" ? (
                <MilestonePanel project={project} />
              ) : (
                <>
                  {/* 카드의 묶음 — 로드맵. 왼쪽 칩은 보드 전체이고
                      오른쪽이 로드맵들이다. 선 하나로 나누어 "모든 카드"가
                      로드맵 이름처럼 읽히지 않게 한다. 로드맵이 없는
                      프로젝트에는 이 줄이 없다 — 거르는 게 없으니까. */}
                  {projectRoadmaps.length ? (
                    <div className="proj__lanes">
                      <div className="proj__lanechips">
                        <button
                          type="button"
                          className={`proj__lanechip${activeRoadmapId === null ? " proj__lanechip--on" : ""}`}
                          aria-pressed={activeRoadmapId === null}
                          onClick={() => setActiveRoadmap(null)}
                        >
                          모든 카드
                          <span className="proj__lanecn">{project.total_tasks}</span>
                        </button>

                        <span className="proj__lanediv" aria-hidden="true" />

                        <span className="proj__lanelabel">로드맵</span>

                        {projectRoadmaps.map((roadmap) => (
                          <span key={roadmap.id} className="proj__lanewrap">
                            <button
                              type="button"
                              className={`proj__lanechip${activeRoadmapId === roadmap.id ? " proj__lanechip--on" : ""}`}
                              aria-pressed={activeRoadmapId === roadmap.id}
                              onClick={() => setActiveRoadmap(roadmap.id)}
                            >
                              <span className="u-truncate">{roadmap.name}</span>
                              <span className="proj__lanecn">{roadmap.task_count}</span>
                            </button>
                            <button
                              type="button"
                              className="iconbtn proj__lanex"
                              aria-label={`${roadmap.name} 로드맵 삭제`}
                              title={`${roadmap.name} 로드맵 삭제`}
                              onClick={() => setPendingRoadmap(roadmap.id)}
                            >
                              <Trash2 size={12} aria-hidden="true" />
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {pendingRoadmap ? (
                    <ConfirmDialog
                      title="로드맵 삭제"
                      message={
                        <>
                          <strong>{pendingRoadmapName}</strong> 로드맵을 삭제할까요?
                        </>
                      }
                      detail="이 안의 할 일은 그대로 남습니다. 로드맵만 사라집니다."
                      busy={deletingRoadmap}
                      onConfirm={() => void confirmRemoveRoadmap()}
                      onClose={() => setPendingRoadmap(null)}
                    />
                  ) : null}

                  <div className="proj__cols">
                    {COLUMNS.map((column) => (
                      <BoardColumn
                        key={column.status}
                        column={column}
                        tasks={board.get(column.status) ?? []}
                        onOpen={(task) => setDialog("task", task.id)}
                        onMove={(taskId, status, position) => void moveTask(taskId, status, position)}
                        onAdd={() => setDialog("task", null)}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function BoardColumn({
  column,
  tasks,
  onOpen,
  onMove,
  onAdd,
}: {
  column: { status: TaskStatus; label: string; hint: string };
  tasks: Task[];
  onOpen: (task: Task) => void;
  onMove: (taskId: string, status: TaskStatus, position?: number) => void;
  onAdd: () => void;
}) {
  const [over, setOver] = useState(false);

  return (
    <div
      className={`projcol${over ? " projcol--over" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const taskId = event.dataTransfer.getData("text/plain");
        if (!taskId) return;
        // The place the card lands in: the first card whose middle the
        // pointer has not passed yet.
        const holder = event.currentTarget;
        const cards = Array.from(holder.querySelectorAll<HTMLElement>(".taskcard")).filter(
          (card) => card.dataset.taskId !== taskId,
        );
        let index = cards.length;
        for (let i = 0; i < cards.length; i += 1) {
          const box = cards[i].getBoundingClientRect();
          if (event.clientY < box.top + box.height / 2) {
            index = i;
            break;
          }
        }
        onMove(taskId, column.status, index);
      }}
    >
      <header className="projcol__head">
        <span className="projcol__label">{column.label}</span>
        <span className="projcol__count">{tasks.length}</span>
      </header>

      <div className="projcol__cards">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} onOpen={onOpen} onMove={onMove} />
        ))}
      </div>

      <button type="button" className="projcol__add" onClick={onAdd}>
        <Plus size={13} aria-hidden="true" />
        할 일 추가
      </button>
    </div>
  );
}

function TaskCard({
  task,
  onOpen,
  onMove,
}: {
  task: Task;
  onOpen: (task: Task) => void;
  onMove: (taskId: string, status: TaskStatus, position?: number) => void;
}) {
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const due = task.due_at ? dueLabel(task.due_at) : null;

  return (
    <article
      className="taskcard"
      data-task-id={task.id}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", task.id);
        event.dataTransfer.effectAllowed = "move";
      }}
    >
      <div className="taskcard__top">
        <button
          type="button"
          className="taskcard__title"
          onClick={() => onOpen(task)}
        >
          {task.title}
        </button>
        {due ? (
          <span className={`taskcard__due taskcard__due--${due.tone}`}>{due.text}</span>
        ) : null}
      </div>

      {task.description ? (
        <p className="taskcard__desc u-clamp2">{task.description}</p>
      ) : null}

      {task.roadmap_name ? (
        <span className="badge badge--roadmap">{task.roadmap_name}</span>
      ) : null}

      {task.milestone_name ? (
        <span
          className="badge badge--milestone"
          style={
            task.milestone_color
              ? ({ ["--ms-color" as string]: task.milestone_color } as CSSProperties)
              : undefined
          }
        >
          {task.milestone_name}
        </span>
      ) : null}

      <div className="taskcard__foot">
        {task.assignee ? (
          <span className="taskcard__who">
            <Avatar user={task.assignee} size="sm" />
          </span>
        ) : (
          <span className="taskcard__who taskcard__who--none">담당 없음</span>
        )}
        {task.comment_count > 0 ? (
          <span className="taskcard__meta">
            <MessageSquare size={12} aria-hidden="true" />
            {task.comment_count}
          </span>
        ) : null}
        <span className="u-grow" />
        <button
          type="button"
          ref={buttonRef}
          className="iconbtn taskcard__move"
          aria-label="옮기기"
          aria-haspopup="menu"
          aria-expanded={Boolean(menuAnchor)}
          onClick={() =>
            setMenuAnchor(menuAnchor ? null : (buttonRef.current as HTMLElement))
          }
        >
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>

      {menuAnchor ? (
        <Menu anchor={menuAnchor} onClose={() => setMenuAnchor(null)} width={180}>
          <div className="menu__label">옮길 곳</div>
          {COLUMNS.map((column) => (
            <button
              key={column.status}
              type="button"
              className="menu__item"
              role="menuitemradio"
              aria-checked={task.status === column.status}
              onClick={() => {
                setMenuAnchor(null);
                onMove(task.id, column.status);
              }}
            >
              <span className="u-grow">{column.label}</span>
              {task.status === column.status ? <span aria-hidden="true">✓</span> : null}
            </button>
          ))}
        </Menu>
      ) : null}
    </article>
  );
}

/** How long a deadline has left, in words — the badge never says only "red". */
function dueLabel(dueAt: string): { text: string; tone: "soon" | "late" | "plain" } {
  const due = new Date(dueAt);
  const now = new Date();
  const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate()).getTime();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const days = Math.round((dueDay - today) / 86_400_000);
  if (days < 0) return { text: `${-days}일 지남`, tone: "late" };
  if (days === 0) return { text: "오늘 마감이", tone: "soon" };
  if (days <= 3) return { text: `${days}일 남음`, tone: "soon" };
  return { text: `${due.getMonth() + 1}월 ${due.getDate()}일`, tone: "plain" };
}
