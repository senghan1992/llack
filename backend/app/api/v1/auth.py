"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from app.api.deps import ClientIp, CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import Forbidden
from app.core.ratelimit import limiter
from app.core.security import decode_access_token
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SessionOut,
    TokenPair,
)
from app.schemas.common import OkResponse
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:512] if value else None


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, db: DbSession, request: Request, ip: ClientIp
) -> AuthResponse:
    """Create an account.

    Open by default (dev). With `LLACK_REQUIRE_INVITE` the token is mandatory
    and is validated *before* the account exists, so a bad invite cannot leave
    an orphan user behind. A valid token also joins its workspace in the same
    transaction — sign-up and onboarding are one step.
    """
    limiter.check(
        "register", ip, capacity=settings.rate_limit_register_per_hour, per_seconds=3_600
    )

    invite_token = payload.invite_token
    if invite_token:
        invite = await workspace_service.peek_invite(db, token=invite_token)
        if invite.email != payload.email.strip().lower():
            raise Forbidden(
                "This invitation was issued to a different email address.",
                code="invite_email_mismatch",
            )
    elif settings.require_invite:
        raise Forbidden(
            "Signing up on this server requires an invitation.",
            code="invite_required",
        )

    user = await auth_service.register_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        handle=payload.handle,
    )
    if invite_token:
        await workspace_service.accept_invite(db, token=invite_token, user=user)
    tokens = await auth_service.issue_tokens(
        db, user, device=payload.device, ip_address=ip, user_agent=_user_agent(request)
    )
    await db.commit()
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest, db: DbSession, request: Request, ip: ClientIp
) -> AuthResponse:
    # Keyed by email *and* address, and checked before the password: the
    # bucket must fill on failures, or it does not slow a guesser down.
    limiter.check(
        "login",
        f"{payload.email.lower()}|{ip or '-'}",
        capacity=settings.rate_limit_login_per_minute,
        per_seconds=60,
    )
    user = await auth_service.authenticate(db, email=payload.email, password=payload.password)
    tokens = await auth_service.issue_tokens(
        db, user, device=payload.device, ip_address=ip, user_agent=_user_agent(request)
    )
    await db.commit()
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Exchange a refresh token for a new pair. The old one stops working."""
    _, tokens = await auth_service.rotate_tokens(db, refresh_token=payload.refresh_token)
    await db.commit()
    return tokens


@router.post("/logout", response_model=OkResponse)
async def logout(
    db: DbSession,
    user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> OkResponse:
    """Revoke the session this access token belongs to."""
    if authorization:
        token = authorization.partition(" ")[2].strip()
        payload = decode_access_token(token)
        session_id = payload.get("sid")
        if session_id:
            await auth_service.revoke_session(db, user_id=user.id, session_id=session_id)
    await db.commit()
    return OkResponse()


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    db: DbSession,
    user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> list[SessionOut]:
    current_session_id: str | None = None
    if authorization:
        token = authorization.partition(" ")[2].strip()
        current_session_id = decode_access_token(token).get("sid")

    rows = await auth_service.list_sessions(db, user_id=user.id)
    await db.commit()
    return [
        SessionOut(
            **SessionOut.model_validate(row).model_dump(exclude={"is_current"}),
            is_current=row.id == current_session_id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", response_model=OkResponse)
async def revoke_session(session_id: str, db: DbSession, user: CurrentUser) -> OkResponse:
    await auth_service.revoke_session(db, user_id=user.id, session_id=session_id)
    await db.commit()
    return OkResponse()


@router.post("/sessions/revoke-others", response_model=OkResponse)
async def revoke_other_sessions(
    db: DbSession,
    user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> OkResponse:
    keep: str | None = None
    if authorization:
        keep = decode_access_token(authorization.partition(" ")[2].strip()).get("sid")
    await auth_service.revoke_all_sessions(db, user_id=user.id, except_session_id=keep)
    await db.commit()
    return OkResponse()


@router.post("/password", response_model=OkResponse)
async def change_password(
    payload: ChangePasswordRequest,
    db: DbSession,
    user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> OkResponse:
    """Change the password and sign every other device out."""
    await auth_service.change_password(
        db,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    keep: str | None = None
    if authorization:
        keep = decode_access_token(authorization.partition(" ")[2].strip()).get("sid")
    await auth_service.revoke_all_sessions(db, user_id=user.id, except_session_id=keep)
    await db.commit()
    return OkResponse()


@router.get("/config", response_model=dict)
async def public_config() -> dict:
    """Unauthenticated bootstrap info the desktop client reads at launch."""
    return {
        "api_prefix": settings.api_prefix,
        "access_token_ttl_seconds": settings.access_token_ttl_seconds,
        "ws_heartbeat_seconds": settings.ws_heartbeat_seconds,
        "max_upload_bytes": settings.max_upload_bytes,
        "realtime_protocol_version": 1,
        # The sign-in screen reads this to say "invite only" up front instead
        # of letting someone fill the whole form first.
        "require_invite": settings.require_invite,
    }
