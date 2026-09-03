"""The audit trail: who did what to whom, as an administrator.

Ordinary messages already carry their author; what was missing is the record
of *administrative* acts — a role change, a removal, an app installed, a
retention policy shortened — the things a compliance review asks about first
and the things a departing admin cannot be asked about later. One row per
act, append-only, never edited by application code.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ULID, Base, Timestamps, ULIDPrimaryKey


class AuditEvent(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_workspace_id_id", "workspace_id", "id"),
        Index("ix_audit_events_actor_id_id", "actor_id", "id"),
    )

    # NULL for server-wide acts (the SMTP relay) that belong to no workspace.
    workspace_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), default=None
    )
    # NULL when the actor was the system (a retention sweep, the scanner).
    actor_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    # Dotted verb: "member.role_changed", "file.quarantined", …
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(26), default=None)
    # A human-readable name captured at the time, because the target may be
    # renamed or gone by the time anyone reads the log.
    target_label: Mapped[str | None] = mapped_column(String(200), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
