"""Workspaces, their channels, DMs and members."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.core.errors import conflict, forbidden, not_found
from app.models.channel import Channel, ChannelMember
from app.models.org import OrgUnit, OrgUnitManager, OrgUnitMember
from app.models.user import User
from app.models.workspace import ROLE_OWNER, WorkspaceMembership
from app.realtime import events
from app.schemas.channel import ChannelCreate, ChannelOut, DmCreate
from app.schemas.user import MemberOut, UserOut
from app.schemas.workspace import BootstrapOut, WorkspaceCreate, WorkspaceOut
from app.services.channels import (
    create_channel,
    create_dm,
    list_channels,
    list_dms,
    serialize_channels,
)
from app.services.members import is_manager
from app.services.org import org_summary
from app.services.workspaces import (
    create_workspace,
    get_workspace_or_404,
    list_members,
    list_workspaces,
    remove_member,
    set_role,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class RoleUpdate(BaseModel):
    role: Literal["owner", "admin", "member"]


@router.get("", response_model=list[WorkspaceOut])
async def read_workspaces(user: CurrentUser, session: DbSession) -> list[WorkspaceOut]:
    workspaces = await list_workspaces(session, user.id)
    return [WorkspaceOut.model_validate(workspace) for workspace in workspaces]


@router.post("", response_model=WorkspaceOut)
async def create_new_workspace(
    payload: WorkspaceCreate, user: CurrentUser, session: DbSession
) -> WorkspaceOut:
    workspace = await create_workspace(session, user, payload.name)
    await session.commit()
    return WorkspaceOut.model_validate(workspace)


@router.get("/{workspace_id}/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> BootstrapOut:
    workspace = await get_workspace_or_404(session, workspace_id)
    channels = await list_channels(session, workspace_id, user.id)
    dms = await list_dms(session, workspace_id, user.id)

    channel_payload = await serialize_channels(session, channels, user.id)
    dm_payload = await serialize_channels(session, dms, user.id)
    return BootstrapOut(
        workspace=WorkspaceOut.model_validate(workspace),
        channels=channel_payload,
        dms=dm_payload,
        members=await list_members(session, workspace_id),
        me=UserOut.model_validate(user),
        org=await org_summary(session, workspace_id, user.id, membership),
    )


@router.get("/{workspace_id}/channels", response_model=list[ChannelOut])
async def read_channels(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[ChannelOut]:
    channels = await list_channels(session, workspace_id, user.id)
    return await serialize_channels(session, channels, user.id)


@router.post("/{workspace_id}/channels", response_model=ChannelOut)
async def create_new_channel(
    workspace_id: WorkspaceId,
    payload: ChannelCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> ChannelOut:
    if payload.is_private and not is_manager(membership):
        raise forbidden("only owners and admins can create private channels")

    workspace = await get_workspace_or_404(session, workspace_id)
    # The room can be made with people in it, but only people who are already
    # in the workspace — a room is not a way around the invite.
    newcomers = list(dict.fromkeys(payload.member_ids))
    if newcomers:
        found = set(
            await session.scalars(
                select(WorkspaceMembership.user_id).where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.user_id.in_(newcomers),
                )
            )
        )
        missing = [user_id for user_id in newcomers if user_id not in found]
        if missing:
            raise not_found("that person is not a member of this workspace")
    channel = await create_channel(
        session,
        workspace,
        user,
        payload.name,
        payload.topic,
        payload.is_private,
        newcomers,
    )
    await session.commit()
    await events.emit_channel_created(session, channel)
    if newcomers:
        await events.emit_members_changed(session, channel)
    return (await serialize_channels(session, [channel], user.id))[0]


@router.get("/{workspace_id}/dms", response_model=list[ChannelOut])
async def read_dms(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[ChannelOut]:
    dms = await list_dms(session, workspace_id, user.id)
    return await serialize_channels(session, dms, user.id)


@router.post("/{workspace_id}/dms", response_model=ChannelOut)
async def open_dm(
    workspace_id: WorkspaceId,
    payload: DmCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> ChannelOut:
    target = await session.get(User, payload.user_id)
    if target is None:
        raise not_found("user not found")

    target_membership = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == target.id,
        )
    )
    if target_membership is None:
        raise forbidden("that user is not a member of this workspace")

    workspace = await get_workspace_or_404(session, workspace_id)
    channel = await create_dm(session, workspace, user, target)
    await session.commit()
    return (await serialize_channels(session, [channel], user.id))[0]


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
async def read_members(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[MemberOut]:
    return await list_members(session, workspace_id)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
async def update_member_role(
    workspace_id: WorkspaceId,
    user_id: str,
    payload: RoleUpdate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> MemberOut:
    if not is_manager(membership):
        raise forbidden("only owners and admins can change roles")
    if payload.role == ROLE_OWNER and membership.role != ROLE_OWNER:
        raise forbidden("only an owner can grant the owner role")

    target = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if target is None:
        raise not_found("member not found")

    if target.role == ROLE_OWNER and payload.role != ROLE_OWNER:
        await _guard_last_owner(session, workspace_id)

    await set_role(session, target, payload.role)
    await session.commit()
    target_user = await session.get(User, target.user_id)
    return MemberOut(
        user=UserOut.model_validate(target_user),
        role=target.role,
        joined_at=target.joined_at,
    )


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    workspace_id: WorkspaceId,
    user_id: str,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> Response:
    if not is_manager(membership):
        raise forbidden("only owners and admins can remove members")

    target = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if target is None:
        raise not_found("member not found")
    if target.role == ROLE_OWNER:
        await _guard_last_owner(session, workspace_id)

    rows = await session.scalars(select(ChannelMember).where(ChannelMember.user_id == user_id))
    for row in list(rows):
        channel = await session.get(Channel, row.channel_id)
        if channel is not None and channel.workspace_id == workspace_id:
            await session.delete(row)

    # The organization goes with the person: a seat in a unit and the
    # appointment to look after it belong to a member of this workspace.
    for row in list(
        await session.scalars(select(OrgUnitMember).where(OrgUnitMember.user_id == user_id))
    ):
        unit = await session.get(OrgUnit, row.org_unit_id)
        if unit is not None and unit.workspace_id == workspace_id:
            await session.delete(row)

    for row in list(
        await session.scalars(select(OrgUnitManager).where(OrgUnitManager.user_id == user_id))
    ):
        unit = await session.get(OrgUnit, row.org_unit_id)
        if unit is not None and unit.workspace_id == workspace_id:
            await session.delete(row)

    await remove_member(session, target)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _guard_last_owner(session: DbSession, workspace_id: str) -> None:
    owners = await session.scalars(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == ROLE_OWNER,
        )
    )
    if len(list(owners.all())) <= 1:
        raise conflict("a workspace must keep at least one owner")
