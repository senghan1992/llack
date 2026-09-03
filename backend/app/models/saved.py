"""Saved messages, reminders, and the link-preview cache."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ULID, Base, Timestamps, ULIDPrimaryKey, UTCDateTime

if TYPE_CHECKING:
    from app.models.message import Message


class SavedItem(Base, ULIDPrimaryKey, Timestamps):
    """A message someone kept for later — Slack's "Later", with a reminder.

    One row per (user, message). `remind_at` turns the bookmark into a
    notification at that moment; `reminded_at` records that it fired so a
    restarted worker never fires it twice; `done_at` moves it to the 완료 tab.
    """

    __tablename__ = "saved_items"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_saved_items_user_id_message_id"),
        Index("ix_saved_items_user_id_done_at_id", "user_id", "done_at", "id"),
        Index("ix_saved_items_remind_at", "remind_at"),
    )

    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    remind_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    message: Mapped[Message] = relationship(lazy="raise_on_sql")


class LinkPreview(Base):
    """What a URL looked like the last time the server fetched it.

    Keyed by the URL's SHA-256 so a long URL never overflows an index. A
    failed fetch is remembered too (`title`/`description` empty, `ok` false)
    so a dead link does not get re-fetched on every message that pastes it.
    """

    __tablename__ = "link_previews"

    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), default=None)
    description: Mapped[str | None] = mapped_column(String(1000), default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    site_name: Mapped[str | None] = mapped_column(String(200), default=None)
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
