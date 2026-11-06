"""Project routes: the board of work a team is doing."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.core.errors import forbidden
from app.realtime import events
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectOut,
    ProjectUpdate,
    RoadmapOut,
    RoadmapUpdate,
    TaskCommentCreate,
    TaskCommentOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.schemas.user import UserOut
from app.services.members import is_manager, require_membership
from app.services.projects import (
    add_comment,
    add_project_member,
    can_delete_task,
    can_manage_project,
    create_project,
    create_task,
    delete_comment,
    delete_project,
    delete_roadmap,
    delete_task,
    get_comment_or_404,
    get_project_or_404,
    get_roadmap_or_404,
    get_task_or_404,
    list_projects,
    list_roadmaps,
    list_tasks,
    my_tasks,
    remove_project_member,
    rename_roadmap,
    serialize_projects,
    serialize_roadmaps,
    serialize_tasks,
    update_project,
    update_task,
)

router = APIRouter(tags=["projects"])


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectOut])
async def read_projects(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[ProjectOut]:
    """Every project of the workspace, with the caller's own counts."""
    projects = await list_projects(session, workspace_id)
    return await serialize_projects(session, projects, user.id)


@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectOut)
async def post_project(
    workspace_id: WorkspaceId,
    payload: ProjectCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> ProjectOut:
    project = await create_project(
        session,
        workspace_id,
        user,
        payload.name,
        description=payload.description,
        purpose=payload.purpose,
        deliverables=payload.deliverables,
        channel_id=payload.channel_id,
        member_ids=payload.member_ids,
    )
    await session.commit()
    await events.emit_project_created(session, project)
    rendered = await serialize_projects(session, [project], user.id)
    return rendered[0]


@router.get("/workspaces/{workspace_id}/tasks", response_model=list[TaskOut])
async def read_my_tasks(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[TaskOut]:
    """The tasks of the whole workspace that are mine and not finished."""
    tasks = await my_tasks(session, workspace_id, user.id)
    return await serialize_tasks(session, tasks, user.id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def read_project(
    project_id: str,
    user: CurrentUser,
    session: DbSession,
) -> ProjectOut:
    project = await get_project_or_404(session, project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)
    rendered = await serialize_projects(session, [project], user.id)
    return rendered[0]


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: str,
    payload: ProjectUpdate,
    user: CurrentUser,
    session: DbSession,
) -> ProjectOut:
    project = await get_project_or_404(session, project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can change this project")

    data = payload.model_dump(exclude_unset=True)
    await update_project(session, project, data, project.workspace_id, user.id)
    await session.commit()
    await events.emit_project_updated(session, project)
    rendered = await serialize_projects(session, [project], user.id)
    return rendered[0]


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project(
    project_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    project = await get_project_or_404(session, project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can delete this project")

    await delete_project(session, project)
    await session.commit()
    await events.emit_project_deleted(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/members", response_model=ProjectOut)
async def post_project_member(
    project_id: str,
    payload: ProjectMemberAdd,
    user: CurrentUser,
    session: DbSession,
) -> ProjectOut:
    project = await get_project_or_404(session, project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can change the roster")

    await add_project_member(session, project, payload.user_id, project.workspace_id)
    await session.commit()
    await events.emit_project_updated(session, project)
    rendered = await serialize_projects(session, [project], user.id)
    return rendered[0]


@router.delete("/projects/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_member(
    project_id: str,
    user_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    project = await get_project_or_404(session, project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can change the roster")
    if user_id == project.created_by:
        raise forbidden("the owner cannot be removed from their own project")

    await remove_project_member(session, project, user_id)
    await session.commit()
    await events.emit_project_updated(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/roadmaps", response_model=list[RoadmapOut])
async def read_roadmaps(
    project_id: str,
    user: CurrentUser,
    session: DbSession,
) -> list[RoadmapOut]:
    """The roadmaps of a project, in the order they are shown."""
    project = await get_project_or_404(session, project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)
    roadmaps = await list_roadmaps(session, project.id)
    return await serialize_roadmaps(session, roadmaps)


@router.patch("/roadmaps/{roadmap_id}", response_model=RoadmapOut)
async def patch_roadmap(
    roadmap_id: str,
    payload: RoadmapUpdate,
    user: CurrentUser,
    session: DbSession,
) -> RoadmapOut:
    roadmap = await get_roadmap_or_404(session, roadmap_id)
    project = await get_project_or_404(session, roadmap.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can change this roadmap")

    if payload.name is not None:
        await rename_roadmap(session, roadmap, payload.name)
    await session.commit()
    rendered = await serialize_roadmaps(session, [roadmap])
    return rendered[0]


@router.delete("/roadmaps/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_roadmap(
    roadmap_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Take a roadmap off the board. The tasks planned in it stay."""
    roadmap = await get_roadmap_or_404(session, roadmap_id)
    project = await get_project_or_404(session, roadmap.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("only the project's owner or a workspace admin can delete this roadmap")

    await delete_roadmap(session, roadmap)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def read_tasks(
    project_id: str,
    user: CurrentUser,
    session: DbSession,
) -> list[TaskOut]:
    project = await get_project_or_404(session, project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)
    tasks = await list_tasks(session, project.id)
    return await serialize_tasks(session, tasks, user.id)


@router.post("/projects/{project_id}/tasks", response_model=TaskOut)
async def post_task(
    project_id: str,
    payload: TaskCreate,
    user: CurrentUser,
    session: DbSession,
) -> TaskOut:
    project = await get_project_or_404(session, project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)

    task = await create_task(
        session,
        project,
        user,
        payload.title,
        payload.description,
        payload.status,
        payload.assignee_id,
        payload.start_at,
        payload.due_at,
        payload.roadmap_id,
        milestone_id=payload.milestone_id,
    )
    await session.commit()
    await events.emit_task_created(session, project, task)
    rendered = await serialize_tasks(session, [task], user.id)
    return rendered[0]


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def patch_task(
    task_id: str,
    payload: TaskUpdate,
    user: CurrentUser,
    session: DbSession,
) -> TaskOut:
    task = await get_task_or_404(session, task_id)
    project = await get_project_or_404(session, task.project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)

    data = payload.model_dump(exclude_unset=True)
    await update_task(session, task, data, project.workspace_id)
    await session.commit()
    await events.emit_task_updated(session, project, task)
    rendered = await serialize_tasks(session, [task], user.id)
    return rendered[0]


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task(
    task_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    task = await get_task_or_404(session, task_id)
    project = await get_project_or_404(session, task.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_delete_task(task, project, membership, user.id):
        raise forbidden("only the author, the project's owner or an admin can delete this task")

    await delete_task(session, task)
    await session.commit()
    await events.emit_task_deleted(session, project, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tasks/{task_id}/comments", response_model=TaskCommentOut)
async def post_task_comment(
    task_id: str,
    payload: TaskCommentCreate,
    user: CurrentUser,
    session: DbSession,
) -> TaskCommentOut:
    task = await get_task_or_404(session, task_id)
    project = await get_project_or_404(session, task.project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)

    comment = await add_comment(session, task, user, payload.body)
    await session.commit()
    await events.emit_task_updated(session, project, task)
    return TaskCommentOut(
        id=comment.id,
        task_id=comment.task_id,
        user_id=comment.user_id,
        author=UserOut.model_validate(user),
        body=comment.body,
        created_at=comment.created_at,
    )


@router.delete("/task-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task_comment(
    comment_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    comment = await get_comment_or_404(session, comment_id)
    task = await get_task_or_404(session, comment.task_id)
    project = await get_project_or_404(session, task.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if comment.user_id != user.id and not is_manager(membership):
        raise forbidden("only the author or an admin can delete this comment")

    await delete_comment(session, comment)
    await session.commit()
    await events.emit_task_updated(session, project, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _require_workspace_member(
    session: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMember:
    """The caller's membership of a project's workspace."""
    return await require_membership(session, workspace_id, user_id)
