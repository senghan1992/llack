"""Projects and their boards: the work a team is doing, in one place.

A project lives inside a workspace and is open to everyone in it — the way a
public channel is. What makes it *yours* is the roster: the people named on
the project are its members, and a board can be filtered down to the
projects you are on.

The board holds tasks in four columns — 요청, 할 일, 진행 중, 완료 — and a
task keeps its place inside a column.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found, validation_error
from app.core.ids import (
    MILESTONE_PREFIX,
    PROJECT_MEMBER_PREFIX,
    PROJECT_PREFIX,
    TASK_COMMENT_PREFIX,
    TASK_PREFIX,
    new_id,
)
from app.models.channel import Channel, ChannelMember
from app.models.project import (
    STATUS_DONE,
    STATUS_TODO,
    TASK_STATUSES,
    Milestone,
    Project,
    ProjectMember,
    Roadmap,
    Task,
    TaskComment,
)
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.project import (
    MilestoneOut,
    ProjectOut,
    RoadmapOut,
    TaskCommentOut,
    TaskOut,
)
from app.schemas.user import UserOut


async def get_project_or_404(session: AsyncSession, project_id: str) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found("project not found")
    return project


async def get_task_or_404(session: AsyncSession, task_id: str) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise not_found("task not found")
    return task


async def project_member_ids(session: AsyncSession, project_id: str) -> set[str]:
    rows = await session.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    )
    return set(rows.all())


def can_manage_project(project: Project, membership: WorkspaceMembership, user_id: str) -> bool:
    """Who may change a project: the one who made it, or an administrator."""
    return project.created_by == user_id or membership.role in ("owner", "admin")


def can_delete_task(
    task: Task, project: Project, membership: WorkspaceMembership, user_id: str
) -> bool:
    """Who may remove a task: its author, the project's owner, or an administrator."""
    return (
        task.created_by == user_id
        or project.created_by == user_id
        or membership.role in ("owner", "admin")
    )


async def resolve_channel(
    session: AsyncSession, workspace_id: str, channel_id: str | None, user_id: str
) -> str | None:
    """Check that a linked channel exists and that the user may see it."""
    if not channel_id:
        return None
    channel = await session.get(Channel, channel_id)
    if channel is None or channel.workspace_id != workspace_id:
        raise validation_error("that channel does not belong to this workspace", "channel_id")
    if channel.is_private:
        member = await session.scalar(
            select(ChannelMember.id).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == user_id,
            )
        )
        if member is None:
            raise forbidden("you cannot see this channel")
    return channel_id


async def _sync_members(
    session: AsyncSession, project: Project, user_ids: list[str], workspace_id: str
) -> None:
    """Replace the roster, keeping the people who are still on it."""
    wanted = list(dict.fromkeys(user_ids))
    for user_id in wanted:
        member = await session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        if member is None:
            raise validation_error("a member is not a member of this workspace", "member_ids")

    existing = list(
        await session.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id))
    )
    by_user = {row.user_id: row for row in existing}

    for user_id, row in by_user.items():
        if user_id not in wanted:
            await session.delete(row)

    for user_id in wanted:
        if user_id in by_user:
            continue
        session.add(
            ProjectMember(
                id=new_id(PROJECT_MEMBER_PREFIX),
                project_id=project.id,
                user_id=user_id,
            )
        )
    await session.flush()


async def create_project(
    session: AsyncSession,
    workspace_id: str,
    creator: User,
    name: str,
    description: str = "",
    purpose: str = "",
    deliverables: str = "",
    channel_id: str | None = None,
    member_ids: list[str] | None = None,
) -> Project:
    clean_name = name.strip()
    if not clean_name:
        raise validation_error("the project needs a name", "name")

    resolved_channel = await resolve_channel(session, workspace_id, channel_id, creator.id)

    project = Project(
        id=new_id(PROJECT_PREFIX),
        workspace_id=workspace_id,
        name=clean_name,
        description=(description or "").strip(),
        purpose=(purpose or "").strip(),
        deliverables=(deliverables or "").strip(),
        channel_id=resolved_channel,
        created_by=creator.id,
        is_archived=False,
    )
    session.add(project)
    await session.flush()

    # The one who made the project is on it — a project without a maker is
    # a project nobody looks after.
    await _sync_members(
        session,
        project,
        [creator.id, *(member_ids or [])],
        workspace_id,
    )
    return project


