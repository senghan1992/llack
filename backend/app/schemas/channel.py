"""Channel payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.core.enums import ChannelKind, ChannelRole, NotificationLevel
from app.schemas.common import Payload, Schema, Slug
from app.schemas.user import UserBrief


class ChannelMembershipOut(Schema):
    """The requesting user's own state in a channel."""

    role: ChannelRole = ChannelRole.MEMBER
    last_read_message_id: str | None = None
    unread_count: int = 0
    mention_count: int = 0
    notification_level: NotificationLevel = NotificationLevel.ALL
    is_muted: bool = False
    is_starred: bool = False
    section: str | None = None
    sort_order: int = 0


class ChannelOut(Schema):
    id: str
    workspace_id: str
    kind: ChannelKind
    slug: str | None = None
    name: str | None = None
    topic: str | None = None
    purpose: str | None = None
    is_archived: bool = False
    is_default: bool = False
    # Message retention override in days; None defers to the workspace.
    retention_days: int | None = None
    created_at: datetime
    last_message_at: datetime | None = None
    message_count: int = 0
    member_count: int = 0

    # Populated for DMs so the client can render the other person.
    peers: list[UserBrief] = Field(default_factory=list)
    membership: ChannelMembershipOut | None = None


class CreateChannelRequest(Payload):
    name: str = Field(min_length=1, max_length=120)
    slug: Slug | None = None
    kind: ChannelKind = ChannelKind.PUBLIC
    topic: str | None = Field(default=None, max_length=400)
    purpose: str | None = Field(default=None, max_length=4000)
    member_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _reject_dm_kinds(self) -> CreateChannelRequest:
        if ChannelKind(self.kind).is_conversation:
            raise ValueError("use POST /channels/dm to open a direct message")
        return self


class UpdateChannelRequest(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    topic: str | None = Field(default=None, max_length=400)
    purpose: str | None = Field(default=None, max_length=4000)
    is_archived: bool | None = None
    # Channel-admin only. Explicit null = follow the workspace policy.
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class OpenDmRequest(Payload):
    """Idempotent: opening a DM with the same people returns the same channel."""

    user_ids: list[str] = Field(min_length=1, max_length=8)


class AddMembersRequest(Payload):
    user_ids: list[str] = Field(min_length=1, max_length=500)


class ChannelMemberOut(Schema):
    id: str
    user: UserBrief
    role: ChannelRole
    joined_at: datetime = Field(validation_alias="created_at")


class UpdateMemberRoleRequest(Payload):
    role: ChannelRole


class UpdateMembershipRequest(Payload):
    notification_level: NotificationLevel | None = None
    is_muted: bool | None = None
    is_starred: bool | None = None
    section: str | None = Field(default=None, max_length=80)
    sort_order: int | None = None


class MarkReadRequest(Payload):
    message_id: str | None = None  # None = mark everything read
