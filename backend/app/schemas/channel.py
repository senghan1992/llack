"""Channel schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserOut

KIND_CHANNEL = "channel"
KIND_DM = "dm"


class ChannelOut(ORMModel):
    id: str
    workspace_id: str
    name: str
    topic: str = ""
    purpose: str = ""
    kind: str = KIND_CHANNEL
    is_private: bool = False
    created_by: str
    created_at: datetime
    member_count: int = 0
    unread_count: int = 0
    last_message_at: datetime | None = None
    dm_user: UserOut | None = None
    members: list[UserOut] | None = None
    is_member: bool = False


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    topic: str | None = Field(default=None, max_length=300)
    is_private: bool = False
    # The people who are in the room from the start.
    member_ids: list[str] = Field(default_factory=list, max_length=100)


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    topic: str | None = Field(default=None, max_length=300)
    purpose: str | None = Field(default=None, max_length=300)


class ChannelMemberAdd(BaseModel):
    user_id: str = Field(min_length=1)


class DmCreate(BaseModel):
    user_id: str = Field(min_length=1)


class ReadUpdate(BaseModel):
    message_id: str | None = None