async def update_project(
    session: AsyncSession,
    project: Project,
    payload: dict,
    workspace_id: str,
    user_id: str,
) -> Project:
    data = payload

    if "name" in data and data["name"] is not None:
        clean = data["name"].strip()
        if not clean:
            raise validation_error("the project needs a name", "name")
        project.name = clean
    if "description" in data and data["description"] is not None:
        project.description = data["description"].strip()
    if "purpose" in data and data["purpose"] is not None:
        project.purpose = data["purpose"].strip()
    if "deliverables" in data and data["deliverables"] is not None:
        project.deliverables = data["deliverables"].strip()
    if "channel_id" in data:
        project.channel_id = await resolve_channel(
            session, workspace_id, data["channel_id"], user_id
        )
    if "is_archived" in data and data["is_archived"] is not None:
        project.is_archived = data["is_archived"]

    await session.flush()

    if data.get("member_ids") is not None:
        roster = list(data["member_ids"])
        if project.created_by not in roster:
            roster.append(project.created_by)
        await _sync_members(session, project, roster, workspace_id)
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)
    await session.flush()


async def add_project_member(
    session: AsyncSession, project: Project, user_id: str, workspace_id: str
) -> Project:
    current = await project_member_ids(session, project.id)
    await _sync_members(session, project, [*current, user_id], workspace_id)
    return project


async def remove_project_member(session: AsyncSession, project: Project, user_id: str) -> Project:
    row = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    if row is not None:
        await session.delete(row)
        await session.flush()
    return project


async def list_projects(
    session: AsyncSession, workspace_id: str, include_archived: bool = False
) -> list[Project]:
    query = select(Project).where(Project.workspace_id == workspace_id)
    if not include_archived:
        query = query.where(Project.is_archived.is_(False))
    rows = await session.scalars(query.order_by(Project.created_at, Project.id))
    return list(rows)


async def list_tasks(session: AsyncSession, project_id: str) -> list[Task]:
    rows = await session.scalars(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.position, Task.created_at, Task.id)
    )
    return list(rows)


async def my_tasks(session: AsyncSession, workspace_id: str, user_id: str) -> list[Task]:
    """Every task of the workspace that is mine and not finished."""
    rows = await session.scalars(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Project.workspace_id == workspace_id,
            Task.assignee_id == user_id,
            Task.status != STATUS_DONE,
        )
        .order_by(Task.due_at.is_(None), Task.due_at, Task.created_at, Task.id)
    )
    return list(rows)


async def next_position(session: AsyncSession, project_id: str, status: str) -> int:
    """The place a new task takes in its column. The first one is zero."""
    current = await session.scalar(
        select(func.max(Task.position)).where(
            Task.project_id == project_id,
            Task.status == status,
        )
    )
    if current is None:
        return 0
    return int(current) + 1


async def create_task(
    session: AsyncSession,
    project: Project,
    creator: User,
    title: str,
    description: str = "",
    status: str = STATUS_TODO,
    assignee_id: str | None = None,
    start_at: datetime | None = None,
    due_at: datetime | None = None,
    roadmap_id: str | None = None,
    milestone_id: str | None = None,
) -> Task:
    clean_title = title.strip()
    if not clean_title:
        raise validation_error("the task needs a title", "title")
    if status not in TASK_STATUSES:
        raise validation_error("unknown task status", "status")

    await _require_assignee(session, project.workspace_id, assignee_id)
    if roadmap_id is not None:
        roadmap_id = await require_roadmap(session, project.id, roadmap_id)
    if milestone_id is not None:
        milestone_id = await require_milestone(session, project.id, milestone_id)

    task = Task(
        id=new_id(TASK_PREFIX),
        project_id=project.id,
        title=clean_title,
        description=(description or "").strip(),
        status=status,
        assignee_id=assignee_id,
        roadmap_id=roadmap_id,
        milestone_id=milestone_id,
        created_by=creator.id,
        start_at=start_at,
        due_at=due_at,
        position=await next_position(session, project.id, status),
    )
    session.add(task)
    await session.flush()
    return task


async def _require_assignee(
    session: AsyncSession, workspace_id: str, assignee_id: str | None
) -> None:
    if not assignee_id:
        return
    member = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == assignee_id,
        )
    )
    if member is None:
        raise validation_error("the assignee is not a member of this workspace", "assignee_id")


