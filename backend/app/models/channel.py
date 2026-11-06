"""Channels (public/private) and direct-message channels."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

KIND_CHANNEL = "channel"
KIND_DM = "dm"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    topic: Mapped[str] = mapped_column(String(300), default="")
    purpose: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(16), default=KIND_CHANNEL, index=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dm_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)

    members: Mapped[list[ChannelMember]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelMember(Base):
    __tablename__ = "channel_memberships"
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    channel: Mapped[Channel] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="channel_memberships")  # noqa: F821
