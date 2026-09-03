"""나중에 볼 항목 — saved messages and reminders."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.activity import ChannelRef
from app.schemas.common import Payload, Schema
from app.schemas.message import MessageOut


class SaveMessageRequest(Payload):
    note: str | None = Field(default=None, max_length=500)
    remind_at: datetime | None = None


class SavedItemOut(Schema):
    id: str
    note: str | None = None
    remind_at: datetime | None = None
    reminded_at: datetime | None = None
    done_at: datetime | None = None
    created_at: datetime
    message: MessageOut
    channel: ChannelRef


class SavedItemPage(Schema):
    items: list[SavedItemOut]
    has_more: bool = False
    # Pass back as `before` (saved item id of the last row).
    next_before: str | None = None
