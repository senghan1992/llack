"""Milestone routes: the dated markers of what is to be delivered."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, WorkspaceMember
from app.core.errors import forbidden
from app.realtime import events
from app.schemas.project import MilestoneCreate, MilestoneOut, MilestoneUpdate
from app.services.members import require_membership
from app.services.projects import (
    can_manage_project,
    create_milestone,
    delete_milestone,
    get_milestone_or_404,
    get_project_or_404,
    list_milestones,
    serialize_milestones,
    update_milestone,
)

router = APIRouter(tags=["milestones"])


@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneOut])
async def read_milestones(
    project_id: str,
    user: CurrentUser,
    session: DbSession,
) -> list[MilestoneOut]:
    """The milestones of a project, the ones that start first in front."""
    project = await get_project_or_404(session, project_id)
    await _require_workspace_member(session, project.workspace_id, user.id)
    milestones = await list_milestones(session, project.id)
    return await serialize_milestones(session, milestones)


@router.post("/projects/{project_id}/milestones", response_model=MilestoneOut)
async def post_milestone(
    project_id: str,
    payload: MilestoneCreate,
    user: CurrentUser,
    session: DbSession,
) -> MilestoneOut:
    """Mark a deliverable on the board of a project.

    A milestone is the dated end of a piece of work: it has its own colour
    and its own cards, and their progress is its progress.
    """
    project = await get_project_or_404(session, project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("프로젝트 책임자나 워크스페이스 관리자만 마일스톤을 만들 수 있습니다")

    milestone = await create_milestone(
        session,
        project,
        user,
        payload.title,
        payload.start_at,
        payload.end_at,
        color=payload.color,
        progress=payload.progress,
        description=payload.description,
        task_ids=payload.task_ids,
    )
    await session.commit()
    await events.emit_milestone_created(session, project, milestone)
    rendered = await serialize_milestones(session, [milestone])
    return rendered[0]


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
async def patch_milestone(
    milestone_id: str,
    payload: MilestoneUpdate,
    user: CurrentUser,
    session: DbSession,
) -> MilestoneOut:
    milestone = await get_milestone_or_404(session, milestone_id)
    project = await get_project_or_404(session, milestone.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("프로젝트 책임자나 워크스페이스 관리자만 마일스톤을 고칠 수 있습니다")

    data = payload.model_dump(exclude_unset=True)
    await update_milestone(session, milestone, data)
    await session.commit()
    await events.emit_milestone_updated(session, project, milestone)
    rendered = await serialize_milestones(session, [milestone])
    return rendered[0]


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_milestone(
    milestone_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Take a milestone off the board. The cards that deliver it stay."""
    milestone = await get_milestone_or_404(session, milestone_id)
    project = await get_project_or_404(session, milestone.project_id)
    membership = await _require_workspace_member(session, project.workspace_id, user.id)
    if not can_manage_project(project, membership, user.id):
        raise forbidden("프로젝트 책임자나 워크스페이스 관리자만 마일스톤을 지울 수 있습니다")

    await delete_milestone(session, milestone)
    await session.commit()
    await events.emit_milestone_deleted(session, project, milestone)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _require_workspace_member(
    session: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMember:
    """The caller's membership of a project's workspace."""
    return await require_membership(session, workspace_id, user_id)
