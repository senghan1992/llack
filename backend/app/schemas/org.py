"""Organization schemas: the units a workspace is arranged in."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import MemberOut, UserOut

OrgRole = Literal["owner", "admin", "member"]


class OrgUnit(ORMModel):
    """One unit of the organization's tree, as the API shows it."""

    id: str
    workspace_id: str
    parent_id: str | None = None
    name: str
    kind: str = "team"
    description: str = ""
    position: int = 0
    created_at: datetime
    updated_at: datetime
    # How many people are in the unit, and how many units hang below it.
    member_count: int = 0
    child_count: int = 0
    # How deep the unit sits: a unit at the top has depth 0.
    depth: int = 0
    members: list[UserOut] = []
    managers: list[UserOut] = []
    # Whether the caller is appointed to look after this very unit. The
    # reach that is inherited from a parent is ``can_manage``.
    is_manager: bool = False
    # Whether the caller may rename, move, delete it and change its roster.
    can_manage: bool = False
    # Whether the caller may appoint or dismiss its managers.
    can_appoint_managers: bool = False


class OrgOverview(BaseModel):
    """The whole organization of a workspace, as the screen draws it."""

    # A flat list: the tree is drawn from parent_id.
    units: list[OrgUnit] = []
    # The workspace owners and admins.
    admins: list[MemberOut] = []
    my_role: OrgRole = "member"
    # Whether the caller may change the roles of the workspace members.
    can_manage_admins: bool = False
    # The units the caller looks after.
    managed_unit_ids: list[str] = []


class OrgSummary(BaseModel):
    """The little of the organization that comes with the bootstrap."""

    unit_count: int = 0
    managed_unit_ids: list[str] = []


class OrgUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None
    kind: str = Field(default="team", max_length=24)
    description: str = Field(default="", max_length=4000)


class OrgUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = Field(default=None, max_length=24)
    description: str | None = Field(default=None, max_length=4000)
    # A null parent_id moves the unit to the top of the tree.
    parent_id: str | None = None


class OrgMemberAdd(BaseModel):
    user_id: str = Field(min_length=1)


class OrgManagerAdd(BaseModel):
    user_id: str = Field(min_length=1)
