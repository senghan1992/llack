"""Registration, login, token refresh and session management."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.core.ids import new_token, new_ulid
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.models.user import Session, User
from app.schemas.auth import DeviceInfo, TokenPair

log = get_logger(__name__)

_HANDLE_SAFE = re.compile(r"[^a-z0-9._-]+")


def derive_handle(email: str, display_name: str) -> str:
    """Best-effort handle from the email local part, falling back to the name."""
    base = _HANDLE_SAFE.sub("", email.split("@", 1)[0].lower()).strip("._-")
    if len(base) < 2:
        base = _HANDLE_SAFE.sub("", display_name.lower().replace(" ", ".")).strip("._-")
    if len(base) < 2:
        base = "user"
    return base[:56]


async def allocate_handle(session: AsyncSession, desired: str) -> str:
    """Return `desired`, or `desired2`, `desired3`, … if it is taken."""
    candidate = desired
    for suffix in range(1, 200):
        exists = await session.scalar(select(User.id).where(User.handle == candidate).limit(1))
        if exists is None:
            return candidate
        candidate = f"{desired[:56]}{suffix + 1}"
    # Astronomically unlikely; a random suffix is still better than failing.
    return f"{desired[:48]}-{new_token(4)}"


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    handle: str | None = None,
) -> User:
    normalised_email = email.strip().lower()
    existing = await db.scalar(select(User).where(User.email == normalised_email).limit(1))
    if existing is not None:
        raise Conflict("An account with this email already exists.", code="email_taken")

    desired_handle = handle or derive_handle(normalised_email, display_name)
    if handle is not None:
        taken = await db.scalar(select(User.id).where(User.handle == handle).limit(1))
        if taken is not None:
            raise Conflict("This handle is already taken.", code="handle_taken")
        final_handle = handle
    else:
        final_handle = await allocate_handle(db, desired_handle)

    user = User(
        id=new_ulid(),
        email=normalised_email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        handle=final_handle,
    )
    db.add(user)
    await db.flush()
    log.info("auth.user_registered", user_id=user.id, email=normalised_email)
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()).limit(1))

    # Verify against a dummy hash when the user does not exist, so a missing
    # account and a wrong password take the same amount of time.
    if user is None or not user.password_hash:
        verify_password(password, _DUMMY_HASH)
        raise Unauthorized("Email or password is incorrect.", code="invalid_credentials")

    if not verify_password(password, user.password_hash):
        raise Unauthorized("Email or password is incorrect.", code="invalid_credentials")

    if not user.is_active or user.deleted_at is not None:
        raise Forbidden("This account has been deactivated.", code="account_disabled")

    # Opportunistically upgrade the hash if the cost parameters changed.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user


# Precomputed once so `authenticate` never pays a hashing cost to build it.
_DUMMY_HASH = hash_password("llack-timing-equalisation-placeholder")


async def issue_tokens(
    db: AsyncSession,
    user: User,
    *,
    device: DeviceInfo | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    """Create a device session and return an access/refresh pair."""
    refresh_token = new_token(48)
    now = datetime.now(UTC)
    session_row = Session(
        id=new_ulid(),
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        device_name=device.device_name if device else None,
        platform=device.platform if device else None,
        app_version=device.app_version if device else None,
        ip_address=ip_address,
        user_agent=user_agent,
        last_used_at=now,
    )
    db.add(session_row)
    await db.flush()

    access_token, expires_at = create_access_token(subject=user.id, session_id=session_row.id)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        expires_in=settings.access_token_ttl_seconds,
    )


async def rotate_tokens(db: AsyncSession, *, refresh_token: str) -> tuple[User, TokenPair]:
    """Exchange a refresh token for a new pair.

    The presented token is rotated: its session row gets a brand-new refresh
    token. Re-presenting a rotated token fails, which is what makes theft of a
    refresh token detectable rather than silently durable.
    """
    token_hash = hash_token(refresh_token)
    session_row = await db.scalar(
        select(Session).where(Session.refresh_token_hash == token_hash).limit(1)
    )
    if session_row is None:
        raise Unauthorized("Refresh token is invalid.", code="refresh_invalid")
    if not session_row.is_valid:
        raise Unauthorized("Refresh token has expired or been revoked.", code="refresh_expired")

    user = await db.get(User, session_row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Forbidden("This account has been deactivated.", code="account_disabled")

    now = datetime.now(UTC)
    new_refresh = new_token(48)
    session_row.refresh_token_hash = hash_token(new_refresh)
    session_row.expires_at = now + timedelta(seconds=settings.refresh_token_ttl_seconds)
    session_row.last_used_at = now
    await db.flush()

    access_token, expires_at = create_access_token(subject=user.id, session_id=session_row.id)
    return user, TokenPair(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_at=expires_at,
        expires_in=settings.access_token_ttl_seconds,
    )


async def revoke_session(db: AsyncSession, *, user_id: str, session_id: str) -> None:
    await db.execute(
        update(Session)
        .where(Session.id == session_id, Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_sessions(
    db: AsyncSession, *, user_id: str, except_session_id: str | None = None
) -> int:
    stmt = (
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if except_session_id:
        stmt = stmt.where(Session.id != except_session_id)
    result = await db.execute(stmt)
    return result.rowcount or 0


async def list_sessions(db: AsyncSession, *, user_id: str) -> list[Session]:
    rows = await db.scalars(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > datetime.now(UTC),
        )
        .order_by(Session.last_used_at.desc().nullslast(), Session.created_at.desc())
    )
    return list(rows)


async def change_password(
    db: AsyncSession, user: User, *, current_password: str, new_password: str
) -> None:
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect.", code="invalid_credentials")
    user.password_hash = hash_password(new_password)
    await db.flush()


async def admin_set_password(db: AsyncSession, user: User, new_password: str) -> None:
    """Overwrite a password without knowing the old one.

    The recovery path for "비밀번호를 잊었습니다" on a server with no outbound
    email. Authorisation (a strictly higher workspace role) is the API layer's
    job; every caller must also revoke the target's sessions.
    """
    user.password_hash = hash_password(new_password)
    await db.flush()
