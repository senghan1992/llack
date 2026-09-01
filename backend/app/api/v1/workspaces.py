"""Workspace endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import AdminWorkspaceCtx, CurrentUser, DbSession, WorkspaceCtx
from app.core.enums import WorkspaceRole
from app.core.errors import Conflict, Forbidden, NotFound
from app.models.workspace import WorkspaceInvite, WorkspaceMember
from app.schemas.common import OkResponse
from app.schemas.workspace import (
    CreateWorkspaceRequest,
    InviteOut,
    InviteRequest,
    UpdateMemberRoleRequest,
    UpdateWorkspaceRequest,
    WorkspaceMemberOut,
    WorkspaceOut,
)
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
async def list_my_workspaces(db: DbSession, user: CurrentUser) -> list[WorkspaceOut]:
    rows = await workspace_service.list_user_workspaces(db, user_id=user.id)
    out: list[WorkspaceOut] = []
    for workspace, role in rows:
        item = WorkspaceOut.model_validate(workspace)
        item.my_role = WorkspaceRole(role)
        item.member_count = await workspace_service.count_members(db, workspace.id)
        out.append(item)
    return out


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: CreateWorkspaceRequest, db: DbSession, user: CurrentUser
) -> WorkspaceOut:
    """Create a workspace, seeding #general and #random with the caller as owner."""
    workspace = await workspace_service.create_workspace(
        db,
        owner=user,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        allowed_email_domains=payload.allowed_email_domains,
    )
    await db.commit()
    out = WorkspaceOut.model_validate(workspace)
    out.my_role = WorkspaceRole.OWNER
    out.member_count = 1
    return out


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(ctx: WorkspaceCtx, db: DbSession) -> WorkspaceOut:
    out = WorkspaceOut.model_validate(ctx.workspace)
    out.my_role = ctx.role
    out.member_count = await workspace_service.count_members(db, ctx.workspace.id)
    return out


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    payload: UpdateWorkspaceRequest, ctx: AdminWorkspaceCtx, db: DbSession
) -> WorkspaceOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ctx.workspace, field, value)
    await db.commit()
    out = WorkspaceOut.model_validate(ctx.workspace)
    out.my_role = ctx.role
    return out


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
async def list_members(ctx: WorkspaceCtx, db: DbSession) -> list[WorkspaceMemberOut]:
    from sqlalchemy.orm import selectinload

    rows = await db.scalars(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == ctx.workspace.id,
            WorkspaceMember.is_active.is_(True),
        )
        .options(selectinload(WorkspaceMember.user))
        .order_by(WorkspaceMember.role, WorkspaceMember.created_at)
    )
    return [WorkspaceMemberOut.model_validate(row) for row in rows.all()]


@router.patch("/{workspace_id}/members/{member_id}", response_model=WorkspaceMemberOut)
async def update_member_role(
    member_id: str,
    payload: UpdateMemberRoleRequest,
    ctx: AdminWorkspaceCtx,
    db: DbSession,
) -> WorkspaceMemberOut:
    from sqlalchemy.orm import selectinload

    member = await db.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == ctx.workspace.id,
        )
        .options(selectinload(WorkspaceMember.user))
        .limit(1)
    )
    if member is None:
        raise NotFound("This person is not in this workspace.", code="member_not_found")

    # Only an owner may create or demote another owner.
    touches_owner = WorkspaceRole.OWNER in (payload.role, member.role_enum)
    if touches_owner and ctx.role is not WorkspaceRole.OWNER:
        raise Forbidden("Only an owner can change owner roles.", code="owner_role_required")

    if member.role_enum is WorkspaceRole.OWNER and payload.role is not WorkspaceRole.OWNER:
        remaining = await db.scalar(
            select(WorkspaceMember.id)
            .where(
                WorkspaceMember.workspace_id == ctx.workspace.id,
                WorkspaceMember.role == WorkspaceRole.OWNER.value,
                WorkspaceMember.id != member.id,
                WorkspaceMember.is_active.is_(True),
            )
            .limit(1)
        )
        if remaining is None:
            raise Conflict(
                "A workspace must keep at least one owner.", code="last_owner"
            )

    member.role = payload.role.value
    await db.commit()
    return WorkspaceMemberOut.model_validate(member)


@router.delete("/{workspace_id}/members/{member_id}", response_model=OkResponse)
async def remove_member(member_id: str, ctx: AdminWorkspaceCtx, db: DbSession) -> OkResponse:
    member = await db.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == ctx.workspace.id,
        )
        .limit(1)
    )
    if member is None:
        raise NotFound("This person is not in this workspace.", code="member_not_found")
    if member.role_enum is WorkspaceRole.OWNER and ctx.role is not WorkspaceRole.OWNER:
        raise Forbidden("Only an owner can remove an owner.", code="owner_role_required")

    # Deactivate rather than delete, so their messages keep their author.
    member.is_active = False
    await db.commit()
    return OkResponse()


@router.post("/{workspace_id}/invites", response_model=list[InviteOut],
             status_code=status.HTTP_201_CREATED)
async def create_invites(
    payload: InviteRequest, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> list[InviteOut]:
    """Issue invitations. The returned URLs are shown once and never stored."""
    created = await workspace_service.create_invites(
        db,
        workspace_id=ctx.workspace.id,
        emails=[str(e) for e in payload.emails],
        role=payload.role,
        invited_by=ctx.user.id,
    )
    await db.commit()

    base = str(request.base_url).rstrip("/")
    return [
        InviteOut(
            **InviteOut.model_validate(invite).model_dump(exclude={"invite_url"}),
            invite_url=f"llack://invite?token={raw}&workspace={ctx.workspace.slug}"
            f"&api={base}",
        )
        for invite, raw in created
    ]


@router.get("/{workspace_id}/invites", response_model=list[InviteOut])
async def list_invites(ctx: AdminWorkspaceCtx, db: DbSession) -> list[InviteOut]:
    rows = await db.scalars(
        select(WorkspaceInvite)
        .where(
            WorkspaceInvite.workspace_id == ctx.workspace.id,
            WorkspaceInvite.revoked_at.is_(None),
        )
        .order_by(WorkspaceInvite.created_at.desc())
    )
    return [InviteOut.model_validate(row) for row in rows.all()]
