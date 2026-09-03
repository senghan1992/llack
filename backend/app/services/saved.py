"""Saved items — the service behind 나중에."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models.saved import SavedItem


async def save(
    db: AsyncSession,
    *,
    user_id: str,
    message_id: str,
    note: str | None,
    remind_at: datetime | None,
) -> SavedItem:
    """Create or update the viewer's bookmark on a message.

    Saving again re-arms the reminder: a new `remind_at` clears `reminded_at`
    so "remind me again tomorrow" works on an item that already fired, and
    reopens a done item because the person clearly still wants it.
    """
    item = await db.scalar(
        select(SavedItem)
        .where(SavedItem.user_id == user_id, SavedItem.message_id == message_id)
        .limit(1)
    )
    if item is None:
        item = SavedItem(user_id=user_id, message_id=message_id)
        db.add(item)
    item.note = note
    item.remind_at = remind_at
    item.reminded_at = None
    item.done_at = None
    await db.flush()
    return item


async def unsave(db: AsyncSession, *, user_id: str, message_id: str) -> bool:
    item = await db.scalar(
        select(SavedItem)
        .where(SavedItem.user_id == user_id, SavedItem.message_id == message_id)
        .limit(1)
    )
    if item is None:
        return False
    await db.delete(item)
    await db.flush()
    return True


async def get_owned(db: AsyncSession, *, saved_id: str, user_id: str) -> SavedItem:
    item = await db.get(SavedItem, saved_id)
    if item is None or item.user_id != user_id:
        raise NotFound("This saved item does not exist.", code="saved_not_found")
    return item


async def set_done(db: AsyncSession, item: SavedItem, *, done: bool) -> SavedItem:
    item.done_at = datetime.now(UTC) if done else None
    await db.flush()
    return item
