"""Activity payloads: the threads I am in, and the messages that call me.

A question asked in a channel gets its answer in a thread, and until now the
only trace of that answer was a "답글 1개" under the original and a badge on
the channel. This is the view that lists them.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.message import MessageOut
from app.schemas.user import UserBrief


class ChannelRef(Schema):
    """Enough of a channel to label a row and jump to it."""

    id: str
    name: str | None = None
    kind: str
    # The other people in a DM / group DM, so the row can say who instead of "#".
    peers: list[UserBrief] = Field(default_factory=list)


class ThreadActivityOut(Schema):
    root: MessageOut
    channel: ChannelRef
    last_reply: MessageOut | None = None
    participants: list[UserBrief] = Field(default_factory=list)
    # Replies by others since the viewer last spoke in the thread (or since the
    # root, if they only started it).
    unread_replies: int = 0


class ThreadActivityPage(Schema):
    items: list[ThreadActivityOut]
    has_more: bool = False
    # Pass back as `before` to get the next page (root message id of the last row).
    next_before: str | None = None


class MentionActivityOut(Schema):
    message: MessageOut
    channel: ChannelRef


class MentionActivityPage(Schema):
    items: list[MentionActivityOut]
    has_more: bool = False
    # Pass back as `before` (message id of the last item).
    next_before: str | None = None
