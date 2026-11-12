"""Message schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.file import FileOut
from app.schemas.user import UserOut

KIND_TEXT = "text"
KIND_SYSTEM = "system"


class ReactionOut(BaseModel):
    emoji: str
    count: int
    user_ids: list[str]
    me: bool


class ReplyToOut(BaseModel):
    """The message a reply answers, in the small form a quote needs."""

    id: str
    author_name: str
    body: str = ""
    deleted: bool = False


class MessageOut(ORMModel):
    id: str
    channel_id: str
    user_id: str
    author: UserOut
    body: str = ""
    kind: str = KIND_TEXT
    parent_id: str | None = None
    reply_to_id: str | None = None
    reply_to: ReplyToOut | None = None
    inline: bool = False
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    reply_count: int = 0
    last_reply_at: datetime | None = None
    pinned: bool = False
    reactions: list[ReactionOut] = []
    attachments: list[FileOut] = []


class MessagePage(BaseModel):
    messages: list[MessageOut]
    has_more: bool
    has_more_after: bool = False


class MessageCreate(BaseModel):
    body: str = Field(default="", max_length=4000)
    parent_id: str | None = None
    reply_to_id: str | None = None
    inline: bool = False
    attachment_ids: list[str] = Field(default_factory=list)


class MessageUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReactionCreate(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)
