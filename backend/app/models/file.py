"""Uploaded files.

A file is a workspace-scoped object with its own lifecycle; messages reference
it via `message_attachments`. That way the same file can be shared into several
channels without being re-uploaded, and the Files browser can list everything
in a workspace independently of the messages that mention it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ULID, Base, SoftDelete, Timestamps, ULIDPrimaryKey, UTCDateTime
from app.models.user import User


class FileObject(Base, ULIDPrimaryKey, Timestamps, SoftDelete):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_workspace_id_id", "workspace_id", "id"),
        Index("ix_files_uploader_id_id", "uploader_id", "id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    uploader_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(160), nullable=False, default="application/octet-stream"
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None, index=True)

    # Opaque key in the configured backend (local path fragment or S3 key).
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(16), nullable=False, default="local")

    # Image/video dimensions, page count, generated thumbnail key, …
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    thumbnail_key: Mapped[str | None] = mapped_column(Text, default=None)

    # False until the bytes finished uploading, so a half-written file is
    # never attached to a message.
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Antivirus verdict: skipped (no scanner configured) | pending | clean |
    # infected | error. Infected files are quarantined (bytes gone, row kept
    # so the transcript can say what happened).
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="skipped")
    # Set for files stored by a mini-app rather than a person.
    app_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("apps.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    uploader: Mapped[User | None] = relationship(lazy="joined")

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")
