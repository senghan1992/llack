"""Invitation acceptance — not workspace-scoped, since the caller is not a
member yet."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, DbSession
from app.core.enums import WorkspaceRole
from app.schemas.common import Payload
from app.schemas.workspace import WorkspaceOut
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/invites", tags=["invites"])


class AcceptInviteRequest(Payload):
    token: str = Field(min_length=10, max_length=512)


@router.post("/accept", response_model=WorkspaceOut)
async def accept_invite(
    payload: AcceptInviteRequest, db: DbSession, user: CurrentUser
) -> WorkspaceOut:
    workspace = await workspace_service.accept_invite(db, token=payload.token, user=user)
    await db.commit()
    membership = await workspace_service.get_membership(
        db, workspace_id=workspace.id, user_id=user.id
    )
    out = WorkspaceOut.model_validate(workspace)
    out.my_role = membership.role_enum if membership else WorkspaceRole.MEMBER
    out.member_count = await workspace_service.count_members(db, workspace.id)
    return out
