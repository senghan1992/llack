"""The user table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

PRESENCE_ONLINE = "online"
PRESENCE_BUSY = "busy"
PRESENCE_AWAY = "away"
PRESENCE_DND = "dnd"
PRESENCE_BRB = "brb"
PRESENCE_OFFLINE = "offline"

# The states a person claims for themselves. They are not the app's to give
# or take back: a socket opening does not turn "busy" into "online".
PRESENCE_CLAIMED = (PRESENCE_BUSY, PRESENCE_DND, PRESENCE_AWAY, PRESENCE_BRB)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str | None] = mapped_column(String(120), default=None)
    status_text: Mapped[str | None] = mapped_column(String(120), default=None)
    avatar_color: Mapped[str] = mapped_column(String(16), default="#3f6f52")
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    presence: Mapped[str] = mapped_column(String(16), default=PRESENCE_OFFLINE, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    memberships: Mapped[list[WorkspaceMembership]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    channel_memberships: Mapped[list[ChannelMember]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    org_memberships: Mapped[list[OrgUnitMember]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    org_appointments: Mapped[list[OrgUnitManager]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="OrgUnitManager.user_id",
    )
