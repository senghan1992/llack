"""Schedule schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserOut

RsvpResponse = Literal["accepted", "declined", "tentative"]


class AttendeeOut(BaseModel):
    user: UserOut
    response: str = "pending"


class EventOut(ORMModel):
    id: str
    workspace_id: str
    title: str
    description: str = ""
    location: str = ""
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    is_private: bool = False
    created_by: str
    channel_id: str | None = None
    created_at: datetime
    updated_at: datetime
    attendees: list[AttendeeOut] = []
    my_response: str | None = None


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=200)
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    is_private: bool = False
    channel_id: str | None = None
    attendee_ids: list[str] = Field(default_factory=list)


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    is_private: bool | None = None
    channel_id: str | None = None
    attendee_ids: list[str] | None = None


class AttendeeAdd(BaseModel):
    user_id: str = Field(min_length=1)


class RsvpUpdate(BaseModel):
    response: RsvpResponse
