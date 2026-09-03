"""Shared FastAPI dependencies: authentication, workspace/channel resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, Header, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import AppScope, WorkspaceRole
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.security import decode_access_token
from app.models.app import AppInstallation
from app.models.channel import Channel, ChannelMember
from app.models.user import Session, User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import apps as app_service
from app.services import channels as channel_service
from app.services.workspaces import require_membership

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise Unauthorized("Authorization header is missing.", code="missing_credentials")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized(
            "Authorization header must be 'Bearer <token>'.", code="malformed_credentials"
        )
    return token.strip()


# ── User authentication ─────────────────────────────────────────────────────


@dataclass(slots=True)
class Principal:
    """Who is making this request, and on whose behalf."""

    user: User
    session_id: str | None = None
    # Set when the request arrived with an app bridge/server token.
    installation: AppInstallation | None = None
    scopes: tuple[str, ...] = ()

    @property
    def is_app(self) -> bool:
        return self.installation is not None

    def require_scope(self, scope: AppScope) -> None:
        """No-op for a human request; enforced for an app request."""
        if self.installation is None:
            return
        app_service.require_scope(list(self.scopes), scope)


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    payload = decode_access_token(_bearer(authorization))
    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("This account is no longer active.", code="account_inactive")

    # A revoked device must stop working before its access token expires.
    session_id = payload.get("sid")
    if session_id:
        session_row = await db.get(Session, session_id)
        if session_row is None or not session_row.is_valid:
            raise Unauthorized("This session has been signed out.", code="session_revoked")
        session_row.last_used_at = datetime.now(UTC)

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_principal(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Accept either a user access token or an app token.

    Lets one route serve both the desktop client and an installed mini-app,
    with scope enforcement applied only in the app case.
    """
    token = _bearer(authorization)

    if token.startswith("llack_at_"):
        installation = await app_service.resolve_app_token(db, token)
        bot_id = installation.bot_user_id
        if bot_id is None:
            raise Forbidden("This app has no bot identity.", code="app_without_bot")
        bot = await db.get(User, bot_id)
        if bot is None:
            raise Forbidden("This app's bot identity is missing.", code="app_without_bot")
        return Principal(
            user=bot,
            installation=installation,
            scopes=tuple(installation.granted_scopes),
        )

    # Peek at the (still unverified) `typ` claim to decide which verifier to
    # use. Nothing is trusted from this read — both branches below verify the
    # signature before acting on anything.
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise Unauthorized("Access token is invalid.", code="token_invalid") from exc

    if unverified.get("typ") == "app":
        payload = app_service.decode_bridge_token(token)
        installation = await db.get(AppInstallation, payload["iid"])
        if installation is None or not installation.is_enabled:
            raise NotFound("This app is not installed.", code="installation_not_found")
        acting_user = await db.get(User, payload["sub"])
        if acting_user is None or not acting_user.is_active:
            raise Unauthorized("The acting user is no longer active.", code="account_inactive")
        return Principal(
            user=acting_user,
            installation=installation,
            # Trust the installation row, not the token's copy of the scopes —
            # an admin may have narrowed them since the token was minted.
            scopes=tuple(installation.granted_scopes),
        )

    payload = decode_access_token(token)
    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("This account is no longer active.", code="account_inactive")
    return Principal(user=user, session_id=payload.get("sid"))


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


# ── Workspace resolution ────────────────────────────────────────────────────


@dataclass(slots=True)
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMember
    user: User

    @property
    def role(self) -> WorkspaceRole:
        return self.membership.role_enum

    def require_role(self, minimum: WorkspaceRole) -> None:
        if not self.role.at_least(minimum):
            raise Forbidden(
                f"This action requires the {minimum.value} role.",
                code="insufficient_role",
                details={"required_role": minimum.value, "your_role": self.membership.role},
            )


async def get_workspace_context(
    db: DbSession,
    user: CurrentUser,
    workspace_id: Annotated[str, Path()],
) -> WorkspaceContext:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound("Workspace not found.", code="workspace_not_found")
    membership = await require_membership(db, workspace_id=workspace_id, user_id=user.id)
    return WorkspaceContext(workspace=workspace, membership=membership, user=user)


