"""Membership lookups and channel access rules."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden
from app.models.channel import KIND_CHANNEL, Channel, ChannelMember
from app.models.workspace import ROLE_ADMIN, ROLE_OWNER, WorkspaceMembership


async def get_membership(
    session: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMembership | None:
    return await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )


async def require_membership(
    session: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMembership:
    membership = await get_membership(session, workspace_id, user_id)
    if membership is None:
        raise forbidden("you are not a member of this workspace")
    return membership


def is_manager(membership: WorkspaceMembership) -> bool:
    return membership.role in (ROLE_OWNER, ROLE_ADMIN)


async def is_channel_member(session: AsyncSession, channel_id: str, user_id: str) -> bool:
    found = await session.scalar(
        select(ChannelMember.id).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == user_id,
        )
    )
    return found is not None


async def channel_member_ids(session: AsyncSession, channel_id: str) -> set[str]:
    rows = await session.scalars(
        select(ChannelMember.user_id).where(ChannelMember.channel_id == channel_id)
    )
    return set(rows.all())


async def workspace_member_ids(session: AsyncSession, workspace_id: str) -> set[str]:
    rows = await session.scalars(
        select(WorkspaceMembership.user_id).where(WorkspaceMembership.workspace_id == workspace_id)
    )
    return set(rows.all())


async def channel_audience(session: AsyncSession, channel: Channel) -> set[str]:
    """Every user that should receive live events for ``channel``."""
    audience = await channel_member_ids(session, channel.id)
    if channel.kind == KIND_CHANNEL and not channel.is_private:
        audience |= await workspace_member_ids(session, channel.workspace_id)
    return audience


async def require_channel_access(
    session: AsyncSession, channel: Channel, user_id: str
) -> WorkspaceMembership:
    """Enforce the visibility rules of ``docs/API.md`` for one channel."""
    membership = await require_membership(session, channel.workspace_id, user_id)
    if (channel.kind != KIND_CHANNEL or channel.is_private) and not await is_channel_member(
        session, channel.id, user_id
    ):
        raise forbidden("you are not a member of this channel")
    return membership
