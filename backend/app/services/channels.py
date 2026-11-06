"""Channel creation, visibility, membership and serialisation."""

from __future__ import annotations

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, not_found, validation_error
from app.core.ids import CHANNEL_MEMBER_PREFIX, CHANNEL_PREFIX, new_id
from app.models.channel import KIND_CHANNEL, KIND_DM, Channel, ChannelMember
from app.models.message import Message, Reaction, ReadState, message_attachments
from app.models.project import Project
from app.models.schedule import ScheduleEvent
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.channel import ChannelOut
from app.schemas.user import MemberOut
from app.services.messages import unread_counts


async def get_channel_or_404(session: AsyncSession, channel_id: str) -> Channel:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise not_found("channel not found")
    return channel


async def list_channels(session: AsyncSession, workspace_id: str, viewer_id: str) -> list[Channel]:
    """Public channels plus the private ones the viewer belongs to."""
    member_channels = select(ChannelMember.channel_id).where(ChannelMember.user_id == viewer_id)
    rows = await session.scalars(
        select(Channel)
        .where(
            Channel.workspace_id == workspace_id,
            Channel.kind == KIND_CHANNEL,
            (Channel.is_private.is_(False)) | (Channel.id.in_(member_channels)),
        )
        .order_by(Channel.created_at, Channel.id)
    )
    return list(rows)


async def list_dms(session: AsyncSession, workspace_id: str, viewer_id: str) -> list[Channel]:
    rows = await session.scalars(
        select(Channel)
        .join(ChannelMember, ChannelMember.channel_id == Channel.id)
        .where(
            Channel.workspace_id == workspace_id,
            Channel.kind == KIND_DM,
            ChannelMember.user_id == viewer_id,
        )
        .order_by(Channel.created_at, Channel.id)
    )
    return list(rows)


async def create_channel(
    session: AsyncSession,
    workspace: Workspace,
    creator: User,
    name: str,
    topic: str | None = None,
    is_private: bool = False,
    member_ids: list[str] | None = None,
) -> Channel:
    clean_name = name.strip()
    if not clean_name:
        raise validation_error("channel name is required", "name")
    duplicate = await session.scalar(
        select(Channel.id).where(
            Channel.workspace_id == workspace.id,
            Channel.kind == KIND_CHANNEL,
            Channel.name == clean_name,
        )
    )
    if duplicate is not None:
        raise conflict(f"a channel named {clean_name} already exists")

    channel = Channel(
        id=new_id(CHANNEL_PREFIX),
        workspace_id=workspace.id,
        name=clean_name,
        topic=(topic or "").strip(),
        purpose="",
        kind=KIND_CHANNEL,
        is_private=is_private,
        created_by=creator.id,
    )
    session.add(channel)
    session.add(
        ChannelMember(
            id=new_id(CHANNEL_MEMBER_PREFIX),
            channel_id=channel.id,
            user_id=creator.id,
        )
    )
    # The room can be made with people already in it. The creator is in the
    # room already, so they are not added twice.
    for user_id in dict.fromkeys(member_ids or []):
        if user_id == creator.id:
            continue
        session.add(
            ChannelMember(
                id=new_id(CHANNEL_MEMBER_PREFIX),
                channel_id=channel.id,
                user_id=user_id,
            )
        )
    await session.flush()
    return channel


def dm_key(workspace_id: str, first_user_id: str, second_user_id: str) -> str:
    low, high = sorted([first_user_id, second_user_id])
    return f"{workspace_id}:{low}:{high}"


async def create_dm(
    session: AsyncSession, workspace: Workspace, caller: User, target: User
) -> Channel:
    """Return the DM between two users, creating it the first time."""
    if caller.id == target.id:
        raise validation_error("you cannot open a DM with yourself", "user_id")

    key = dm_key(workspace.id, caller.id, target.id)
    existing = await session.scalar(select(Channel).where(Channel.dm_key == key))
    if existing is not None:
        return existing

    channel = Channel(
        id=new_id(CHANNEL_PREFIX),
        workspace_id=workspace.id,
        name=target.name,
        topic="",
        purpose="",
        kind=KIND_DM,
        is_private=True,
        created_by=caller.id,
        dm_key=key,
    )
    session.add(channel)
    for participant in (caller, target):
        session.add(
            ChannelMember(
                id=new_id(CHANNEL_MEMBER_PREFIX),
                channel_id=channel.id,
                user_id=participant.id,
            )
        )
    await session.flush()
    return channel


async def add_channel_member(session: AsyncSession, channel: Channel, user_id: str) -> None:
    existing = await session.scalar(
        select(ChannelMember.id).where(
            ChannelMember.channel_id == channel.id,
            ChannelMember.user_id == user_id,
        )
    )
    if existing is not None:
        return
    session.add(
        ChannelMember(
            id=new_id(CHANNEL_MEMBER_PREFIX),
            channel_id=channel.id,
            user_id=user_id,
        )
    )
    await session.flush()


async def remove_channel_member(session: AsyncSession, channel: Channel, user_id: str) -> None:
    row = await session.scalar(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel.id,
            ChannelMember.user_id == user_id,
        )
    )
    if row is None:
        return
    await session.delete(row)
    await session.flush()


