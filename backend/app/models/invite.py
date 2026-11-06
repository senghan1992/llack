"""Workspace invitations — the code an admin hands to a new teammate."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow
from app.models.workspace import ROLE_MEMBER

INVITE_TTL_DAYS = 7


def default_expiry() -> datetime:
    """The expiry a freshly written row gets: seven days out."""
    return utcnow() + timedelta(days=INVITE_TTL_DAYS)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MEMBER)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, default=default_expiry)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    accepted_by: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
