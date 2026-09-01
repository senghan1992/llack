"""The realtime (WebSocket) protocol.

One envelope in both directions. `seq` is a monotonic per-connection counter
the client uses to detect gaps and trigger a catch-up fetch after a reconnect.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.schemas.common import Payload, Schema


class ServerEvent(StrEnum):
    HELLO = "hello"
    PONG = "pong"
    ERROR = "error"

    MESSAGE_CREATED = "message.created"
    MESSAGE_UPDATED = "message.updated"
    MESSAGE_DELETED = "message.deleted"
    REACTION_ADDED = "reaction.added"
    REACTION_REMOVED = "reaction.removed"

    CHANNEL_CREATED = "channel.created"
    CHANNEL_UPDATED = "channel.updated"
    CHANNEL_ARCHIVED = "channel.archived"
    CHANNEL_MEMBER_JOINED = "channel.member_joined"
    CHANNEL_MEMBER_LEFT = "channel.member_left"
    CHANNEL_READ = "channel.read"

    TYPING = "typing"
    PRESENCE_UPDATED = "presence.updated"
    USER_UPDATED = "user.updated"

    APP_INSTALLED = "app.installed"
    APP_UNINSTALLED = "app.uninstalled"
    APP_EVENT = "app.event"          # a mini-app pushing to its own panel


class ClientCommand(StrEnum):
    PING = "ping"
    SUBSCRIBE = "subscribe"          # follow extra channels (e.g. on navigate)
    UNSUBSCRIBE = "unsubscribe"
    TYPING = "typing"
    PRESENCE = "presence"
    MARK_READ = "mark_read"


class Envelope(Schema):
    type: str
    seq: int | None = None
    ts: datetime | None = None
    workspace_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ClientFrame(Payload):
    type: ClientCommand
    # Echoed back on the response so the client can match request/reply.
    id: str | None = Field(default=None, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


class HelloData(Schema):
    session_id: str
    user_id: str
    workspace_ids: list[str] = Field(default_factory=list)
    heartbeat_seconds: int = 25
    server_time: datetime
    protocol_version: int = 1


class TypingData(Schema):
    channel_id: str
    user_id: str
    parent_id: str | None = None