WorkspaceCtx = Annotated[WorkspaceContext, Depends(get_workspace_context)]


async def require_workspace_admin(ctx: WorkspaceCtx) -> WorkspaceContext:
    ctx.require_role(WorkspaceRole.ADMIN)
    return ctx


AdminWorkspaceCtx = Annotated[WorkspaceContext, Depends(require_workspace_admin)]


# ── Channel resolution ──────────────────────────────────────────────────────


@dataclass(slots=True)
class ChannelContext:
    channel: Channel
    membership: ChannelMember | None
    user: User
    # Set when the request was authenticated as a principal (user *or* app),
    # so a route can enforce app scopes without a second dependency.
    principal: Principal | None = None

    @property
    def is_member(self) -> bool:
        return self.membership is not None

    @property
    def is_app(self) -> bool:
        return self.principal is not None and self.principal.is_app

    def require_member(self) -> ChannelMember:
        if self.membership is None:
            raise Forbidden("Join this channel first.", code="not_channel_member")
        return self.membership

    def require_scope(self, scope: AppScope) -> None:
        if self.principal is not None:
            self.principal.require_scope(scope)


async def get_channel_context(
    db: DbSession,
    user: CurrentUser,
    channel_id: Annotated[str, Path()],
) -> ChannelContext:
    """Readable channel + the user's membership (which may be None for public)."""
    channel, membership = await channel_service.resolve_access(
        db, channel_id=channel_id, user_id=user.id, require_member=False
    )
    return ChannelContext(channel=channel, membership=membership, user=user)


ChannelCtx = Annotated[ChannelContext, Depends(get_channel_context)]


async def get_channel_context_for_principal(
    db: DbSession,
    principal: CurrentPrincipal,
    channel_id: Annotated[str, Path()],
) -> ChannelContext:
    """Channel access for a request that may come from a mini-app."""
    channel, membership = await channel_service.resolve_access(
        db, channel_id=channel_id, user_id=principal.user.id, require_member=False
    )
    if principal.installation is not None:
        if principal.installation.workspace_id != channel.workspace_id:
            raise NotFound("Channel not found.", code="channel_not_found")
        allowed = principal.installation.channel_ids
        # An empty allow-list means workspace-wide.
        if allowed and channel.id not in allowed:
            raise Forbidden(
                "This app was not added to this channel.", code="app_not_in_channel"
            )
    return ChannelContext(
        channel=channel,
        membership=membership,
        user=principal.user,
        principal=principal,
    )


PrincipalChannelCtx = Annotated[ChannelContext, Depends(get_channel_context_for_principal)]


# ── Misc ────────────────────────────────────────────────────────────────────


def client_ip(request: Request) -> str | None:
    # Trust X-Forwarded-For only when a reverse proxy sets it; uvicorn is run
    # with --proxy-headers behind one.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


ClientIp = Annotated[str | None, Depends(client_ip)]


@dataclass(slots=True)
class Pagination:
    limit: int
    cursor: str | None


async def pagination(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> Pagination:
    return Pagination(limit=limit, cursor=cursor)


Paging = Annotated[Pagination, Depends(pagination)]


async def require_server_admin(db: DbSession, user: CurrentUser) -> User:
    """Server-wide settings (SMTP, …) need more than a workspace role.

    The bar: `is_service_admin`, or **owner** of at least one workspace. On a
    single-workspace 사내 서버 that is exactly "the person who set this up";
    a mere channel/workspace admin cannot re-point everyone's outbound mail.
    """
    if user.is_service_admin:
        return user
    from sqlalchemy import select as _select

    from app.core.enums import WorkspaceRole
    from app.models.workspace import WorkspaceMember as _WM

    owner = await db.scalar(
        _select(_WM.id)
        .where(
            _WM.user_id == user.id,
            _WM.role == WorkspaceRole.OWNER.value,
            _WM.is_active.is_(True),
        )
        .limit(1)
    )
    if owner is None:
        raise Forbidden(
            "Server settings require a workspace owner.",
            code="server_admin_required",
        )
    return user


ServerAdmin = Annotated[User, Depends(require_server_admin)]
