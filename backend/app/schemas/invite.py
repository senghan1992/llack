"""Invite schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class InviteOut(ORMModel):
    id: str
    workspace_id: str
    email: str
    role: str
    token: str
    created_by: str
    created_at: datetime
    expires_at: datetime


class InviteCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


class InviteAccept(BaseModel):
    token: str = Field(min_length=1, max_length=128)
