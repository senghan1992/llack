"""Workspace schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.channel import ChannelOut
from app.schemas.common import ORMModel
from app.schemas.org import OrgSummary
from app.schemas.user import MemberOut, UserOut


class WorkspaceOut(ORMModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BootstrapOut(BaseModel):
    workspace: WorkspaceOut
    channels: list[ChannelOut]
    dms: list[ChannelOut]
    members: list[MemberOut]
    me: UserOut
    org: OrgSummary
