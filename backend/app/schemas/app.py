"""Mini-app platform payloads, including the install manifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator

from app.core.enums import AppKind, AppScope, AppStatus
from app.schemas.common import Payload, Schema, Slug


class SlashCommandSpec(Payload):
    command: str = Field(min_length=2, max_length=40, pattern=r"^/[a-z0-9][a-z0-9_-]*$")
    description: str = Field(max_length=200)
    usage_hint: str | None = Field(default=None, max_length=120)


class AppManifest(Payload):
    """What an app author submits to register an app.

    Deliberately close to the shape the desktop host needs, so registering an
    app is a single POST with no follow-up configuration round-trips.
    """

    slug: Slug
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(default="0.1.0", max_length=32)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    icon_url: str | None = None
    accent_color: str | None = Field(default=None, pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")

    kind: AppKind = AppKind.PANEL
    panel_url: AnyHttpUrl | None = None
    sidebar_url: AnyHttpUrl | None = None
    event_webhook_url: AnyHttpUrl | None = None
    default_width: int = Field(default=420, ge=280, le=1200)

    scopes: list[AppScope] = Field(default_factory=list, max_length=32)
    slash_commands: list[SlashCommandSpec] = Field(default_factory=list, max_length=20)
    events: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("scopes")
    @classmethod
    def _dedupe_scopes(cls, v: list[AppScope]) -> list[AppScope]:
        return list(dict.fromkeys(v))


class AppOut(Schema):
    id: str
    slug: str
    name: str
    version: str
    tagline: str | None = None
    description: str | None = None
    icon_url: str | None = None
    accent_color: str | None = None
    kind: AppKind
    status: AppStatus
    panel_url: str | None = None
    sidebar_url: str | None = None
    default_width: int = 420
    requested_scopes: list[str] = Field(default_factory=list)
    slash_commands: list[dict[str, Any]] = Field(default_factory=list)
    is_first_party: bool = False
    owner_workspace_id: str | None = None
    created_at: datetime


class InstallAppRequest(Payload):
    # Omit to grant exactly what the manifest requested.
    granted_scopes: list[AppScope] | None = Field(default=None, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    pin_to_dock: bool = True


class AppInstallationOut(Schema):
    id: str
    workspace_id: str
    app: AppOut
    granted_scopes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    bot_user_id: str | None = None
    is_enabled: bool = True
    is_pinned: bool = False
    sort_order: int = 0
    installed_version: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class UpdateInstallationRequest(Payload):
    config: dict[str, Any] | None = None
    granted_scopes: list[AppScope] | None = Field(default=None, max_length=32)
    is_enabled: bool | None = None
    is_pinned: bool | None = None
    sort_order: int | None = None


class AppTokenOut(Schema):
    id: str
    name: str
    token_prefix: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    # Returned exactly once, at creation.
    token: str | None = None


class CreateAppTokenRequest(Payload):
    name: str = Field(default="default", max_length=120)
    ttl_days: int | None = Field(default=None, ge=1, le=3650)


class PanelSessionOut(Schema):
    """Everything the desktop host needs to boot a mini-app webview.

    The host injects this into the sandboxed frame; the frame never sees the
    user's own access token.
    """

    installation_id: str
    app_id: str
    panel_url: str
    # Short-lived token scoped to this installation, for the SDK's calls.
    bridge_token: str
    expires_at: datetime
    granted_scopes: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class AppStorageSetRequest(Payload):
    value: Any
    scope_key: str = Field(default="workspace", max_length=80)


class AppStorageItemOut(Schema):
    key: str
    scope_key: str
    value: Any
    updated_at: datetime
