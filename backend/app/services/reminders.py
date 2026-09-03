"""Reminders: a saved message that comes back at the time you asked.

`saved_items.remind_at` is the only state. Every minute the worker takes the
due rows nobody has been told about yet, sends one `notification` frame per
row (kind="reminder") and stamps `reminded_at` — so a worker restart, or two
nodes racing, never fires the same reminder twice.

Registered at import time, like the ops workers; the saved-items router
imports this module so it is always registered before the lifespan starts.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import workers
from app.core.logging import get_logger
from app.models.channel import Channel
from app.models.message import Message
from app.models.saved import SavedItem
from app.realtime.events import emit_to_users
from app.services.text import plain_text_preview

log = get_logger(__name__)

BATCH = 200


def reminder_payload(item: SavedItem, message: Message, channel: Channel | None) -> dict:
    where = (
        ""
        if channel is None or channel.kind in ("dm", "group_dm")
        else f"#{channel.name or channel.slug or ''} · "
    )
    body = item.note or plain_text_preview(message.body) or "저장한 메시지"
    return {
        "kind": "reminder",
        "title": "리마인더",
        "body": f"{where}{body}",
        "channel_id": message.channel_id,
        "message_id": message.id,
        "saved_id": item.id,
        "thread_id": message.parent_id,
    }


async def fire_due(now: datetime | None = None) -> int:
    """Send every due reminder once. Returns how many fired."""
    from app.core.db import get_sessionmaker

    now = now or datetime.now(UTC)
    fired = 0
    async with get_sessionmaker()() as db:
        rows = list(
            (
                await db.scalars(
                    select(SavedItem)
                    .where(
                        SavedItem.remind_at.isnot(None),
                        SavedItem.remind_at <= now,
                        SavedItem.reminded_at.is_(None),
                        SavedItem.done_at.is_(None),
                    )
                    .options(selectinload(SavedItem.message))
                    .order_by(SavedItem.remind_at)
                    .limit(BATCH)
                )
            ).all()
        )
        for item in rows:
            message = item.message
            # Stamp first: a notification that fails to send is a lost toast,
            # a reminder that fires every minute forever is a bug report.
            item.reminded_at = now
            await db.flush()
            if message is None or message.deleted_at is not None:
                continue
            channel = await db.get(Channel, message.channel_id)
            try:
                await emit_to_users(
                    [item.user_id],
                    "notification",
                    reminder_payload(item, message, channel),
                    workspace_id=channel.workspace_id if channel else None,
                )
                fired += 1
            except Exception:  # noqa: BLE001
                log.exception("reminders.emit_failed", saved_id=item.id)
        await db.commit()
    if fired:
        log.info("reminders.fired", count=fired)
    return fired


async def _reminders_due() -> None:
    await fire_due()


workers.register("reminders_due", 60, _reminders_due)
