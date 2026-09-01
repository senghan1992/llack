"""Password hashing and JWT access tokens.

Access tokens are short-lived signed JWTs (stateless, checked without a DB
round-trip). Refresh tokens are opaque random strings stored hashed in the
`sessions` table, so an individual device can be revoked — a plain JWT refresh
token cannot be.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import Unauthorized

# Tuned for an interactive login: ~50-100ms on a modern server core.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

TokenType = Literal["access", "app"]


# ── Passwords ───────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


# ── Opaque token hashing (refresh tokens, app tokens) ───────────────────────


def hash_token(token: str) -> str:
    """Keyed hash so a leaked DB alone cannot be used to forge tokens."""
    return hmac.new(
        settings.secret_key.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def tokens_equal(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


# ── JWT ─────────────────────────────────────────────────────────────────────


def create_access_token(
    *,
    subject: str,
    session_id: str | None = None,
    token_type: TokenType = "access",
    extra: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    """Return (token, expires_at)."""
    now = datetime.now(UTC)
    ttl = ttl_seconds if ttl_seconds is not None else settings.access_token_ttl_seconds
    expires_at = now + timedelta(seconds=ttl)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if session_id:
        payload["sid"] = session_id
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str, *, expected_type: TokenType = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Access token has expired.", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Access token is invalid.", code="token_invalid") from exc

    if payload.get("typ") != expected_type:
        raise Unauthorized("Access token is of the wrong type.", code="token_invalid")
    return payload
