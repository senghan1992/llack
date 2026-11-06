"""Password hashing, JWT issuing/verification and the current-user dependency."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import unauthorized
from app.models.user import User

_password_hash = PasswordHash.recommended()
_bearer = HTTPBearer(auto_error=False)

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def hash_password(raw_password: str) -> str:
    return _password_hash.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(raw_password, password_hash)
    except Exception:
        return False


def _encode(user_id: str, token_type: str, ttl_seconds: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return _encode(user_id, ACCESS_TOKEN, settings.access_token_ttl_seconds)


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return _encode(user_id, REFRESH_TOKEN, settings.refresh_token_ttl_seconds)


def decode_token(token: str, expected_type: str) -> str:
    """Return the user id carried by ``token``; raises ``ValueError`` when invalid."""
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != expected_type:
        raise ValueError("unexpected token type")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise ValueError("token has no subject")
    return subject


async def load_user(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """FastAPI dependency returning the authenticated user."""
    if credentials is None or not credentials.credentials:
        raise unauthorized("missing bearer token")
    try:
        user_id = decode_token(credentials.credentials, ACCESS_TOKEN)
    except jwt.PyJWTError as exc:
        raise unauthorized("invalid or expired token") from exc
    except ValueError as exc:
        raise unauthorized("invalid or expired token") from exc
    user = await load_user(session, user_id)
    if user is None:
        raise unauthorized("unknown user")
    request.state.user_id = user.id
    return user


async def authenticate_query_token(session: AsyncSession, token: str | None) -> User | None:
    """Resolve the user behind a ``?token=`` query parameter."""
    if not token:
        return None
    try:
        user_id = decode_token(token, ACCESS_TOKEN)
    except (jwt.PyJWTError, ValueError):
        return None
    return await load_user(session, user_id)


async def current_user_or_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """The bearer header, or a ``?token=`` query parameter.

    An ``<img>`` tag cannot send an Authorization header, so a browser that
    wants to show a file needs the token in the URL. The websocket already
    takes it the same way.
    """
    if credentials is not None and credentials.credentials:
        return await current_user(request, credentials, session)
    user = await authenticate_query_token(session, token)
    if user is None:
        raise unauthorized("missing bearer token")
    request.state.user_id = user.id
    return user