async def update_task(
    session: AsyncSession,
    task: Task,
    payload: dict,
    workspace_id: str,
) -> Task:
    data = payload

    if "title" in data and data["title"] is not None:
        clean = data["title"].strip()
        if not clean:
            raise validation_error("the task needs a title", "title")
        task.title = clean
    if "description" in data and data["description"] is not None:
        task.description = data["description"].strip()
    if "assignee_id" in data:
        await _require_assignee(session, workspace_id, data["assignee_id"])
        task.assignee_id = data["assignee_id"] or None
    if "roadmap_id" in data:
        if data["roadmap_id"] is None:
            task.roadmap_id = None
        else:
            task.roadmap_id = await require_roadmap(session, task.project_id, data["roadmap_id"])
    if "milestone_id" in data:
        if data["milestone_id"] is None:
            task.milestone_id = None
        else:
            task.milestone_id = await require_milestone(
                session, task.project_id, data["milestone_id"]
            )
    if "start_at" in data:
        task.start_at = data["start_at"]
    if "due_at" in data:
        task.due_at = data["due_at"]

    await session.flush()

    if data.get("status") is not None and data["status"] != task.status:
        await move_task(session, task, data["status"], data.get("position"))
    elif data.get("position") is not None:
        await reorder_task(session, task, task.status, data["position"])
    return task


async def move_task(
    session: AsyncSession, task: Task, status: str, position: int | None = None
) -> Task:
    """Put a task on another column, at the end of it unless a place is named."""
    if status not in TASK_STATUSES:
        raise validation_error("unknown task status", "status")

    if status != task.status:
        # The task leaves its old column; the others behind it step up.
        await _compact(session, task.project_id, task.status, exclude_id=task.id)
        task.status = status
        await session.flush()
        task.position = await next_position(session, task.project_id, status)

    if position is not None:
        await reorder_task(session, task, status, position)
    return task


async def reorder_task(session: AsyncSession, task: Task, status: str, position: int) -> Task:
    """Place a task at ``position`` inside its column."""
    if position < 0:
        raise validation_error("the position must not be negative", "position")
    rows = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == task.project_id, Task.status == status)
            .order_by(Task.position, Task.created_at, Task.id)
        )
    )
    others = [row for row in rows if row.id != task.id]
    index = min(position, len(others))
    others.insert(index, task)

    task.status = status
    for order, row in enumerate(others):
        row.position = order
    await session.flush()
    return task


async def _compact(
    session: AsyncSession, project_id: str, status: str, exclude_id: str | None = None
) -> None:
    """Number the tasks of a column from zero, leaving out one."""
    rows = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.status == status)
            .order_by(Task.position, Task.created_at, Task.id)
        )
    )
    order = 0
    for row in rows:
        if row.id == exclude_id:
            continue
        row.position = order
        order += 1
    await session.flush()


async def delete_task(session: AsyncSession, task: Task) -> None:
    await session.delete(task)
    await session.flush()


async def add_comment(session: AsyncSession, task: Task, author: User, body: str) -> TaskComment:
    clean = body.strip()
    if not clean:
        raise validation_error("a comment needs a body", "body")
    comment = TaskComment(
        id=new_id(TASK_COMMENT_PREFIX),
        task_id=task.id,
        user_id=author.id,
        body=clean,
    )
    session.add(comment)
    await session.flush()
    return comment


async def get_comment_or_404(session: AsyncSession, comment_id: str) -> TaskComment:
    comment = await session.get(TaskComment, comment_id)
    if comment is None:
        raise not_found("comment not found")
    return comment


async def delete_comment(session: AsyncSession, comment: TaskComment) -> None:
    await session.delete(comment)
    await session.flush()


# ── roadmaps ─────────────────────────────────────────────────────────────


async def get_roadmap_or_404(session: AsyncSession, roadmap_id: str) -> Roadmap:
    roadmap = await session.get(Roadmap, roadmap_id)
    if roadmap is None:
        raise not_found("roadmap not found")
    return roadmap


async def list_roadmaps(session: AsyncSession, project_id: str) -> list[Roadmap]:
    rows = await session.scalars(
        select(Roadmap)
        .where(Roadmap.project_id == project_id)
        .order_by(Roadmap.position, Roadmap.created_at, Roadmap.id)
    )
    return list(rows)


async def rename_roadmap(session: AsyncSession, roadmap: Roadmap, name: str) -> Roadmap:
    clean_name = name.strip()
    if not clean_name:
        raise validation_error("the roadmap needs a name", "name")
    roadmap.name = clean_name
    await session.flush()
    return roadmap


