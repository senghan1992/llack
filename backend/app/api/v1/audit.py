"""Read the audit trail.

Admins of a workspace see its events. Owners additionally see the server-wide
events (SMTP relay changes) that have no workspace, since they are the ones
who could have made them. The CSV export is what gets attached to a
compliance ticket; it streams so a year of events does not have to fit in
memory.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select

from app.api.deps import AdminWorkspaceCtx, DbSession
from app.core.enums import WorkspaceRole
from app.models.audit import AuditEvent
from app.models.user import User
from app.schemas.common import Schema
from app.schemas.user import UserBrief

router = APIRouter(tags=["audit"])

EXPORT_LIMIT = 10_000


class AuditEventOut(Schema):
    id: str
    action: str
    actor: UserBrief | None = None
    target_type: str
    target_id: str | None = None
    target_label: str | None = None
    details: dict[str, Any]
    ip: str | None = None
    created_at: datetime


class AuditPage(Schema):
    items: list[AuditEventOut]
    has_more: bool
    next_before: str | None = None


def _scope(ctx: AdminWorkspaceCtx):  # noqa: ANN202
    if ctx.role is WorkspaceRole.OWNER:
        return or_(
            AuditEvent.workspace_id == ctx.workspace.id,
            AuditEvent.workspace_id.is_(None),
        )
    return AuditEvent.workspace_id == ctx.workspace.id


async def _actors(db: DbSession, events: list[AuditEvent]) -> dict[str, User]:
    ids = {e.actor_id for e in events if e.actor_id}
    if not ids:
        return {}
    rows = await db.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: u for u in rows.all()}


def _serialise(event: AuditEvent, actors: dict[str, User]) -> AuditEventOut:
    actor = actors.get(event.actor_id) if event.actor_id else None
    return AuditEventOut(
        id=event.id,
        action=event.action,
        actor=UserBrief.model_validate(actor) if actor else None,
        target_type=event.target_type,
        target_id=event.target_id,
        target_label=event.target_label,
        details=event.details or {},
        ip=event.ip,
        created_at=event.created_at,
    )


@router.get("/workspaces/{workspace_id}/audit", response_model=AuditPage)
async def list_audit(
    ctx: AdminWorkspaceCtx,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[str | None, Query(max_length=26)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: Annotated[str | None, Query(max_length=26)] = None,
) -> AuditPage:
    stmt = select(AuditEvent).where(_scope(ctx))
    if before:
        stmt = stmt.where(AuditEvent.id < before)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    rows = list((await db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    actors = await _actors(db, rows)
    return AuditPage(
        items=[_serialise(e, actors) for e in rows],
        has_more=has_more,
        next_before=rows[-1].id if rows and has_more else None,
    )


@router.get("/workspaces/{workspace_id}/audit/export.csv")
async def export_audit(ctx: AdminWorkspaceCtx, db: DbSession) -> StreamingResponse:
    """The most recent 10,000 events as CSV, UTF-8 with BOM so Excel reads
    Korean labels correctly."""
    rows = list(
        (
            await db.scalars(
                select(AuditEvent)
                .where(_scope(ctx))
                .order_by(AuditEvent.id.desc())
                .limit(EXPORT_LIMIT)
            )
        ).all()
    )
    actors = await _actors(db, rows)

    async def body() -> AsyncIterator[bytes]:
        yield "﻿".encode()
        buffer = io.StringIO()
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
        writer.writerow(
            ["시각(UTC)", "행위", "행위자", "행위자 이메일", "대상 종류", "대상 id", "대상", "IP",
             "세부"]
        )
        yield buffer.getvalue().encode()
        for event in rows:
            buffer.seek(0)
            buffer.truncate()
            actor = actors.get(event.actor_id) if event.actor_id else None
            writer.writerow(
                [
                    event.created_at.isoformat(),
                    event.action,
                    actor.display_name if actor else "시스템",
                    actor.email if actor else "",
                    event.target_type,
                    event.target_id or "",
                    event.target_label or "",
                    event.ip or "",
                    _compact(event.details),
                ]
            )
            yield buffer.getvalue().encode()

    stamp = datetime.now().strftime("%Y%m%d")
    filename = f"llack-audit-{ctx.workspace.slug}-{stamp}.csv"
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _compact(details: dict[str, Any]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted((details or {}).items()))
