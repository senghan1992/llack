"""Organization routes: the units a workspace is arranged in."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.models.org import OrgUnit as OrgUnitRow
from app.models.workspace import WorkspaceMembership
from app.realtime import events
from app.schemas.org import (
    OrgManagerAdd,
    OrgMemberAdd,
    OrgOverview,
    OrgUnit,
    OrgUnitCreate,
    OrgUnitUpdate,
)
from app.services import org as org_service
from app.services.members import require_membership

router = APIRouter(tags=["org"])


@router.get("/workspaces/{workspace_id}/org", response_model=OrgOverview)
async def read_org(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> OrgOverview:
    """The organization of the workspace, with the caller's own reach."""
    return await org_service.serialize_overview(session, workspace_id, user.id, membership)


@router.post("/workspaces/{workspace_id}/org/units", response_model=OrgUnit)
async def post_org_unit(
    workspace_id: WorkspaceId,
    payload: OrgUnitCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> OrgUnit:
    """Open a unit — at the top of the tree, or under a unit the caller looks after."""
    scope = await org_service.managed_unit_ids(session, workspace_id, user.id, membership)
    unit = await org_service.create_unit(
        session,
        workspace_id,
        user,
        membership,
        scope,
        payload.name,
        parent_id=payload.parent_id,
        kind=payload.kind,
        description=payload.description,
    )
    await session.commit()
    await events.emit_org_changed(session, workspace_id)
    return (await org_service.serialize_units(session, [unit], scope, user.id))[0]


@router.patch("/org/units/{unit_id}", response_model=OrgUnit)
async def patch_org_unit(
    unit_id: str,
    payload: OrgUnitUpdate,
    user: CurrentUser,
    session: DbSession,
) -> OrgUnit:
    """Rename a unit, write about it, or hang it under another one."""
    unit, membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.update_unit(
        session, unit, membership, scope, payload.model_dump(exclude_unset=True)
    )
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return (await org_service.serialize_units(session, [unit], scope, user.id))[0]


@router.delete("/org/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_unit(
    unit_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Take a unit away — but only when it is empty."""
    unit, _membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.delete_unit(session, unit, scope)
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/org/units/{unit_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def post_org_member(
    unit_id: str,
    payload: OrgMemberAdd,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Put a person into a unit."""
    unit, _membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.add_unit_member(session, unit, payload.user_id, unit.workspace_id, scope)
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/org/units/{unit_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_member(
    unit_id: str,
    user_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Take a person out of a unit."""
    unit, _membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.remove_unit_member(session, unit, user_id, scope)
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/org/units/{unit_id}/managers", status_code=status.HTTP_204_NO_CONTENT)
async def post_org_manager(
    unit_id: str,
    payload: OrgManagerAdd,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Appoint a person to look after a unit."""
    unit, membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.appoint_manager(
        session, unit, payload.user_id, user, unit.workspace_id, scope, membership
    )
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/org/units/{unit_id}/managers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_manager(
    unit_id: str,
    user_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Take the appointment away. A manager may do this to themselves."""
    unit, _membership, scope = await _unit_context(session, unit_id, user.id)
    await org_service.dismiss_manager(session, unit, user_id, scope)
    await session.commit()
    await events.emit_org_changed(session, unit.workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _unit_context(
    session: AsyncSession, unit_id: str, user_id: str
) -> tuple[OrgUnitRow, WorkspaceMembership, set[str]]:
    """The unit, the caller's membership of its workspace, and their reach."""
    unit = await org_service.get_unit_or_404(session, unit_id)
    membership = await require_membership(session, unit.workspace_id, user_id)
    scope = await org_service.managed_unit_ids(session, unit.workspace_id, user_id, membership)
    return unit, membership, scope
