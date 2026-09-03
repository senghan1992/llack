"""Write to the audit trail.

One function, called from the routes that perform administrative acts. It
never raises into the caller — a failed audit insert must not roll back the
act it describes, but it is logged loudly because a silent gap in an audit
log is the one failure mode the log exists to prevent.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditEvent
from app.models.user import User

log = get_logger(__name__)


def _ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


async def record(
    db: AsyncSession,
    *,
    workspace_id: str | None,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    target_label: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditEvent | None:
    """Append one event. The caller commits with the act it belongs to."""
    try:
        event = AuditEvent(
            workspace_id=workspace_id,
            actor_id=actor.id if actor else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=(target_label or None) and str(target_label)[:200],
            details=details or {},
            ip=_ip(request),
        )
        db.add(event)
        await db.flush()
        return event
    except Exception:  # noqa: BLE001
        log.exception("audit.record_failed", action=action, workspace_id=workspace_id)
        return None
