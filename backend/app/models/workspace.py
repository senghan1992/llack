"""Workspaces (tenants), their members and invitations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import WorkspaceRole
from app.models.base import ULID, Base, Timestamps, ULIDPrimaryKey, UTCDateTime

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.user import User


class Workspace(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "workspaces"

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon_url: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    # Email domains that may self-serve join (["example.com"]).
    allowed_email_domains: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Free-form policy knobs: who may install apps, etc.
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Retention: NULL = keep forever. Messages older than N days are
    # soft-deleted (body cleared, attachments unlinked); files older than N
    # days are removed from storage. A channel may override the message value.
    retention_days_messages: Mapped[int | None] = mapped_column(Integer, default=None)
    retention_days_files: Mapped[int | None] = mapped_column(Integer, default=None)

    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", lazy="raise_on_sql"
    )
    channels: Mapped[list[Channel]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", lazy="raise_on_sql"
    )


class WorkspaceMember(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "workspace_members"
    __table_args__ = (
        Index("uq_workspace_members_workspace_id_user_id", "workspace_id", "user_id", unique=True),
    )

    workspace_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WorkspaceRole.MEMBER.value
    )
    # Order of the workspace rail in the desktop client.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workspace: Mapped[Workspace] = relationship(back_populates="members", lazy="raise_on_sql")
    user: Mapped[User] = relationship(back_populates="memberships", lazy="raise_on_sql")

    @property
    def role_enum(self) -> WorkspaceRole:
        return WorkspaceRole(self.role)


class WorkspaceInvite(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "workspace_invites"

    workspace_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WorkspaceRole.MEMBER.value
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    invited_by: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
