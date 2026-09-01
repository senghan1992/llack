"""Messages, threads, attachments and reactions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MessageKind
from app.models.base import ULID, Base, SoftDelete, Timestamps, ULIDPrimaryKey, UTCDateTime

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.file import FileObject
    from app.models.user import User


class Message(Base, ULIDPrimaryKey, Timestamps, SoftDelete):
    __tablename__ = "messages"
    __table_args__ = (
        # The channel-history query: WHERE channel_id = ? ORDER BY id DESC.
        Index("ix_messages_channel_id_id", "channel_id", "id"),
        # The thread query.
        Index("ix_messages_parent_id_id", "parent_id", "id"),
        # Idempotent send: the client generates client_msg_id, so a retried
        # POST after a flaky network does not double-post.
        UniqueConstraint(
            "channel_id", "client_msg_id", name="uq_messages_channel_id_client_msg_id"
        ),
    )

    channel_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    # Set when the message was posted by an installed mini-app.
    app_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("apps.id", ondelete="SET NULL"), default=None
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=MessageKind.USER.value)
    client_msg_id: Mapped[str | None] = mapped_column(String(64), default=None)

    # Markdown source of truth. `blocks` holds the parsed/rich representation
    # (app-authored rich layouts, link unfurls, attachments metadata).
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blocks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)

    # Denormalised mention targets so the notification fan-out is one read.
    mentioned_user_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    mentions_everyone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Threading ───────────────────────────────────────────────────────
    parent_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("messages.id", ondelete="CASCADE"), default=None
    )
    # Denormalised on the thread root.
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reply_user_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_reply_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # A threaded reply the author also broadcast to the channel.
    also_sent_to_channel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    channel: Mapped[Channel] = relationship(back_populates="messages", lazy="raise_on_sql")
    author: Mapped[User | None] = relationship(lazy="raise_on_sql")
    parent: Mapped[Message | None] = relationship(remote_side="Message.id", lazy="raise_on_sql")
    reactions: Mapped[list[Reaction]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="raise_on_sql"
    )
    attachments: Mapped[list[MessageAttachment]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="raise_on_sql"
    )

    @property
    def is_thread_reply(self) -> bool:
        return self.parent_id is not None


class Reaction(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "user_id", "emoji", name="uq_reactions_message_id_user_id_emoji"
        ),
        Index("ix_reactions_message_id_emoji", "message_id", "emoji"),
    )

    message_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(80), nullable=False)

    message: Mapped[Message] = relationship(back_populates="reactions", lazy="raise_on_sql")


class MessageAttachment(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "message_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "file_id", name="uq_message_attachments_message_id_file_id"),
    )

    message_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    message: Mapped[Message] = relationship(back_populates="attachments", lazy="raise_on_sql")
    file: Mapped[FileObject] = relationship(lazy="joined")
