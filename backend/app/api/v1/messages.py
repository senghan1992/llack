"""Message routes: editing, deleting, reactions, pins and thread replies."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession, MessageId
from app.core.errors import forbidden, not_found
from app.models.channel import Channel
from app.models.message import Message
from app.models.workspace import WorkspaceMembership
from app.realtime import events
from app.schemas.message import MessageOut, MessageUpdate, ReactionCreate
from app.services.members import is_manager, require_channel_access
from app.services.messages import (
    MAX_PAGE_SIZE,
    delete_message,
    edit_message,
    get_message_or_404,
    list_thread_replies,
    remove_reaction,
    restore_message,
    serialize_message,
    serialize_messages,
    set_pinned,
    toggle_reaction,
)

router = APIRouter(prefix="/messages", tags=["messages"])


async def _load_message(
    session: DbSession, user: CurrentUser, message_id: str
) -> tuple[Message, Channel, WorkspaceMembership]:
    """Load a message and check that the caller may see its channel."""
    message = await get_message_or_404(session, message_id)
    channel = await session.get(Channel, message.channel_id)
    if channel is None:
        raise not_found("channel not found")
    membership = await require_channel_access(session, channel, user.id)
    return message, channel, membership


def _can_modify(user: CurrentUser, message: Message, membership: WorkspaceMembership) -> bool:
    """Authors may edit their own messages, owners and admins may edit any."""
    if message.user_id == user.id:
        return True
    return is_manager(membership)


@router.patch("/{message_id}", response_model=MessageOut)
async def update_message(
    payload: MessageUpdate,
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    message, channel, membership = await _load_message(session, user, message_id)
    if not _can_modify(user, message, membership):
        raise forbidden("only the author or an admin can edit this message")

    await edit_message(session, message, payload.body)
    await session.commit()
    await events.emit_message_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_route(
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    message, channel, membership = await _load_message(session, user, message_id)
    if not _can_modify(user, message, membership):
        raise forbidden("only the author or an admin can delete this message")

    await delete_message(session, message)
    await session.commit()
    await events.emit_message_deleted(session, channel, message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{message_id}/restore", response_model=MessageOut)
async def restore_message_route(
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    """Undo a deletion: the message comes back with its body."""
    message, channel, membership = await _load_message(session, user, message_id)
    if not _can_modify(user, message, membership):
        raise forbidden("only the author or an admin can restore this message")

    await restore_message(session, message)
    await session.commit()
    # 다른 기기에서도 즉시 복구된 메시지가 보이도록 알린다.
    await events.emit_message_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.post("/{message_id}/reactions", response_model=MessageOut)
async def add_reaction(
    payload: ReactionCreate,
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    message, channel, _ = await _load_message(session, user, message_id)
    await toggle_reaction(session, message, user.id, payload.emoji)
    await session.commit()
    await events.emit_reaction_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.delete("/{message_id}/reactions/{emoji}", response_model=MessageOut)
async def delete_reaction(
    message_id: MessageId,
    emoji: str,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    message, channel, _ = await _load_message(session, user, message_id)
    await remove_reaction(session, message, user.id, emoji)
    await session.commit()
    await events.emit_reaction_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.post("/{message_id}/pin", response_model=MessageOut)
async def pin_message(
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    message, channel, membership = await _load_message(session, user, message_id)
    if message.user_id != user.id and not is_manager(membership):
        raise forbidden("only the author or an admin can pin this message")

    await set_pinned(session, message, True)
    await session.commit()
    await events.emit_message_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.delete("/{message_id}/pin", response_model=MessageOut)
async def unpin_message(
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    message, channel, membership = await _load_message(session, user, message_id)
    if message.user_id != user.id and not is_manager(membership):
        raise forbidden("only the author or an admin can unpin this message")

    await set_pinned(session, message, False)
    await session.commit()
    await events.emit_message_updated(session, channel, message)
    return await serialize_message(session, message, user.id)


@router.get("/{message_id}/replies", response_model=list[MessageOut])
async def read_replies(
    message_id: MessageId,
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=MAX_PAGE_SIZE, ge=1),
) -> list[MessageOut]:
    """The replies of a thread root, oldest first."""
    message, _channel, _membership = await _load_message(session, user, message_id)
    replies = await list_thread_replies(session, message, limit)
    return await serialize_messages(session, replies, user.id)
