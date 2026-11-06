"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import current_user
from app.models.channel import Channel
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.services.channels import get_channel_or_404
from app.services.members import require_channel_access, require_membership
from app.services.workspaces import get_workspace_or_404

WorkspaceId = Annotated[str, Path(description="Workspace id")]
ChannelId = Annotated[str, Path(description="Channel id")]
MessageId = Annotated[str, Path(description="Message id")]

CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


async def workspace_membership(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
) -> WorkspaceMembership:
    """The caller's membership of the workspace, or 404/403."""
    await get_workspace_or_404(session, workspace_id)
    return await require_membership(session, workspace_id, user.id)


async def channel_with_access(
    channel_id: ChannelId,
    user: CurrentUser,
    session: DbSession,
) -> tuple[Channel, WorkspaceMembership]:
    """The channel plus the caller's membership, enforcing visibility rules."""
    channel = await get_channel_or_404(session, channel_id)
    membership = await require_channel_access(session, channel, user.id)
    return channel, membership


WorkspaceMember = Annotated[WorkspaceMembership, Depends(workspace_membership)]
ChannelAccess = Annotated[tuple[Channel, WorkspaceMembership], Depends(channel_with_access)]