async def delete_roadmap(session: AsyncSession, roadmap: Roadmap) -> None:
    """Take a roadmap off the board.

    The tasks planned in it are not deleted: only the link to the roadmap
    is cut. SQLite does not enforce the foreign key here, so the link is
    undone by hand.
    """
    await session.execute(update(Task).where(Task.roadmap_id == roadmap.id).values(roadmap_id=None))
    await session.delete(roadmap)
    await session.flush()


async def require_roadmap(session: AsyncSession, project_id: str, roadmap_id: str) -> str:
    """Check that the roadmap is one of this project's."""
    roadmap = await session.get(Roadmap, roadmap_id)
    if roadmap is None or roadmap.project_id != project_id:
        raise validation_error("that roadmap does not belong to this project", "roadmap_id")
    return roadmap.id


# ── milestones ───────────────────────────────────────────────────────────

MILESTONE_COLOR = "#4f6cff"


async def get_milestone_or_404(session: AsyncSession, milestone_id: str) -> Milestone:
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None:
        raise not_found("마일스톤을 찾을 수 없습니다")
    return milestone


async def list_milestones(session: AsyncSession, project_id: str) -> list[Milestone]:
    """The milestones of a project, the ones that start first in front."""
    rows = await session.scalars(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.start_at, Milestone.created_at, Milestone.id)
    )
    return list(rows)


async def require_milestone(session: AsyncSession, project_id: str, milestone_id: str) -> str:
    """Check that the milestone is one of this project's."""
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != project_id:
        raise validation_error("이 프로젝트에 없는 마일스톤입니다", "milestone_id")
    return milestone.id


