"""Channels (including DMs) and per-member read/notification state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ChannelKind, ChannelRole, NotificationLevel
from app.models.base import ULID, Base, Timestamps, ULIDPrimaryKey, UTCDateTime

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User
    from app.models.workspace import Workspace


class Channel(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "channels"
    __table_args__ = (
        # Names are unique per workspace, but DMs have no name (NULL slugs are
        # allowed to repeat under this constraint on both PG and SQLite).
        UniqueConstraint("workspace_id", "slug", name="uq_channels_workspace_id_slug"),
        Index("ix_channels_workspace_id_kind", "workspace_id", "kind"),
        Index("ix_channels_dm_key", "dm_key"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ChannelKind.PUBLIC.value)

    slug: Mapped[str | None] = mapped_column(String(80), default=None)
    name: Mapped[str | None] = mapped_column(String(120), default=None)
    topic: Mapped[str | None] = mapped_column(String(400), default=None)
    purpose: Mapped[str | None] = mapped_column(Text, default=None)

    # Deterministic key for DMs: sorted member ids joined by ":". Lets
    # "open a DM with X" be an idempotent upsert instead of a search.
    dm_key: Mapped[str | None] = mapped_column(String(600), default=None)

    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Per-channel message retention override; NULL defers to the workspace.
    retention_days: Mapped[int | None] = mapped_column(Integer, default=None)

    created_by: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    # Denormalised so the sidebar can render without touching `messages`.
    last_message_id: Mapped[str | None] = mapped_column(ULID, default=None)
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped[Workspace] = relationship(back_populates="channels", lazy="raise_on_sql")
    members: Mapped[list[ChannelMember]] = relationship(
        back_populates="channel", cascade="all, delete-orphan", lazy="raise_on_sql"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="channel", cascade="all, delete-orphan", lazy="raise_on_sql"
    )

    @property
    def kind_enum(self) -> ChannelKind:
        return ChannelKind(self.kind)


class ChannelMember(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "channel_members"
    __table_args__ = (
        UniqueConstraint("channel_id", "user_id", name="uq_channel_members_channel_id_user_id"),
        Index("ix_channel_members_user_id_channel_id", "user_id", "channel_id"),
    )

    channel_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ChannelRole.MEMBER.value)

    # Read state. `last_read_message_id` is a ULID, so "unread" is the string
    # comparison `message.id > last_read_message_id`.
    last_read_message_id: Mapped[str | None] = mapped_column(ULID, default=None)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    notification_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=NotificationLevel.ALL.value
    )
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # NULL = not in a section; otherwise a user-defined sidebar section name.
    section: Mapped[str | None] = mapped_column(String(80), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set when the user hides a DM without leaving it.
    hidden_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    channel: Mapped[Channel] = relationship(back_populates="members", lazy="raise_on_sql")
    user: Mapped[User] = relationship(lazy="raise_on_sql")
