"""User-facing representations."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import PresenceState
from app.schemas.common import Payload, Schema


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


class UpdateStatusRequest(Payload):
    status_emoji: str | None = Field(default=None, max_length=64)
    status_text: str | None = Field(default=None, max_length=200)
    status_expires_at: datetime | None = None
    presence: PresenceState | None = None
