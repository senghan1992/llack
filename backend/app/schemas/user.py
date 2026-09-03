"""User-facing representations."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.core.enums import PresenceState
from app.schemas.common import Payload, Schema
from app.services.dnd import DEFAULT_DAYS, in_dnd, parse_hhmm


class UserOut(Schema):
    id: str
    email: str
    handle: str
    display_name: str
    title: str | None = None
    avatar_url: str | None = None
    timezone: str = "Asia/Seoul"
    locale: str = "ko-KR"
    status_emoji: str | None = None
    status_text: str | None = None
    status_expires_at: datetime | None = None
    presence: PresenceState = PresenceState.OFFLINE
    is_bot: bool = False
    is_active: bool = True
    # The client shows the app-review queue and server-wide settings only to
    # service admins; without this flag on /me it could never know.
    is_service_admin: bool = False

    # 방해 금지 — see services/dnd.py. `in_dnd` is derived here so every place
    # that renders a UserOut (login, /me, directory) agrees without call-site
    # changes.
    dnd_start: str | None = None
    dnd_end: str | None = None
    dnd_days: list[int] = Field(default_factory=lambda: list(DEFAULT_DAYS))
    notify_paused_until: datetime | None = None
    in_dnd: bool = False

    @model_validator(mode="after")
    def _derive_in_dnd(self) -> UserOut:
        self.in_dnd = in_dnd(
            dnd_start=self.dnd_start,
            dnd_end=self.dnd_end,
            dnd_days=self.dnd_days,
            paused_until=self.notify_paused_until,
            timezone=self.timezone,
        )
        return self


class UserBrief(Schema):
    """Trimmed user embedded in message/channel payloads."""

    id: str
    handle: str
    display_name: str
    avatar_url: str | None = None
    is_bot: bool = False


class UpdateProfileRequest(Payload):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=160)
    avatar_url: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)


class UpdateNotificationsRequest(Payload):
    """`PATCH /me/notifications`. Unset fields are left alone; explicit null
    clears. `paused_until` in the past is the same as clearing it."""

    dnd_start: str | None = Field(default=None, max_length=5)
    dnd_end: str | None = Field(default=None, max_length=5)
    dnd_days: list[int] | None = Field(default=None, max_length=7)
    paused_until: datetime | None = None

    @field_validator("dnd_start", "dnd_end")
    @classmethod
    def _hhmm(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parse_hhmm(value)  # raises ValueError → 422
        return value

    @field_validator("dnd_days")
    @classmethod
    def _weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays are 0 (Monday) to 6 (Sunday)")
        return sorted(set(value))


class UpdateStatusRequest(Payload):
    status_emoji: str | None = Field(default=None, max_length=64)
    status_text: str | None = Field(default=None, max_length=200)
    status_expires_at: datetime | None = None
    presence: PresenceState | None = None
