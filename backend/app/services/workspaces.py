"""Workspace creation, membership and invitations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ChannelKind, WorkspaceRole
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ids import new_token, new_ulid
from app.core.logging import get_logger
from app.core.security import hash_token
from app.models.channel import Channel, ChannelMember
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceInvite, WorkspaceMember
from app.services.text import slugify

log = get_logger(__name__)

DEFAULT_CHANNELS: tuple[tuple[str, str], tuple[str, str]] = (
    ("general", "팀 전체 공지와 잡담"),
    ("random", "가벼운 이야기"),
)


async def get_membership(
    db: AsyncSession, *, workspace_id: str, user_id: str
) -> WorkspaceMember | None:
    return await db.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active.is_(True),
        )
        .limit(1)
    )


async def require_membership(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    minimum_role: WorkspaceRole = WorkspaceRole.GUEST,
) -> WorkspaceMember:
    membership = await get_membership(db, workspace_id=workspace_id, user_id=user_id)
    if membership is None:
        # 404 rather than 403: a non-member should not learn the workspace exists.
        raise NotFound("Workspace not found.", code="workspace_not_found")
    if not membership.role_enum.at_least(minimum_role):
        raise Forbidden(
            f"This action requires the {minimum_role.value} role.",
            code="insufficient_role",
            details={"required_role": minimum_role.value, "your_role": membership.role},
        )
    return membership


async def create_workspace(
    db: AsyncSession,
    *,
    owner: User,
    name: str,
    slug: str,
    description: str | None = None,
    allowed_email_domains: list[str] | None = None,
) -> Workspace:
    taken = await db.scalar(select(Workspace.id).where(Workspace.slug == slug).limit(1))
    if taken is not None:
        raise Conflict("This workspace URL is already taken.", code="slug_taken")

    workspace = Workspace(
        id=new_ulid(),
        slug=slug,
        name=name.strip(),
        description=description,
        created_by=owner.id,
        allowed_email_domains=allowed_email_domains or [],
    )
    db.add(workspace)
    db.add(
        WorkspaceMember(
            id=new_ulid(),
            workspace_id=workspace.id,
            user_id=owner.id,
            role=WorkspaceRole.OWNER.value,
        )
    )

    for index, (channel_name, topic) in enumerate(DEFAULT_CHANNELS):
        channel = Channel(
            id=new_ulid(),
            workspace_id=workspace.id,
            kind=ChannelKind.PUBLIC.value,
            slug=channel_name,
            name=channel_name,
            topic=topic,
            created_by=owner.id,
            is_default=index == 0,
            member_count=1,
        )
        db.add(channel)
        db.add(
            ChannelMember(
                id=new_ulid(),
                channel_id=channel.id,
                user_id=owner.id,
                role="admin",
                sort_order=index,
            )
        )

    await db.flush()
    log.info("workspace.created", workspace_id=workspace.id, slug=slug, owner_id=owner.id)
    return workspace


async def list_user_workspaces(db: AsyncSession, *, user_id: str) -> list[tuple[Workspace, str]]:
    rows = await db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.is_active.is_(True))
        .order_by(WorkspaceMember.sort_order, Workspace.name)
    )
    return [(w, role) for w, role in rows.all()]


async def count_members(db: AsyncSession, workspace_id: str) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_active.is_(True),
            )
        )
    ) or 0


async def add_member(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    role: WorkspaceRole = WorkspaceRole.MEMBER,
) -> WorkspaceMember:
    """Idempotent: re-adding an existing member reactivates them."""
    existing = await db.scalar(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .limit(1)
    )
    if existing is not None:
        existing.is_active = True
        await db.flush()
        return existing

    membership = WorkspaceMember(
        id=new_ulid(), workspace_id=workspace_id, user_id=user_id, role=role.value
    )
    db.add(membership)

    # Auto-join the default channels so a new member lands somewhere useful.
    default_channels = await db.scalars(
        select(Channel).where(
            Channel.workspace_id == workspace_id,
            Channel.kind == ChannelKind.PUBLIC.value,
            Channel.is_default.is_(True),
            Channel.is_archived.is_(False),
        )
    )
    for channel in default_channels:
        db.add(
            ChannelMember(id=new_ulid(), channel_id=channel.id, user_id=user_id)
        )
        channel.member_count += 1

    await db.flush()
    return membership


async def create_invites(
    db: AsyncSession,
    *,
    workspace_id: str,
    emails: list[str],
    role: WorkspaceRole,
    invited_by: str,
    ttl_days: int = 14,
) -> list[tuple[WorkspaceInvite, str]]:
    """Returns (invite row, raw token) pairs — the raw token is shown once."""
    created: list[tuple[WorkspaceInvite, str]] = []
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

    for email in {e.strip().lower() for e in emails}:
        already_member = await db.scalar(
            select(WorkspaceMember.id)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                User.email == email,
                WorkspaceMember.is_active.is_(True),
            )
            .limit(1)
        )
        if already_member is not None:
            continue

        raw_token = new_token(32)
        invite = WorkspaceInvite(
            id=new_ulid(),
            workspace_id=workspace_id,
            email=email,
            role=role.value,
            token_hash=hash_token(raw_token),
            invited_by=invited_by,
            expires_at=expires_at,
        )
        db.add(invite)
        created.append((invite, raw_token))

    await db.flush()
    return created


async def rotate_invite(db: AsyncSession, *, invite: WorkspaceInvite, ttl_days: int = 14) -> str:
    """Replace the token and extend expiry. Returns the new raw token (shown once)."""
    raw_token = new_token(32)
    invite.token_hash = hash_token(raw_token)
    invite.expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    await db.flush()
    return raw_token


async def peek_invite(db: AsyncSession, *, token: str) -> WorkspaceInvite:
    """Validate an invite token without consuming it.

    Sign-up needs to reject a bad token *before* creating the account — an
    orphan user behind a failed invite is exactly what invite-gated sign-up
    exists to prevent. Same checks as acceptance, minus the user comparison.
    """
    invite = await db.scalar(
        select(WorkspaceInvite).where(WorkspaceInvite.token_hash == hash_token(token)).limit(1)
    )
    if invite is None:
        raise NotFound("This invitation is not valid.", code="invite_invalid")
    if invite.accepted_at is not None:
        raise Conflict("This invitation has already been used.", code="invite_used")
    if invite.revoked_at is not None or invite.expires_at < datetime.now(UTC):
        raise Forbidden("This invitation has expired.", code="invite_expired")
    return invite


async def accept_invite(db: AsyncSession, *, token: str, user: User) -> Workspace:
    # A member who re-opens a bookmarked invite link is already where the link
    # leads. Answer with the workspace instead of "already used" — the token
    # is spent precisely because *they* spent it.
    spent = await db.scalar(
        select(WorkspaceInvite).where(WorkspaceInvite.token_hash == hash_token(token)).limit(1)
    )
    if spent is not None:
        membership = await db.scalar(
            select(WorkspaceMember.id)
            .where(
                WorkspaceMember.workspace_id == spent.workspace_id,
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.is_active.is_(True),
            )
            .limit(1)
        )
        if membership is not None:
            workspace = await db.get(Workspace, spent.workspace_id)
            if workspace is not None:
                return workspace

    invite = await peek_invite(db, token=token)
    if invite.email != user.email:
        raise Forbidden("This invitation was issued to a different email address.",
                        code="invite_email_mismatch")

    workspace = await db.get(Workspace, invite.workspace_id)
    if workspace is None:
        raise NotFound("Workspace not found.", code="workspace_not_found")

    await add_member(
        db,
        workspace_id=invite.workspace_id,
        user_id=user.id,
        role=WorkspaceRole(invite.role),
    )
    invite.accepted_at = datetime.now(UTC)
    await db.flush()
    return workspace


async def ensure_unique_channel_slug(db: AsyncSession, *, workspace_id: str, name: str) -> str:
    base = slugify(name)
    candidate = base
    for suffix in range(1, 100):
        taken = await db.scalar(
            select(Channel.id)
            .where(Channel.workspace_id == workspace_id, Channel.slug == candidate)
            .limit(1)
        )
        if taken is None:
            return candidate
        candidate = f"{base[:74]}-{suffix + 1}"
    return f"{base[:70]}-{new_token(3)}"
