"""Message search inside a workspace."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import KIND_CHANNEL, Channel, ChannelMember
from app.models.message import Message
from app.schemas.search import SearchResult
from app.services.channels import serialize_channels
from app.services.messages import serialize_messages


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_messages(
    session: AsyncSession,
    workspace_id: str,
    viewer_id: str,
    query: str,
    limit: int = 30,
) -> list[SearchResult]:
    """Search the messages of every channel the viewer can read."""
    term = query.strip()
    if not term:
        return []

    member_channels = select(ChannelMember.channel_id).where(ChannelMember.user_id == viewer_id)
    readable = select(Channel.id).where(
        Channel.workspace_id == workspace_id,
        or_(
            and_(Channel.kind == KIND_CHANNEL, Channel.is_private.is_(False)),
            Channel.id.in_(member_channels),
        ),
    )
    rows = await session.scalars(
        select(Message)
        .where(
            Message.channel_id.in_(readable),
            Message.deleted_at.is_(None),
            Message.body.ilike(f"%{_escape_like(term)}%", escape="\\"),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    messages = list(rows)
    if not messages:
        return []

    channel_ids = list({message.channel_id for message in messages})
    channels = list(await session.scalars(select(Channel).where(Channel.id.in_(channel_ids))))

    serialized_messages = await serialize_messages(session, messages, viewer_id)
    message_map = {item.id: item for item in serialized_messages}
    serialized_channels = await serialize_channels(session, channels, viewer_id)
    channel_map = {item.id: item for item in serialized_channels}

    results: list[SearchResult] = []
    for message in messages:
        channel_out = channel_map.get(message.channel_id)
        message_out = message_map.get(message.id)
        if channel_out is None or message_out is None:
            continue
        results.append(SearchResult(message=message_out, channel=channel_out))
    return results
