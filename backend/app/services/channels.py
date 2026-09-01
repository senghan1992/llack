"""Channel lifecycle, membership, DM resolution and read state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ChannelKind, ChannelRole, WorkspaceRole
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.models.channel import Channel, ChannelMember
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services.workspaces import ensure_unique_channel_slug, require_membership

log = get_logger(__name__)


def build_dm_key(user_ids: list[str]) -> str:
    """Deterministic identity for a DM, independent of who opened it."""
    return ":".join(sorted(set(user_ids)))


async def get_channel(db: AsyncSession, channel_id: str) -> Channel:
    channel = await db.get(Channel, channel_id)
    if channel is None:
        raise NotFound("Channel not found.", code="channel_not_found")
    return channel


async def get_channel_member(
    db: AsyncSession, *, channel_id: str, user_id: str
) -> ChannelMember | None:
    return await db.scalar(
        select(ChannelMember)
        .where(ChannelMember.channel_id == channel_id, ChannelMember.user_id == user_id)
        .limit(1)
    )


async def resolve_access(
    db: AsyncSession, *, channel_id: str, user_id: str, require_member: bool = True
) -> tuple[Channel, ChannelMember | None]:
    """Load a channel the user is allowed to see, plus their membership.

    Public channels in a workspace the user belongs to are readable without
    joining — that is what makes "browse channels" work. Private channels and
    DMs require membership.
    """
    channel = await get_channel(db, channel_id)
    membership = await get_channel_member(db, channel_id=channel_id, user_id=user_id)

    if membership is None:
        if channel.kind != ChannelKind.PUBLIC.value:
            raise NotFound("Channel not found.", code="channel_not_found")
        # Confirms the user is at least in the workspace.
        await require_membership(db, workspace_id=channel.workspace_id, user_id=user_id)
        if require_member:
            raise Forbidden("Join this channel first.", code="not_channel_member")

    return channel, membership


async def create_channel(
    db: AsyncSession,
    *,
    workspace_id: str,
    creator: User,
    name: str,
    slug: str | None,
    kind: ChannelKind,
    topic: str | None = None,
    purpose: str | None = None,
    member_ids: list[str] | None = None,
) -> Channel:
    await require_membership(
        db, workspace_id=workspace_id, user_id=creator.id, minimum_role=WorkspaceRole.MEMBER
    )

    if slug:
        taken = await db.scalar(
            select(Channel.id)
            .where(Channel.workspace_id == workspace_id, Channel.slug == slug)
            .limit(1)
        )
        if taken is not None:
            raise Conflict("A channel with this name already exists.", code="channel_slug_taken")
        final_slug = slug
    else:
        final_slug = await ensure_unique_channel_slug(db, workspace_id=workspace_id, name=name)

    channel = Channel(
        id=new_ulid(),
        workspace_id=workspace_id,
        kind=kind.value,
        slug=final_slug,
        name=name.strip(),
        topic=topic,
        purpose=purpose,
        created_by=creator.id,
    )
    db.add(channel)

    invitees = {creator.id, *(member_ids or [])}
    # Only people already in the workspace can be added.
    valid_ids = set(
        (
            await db.scalars(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id.in_(invitees),
                    WorkspaceMember.is_active.is_(True),
                )
            )
        ).all()
    )
    for user_id in valid_ids:
        db.add(
            ChannelMember(
                id=new_ulid(),
                channel_id=channel.id,
                user_id=user_id,
                role=ChannelRole.ADMIN.value if user_id == creator.id else ChannelRole.MEMBER.value,
            )
        )
    channel.member_count = len(valid_ids)

    await db.flush()
    log.info("channel.created", channel_id=channel.id, kind=kind.value, workspace_id=workspace_id)
    return channel


async def open_dm(
    db: AsyncSession, *, workspace_id: str, opener: User, user_ids: list[str]
) -> tuple[Channel, bool]:
    """Get-or-create a DM. Returns (channel, created)."""
    await require_membership(db, workspace_id=workspace_id, user_id=opener.id)

    participants = sorted({opener.id, *user_ids})
    if len(participants) < 2:
        raise Conflict("A direct message needs at least one other person.", code="dm_needs_peer")

    valid_ids = set(
        (
            await db.scalars(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id.in_(participants),
                    WorkspaceMember.is_active.is_(True),
                )
            )
        ).all()
    )
    missing = set(participants) - valid_ids
    if missing:
        raise NotFound(
            "Some of these people are not in this workspace.",
            code="user_not_in_workspace",
            details={"user_ids": sorted(missing)},
        )

    dm_key = build_dm_key(participants)
    existing = await db.scalar(
        select(Channel)
        .where(Channel.workspace_id == workspace_id, Channel.dm_key == dm_key)
        .limit(1)
    )
    if existing is not None:
        # Un-hide it for everyone involved: a new message should resurface a
        # conversation someone previously closed.
        await db.execute(
            update(ChannelMember)
            .where(ChannelMember.channel_id == existing.id)
            .values(hidden_at=None)
        )
        await db.flush()
        return existing, False

    kind = ChannelKind.DM if len(participants) == 2 else ChannelKind.GROUP_DM
    channel = Channel(
        id=new_ulid(),
        workspace_id=workspace_id,
        kind=kind.value,
        dm_key=dm_key,
        created_by=opener.id,
        member_count=len(participants),
    )
    db.add(channel)
    for user_id in participants:
        db.add(ChannelMember(id=new_ulid(), channel_id=channel.id, user_id=user_id))
    await db.flush()
    return channel, True


async def join_channel(db: AsyncSession, *, channel: Channel, user_id: str) -> ChannelMember:
    if channel.kind_enum.is_conversation:
        raise Forbidden("Direct messages cannot be joined.", code="cannot_join_dm")
    if channel.is_archived:
        raise Forbidden("This channel is archived.", code="channel_archived")
    if channel.kind == ChannelKind.PRIVATE.value:
        raise Forbidden("Private channels are invite-only.", code="channel_private")

    await require_membership(db, workspace_id=channel.workspace_id, user_id=user_id)

    existing = await get_channel_member(db, channel_id=channel.id, user_id=user_id)
    if existing is not None:
        return existing

    membership = ChannelMember(id=new_ulid(), channel_id=channel.id, user_id=user_id)
    db.add(membership)
    channel.member_count += 1
    await db.flush()
    return membership


async def leave_channel(db: AsyncSession, *, channel: Channel, user_id: str) -> None:
    if channel.kind_enum.is_conversation:
        # Leaving a DM hides it instead of removing membership, so history is
        # preserved and a new message can bring it back.
        await db.execute(
            update(ChannelMember)
            .where(ChannelMember.channel_id == channel.id, ChannelMember.user_id == user_id)
            .values(hidden_at=datetime.now(UTC))
        )
        await db.flush()
        return

    membership = await get_channel_member(db, channel_id=channel.id, user_id=user_id)
    if membership is None:
        return
    await db.delete(membership)
    channel.member_count = max(0, channel.member_count - 1)
    await db.flush()


async def add_members(
    db: AsyncSession, *, channel: Channel, user_ids: list[str], actor_id: str
) -> list[str]:
    """Add workspace members to a channel. Returns the ids actually added."""
    if channel.kind_enum.is_conversation:
        raise Forbidden(
            "Add people by opening a new group message instead.", code="cannot_add_to_dm"
        )
    await require_membership(db, workspace_id=channel.workspace_id, user_id=actor_id)

    eligible = set(
        (
            await db.scalars(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == channel.workspace_id,
                    WorkspaceMember.user_id.in_(set(user_ids)),
                    WorkspaceMember.is_active.is_(True),
                )
            )
        ).all()
    )
    already = set(
        (
            await db.scalars(
                select(ChannelMember.user_id).where(
                    ChannelMember.channel_id == channel.id,
                    ChannelMember.user_id.in_(eligible),
                )
            )
        ).all()
    )
    to_add = sorted(eligible - already)
    for user_id in to_add:
        db.add(ChannelMember(id=new_ulid(), channel_id=channel.id, user_id=user_id))
    channel.member_count += len(to_add)
    await db.flush()
    return to_add


async def list_my_channels(
    db: AsyncSession, *, workspace_id: str, user_id: str, include_archived: bool = False
) -> list[tuple[Channel, ChannelMember]]:
    conditions = [
        Channel.workspace_id == workspace_id,
        ChannelMember.user_id == user_id,
        # A hidden DM stays out of the sidebar until it has new activity.
        or_(
            ChannelMember.hidden_at.is_(None),
            and_(
                Channel.last_message_at.isnot(None),
                Channel.last_message_at > ChannelMember.hidden_at,
            ),
        ),
    ]
    if not include_archived:
        conditions.append(Channel.is_archived.is_(False))

    rows = await db.execute(
        select(Channel, ChannelMember)
        .join(ChannelMember, ChannelMember.channel_id == Channel.id)
        .where(*conditions)
        .order_by(
            ChannelMember.is_starred.desc(),
            ChannelMember.sort_order,
            Channel.last_message_at.desc().nullslast(),
            Channel.name,
        )
    )
    return [(c, m) for c, m in rows.all()]


async def browse_channels(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    query: str | None = None,
    limit: int = 50,
) -> list[Channel]:
    """Public channels in the workspace, joined or not."""
    await require_membership(db, workspace_id=workspace_id, user_id=user_id)
    stmt = select(Channel).where(
        Channel.workspace_id == workspace_id,
        Channel.kind == ChannelKind.PUBLIC.value,
        Channel.is_archived.is_(False),
    )
    if query:
        pattern = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Channel.name).like(pattern), func.lower(Channel.slug).like(pattern))
        )
    stmt = stmt.order_by(Channel.member_count.desc(), Channel.name).limit(limit)
    return list((await db.scalars(stmt)).all())


async def dm_peers(db: AsyncSession, *, channel_id: str, exclude_user_id: str) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(ChannelMember, ChannelMember.user_id == User.id)
        .where(ChannelMember.channel_id == channel_id, User.id != exclude_user_id)
        .order_by(User.display_name)
    )
    return list(rows.all())


async def mark_read(
    db: AsyncSession, *, membership: ChannelMember, message_id: str | None, channel: Channel
) -> ChannelMember:
    target = message_id or channel.last_message_id
    # Never move the read marker backwards; ULIDs make that a string compare.
    if target and (
        membership.last_read_message_id is None or target > membership.last_read_message_id
    ):
        membership.last_read_message_id = target
        membership.unread_count = 0
        membership.mention_count = 0
        await db.flush()
    return membership


async def recompute_unread(
    db: AsyncSession, *, membership: ChannelMember
) -> tuple[int, int]:
    """Recount unread/mentions from `messages`. Used on reconnect and repair."""
    from app.models.message import Message

    cursor = membership.last_read_message_id or ""
    total = (
        await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.channel_id == membership.channel_id,
                Message.id > cursor,
                Message.deleted_at.is_(None),
                Message.user_id != membership.user_id,
            )
        )
    ) or 0
    membership.unread_count = total
    await db.flush()
    return total, membership.mention_count