async def delete_channel(session: AsyncSession, channel: Channel) -> None:
    """Delete a channel together with everything inside it.

    SQLite does not enforce foreign keys in this project, so the child
    rows are removed by hand: the attachments of the messages, their
    reactions, the read state of the channel, the roster, the messages
    themselves and the links that pointed at the room.
    """
    message_ids = list(
        await session.scalars(select(Message.id).where(Message.channel_id == channel.id))
    )
    if message_ids:
        await session.execute(
            delete(message_attachments).where(message_attachments.c.message_id.in_(message_ids))
        )
        await session.execute(delete(Reaction).where(Reaction.message_id.in_(message_ids)))
    await session.execute(delete(Message).where(Message.channel_id == channel.id))
    await session.execute(delete(ReadState).where(ReadState.channel_id == channel.id))

    # A project or a schedule that pointed at this room keeps its work and
    # loses the room.
    await session.execute(
        update(Project).where(Project.channel_id == channel.id).values(channel_id=None)
    )
    await session.execute(
        update(ScheduleEvent).where(ScheduleEvent.channel_id == channel.id).values(channel_id=None)
    )

    roster = list(
        await session.scalars(select(ChannelMember).where(ChannelMember.channel_id == channel.id))
    )
    for member in roster:
        await session.delete(member)

    await session.delete(channel)
    await session.flush()


async def list_public_channels(session: AsyncSession, workspace_id: str) -> list[Channel]:
    """Every public channel of the workspace."""
    rows = await session.scalars(
        select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.kind == KIND_CHANNEL,
            Channel.is_private.is_(False),
        )
    )
    return list(rows)


async def join_public_channels(session: AsyncSession, workspace_id: str, user_id: str) -> None:
    for channel in await list_public_channels(session, workspace_id):
        await add_channel_member(session, channel, user_id)


async def list_channel_members(session: AsyncSession, channel: Channel) -> list[MemberOut]:
    """The channel roster, carrying each user's workspace role."""
    rows = await session.execute(
        select(ChannelMember, User, WorkspaceMembership.role)
        .join(User, User.id == ChannelMember.user_id)
        .outerjoin(
            WorkspaceMembership,
            and_(
                WorkspaceMembership.workspace_id == channel.workspace_id,
                WorkspaceMembership.user_id == ChannelMember.user_id,
            ),
        )
        .where(ChannelMember.channel_id == channel.id)
        .order_by(ChannelMember.joined_at, ChannelMember.id)
    )
    return [
        MemberOut(user=user, role=role or "member", joined_at=membership.joined_at)
        for membership, user, role in rows.all()
    ]


async def serialize_channels(
    session: AsyncSession,
    channels: list[Channel],
    viewer_id: str,
    *,
    include_members: bool = False,
) -> list[ChannelOut]:
    """Serialise a batch of channels for one viewer."""
    if not channels:
        return []

    channel_ids = [channel.id for channel in channels]
    counts = await unread_counts(session, channel_ids, viewer_id)

    member_counts = dict(
        (
            await session.execute(
                select(ChannelMember.channel_id, func.count(ChannelMember.id))
                .where(ChannelMember.channel_id.in_(channel_ids))
                .group_by(ChannelMember.channel_id)
            )
        ).all()
    )

    last_messages = dict(
        (
            await session.execute(
                select(Message.channel_id, func.max(Message.created_at))
                .where(
                    Message.channel_id.in_(channel_ids),
                    Message.deleted_at.is_(None),
                )
                .group_by(Message.channel_id)
            )
        ).all()
    )

    dm_channels = [channel.id for channel in channels if channel.kind == KIND_DM]
    dm_partner: dict[str, User] = {}
    if dm_channels:
        rows = await session.execute(
            select(ChannelMember.channel_id, User)
            .join(User, User.id == ChannelMember.user_id)
            .where(
                ChannelMember.channel_id.in_(dm_channels),
                ChannelMember.user_id != viewer_id,
            )
        )
        for channel_id, user in rows.all():
            dm_partner.setdefault(channel_id, user)

    # Which of these the viewer is actually in. A public channel stays in the
    # workspace's directory after you leave it, so the rail needs to know.
    joined = set(
        await session.scalars(
            select(ChannelMember.channel_id).where(
                ChannelMember.user_id == viewer_id,
                ChannelMember.channel_id.in_(channel_ids),
            )
        )
    )

    members_by_channel: dict[str, list[User]] = {}
    if include_members:
        rows = await session.execute(
            select(ChannelMember.channel_id, User)
            .join(User, User.id == ChannelMember.user_id)
            .where(ChannelMember.channel_id.in_(channel_ids))
            .order_by(ChannelMember.joined_at, ChannelMember.id)
        )
        for channel_id, user in rows.all():
            members_by_channel.setdefault(channel_id, []).append(user)

    out: list[ChannelOut] = []
    for channel in channels:
        partner = dm_partner.get(channel.id)
        members = members_by_channel.get(channel.id) if include_members else None
        out.append(
            ChannelOut(
                id=channel.id,
                workspace_id=channel.workspace_id,
                name=partner.name if partner is not None else channel.name,
                topic=channel.topic,
                purpose=channel.purpose,
                kind=channel.kind,
                is_private=channel.is_private,
                created_by=channel.created_by,
                created_at=channel.created_at,
                member_count=int(member_counts.get(channel.id, 0)),
                unread_count=int(counts.get(channel.id, 0)),
                last_message_at=last_messages.get(channel.id),
                dm_user=partner,
                members=members,
                is_member=channel.id in joined,
            )
        )
    return out


async def serialize_channel(
    session: AsyncSession,
    channel: Channel,
    viewer_id: str,
    *,
    include_members: bool = False,
) -> ChannelOut:
    result = await serialize_channels(
        session, [channel], viewer_id, include_members=include_members
    )
    return result[0]
