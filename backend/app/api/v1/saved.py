"""나중에 볼 항목: save a message, list what you saved, mark it done.

The list is filtered by the viewer's *current* channel memberships, so a
message saved from a channel the viewer has since left (or been removed from)
does not keep showing them its text.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, WorkspaceCtx
from app.api.v1.activity import _channel_refs
from app.api.v1.messages import serialise_message
from app.models.channel import Channel, ChannelMember
from app.models.message import Message, MessageAttachment
from app.models.saved import SavedItem
from app.schemas.common import OkResponse
from app.schemas.saved import SavedItemOut, SavedItemPage, SaveMessageRequest
from app.services import messages as message_service
from app.services import reminders as _reminders  # noqa: F401 — registers the worker
from app.services import saved as saved_service
from app.services.channels import resolve_access

router = APIRouter(tags=["saved"])


def _message_relations() -> list:  # noqa: ANN202
    return [
        selectinload(Message.author),
        selectinload(Message.reactions),
        selectinload(Message.attachments).selectinload(MessageAttachment.file),
    ]


async def _serialise_item(db: DbSession, item: SavedItem, *, viewer_id: str) -> SavedItemOut:
    message = await db.scalar(
        select(Message).where(Message.id == item.message_id).options(*_message_relations())
    )
    refs = await _channel_refs(db, channel_ids={message.channel_id}, viewer_id=viewer_id)
    return SavedItemOut(
        id=item.id,
        note=item.note,
        remind_at=item.remind_at,
        reminded_at=item.reminded_at,
        done_at=item.done_at,
        created_at=item.created_at,
        message=serialise_message(message, viewer_id=viewer_id, saved={message.id}),
        channel=refs[message.channel_id],
    )


@router.put("/messages/{message_id}/save", response_model=SavedItemOut)
async def save_message(
    message_id: str, payload: SaveMessageRequest, db: DbSession, user: CurrentUser
) -> SavedItemOut:
    message = await message_service.get_message(db, message_id, with_relations=False)
    await resolve_access(db, channel_id=message.channel_id, user_id=user.id, require_member=True)
    item = await saved_service.save(
        db,
        user_id=user.id,
        message_id=message.id,
        note=payload.note,
        remind_at=payload.remind_at,
    )
    await db.commit()
    return await _serialise_item(db, item, viewer_id=user.id)


@router.delete("/messages/{message_id}/save", response_model=OkResponse)
async def unsave_message(message_id: str, db: DbSession, user: CurrentUser) -> OkResponse:
    await saved_service.unsave(db, user_id=user.id, message_id=message_id)
    await db.commit()
    return OkResponse()


@router.post("/saved/{saved_id}/done", response_model=SavedItemOut)
async def mark_done(saved_id: str, db: DbSession, user: CurrentUser) -> SavedItemOut:
    item = await saved_service.get_owned(db, saved_id=saved_id, user_id=user.id)
    await saved_service.set_done(db, item, done=True)
    await db.commit()
    return await _serialise_item(db, item, viewer_id=user.id)


@router.post("/saved/{saved_id}/reopen", response_model=SavedItemOut)
async def reopen(saved_id: str, db: DbSession, user: CurrentUser) -> SavedItemOut:
    item = await saved_service.get_owned(db, saved_id=saved_id, user_id=user.id)
    await saved_service.set_done(db, item, done=False)
    await db.commit()
    return await _serialise_item(db, item, viewer_id=user.id)


@router.get("/workspaces/{workspace_id}/saved", response_model=SavedItemPage)
async def list_saved(
    ctx: WorkspaceCtx,
    db: DbSession,
    done: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query(max_length=26)] = None,
) -> SavedItemPage:
    viewer = ctx.user.id
    stmt = (
        select(SavedItem, Message)
        .join(Message, Message.id == SavedItem.message_id)
        .join(Channel, Channel.id == Message.channel_id)
        .join(
            ChannelMember,
            (ChannelMember.channel_id == Message.channel_id) & (ChannelMember.user_id == viewer),
        )
        .where(
            SavedItem.user_id == viewer,
            Channel.workspace_id == ctx.workspace.id,
            Message.deleted_at.is_(None),
            SavedItem.done_at.isnot(None) if done else SavedItem.done_at.is_(None),
        )
        .options(*_message_relations())
        .order_by(SavedItem.id.desc())
        .limit(limit + 1)
    )
    if before:
        stmt = stmt.where(SavedItem.id < before)
    rows = list((await db.execute(stmt)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    refs = await _channel_refs(
        db, channel_ids={message.channel_id for _item, message in rows}, viewer_id=viewer
    )
    saved_ids = {message.id for _item, message in rows}
    items = [
        SavedItemOut(
            id=item.id,
            note=item.note,
            remind_at=item.remind_at,
            reminded_at=item.reminded_at,
            done_at=item.done_at,
            created_at=item.created_at,
            message=serialise_message(message, viewer_id=viewer, saved=saved_ids),
            channel=refs[message.channel_id],
        )
        for item, message in rows
    ]
    return SavedItemPage(
        items=items,
        has_more=has_more,
        next_before=items[-1].id if items and has_more else None,
    )
