"""Mini-app platform payloads, including the install manifest."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from app.core.enums import AppKind, AppScope, AppStatus
from app.schemas.common import Payload, Schema, Slug


class SlashCommandSpec(Payload):
    command: str = Field(min_length=2, max_length=40, pattern=r"^/[a-z0-9][a-z0-9_-]*$")
    description: str = Field(default="", max_length=200)
    # `usage` is the documented name; `usage_hint` is accepted for manifests
    # written before the platform batch and normalised to `usage`.
    usage: str | None = Field(default=None, max_length=120)
    usage_hint: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _normalise_usage(self) -> SlashCommandSpec:
        if self.usage is None and self.usage_hint is not None:
            self.usage = self.usage_hint
        self.usage_hint = self.usage
        return self


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
    # Where slash commands, block clicks and the 앱 홈 screen go. All optional;
    # an app that declares none of them is a pure panel/bot as before.
    command_url: AnyHttpUrl | None = None
    interaction_url: AnyHttpUrl | None = None
    home_url: AnyHttpUrl | None = None
    default_width: int = Field(default=420, ge=280, le=1200)

    scopes: list[AppScope] = Field(default_factory=list, max_length=32)
    slash_commands: list[SlashCommandSpec] = Field(default_factory=list, max_length=20)
    events: list[str] = Field(default_factory=list, max_length=40)
    # The console speaks `event_subscriptions` (the column name); `events` is
    # the original manifest key. Either is accepted; both are honoured.
    event_subscriptions: list[str] | None = Field(default=None, max_length=40)

    @field_validator("scopes")
    @classmethod
    def _dedupe_scopes(cls, v: list[AppScope]) -> list[AppScope]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _merge_events(self) -> AppManifest:
        if self.event_subscriptions:
            self.events = list(dict.fromkeys([*self.events, *self.event_subscriptions]))
        self.event_subscriptions = None
        return self


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
    home_url: str | None = None
    default_width: int = 420
    requested_scopes: list[str] = Field(default_factory=list)
    slash_commands: list[dict[str, Any]] = Field(default_factory=list)
    is_first_party: bool = False
    owner_workspace_id: str | None = None
    review_note: str | None = None
    created_at: datetime


class DeveloperAppOut(AppOut):
    """The author's view: every URL the platform will call, and the review state."""

    command_url: str | None = None
    interaction_url: str | None = None
    event_webhook_url: str | None = None
    event_subscriptions: list[str] = Field(default_factory=list)
    author_id: str | None = None
    # Present only on the register / rotate-secret responses.
    secret: str | None = None


class ReviewRequest(Payload):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class SecretOut(Schema):
    secret: str


class WebhookDeliveryOut(Schema):
    id: str
    app_id: str
    installation_id: str | None = None
    kind: str = "event"
    event: str
    status: str
    attempts: int = 0
    last_status_code: int | None = None
    last_error: str | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime


# ── Slash commands & interactions ───────────────────────────────────────────


class CommandAppRef(Schema):
    id: str
    name: str
    icon_url: str | None = None


class CommandOut(Schema):
    command: str
    description: str | None = None
    usage: str | None = None
    app: CommandAppRef | None = None
    builtin: bool = False


class RunCommandRequest(Payload):
    text: str = Field(min_length=1, max_length=4000)


class CommandResponseOut(Schema):
    text: str
    ephemeral: bool = True
    blocks: list[dict[str, Any]] | None = None


class CommandResultOut(Schema):
    handled: bool
    response: CommandResponseOut | None = None


class BlockActionRequest(Payload):
    action_id: str = Field(min_length=1, max_length=120)
    value: str | None = Field(default=None, max_length=2000)


class EphemeralOut(Schema):
    text: str


class ActionResultOut(Schema):
    handled: bool
    ephemeral: EphemeralOut | None = None


class RespondRequest(Payload):
    """What an app posts to a command's `response_url` after the fact."""

    text: str = Field(default="", max_length=40_000)
    blocks: list[dict[str, Any]] | None = None


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
    # Who added it — the client shows rename/remove only to them and admins.
    installed_by: str | None = None
    installed_version: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class UpdateInstallationRequest(Payload):
    # Link apps only: the tile's label and icon. The App row behind a link app
    # is private to the workspace, so renaming it renames nothing else.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon_url: str | None = Field(default=None, max_length=2000)
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
    # The console's name for the same knob.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def _merge_ttl(self) -> CreateAppTokenRequest:
        if self.ttl_days is None and self.expires_in_days is not None:
            self.ttl_days = self.expires_in_days
        return self


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
