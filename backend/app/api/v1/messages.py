"""Message endpoints, including threads and reactions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ChannelCtx, CurrentUser, DbSession, PrincipalChannelCtx
from app.core.config import settings
from app.core.enums import AppScope, ChannelRole, MessageKind
from app.core.ratelimit import limiter
from app.realtime.events import emit_to_channel, emit_to_users
from app.schemas.common import CursorPage, OkResponse
from app.schemas.file import FileOut
from app.schemas.message import (
    CreateMessageRequest,
    MessageCore,
    MessageOut,
    ReactionRequest,
    UpdateMessageRequest,
)
from app.schemas.realtime import ServerEvent
from app.schemas.user import UserBrief
from app.services import messages as message_service

router = APIRouter(tags=["messages"])


# ── Serialisation ───────────────────────────────────────────────────────────


def serialise_message(message, *, viewer_id: str | None) -> MessageOut:  # noqa: ANN001
    """Render a Message ORM row for a specific viewer.

    Requires `author`, `reactions` and `attachments` to already be loaded —
    the models use `lazy="raise_on_sql"`, so a missing eager load raises here
    instead of silently firing one query per message.
    """
    return MessageOut(
        **MessageCore.model_validate(message).model_dump(),
        author=UserBrief.model_validate(message.author) if message.author else None,
        reactions=message_service.reactions_summary(message, viewer_id=viewer_id),
        attachments=[
            FileOut(
                **FileOut.model_validate(a.file).model_dump(
                    exclude={"download_url", "thumbnail_url"}
                ),
                download_url=f"/files/{a.file.id}/download",
                thumbnail_url=f"/files/{a.file.id}/thumbnail" if a.file.thumbnail_key else None,
            )
            for a in sorted(message.attachments, key=lambda a: a.sort_order)
        ],
    )


# ── History ─────────────────────────────────────────────────────────────────


@router.get("/channels/{channel_id}/messages", response_model=CursorPage[MessageOut])
async def list_messages(
    ctx: ChannelCtx,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[str | None, Query(max_length=26)] = None,
    after: Annotated[str | None, Query(max_length=26)] = None,
) -> CursorPage[MessageOut]:
    """Channel history, newest first. Thread replies are excluded."""
    rows, has_more = await message_service.history(
        db, channel_id=ctx.channel.id, limit=limit, before=before, after=after
    )
    items = [serialise_message(m, viewer_id=ctx.user.id) for m in rows]
    return CursorPage[MessageOut](
        items=items,
        next_cursor=items[-1].id if items and has_more else None,
        prev_cursor=items[0].id if items else None,
        has_more=has_more,
    )


@router.get("/messages/{message_id}", response_model=MessageOut)
async def get_message(message_id: str, db: DbSession, user: CurrentUser) -> MessageOut:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id)
    await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=False
    )
    return serialise_message(message, viewer_id=user.id)


@router.get("/messages/{message_id}/replies", response_model=CursorPage[MessageOut])
async def list_thread_replies(
    message_id: str,
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    after: Annotated[str | None, Query(max_length=26)] = None,
) -> CursorPage[MessageOut]:
    """Thread replies, oldest first."""
    from app.services.channels import resolve_access

    root = await message_service.get_message(db, message_id, with_relations=False)
    await resolve_access(
        db, channel_id=root.channel_id, user_id=user.id, require_member=False
    )
    rows, has_more = await message_service.thread_replies(
        db, parent_id=message_id, limit=limit, after=after
    )
    items = [serialise_message(m, viewer_id=user.id) for m in rows]
    return CursorPage[MessageOut](
        items=items,
        next_cursor=items[-1].id if items and has_more else None,
        has_more=has_more,
    )


# ── Create ──────────────────────────────────────────────────────────────────


@router.post(
    "/channels/{channel_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    payload: CreateMessageRequest, ctx: PrincipalChannelCtx, db: DbSession
) -> MessageOut:
    """Post a message.

    Accepts a user token or a mini-app token. `client_msg_id` makes the call
    idempotent, so a retry after a dropped response returns the original
    message with 201 rather than posting twice.
    """
    ctx.require_scope(AppScope.MESSAGES_WRITE)
    ctx.require_member()
    limiter.check(
        "messages",
        ctx.user.id,
        capacity=settings.rate_limit_messages_per_10s,
        per_seconds=10,
    )

    message, created = await message_service.create_message(
        db,
        channel=ctx.channel,
        author=ctx.user,
        body=payload.body,
        blocks=payload.blocks,
        client_msg_id=payload.client_msg_id,
        parent_id=payload.parent_id,
        also_send_to_channel=payload.also_send_to_channel,
        file_ids=payload.file_ids,
        app_id=ctx.principal.installation.app_id if ctx.is_app else None,
        kind=MessageKind.APP if ctx.is_app else MessageKind.USER,
    )
    await db.commit()

    # A freshly inserted row has no relationships loaded, and the replay path
    # returns a row whose relationships were loaded by a different query — so
    # load them explicitly before serialising either way.
    await db.refresh(message, ["author", "reactions", "attachments"])
    out = serialise_message(message, viewer_id=ctx.user.id)

    if not created:
        # Replayed request: the event was already fanned out the first time.
        return out

    await emit_to_channel(
        ctx.channel.id,
        ServerEvent.MESSAGE_CREATED,
        {"message": out.model_dump(mode="json")},
        workspace_id=ctx.channel.workspace_id,
    )

    # Desktop notifications go to the people whose settings ask for them.
    targets = await message_service.notifiable_user_ids(
        db, message=message, channel=ctx.channel
    )
    if targets:
        names = await message_service.mention_display_names(
            db, message.mentioned_user_ids
        )
        await emit_to_users(
            targets,
            "notification",
            message_service.notification_preview(
                message,
                channel=ctx.channel,
                author_name=ctx.user.display_name,
                names=names,
            ),
            workspace_id=ctx.channel.workspace_id,
        )
    return out


# ── Edit / delete ───────────────────────────────────────────────────────────


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def update_message(
    message_id: str, payload: UpdateMessageRequest, db: DbSession, user: CurrentUser
) -> MessageOut:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id)
    channel, _ = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    await message_service.update_message(
        db,
        message=message,
        actor=user,
        body=payload.body,
        blocks=payload.blocks,
        workspace_id=channel.workspace_id,
    )
    await db.commit()

    out = serialise_message(message, viewer_id=user.id)
    await emit_to_channel(
        channel.id,
        ServerEvent.MESSAGE_UPDATED,
        {"message": out.model_dump(mode="json")},
        workspace_id=channel.workspace_id,
    )
    return out


@router.delete("/messages/{message_id}", response_model=OkResponse)
async def delete_message(message_id: str, db: DbSession, user: CurrentUser) -> OkResponse:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id, with_relations=False)
    channel, membership = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    is_channel_admin = membership is not None and membership.role == ChannelRole.ADMIN.value
    await message_service.delete_message(
        db, message=message, actor=user, is_channel_admin=is_channel_admin
    )
    await db.commit()

    await emit_to_channel(
        channel.id,
        ServerEvent.MESSAGE_DELETED,
        {
            "message_id": message.id,
            "channel_id": channel.id,
            "parent_id": message.parent_id,
        },
        workspace_id=channel.workspace_id,
    )
    return OkResponse()


# ── Reactions ───────────────────────────────────────────────────────────────


@router.put("/messages/{message_id}/reactions", response_model=OkResponse)
async def add_reaction(
    message_id: str, payload: ReactionRequest, db: DbSession, user: CurrentUser
) -> OkResponse:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id, with_relations=False)
    channel, _ = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    _, created = await message_service.add_reaction(
        db, message=message, user_id=user.id, emoji=payload.emoji
    )
    await db.commit()

    if created:
        await emit_to_channel(
            channel.id,
            ServerEvent.REACTION_ADDED,
            {
                "message_id": message.id,
                "channel_id": channel.id,
                "emoji": payload.emoji,
                "user_id": user.id,
            },
            workspace_id=channel.workspace_id,
        )
    return OkResponse()


@router.delete("/messages/{message_id}/reactions", response_model=OkResponse)
async def remove_reaction(
    message_id: str,
    db: DbSession,
    user: CurrentUser,
    emoji: Annotated[str, Query(min_length=1, max_length=80)],
) -> OkResponse:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id, with_relations=False)
    channel, _ = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    removed = await message_service.remove_reaction(
        db, message_id=message.id, user_id=user.id, emoji=emoji
    )
    await db.commit()

    if removed:
        await emit_to_channel(
            channel.id,
            ServerEvent.REACTION_REMOVED,
            {
                "message_id": message.id,
                "channel_id": channel.id,
                "emoji": emoji,
                "user_id": user.id,
            },
            workspace_id=channel.workspace_id,
        )
    return OkResponse()


# ── Pins ────────────────────────────────────────────────────────────────────


@router.post("/messages/{message_id}/pin", response_model=MessageOut)
async def toggle_pin(
    message_id: str,
    db: DbSession,
    user: CurrentUser,
    pinned: Annotated[bool, Query()] = True,
) -> MessageOut:
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id)
    channel, _ = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    message.is_pinned = pinned
    await db.commit()

    out = serialise_message(message, viewer_id=user.id)
    await emit_to_channel(
        channel.id,
        ServerEvent.MESSAGE_UPDATED,
        {"message": out.model_dump(mode="json")},
        workspace_id=channel.workspace_id,
    )
    return out


@router.get("/channels/{channel_id}/pins", response_model=list[MessageOut])
async def list_pins(ctx: ChannelCtx, db: DbSession) -> list[MessageOut]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.message import Message, MessageAttachment

    rows = await db.scalars(
        select(Message)
        .where(
            Message.channel_id == ctx.channel.id,
            Message.is_pinned.is_(True),
            Message.deleted_at.is_(None),
        )
        .options(
            selectinload(Message.author),
            selectinload(Message.reactions),
            selectinload(Message.attachments).selectinload(MessageAttachment.file),
        )
        .order_by(Message.id.desc())
        .limit(100)
    )
    return [serialise_message(m, viewer_id=ctx.user.id) for m in rows.all()]
