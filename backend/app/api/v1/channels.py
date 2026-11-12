"""Channel routes: metadata, membership, messages, pins and read state."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.deps import ChannelAccess, CurrentUser, DbSession
from app.core.errors import forbidden, not_found, validation_error
from app.models.channel import KIND_CHANNEL, KIND_DM
from app.models.workspace import WorkspaceMembership
from app.realtime import events
from app.schemas.channel import ChannelMemberAdd, ChannelOut, ChannelUpdate, ReadUpdate
from app.schemas.message import MessageCreate, MessageOut, MessagePage
from app.schemas.user import MemberOut
from app.services.channels import (
    add_channel_member,
    delete_channel,
    list_channel_members,
    remove_channel_member,
    serialize_channel,
)
from app.services.members import is_channel_member, is_manager
from app.services.messages import (
    DEFAULT_PAGE_SIZE,
    create_message,
    list_messages_around,
    list_messages_after,
    list_messages_with_flags,
    list_pinned,
    mark_read,
    serialize_message,
    serialize_messages,
)

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("/{channel_id}", response_model=ChannelOut)
async def read_channel(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> ChannelOut:
    return await serialize_channel(session, channel[0], user.id, include_members=True)


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    payload: ChannelUpdate,
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> ChannelOut:
    target, membership = channel
    if target.created_by != user.id and not is_manager(membership):
        raise forbidden("only the channel creator or a workspace admin can edit a channel")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        target.name = data["name"].strip()
    if "topic" in data and data["topic"] is not None:
        target.topic = data["topic"].strip()
    if "purpose" in data and data["purpose"] is not None:
        target.purpose = data["purpose"].strip()

    await session.commit()
    await events.emit_channel_updated(session, target)
    return await serialize_channel(session, target, user.id)


@router.post("/{channel_id}/join", response_model=ChannelOut)
async def join_channel(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> ChannelOut:
    target, _ = channel
    if target.kind != KIND_CHANNEL or target.is_private:
        raise forbidden("you cannot join this channel")

    await add_channel_member(session, target, user.id)
    await session.commit()
    await events.emit_members_changed(session, target)
    return await serialize_channel(session, target, user.id, include_members=True)


@router.post("/{channel_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_channel(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    target, _ = channel
    if target.kind == KIND_DM:
        raise forbidden("you cannot leave a direct message")

    await remove_channel_member(session, target, user.id)
    await session.commit()
    await events.emit_members_changed(session, target)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{channel_id}/members", response_model=list[MemberOut])
async def read_channel_members(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> list[MemberOut]:
    return await list_channel_members(session, channel[0])


@router.post("/{channel_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member_to_channel(
    payload: ChannelMemberAdd,
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Put someone into a room.

    A member of a public room may bring a colleague in. A private room is a
    manager's business only, and the newcomer has to be in the workspace
    already — a room is not a way around the workspace invite.
    """
    target, membership = channel
    if target.kind != KIND_CHANNEL:
        raise forbidden("you cannot add people to a direct message")

    manager = is_manager(membership)
    if target.is_private:
        if not manager:
            raise forbidden("only a workspace admin can invite people to a private channel")
    elif not manager and not await is_channel_member(session, target.id, user.id):
        raise forbidden("only members of this channel can add people to it")

    newcomer = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == target.workspace_id,
            WorkspaceMembership.user_id == payload.user_id,
        )
    )
    if newcomer is None:
        raise not_found("that person is not a member of this workspace")

    await add_channel_member(session, target, payload.user_id)
    await session.commit()
    await events.emit_members_changed(session, target)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_route(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    """Delete a direct message, for both of the people in it.

    A conversation between two people is theirs alone: when one of them
    ends it, it ends for the other one too. Ordinary channels are not
    deleted this way.
    """
    target, _ = channel
    if target.kind != KIND_DM:
        raise forbidden("only a direct message can be deleted")

    await delete_channel(session, target)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{channel_id}/pins", response_model=list[MessageOut])
async def read_pins(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> list[MessageOut]:
    pins = await list_pinned(session, channel[0])
    return await serialize_messages(session, pins, user.id)


@router.post("/{channel_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_channel_read(
    payload: ReadUpdate,
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    await mark_read(session, channel[0], user.id, payload.message_id)
    await session.commit()
    await events.emit_unread_counts(session, channel[0])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{channel_id}/messages", response_model=MessagePage)
async def read_messages(
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    before: str | None = Query(default=None),
    after: str | None = Query(default=None),
    around: str | None = Query(default=None),
) -> MessagePage:
    """One page of a channel's messages.

    ``before`` walks backwards through the history, ``after`` walks forward
    (the opposite direction) and ``around`` returns a window with the given
    message in the middle. The cursors are exclusive: the anchor message
    itself is only part of the answer when ``around`` is used.
    """
    if around is not None and (before is not None or after is not None):
        raise validation_error("around cannot be combined with before or after")
    if before is not None and after is not None:
        raise validation_error("before and after cannot be used together")

    if around is not None:
        messages, has_more, has_more_after = await list_messages_around(
            session, channel[0], limit, around
        )
    elif after is not None:
        messages, has_more, has_more_after = await list_messages_after(
            session, channel[0], limit, after
        )
    else:
        messages, has_more, has_more_after = await list_messages_with_flags(
            session, channel[0], limit, before
        )
    return MessagePage(
        messages=await serialize_messages(session, messages, user.id),
        has_more=has_more,
        has_more_after=has_more_after,
    )


@router.post("/{channel_id}/messages", response_model=MessageOut)
async def post_message(
    payload: MessageCreate,
    channel: ChannelAccess,
    user: CurrentUser,
    session: DbSession,
) -> MessageOut:
    target, _ = channel
    message = await create_message(
        session,
        target,
        user,
        payload.body,
        payload.parent_id,
        payload.reply_to_id,
        payload.inline,
        payload.attachment_ids,
    )
    await session.commit()
    await events.emit_message_created(session, target, message)
    return await serialize_message(session, message, user.id)
