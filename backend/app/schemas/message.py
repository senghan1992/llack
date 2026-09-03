"""Message payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.core.enums import MessageKind
from app.schemas.common import Emoji, Payload, Schema
from app.schemas.file import FileOut
from app.schemas.user import UserBrief


class ReactionOut(Schema):
    emoji: str
    count: int
    user_ids: list[str] = Field(default_factory=list)
    me: bool = False


class MessageCore(Schema):
    """The fields that map straight off the ORM row.

    Kept separate from `MessageOut` because the remaining fields are *derived*
    and viewer-dependent — reactions are grouped per emoji with a `me` flag,
    attachments carry signed URLs. Validating those directly from the ORM
    would try to coerce raw `Reaction` rows into `ReactionOut`, which is not
    the same shape.
    """

    id: str
    channel_id: str
    kind: MessageKind = MessageKind.USER
    body: str = ""
    blocks: list[dict[str, Any]] | None = None
    client_msg_id: str | None = None
    app_id: str | None = None

    parent_id: str | None = None
    reply_count: int = 0
    last_reply_at: datetime | None = None
    also_sent_to_channel: bool = False

    mentioned_user_ids: list[str] = Field(default_factory=list)
    mentions_everyone: bool = False
    # "channel" reached everyone, "here" only those present. Null otherwise.
    broadcast: str | None = None

    is_pinned: bool = False
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime


class MessageOut(MessageCore):
    author: UserBrief | None = None
    reply_users: list[UserBrief] = Field(default_factory=list)
    attachments: list[FileOut] = Field(default_factory=list)
    reactions: list[ReactionOut] = Field(default_factory=list)
    # Kept for later by the viewer (saved_items). Viewer-dependent like `me`.
    is_saved: bool = False


class CreateMessageRequest(Payload):
    body: str = Field(default="", max_length=40_000)
    blocks: list[dict[str, Any]] | None = None
    # Client-generated ULID; makes retries idempotent and lets the optimistic
    # message in the UI be reconciled with the server's copy.
    client_msg_id: str | None = Field(default=None, max_length=64)
    parent_id: str | None = None
    also_send_to_channel: bool = False
    file_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _require_content(self) -> CreateMessageRequest:
        if not self.body.strip() and not self.blocks and not self.file_ids:
            raise ValueError("a message needs a body, blocks or at least one file")
        return self


class UpdateMessageRequest(Payload):
    body: str = Field(min_length=1, max_length=40_000)
    blocks: list[dict[str, Any]] | None = None


class ReactionRequest(Payload):
    emoji: Emoji


class SearchHit(Schema):
    message: MessageOut
    channel_id: str
    channel_name: str | None = None
    # Body with the matched terms wrapped in <mark>…</mark>.
    highlight: str | None = None
    score: float = 0.0


class SearchResponse(Schema):
    query: str
    hits: list[SearchHit] = Field(default_factory=list)
    total: int = 0
    took_ms: int = 0
