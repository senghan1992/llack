"""User and workspace-member schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

PRESENCE_VALUES = ("online", "busy", "dnd", "away", "brb", "offline")
# The states a person may claim for themselves. "offline" is the server's own
# word — the app decides it, not the person.
PRESENCE_SELECTABLE = ("online", "busy", "dnd", "away", "brb")
ROLE_VALUES = ("owner", "admin", "member")


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    title: str | None = None
    avatar_color: str = "#3f6f52"
    avatar_url: str | None = None
    presence: str = "offline"
    last_seen_at: datetime
    created_at: datetime


class MemberOut(BaseModel):
    user: UserOut
    role: str
    joined_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=120)
    avatar_color: str | None = Field(default=None, max_length=16)
    status_text: str | None = Field(default=None, max_length=120)
    # "offline" is the server's own word — a person cannot claim it.
    presence: Literal["online", "busy", "dnd", "away", "brb"] | None = None
