"""Uploaded files."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(150))
    size: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The workspace that keeps this file. It owns the file's place on disk
    # and counts it against the workspace's quota.
    workspace_id: Mapped[str | None] = mapped_column(String(40), index=True, default=None)
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