def _as_utc(moment: datetime) -> datetime:
    """A moment without a timezone is read as UTC — the way it is stored."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


async def create_milestone(
    session: AsyncSession,
    project: Project,
    creator: User,
    title: str,
    start_at: datetime,
    end_at: datetime,
    color: str = MILESTONE_COLOR,
    progress: int = 0,
    description: str = "",
    task_ids: list[str] | None = None,
) -> Milestone:
    """Mark a deliverable on the board of a project."""
    clean_title = title.strip()
    if not clean_title:
        raise validation_error("마일스톤의 제목이 필요합니다", "title")

    start = _as_utc(start_at)
    end = _as_utc(end_at)
    if end < start:
        raise validation_error("종료일은 시작일보다 빠를 수 없습니다", "end_at")

    milestone = Milestone(
        id=new_id(MILESTONE_PREFIX),
        project_id=project.id,
        title=clean_title,
        start_at=start,
        end_at=end,
        color=(color or "").strip() or MILESTONE_COLOR,
        progress=max(0, min(100, int(progress))),
        description=(description or "").strip(),
        created_by=creator.id,
    )
    session.add(milestone)
    await session.flush()

    await link_milestone_tasks(session, milestone, task_ids or [])
    return milestone


async def update_milestone(session: AsyncSession, milestone: Milestone, payload: dict) -> Milestone:
    """Change a milestone — its dates, its colour, its cards."""
    data = payload

    start_at = milestone.start_at
    end_at = milestone.end_at
    if "start_at" in data and data["start_at"] is not None:
        start_at = _as_utc(data["start_at"])
    if "end_at" in data and data["end_at"] is not None:
        end_at = _as_utc(data["end_at"])
    if _as_utc(end_at) < _as_utc(start_at):
        raise validation_error("종료일은 시작일보다 빠를 수 없습니다", "end_at")

    if "title" in data and data["title"] is not None:
        clean = data["title"].strip()
        if not clean:
            raise validation_error("마일스톤의 제목이 필요합니다", "title")
        milestone.title = clean
    if "start_at" in data and data["start_at"] is not None:
        milestone.start_at = start_at
    if "end_at" in data and data["end_at"] is not None:
        milestone.end_at = end_at
    if "color" in data and data["color"] is not None:
        milestone.color = data["color"].strip() or MILESTONE_COLOR
    if "progress" in data and data["progress"] is not None:
        milestone.progress = max(0, min(100, int(data["progress"])))
    if "description" in data and data["description"] is not None:
        milestone.description = data["description"].strip()

    await session.flush()

    if data.get("task_ids") is not None:
        await link_milestone_tasks(session, milestone, list(data["task_ids"]))
    return milestone


async def link_milestone_tasks(
    session: AsyncSession, milestone: Milestone, task_ids: list[str]
) -> None:
    """Make the listed cards the cards that deliver this milestone.

    A card belongs to at most one milestone: it leaves the one it was in.
    The cards that were linked here and are not named any more are let go.
    """
    wanted = list(dict.fromkeys(task_ids))

    found: dict[str, Task] = {}
    if wanted:
        rows = await session.scalars(select(Task).where(Task.id.in_(wanted)))
        found = {task.id: task for task in rows}

    for task_id in wanted:
        task = found.get(task_id)
        if task is None or task.project_id != milestone.project_id:
            raise validation_error("이 프로젝트에 없는 카드입니다", "task_ids")

    previous = list(await session.scalars(select(Task).where(Task.milestone_id == milestone.id)))
    for task in previous:
        if task.id not in wanted:
            task.milestone_id = None

    for task_id in wanted:
        found[task_id].milestone_id = milestone.id

    await session.flush()


async def delete_milestone(session: AsyncSession, milestone: Milestone) -> None:
    """Take a milestone off the board.

    The cards that deliver it are not deleted: only the link to the
    milestone is cut. SQLite does not enforce the foreign key here, so the
    link is undone by hand.
    """
    await session.execute(
        update(Task).where(Task.milestone_id == milestone.id).values(milestone_id=None)
    )
    await session.delete(milestone)
    await session.flush()


# ── serialisation ────────────────────────────────────────────────────────


async def serialize_projects(
    session: AsyncSession, projects: list[Project], viewer_id: str
) -> list[ProjectOut]:
    """The API shape of a batch of projects, for one reader."""
    if not projects:
        return []

    project_ids = [project.id for project in projects]

    rosters = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id.in_(project_ids))
        .order_by(ProjectMember.created_at, ProjectMember.id)
    )
    members: dict[str, list[User]] = {}
    for member, user in rosters.all():
        members.setdefault(member.project_id, []).append(user)

    counts = await session.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            func.sum(case((Task.status == STATUS_DONE, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(Task.status != STATUS_DONE, Task.assignee_id == viewer_id),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.min(Task.due_at),
            func.max(Task.due_at),
        )
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    )
    open_counts = {
        row[0]: (row[1], int(row[2] or 0), int(row[3] or 0), row[4], row[5]) for row in counts.all()
    }

    # The period the project occupies: its milestones, and the deadlines on
    # its cards. The chart rules the same way — the earliest thing to the
    # latest.
    spans = await session.execute(
        select(
            Milestone.project_id,
            func.min(Milestone.start_at),
            func.max(Milestone.end_at),
        )
        .where(Milestone.project_id.in_(project_ids))
        .group_by(Milestone.project_id)
    )
    milestone_spans = {row[0]: (row[1], row[2]) for row in spans.all()}

    rendered: list[ProjectOut] = []
    for project in projects:
        roster = members.get(project.id, [])
        total, done, my_open, first_due, last_due = open_counts.get(
            project.id, (0, 0, 0, None, None)
        )
        milestone_start, milestone_end = milestone_spans.get(project.id, (None, None))
        starts = [value for value in (milestone_start, first_due) if value is not None]
        ends = [value for value in (milestone_end, last_due) if value is not None]
        rendered.append(
            ProjectOut(
                id=project.id,
                workspace_id=project.workspace_id,
                name=project.name,
                description=project.description,
                purpose=project.purpose,
                deliverables=project.deliverables,
                channel_id=project.channel_id,
                created_by=project.created_by,
                is_archived=project.is_archived,
                created_at=project.created_at,
                updated_at=project.updated_at,
                members=[UserOut.model_validate(user) for user in roster],
                is_member=any(user.id == viewer_id for user in roster),
                open_tasks=int(total or 0) - int(done or 0),
                my_open_tasks=my_open,
                total_tasks=int(total or 0),
                done_tasks=int(done or 0),
                start_at=min(starts) if starts else None,
                end_at=max(ends) if ends else None,
            )
        )
    return rendered


async def serialize_tasks(
    session: AsyncSession, tasks: list[Task], viewer_id: str
) -> list[TaskOut]:
    """The API shape of a batch of tasks, for one reader."""
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]

    assignees = await session.execute(
        select(Task.id, User)
        .outerjoin(User, User.id == Task.assignee_id)
        .where(Task.id.in_(task_ids))
    )
    people = {row[0]: row[1] for row in assignees.all()}

    comments = await session.execute(
        select(TaskComment, User)
        .join(User, User.id == TaskComment.user_id)
        .where(TaskComment.task_id.in_(task_ids))
        .order_by(TaskComment.created_at, TaskComment.id)
    )
    by_task: dict[str, list[TaskCommentOut]] = {}
    for comment, user in comments.all():
        by_task.setdefault(comment.task_id, []).append(
            TaskCommentOut(
                id=comment.id,
                task_id=comment.task_id,
                user_id=comment.user_id,
                author=UserOut.model_validate(user),
                body=comment.body,
                created_at=comment.created_at,
            )
        )

    roadmap_names: dict[str, str] = {}
    roadmap_ids = {task.roadmap_id for task in tasks if task.roadmap_id}
    if roadmap_ids:
        for roadmap in await session.scalars(select(Roadmap).where(Roadmap.id.in_(roadmap_ids))):
            roadmap_names[roadmap.id] = roadmap.name

    milestones: dict[str, Milestone] = {}
    milestone_ids = {task.milestone_id for task in tasks if task.milestone_id}
    if milestone_ids:
        for milestone in await session.scalars(
            select(Milestone).where(Milestone.id.in_(milestone_ids))
        ):
            milestones[milestone.id] = milestone

    return [
        TaskOut(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status,
            assignee_id=task.assignee_id,
            assignee=UserOut.model_validate(people[task.id]) if people.get(task.id) else None,
            roadmap_id=task.roadmap_id,
            roadmap_name=roadmap_names.get(task.roadmap_id) if task.roadmap_id else None,
            milestone_id=task.milestone_id,
            milestone_name=(
                milestones[task.milestone_id].title if task.milestone_id in milestones else None
            ),
            milestone_color=(
                milestones[task.milestone_id].color if task.milestone_id in milestones else None
            ),
            created_by=task.created_by,
            start_at=task.start_at,
            due_at=task.due_at,
            position=task.position,
            created_at=task.created_at,
            updated_at=task.updated_at,
            comments=by_task.get(task.id, []),
            comment_count=len(by_task.get(task.id, [])),
        )
        for task in tasks
    ]


async def serialize_roadmaps(session: AsyncSession, roadmaps: list[Roadmap]) -> list[RoadmapOut]:
    """The API shape of a batch of roadmaps, with the tasks they hold."""
    if not roadmaps:
        return []

    roadmap_ids = [roadmap.id for roadmap in roadmaps]
    counts = await session.execute(
        select(Task.roadmap_id, func.count(Task.id))
        .where(Task.roadmap_id.in_(roadmap_ids))
        .group_by(Task.roadmap_id)
    )
    task_counts = {row[0]: int(row[1]) for row in counts.all()}

    return [
        RoadmapOut(
            id=roadmap.id,
            project_id=roadmap.project_id,
            name=roadmap.name,
            position=roadmap.position,
            created_by=roadmap.created_by,
            created_at=roadmap.created_at,
            task_count=task_counts.get(roadmap.id, 0),
        )
        for roadmap in roadmaps
    ]


async def serialize_milestones(
    session: AsyncSession, milestones: list[Milestone]
) -> list[MilestoneOut]:
    """The API shape of a batch of milestones, with the cards that deliver them.

    A milestone that holds cards shows their progress — the share of them
    that is done. One that holds none shows the progress written by hand.
    """
    if not milestones:
        return []

    milestone_ids = [milestone.id for milestone in milestones]
    cards = await session.execute(
        select(Task.milestone_id, Task.id, Task.status)
        .where(Task.milestone_id.in_(milestone_ids))
        .order_by(Task.position, Task.created_at, Task.id)
    )
    linked: dict[str, list[str]] = {}
    finished: dict[str, int] = {}
    for milestone_id, task_id, status in cards.all():
        linked.setdefault(milestone_id, []).append(task_id)
        if status == STATUS_DONE:
            finished[milestone_id] = finished.get(milestone_id, 0) + 1

    rendered: list[MilestoneOut] = []
    for milestone in milestones:
        task_ids = linked.get(milestone.id, [])
        total = len(task_ids)
        done_count = finished.get(milestone.id, 0)
        if total:
            progress = int(done_count * 100 / total + 0.5)
            auto_progress = True
        else:
            progress = milestone.progress
            auto_progress = False
        rendered.append(
            MilestoneOut(
                id=milestone.id,
                project_id=milestone.project_id,
                title=milestone.title,
                start_at=milestone.start_at,
                end_at=milestone.end_at,
                color=milestone.color,
                progress=progress,
                manual_progress=milestone.progress,
                description=milestone.description,
                task_count=total,
                done_count=done_count,
                auto_progress=auto_progress,
                task_ids=task_ids,
                created_by=milestone.created_by,
                created_at=milestone.created_at,
                updated_at=milestone.updated_at,
            )
        )
    return rendered
