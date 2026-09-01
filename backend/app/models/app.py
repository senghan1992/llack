"""The mini-app platform.

An **App** is a registered piece of software (first-party or written by a team
inside the company). Installing it into a workspace creates an
**AppInstallation**, which is what actually grants scopes, holds configuration
and owns the app's key/value storage.

Separating the two matters: the same internal tool (say "배포 현황") is authored
once and installed into several workspaces, each with its own config and its
own granted scopes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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

from app.core.enums import AppKind, AppStatus
from app.models.base import ULID, Base, Timestamps, ULIDPrimaryKey, UTCDateTime


class App(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "apps"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_apps_slug"),
        Index("ix_apps_owner_workspace_id", "owner_workspace_id"),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Accent colour used for the dock icon badge and panel chrome.
    accent_color: Mapped[str | None] = mapped_column(String(16), default=None)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=AppKind.PANEL.value)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AppStatus.DRAFT.value)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.1.0")

    # NULL = available to every workspace on this deployment ("사내 공용 앱").
    # Set = a private app authored by and only installable in that workspace.
    owner_workspace_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), default=None
    )
    author_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    # ── Surfaces ────────────────────────────────────────────────────────
    # URL loaded into the sandboxed panel webview.
    panel_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Optional compact surface rendered inside a channel's right rail.
    sidebar_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Where the backend POSTs events the app subscribed to.
    event_webhook_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Default panel geometry hint for the host window.
    default_width: Mapped[int] = mapped_column(Integer, nullable=False, default=420)

    # ── Manifest ────────────────────────────────────────────────────────
    requested_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Slash commands the app registers: [{"command": "/standup", "description": ...}]
    slash_commands: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Event names the app subscribes to: ["message.created", "channel.joined"]
    event_subscriptions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Full manifest as submitted, kept verbatim for auditing and re-validation.
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    is_first_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    installations: Mapped[list[AppInstallation]] = relationship(
        back_populates="app", cascade="all, delete-orphan", lazy="raise_on_sql"
    )

    @property
    def kind_enum(self) -> AppKind:
        return AppKind(self.kind)

    @property
    def has_panel(self) -> bool:
        return self.kind in (AppKind.PANEL.value, AppKind.BOTH.value) and bool(self.panel_url)


class AppInstallation(Base, ULIDPrimaryKey, Timestamps):
    __tablename__ = "app_installations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_app_installations_workspace_id_app_id"),
        Index("ix_app_installations_workspace_id_enabled", "workspace_id", "is_enabled"),
    )

    workspace_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    app_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
    )
    installed_by: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    # Scopes actually granted at install time — may be narrower than the
    # manifest requested. This, not `App.requested_scopes`, is authoritative.
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Admin-provided configuration (API endpoints, project keys, …).
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # The synthetic bot user this installation posts messages as.
    bot_user_id: Mapped[str | None] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    # Channels the app was explicitly added to (empty = workspace-wide).
    channel_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Pinned to the left dock rail for everyone in the workspace.
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    installed_version: Mapped[str | None] = mapped_column(String(32), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    app: Mapped[App] = relationship(back_populates="installations", lazy="joined")

    def has_scope(self, scope: str) -> bool:
        return scope in self.granted_scopes


class AppToken(Base, ULIDPrimaryKey, Timestamps):
    """Long-lived bearer token an installation uses for server-to-server calls."""

    __tablename__ = "app_tokens"
    __table_args__ = (Index("ix_app_tokens_token_hash", "token_hash", unique=True),)

    installation_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("app_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Never the token itself — just enough to identify it in the UI.
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class AppStorageItem(Base, ULIDPrimaryKey, Timestamps):
    """Per-installation key/value store exposed via the `storage` scope.

    Gives an internal tool somewhere to keep state without standing up its own
    database — the single biggest friction point when a team wants to ship a
    small panel app.
    """

    __tablename__ = "app_storage_items"
    __table_args__ = (
        UniqueConstraint(
            "installation_id", "scope_key", "key", name="uq_app_storage_items_install_scope_key"
        ),
    )

    installation_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("app_installations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "workspace" for shared state, or "user:<id>" / "channel:<id>" for
    # per-user or per-channel state.
    scope_key: Mapped[str] = mapped_column(String(80), nullable=False, default="workspace")
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
