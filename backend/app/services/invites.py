"""Workspace invitations: creating, listing, revoking and accepting them."""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, not_found
from app.core.ids import INVITE_PREFIX, MEMBER_PREFIX, new_id
from app.models.base import utcnow
from app.models.invite import INVITE_TTL_DAYS, Invite
from app.models.user import User
from app.models.workspace import ROLE_ADMIN, ROLE_MEMBER, Workspace, WorkspaceMembership
from app.services.channels import join_public_channels

TOKEN_BYTES = 12
TOKEN_ATTEMPTS = 5


async def new_token(session: AsyncSession) -> str:
    """Return an unguessable token that no other invite uses."""
    for _ in range(TOKEN_ATTEMPTS):
        token = secrets.token_urlsafe(TOKEN_BYTES)
        taken = await session.scalar(select(Invite.id).where(Invite.token == token))
        if taken is None:
            return token
    raise conflict("could not allocate an invite token")


async def find_pending(session: AsyncSession, workspace_id: str, email: str) -> Invite | None:
    """The pending invite for ``email`` in ``workspace``, if there is one."""
    return await session.scalar(
        select(Invite).where(
            Invite.workspace_id == workspace_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > utcnow(),
        )
    )


async def list_pending_invites(session: AsyncSession, workspace_id: str) -> list[Invite]:
    """Every invite that can still be accepted, newest first."""
    rows = await session.scalars(
        select(Invite)
        .where(
            Invite.workspace_id == workspace_id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > utcnow(),
        )
        .order_by(Invite.created_at.desc(), Invite.id.desc())
    )
    return list(rows)


async def create_invite(
    session: AsyncSession,
    workspace: Workspace,
    creator: User,
    email: str,
    role: str = ROLE_MEMBER,
) -> Invite:
    """Create an invite, or hand back the pending one that already exists."""
    clean_email = email.strip().lower()
    existing = await find_pending(session, workspace.id, clean_email)
    if existing is not None:
        return existing

    now = utcnow()
    invite = Invite(
        id=new_id(INVITE_PREFIX),
        workspace_id=workspace.id,
        email=clean_email,
        role=role,
        token=await new_token(session),
        created_by=creator.id,
        created_at=now,
        expires_at=now + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.flush()
    return invite


async def revoke_invite(session: AsyncSession, invite: Invite) -> Invite:
    """Revoke a pending invite; an already accepted one is left untouched."""
    if invite.accepted_at is None and invite.revoked_at is None:
        invite.revoked_at = utcnow()
        await session.flush()
    return invite


async def accept_invite(session: AsyncSession, token: str, user: User) -> Workspace:
    """Add ``user`` to the invited workspace and return it."""
    invite = await session.scalar(select(Invite).where(Invite.token == token))
    if invite is None:
        raise not_found("invite not found")
    if invite.revoked_at is not None:
        raise conflict("this invite has been revoked")
    if invite.accepted_at is not None:
        raise conflict("this invite has already been accepted")
    if invite.expires_at <= utcnow():
        raise conflict("this invite has expired")

    workspace = await session.get(Workspace, invite.workspace_id)
    if workspace is None:
        raise not_found("workspace not found")

    await _join_workspace(session, workspace, user, invite.role)
    invite.accepted_at = utcnow()
    invite.accepted_by = user.id
    await session.flush()
    return workspace


async def _join_workspace(
    session: AsyncSession, workspace: Workspace, user: User, role: str
) -> None:
    """Give ``user`` the invited role and seat them in the public channels."""
    membership = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        session.add(
            WorkspaceMembership(
                id=new_id(MEMBER_PREFIX),
                workspace_id=workspace.id,
                user_id=user.id,
                role=ROLE_ADMIN if role == ROLE_ADMIN else ROLE_MEMBER,
            )
        )
    elif membership.role == ROLE_MEMBER and role == ROLE_ADMIN:
        membership.role = ROLE_ADMIN

    await join_public_channels(session, workspace.id, user.id)
