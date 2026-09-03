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
    RetentionOut,
    RetentionRequest,
    UpdateMemberRoleRequest,
    UpdateWorkspaceRequest,
    WorkspaceMemberOut,
    WorkspaceOut,
)
from app.services import audit, invite_mail
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
    request: Request,
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

    previous = member.role
    member.role = payload.role.value
    await audit.record(
        db,
        workspace_id=ctx.workspace.id,
        actor=ctx.user,
        action="member.role_changed",
        target_type="user",
        target_id=member.user_id,
        target_label=member.user.display_name,
        details={"from": previous, "to": member.role},
        request=request,
    )
    await db.commit()
    return WorkspaceMemberOut.model_validate(member)


@router.delete("/{workspace_id}/members/{member_id}", response_model=OkResponse)
async def remove_member(
    member_id: str, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> OkResponse:
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
    if member.role_enum is WorkspaceRole.OWNER and ctx.role is not WorkspaceRole.OWNER:
        raise Forbidden("Only an owner can remove an owner.", code="owner_role_required")

    # Deactivate rather than delete, so their messages keep their author.
    member.is_active = False
    await audit.record(
        db,
        workspace_id=ctx.workspace.id,
        actor=ctx.user,
        action="member.removed",
        target_type="user",
        target_id=member.user_id,
        target_label=member.user.display_name,
        details={"role": member.role},
        request=request,
    )
    await db.commit()
    return OkResponse()


@router.post("/{workspace_id}/members/{user_id}/reset-password", response_model=dict)
async def reset_member_password(
    user_id: str, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> dict[str, str]:
    """Issue a one-time temporary password for a locked-out member.

    No outbound email exists on this server, so recovery is a human handing a
    human a temporary password. Guard rails: only for a member of *this*
    workspace, only downward in role (an admin cannot reset another admin, an
    owner can), never yourself (that is the ordinary change-password flow),
    and every session of the target dies with the old password.
    """
    if user_id == ctx.user.id:
        raise Forbidden(
            "Use the change-password flow for your own account.",
            code="cannot_reset_self",
        )
    target = await workspace_service.get_membership(
        db, workspace_id=ctx.workspace.id, user_id=user_id
    )
    if target is None:
        raise NotFound("This person is not a member of the workspace.",
                       code="member_not_found")
    if target.role_enum.rank >= ctx.role.rank:
        raise Forbidden(
            "You can only reset the password of a lower role.",
            code="insufficient_role",
        )

    import secrets as _secrets

    from app.models.user import User as UserModel
    from app.services import auth as auth_service

    user = await db.get(UserModel, user_id)
    if user is None:
        raise NotFound("User not found.", code="user_not_found")

    temp_password = _secrets.token_urlsafe(9)
    await auth_service.admin_set_password(db, user, temp_password)
    await auth_service.revoke_all_sessions(db, user_id=user_id)
    await audit.record(
        db,
        workspace_id=ctx.workspace.id,
        actor=ctx.user,
        action="member.password_reset",
        target_type="user",
        target_id=user.id,
        target_label=user.display_name,
        request=request,
    )
    await db.commit()

    # Shown once and never stored in this form; the recipient should change
    # it immediately (환경설정 → 계정).
    return {"temp_password": temp_password}


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
    # Mail after commit: it is best-effort and must not hold the transaction
    # open on a slow relay; the rows exist either way.
    emailed: dict[str, bool] = {invite.id: False for invite, _raw in created}
    await db.commit()
    for invite, raw in created:
        emailed[invite.id] = await invite_mail.send_invite(
            db,
            request=request,
            to=invite.email,
            token=raw,
            workspace_name=ctx.workspace.name,
            inviter_name=ctx.user.display_name,
            expires_days=14,
        )
        await audit.record(
            db,
            workspace_id=ctx.workspace.id,
            actor=ctx.user,
            action="invite.created",
            target_type="invite",
            target_id=invite.id,
            target_label=invite.email,
            details={"role": invite.role, "emailed": emailed[invite.id]},
            request=request,
        )
    await db.commit()

    base = str(request.base_url).rstrip("/")
    return [
        InviteOut(
            **InviteOut.model_validate(invite).model_dump(exclude={"invite_url", "emailed"}),
            invite_url=f"llack://invite?token={raw}&workspace={ctx.workspace.slug}"
            f"&api={base}",
            emailed=emailed[invite.id],
        )
        for invite, raw in created
    ]


@router.post("/{workspace_id}/invites/{invite_id}/resend", response_model=InviteOut)
async def resend_invite(
    invite_id: str, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> InviteOut:
    """A fresh link (and mail) for an invitation whose first link went astray.

    The old token stops working the moment the new one exists — a resend is
    also the polite way to kill a link that was forwarded to the wrong inbox.
    """
    invite = await db.get(WorkspaceInvite, invite_id)
    if invite is None or invite.workspace_id != ctx.workspace.id or invite.revoked_at:
        raise NotFound("This invitation does not exist.", code="invite_invalid")
    if invite.accepted_at is not None:
        raise Conflict("This invitation has already been used.", code="invite_used")
    raw = await workspace_service.rotate_invite(db, invite=invite)
    await db.commit()
    emailed = await invite_mail.send_invite(
        db,
        request=request,
        to=invite.email,
        token=raw,
        workspace_name=ctx.workspace.name,
        inviter_name=ctx.user.display_name,
        expires_days=14,
    )
    await audit.record(
        db,
        workspace_id=ctx.workspace.id,
        actor=ctx.user,
        action="invite.resent",
        target_type="invite",
        target_id=invite.id,
        target_label=invite.email,
        details={"emailed": emailed},
        request=request,
    )
    await db.commit()
    base = str(request.base_url).rstrip("/")
    return InviteOut(
        **InviteOut.model_validate(invite).model_dump(exclude={"invite_url", "emailed"}),
        invite_url=f"llack://invite?token={raw}&workspace={ctx.workspace.slug}&api={base}",
        emailed=emailed,
    )


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


@router.delete("/{workspace_id}/invites/{invite_id}", response_model=OkResponse)
async def revoke_invite(
    invite_id: str, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> OkResponse:
    """Withdraw an outstanding invitation. A leaked link needs a kill switch."""
    from datetime import UTC, datetime

    invite = await db.get(WorkspaceInvite, invite_id)
    if invite is None or invite.workspace_id != ctx.workspace.id:
        raise NotFound("This invitation does not exist.", code="invite_invalid")
    if invite.accepted_at is not None:
        raise Conflict(
            "This invitation has already been used; remove the member instead.",
            code="invite_used",
        )
    if invite.revoked_at is None:
        invite.revoked_at = datetime.now(UTC)
        await audit.record(
            db,
            workspace_id=ctx.workspace.id,
            actor=ctx.user,
            action="invite.revoked",
            target_type="invite",
            target_id=invite.id,
            target_label=invite.email,
            request=request,
        )
        await db.commit()
    return OkResponse()


# ── Retention ───────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/retention", response_model=RetentionOut)
async def get_retention(ctx: AdminWorkspaceCtx) -> RetentionOut:
    return RetentionOut.model_validate(ctx.workspace)


@router.patch("/{workspace_id}/retention", response_model=RetentionOut)
async def update_retention(
    payload: RetentionRequest, ctx: AdminWorkspaceCtx, db: DbSession, request: Request
) -> RetentionOut:
    """Set how long messages and files live. Null keeps forever.

    Only the fields present in the body change (`exclude_unset`), so a client
    can clear one policy without restating the other. Every change is audited
    with before/after — shortening retention is the one setting that destroys
    data on a schedule.
    """
    changes = payload.model_dump(exclude_unset=True)
    before = RetentionOut.model_validate(ctx.workspace).model_dump()
    for field, value in changes.items():
        setattr(ctx.workspace, field, value)
    after = RetentionOut.model_validate(ctx.workspace).model_dump()
    if before != after:
        await audit.record(
            db,
            workspace_id=ctx.workspace.id,
            actor=ctx.user,
            action="retention.updated",
            target_type="workspace",
            target_id=ctx.workspace.id,
            target_label=ctx.workspace.name,
            details={"before": before, "after": after},
            request=request,
        )
    await db.commit()
    return RetentionOut.model_validate(ctx.workspace)
