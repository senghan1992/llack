"""Workspace payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.core.enums import WorkspaceRole
from app.schemas.common import Payload, Schema, Slug
from app.schemas.user import UserBrief


class WorkspaceOut(Schema):
    id: str
    slug: str
    name: str
    description: str | None = None
    icon_url: str | None = None
    created_at: datetime
    # Filled in for the requesting user.
    my_role: WorkspaceRole | None = None
    member_count: int = 0
    # Retention policy (days); None keeps forever.
    retention_days_messages: int | None = None
    retention_days_files: int | None = None


class CreateWorkspaceRequest(Payload):
    name: str = Field(min_length=1, max_length=160)
    slug: Slug
    description: str | None = Field(default=None, max_length=2000)
    allowed_email_domains: list[str] = Field(default_factory=list, max_length=20)


class UpdateWorkspaceRequest(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    icon_url: str | None = None
    allowed_email_domains: list[str] | None = Field(default=None, max_length=20)


class WorkspaceMemberOut(Schema):
    id: str
    user: UserBrief
    role: WorkspaceRole
    joined_at: datetime = Field(validation_alias="created_at")
    is_active: bool = True


class InviteRequest(Payload):
    emails: list[EmailStr] = Field(min_length=1, max_length=100)
    role: WorkspaceRole = WorkspaceRole.MEMBER


class InviteOut(Schema):
    id: str
    email: str
    role: WorkspaceRole
    expires_at: datetime
    accepted_at: datetime | None = None
    # Only returned to the inviter, once, at creation time.
    invite_url: str | None = None
    # True when the server mailed the link itself (relay configured, no error).
    emailed: bool = False


class UpdateMemberRoleRequest(Payload):
    role: WorkspaceRole


class RetentionOut(Schema):
    retention_days_messages: int | None = None
    retention_days_files: int | None = None


class RetentionRequest(Payload):
    """Both fields optional; an explicit null clears the policy (keep forever)."""

    retention_days_messages: int | None = Field(default=None, ge=1, le=3650)
    retention_days_files: int | None = Field(default=None, ge=1, le=3650)
