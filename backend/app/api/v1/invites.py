"""Workspace invitations: listing, creating, revoking and accepting them."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.core.errors import forbidden, not_found
from app.models.invite import Invite
from app.realtime import events
from app.schemas.invite import InviteAccept, InviteCreate, InviteOut
from app.schemas.workspace import WorkspaceOut
from app.services import invites as invite_service
from app.services.channels import list_public_channels
from app.services.members import is_manager
from app.services.workspaces import get_workspace_or_404

router = APIRouter(tags=["invites"])


@router.get("/workspaces/{workspace_id}/invites", response_model=list[InviteOut])
async def read_invites(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> list[InviteOut]:
    if not is_manager(membership):
        raise forbidden("only owners and admins can see the invites")
    rows = await invite_service.list_pending_invites(session, workspace_id)
    return [InviteOut.model_validate(invite) for invite in rows]


@router.post("/workspaces/{workspace_id}/invites", response_model=InviteOut)
async def create_new_invite(
    workspace_id: WorkspaceId,
    payload: InviteCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> InviteOut:
    if not is_manager(membership):
        raise forbidden("only owners and admins can invite people")
    workspace = await get_workspace_or_404(session, workspace_id)
    invite = await invite_service.create_invite(
        session, workspace, user, payload.email, payload.role
    )
    await session.commit()
    return InviteOut.model_validate(invite)


@router.delete(
    "/workspaces/{workspace_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_invite(
    workspace_id: WorkspaceId,
    invite_id: str,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> Response:
    if not is_manager(membership):
        raise forbidden("only owners and admins can revoke invites")

    invite = await session.get(Invite, invite_id)
    if invite is None or invite.workspace_id != workspace_id:
        raise not_found("invite not found")

    await invite_service.revoke_invite(session, invite)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invites/accept", response_model=WorkspaceOut)
async def accept_invite(
    payload: InviteAccept,
    user: CurrentUser,
    session: DbSession,
) -> WorkspaceOut:
    workspace = await invite_service.accept_invite(session, payload.token, user)
    await session.commit()
    for channel in await list_public_channels(session, workspace.id):
        await events.emit_members_changed(session, channel)
    return WorkspaceOut.model_validate(workspace)
