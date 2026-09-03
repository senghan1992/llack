"""Retention: forget on schedule.

A workspace sets how many days messages and files live; a channel may keep
its messages shorter or longer than the workspace. Once an hour the sweep
soft-deletes what has aged out — the message row stays (so "삭제된 메시지"
still anchors its thread), the body goes, the attachment links go, and the
file's bytes leave storage. Nothing is exempt: a pinned message under a
90-day policy is a 90-day message. That is the point of a policy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.channel import Channel
from app.models.file import FileObject
from app.models.message import Message, MessageAttachment
from app.models.workspace import Workspace
from app.services.storage import get_storage

log = get_logger(__name__)

BATCH = 500


def effective_message_days(channel: Channel, workspace: Workspace) -> int | None:
    """Channel override wins; NULL means keep forever."""
    if channel.retention_days is not None:
        return channel.retention_days
    return workspace.retention_days_messages


async def sweep_messages(db: AsyncSession, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    swept = 0
    workspaces = (await db.scalars(select(Workspace))).all()
    for workspace in workspaces:
        channels = (
            await db.scalars(
                select(Channel).where(
                    Channel.workspace_id == workspace.id,
                    or_(
                        Channel.retention_days.isnot(None),
                        Workspace.retention_days_messages.isnot(None)
                        if workspace.retention_days_messages is not None
                        else Channel.retention_days.isnot(None),
                    ),
                )
            )
        ).all()
        for channel in channels:
            days = effective_message_days(channel, workspace)
            if days is None or days <= 0:
                continue
            cutoff = now - timedelta(days=days)
            while True:
                ids = list(
                    (
                        await db.scalars(
                            select(Message.id)
                            .where(
                                Message.channel_id == channel.id,
                                Message.deleted_at.is_(None),
                                Message.created_at < cutoff,
                            )
                            .limit(BATCH)
                        )
                    ).all()
                )
                if not ids:
                    break
                await db.execute(
                    delete(MessageAttachment).where(MessageAttachment.message_id.in_(ids))
                )
                await db.execute(
                    update(Message)
                    .where(Message.id.in_(ids))
                    .values(deleted_at=now, body="", blocks=None)
                )
                await db.commit()
                swept += len(ids)
                if len(ids) < BATCH:
                    break
    return swept


async def sweep_files(db: AsyncSession, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    swept = 0
    storage = get_storage()
    workspaces = (
        await db.scalars(select(Workspace).where(Workspace.retention_days_files.isnot(None)))
    ).all()
    for workspace in workspaces:
        days = workspace.retention_days_files
        if not days or days <= 0:
            continue
        cutoff = now - timedelta(days=days)
        files = (
            await db.scalars(
                select(FileObject)
                .where(
                    FileObject.workspace_id == workspace.id,
                    FileObject.deleted_at.is_(None),
                    FileObject.created_at < cutoff,
                    # A file still being scanned is a decision in flight.
                    FileObject.scan_status != "pending",
                )
                .limit(BATCH)
            )
        ).all()
        for file in files:
            try:
                await storage.delete(file.storage_key)
                if file.thumbnail_key:
                    await storage.delete(file.thumbnail_key)
            except Exception:  # noqa: BLE001 — a missing blob is already gone
                log.warning("retention.file_delete_failed", file_id=file.id)
            file.deleted_at = now
            await db.execute(
                delete(MessageAttachment).where(MessageAttachment.file_id == file.id)
            )
            swept += 1
        await db.commit()
    return swept


async def sweep(db: AsyncSession) -> tuple[int, int]:
    messages = await sweep_messages(db)
    files = await sweep_files(db)
    log.info("retention.swept", messages=messages, files=files)
    return messages, files
