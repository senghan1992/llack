"""Messages, reactions and per-user read state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

KIND_TEXT = "text"
KIND_SYSTEM = "system"

message_attachments = Table(
    "message_attachments",
    Base.metadata,
    Column(
        "message_id", String(40), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("file_id", String(40), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text, default="")
    # 삭제할 때 본문을 따로 보관한다. "실행 취소" 로 메시지를 되돌리기 위해 필요하다.
    deleted_body: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    kind: Mapped[str] = mapped_column(String(16), default=KIND_TEXT)
    parent_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The message this one answers. A reply also joins the thread of the
    # message it answers, so every reply to a message stays in one place.
    reply_to_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    # True when the reply was written in the channel: it shows there too,
    # quoting the message it answers, as well as in that message's thread.
    inline: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, default=None)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reply_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, default=None)

    author: Mapped[User] = relationship(  # noqa: F821
        lazy="joined", foreign_keys=[user_id], viewonly=True
    )
    attachments: Mapped[list[File]] = relationship(  # noqa: F821
        secondary=message_attachments, lazy="selectin", viewonly=True
    )


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    emoji: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ReadState(Base):
    __tablename__ = "read_states"
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_read_state"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    last_read_message_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=None
    )
    last_read_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
