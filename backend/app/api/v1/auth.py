"""Sign-up, sign-in and token refresh."""

from __future__ import annotations

import random

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import conflict, unauthorized
from app.core.ids import USER_PREFIX, new_id
from app.core.security import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.base import utcnow
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import LoginRequest, RefreshRequest, Session, SignupRequest, Tokens
from app.services.workspaces import create_workspace, primary_workspace

router = APIRouter(prefix="/auth", tags=["auth"])

AVATAR_COLORS = (
    "#3f6f52",
    "#7a5c3e",
    "#4a5b8c",
    "#8c4a5b",
    "#5b8c7a",
    "#8c7a4a",
    "#6b4a8c",
    "#4a8c6b",
)


def _tokens(user: User) -> tuple[str, str]:
    return create_access_token(user.id), create_refresh_token(user.id)


def _session(user: User, workspace: Workspace) -> Session:
    access_token, refresh_token = _tokens(user)
    return Session(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user,
        workspace=workspace,
    )


@router.post("/signup", response_model=Session)
async def signup(payload: SignupRequest, session: AsyncSession = Depends(get_session)) -> Session:
    email = payload.email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise conflict("email is already registered")

    now = utcnow()
    user = User(
        id=new_id(USER_PREFIX),
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
        title=None,
        avatar_color=random.choice(AVATAR_COLORS),
        presence="offline",
        last_seen_at=now,
        created_at=now,
    )
    session.add(user)
    await session.flush()

    workspace = await create_workspace(session, user, payload.workspace_name)
    await session.commit()
    return _session(user, workspace)


@router.post("/login", response_model=Session)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> Session:
    email = payload.email.strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise unauthorized("invalid email or password")

    workspace = await primary_workspace(session, user.id)
    if workspace is None:
        raise unauthorized("this account has no workspace")
    return _session(user, workspace)


@router.post("/refresh", response_model=Tokens)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> Tokens:
    try:
        user_id = decode_token(payload.refresh_token, REFRESH_TOKEN)
    except Exception as exc:
        raise unauthorized("invalid or expired refresh token") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized("unknown user")

    access_token, refresh_token = _tokens(user)
    return Tokens(access_token=access_token, refresh_token=refresh_token)
