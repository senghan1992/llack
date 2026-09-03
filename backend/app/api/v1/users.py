"""Current-user profile, presence and workspace-scoped user lookup."""

from __future__ import annotations

import contextlib
import re
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, WorkspaceCtx
from app.core.config import settings
from app.core.enums import PresenceState
from app.core.errors import AppError, NotFound, PayloadTooLarge
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.realtime.events import emit_to_workspace
from app.realtime.presence import get_presence_store
from app.schemas.realtime import ServerEvent
from app.schemas.user import UpdateProfileRequest, UpdateStatusRequest, UserBrief, UserOut
from app.services.storage import get_storage
from app.services.workspaces import list_user_workspaces

router = APIRouter(tags=["users"])

# ── Avatars ─────────────────────────────────────────────────────────────────
#
# An avatar is served from a public, unauthenticated URL because it is loaded
# by `<img src>`, which cannot carry a bearer token. The URL embeds a random
# filename, so it is unguessable, and only the *current* avatar resolves — a
# replaced picture stops being reachable at its old address.

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
AVATAR_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
AVATAR_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.(png|jpg|webp)$")


def _avatar_key(user_id: str, filename: str) -> str:
    return f"avatars/{user_id}/{filename}"


def _own_avatar_filename(user: User) -> str | None:
    """The stored filename behind `avatar_url`, or None if it points elsewhere
    (an external URL set through the profile API)."""
    if not user.avatar_url:
        return None
    match = re.search(rf"/users/{re.escape(user.id)}/avatar/([A-Za-z0-9_-]+\.(?:png|jpg|webp))$",
                      user.avatar_url)
    return match.group(1) if match else None


async def _discard_own_avatar(user: User) -> None:
    filename = _own_avatar_filename(user)
    if filename is None:
        return
    with contextlib.suppress(Exception):
        await get_storage().delete(_avatar_key(user.id, filename))


async def _broadcast_user(db: DbSession, user: User) -> None:
    for workspace, _role in await list_user_workspaces(db, user_id=user.id):
        await emit_to_workspace(
            workspace.id,
            ServerEvent.USER_UPDATED,
            {"user": UserBrief.model_validate(user).model_dump()},
        )


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> UserOut:
    out = UserOut.model_validate(user)
    out.presence = await get_presence_store().get(user.id)
    return out


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UpdateProfileRequest, db: DbSession, user: CurrentUser) -> UserOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()

    # Everyone who shares a workspace needs the new name/avatar.
    for workspace, _role in await list_user_workspaces(db, user_id=user.id):
        await emit_to_workspace(
            workspace.id,
            ServerEvent.USER_UPDATED,
            {"user": UserBrief.model_validate(user).model_dump()},
        )
    return UserOut.model_validate(user)


@router.put("/me/avatar", response_model=UserOut)
async def upload_avatar(request: Request, db: DbSession, user: CurrentUser) -> UserOut:
    """Replace the profile picture with the request body (PNG/JPEG/WebP, ≤2 MiB).

    Raw bytes rather than the two-step workspace upload: an avatar belongs to
    the person, not to a workspace, and a 2 MiB cap makes a single request the
    right shape. The client resizes before sending, so the cap is generous.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    ext = AVATAR_TYPES.get(content_type)
    if ext is None:
        raise AppError(
            "Avatars must be PNG, JPEG or WebP.",
            code="unsupported_media_type",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > AVATAR_MAX_BYTES:
        raise PayloadTooLarge(details={"max_bytes": AVATAR_MAX_BYTES})
    body = await request.body()
    if len(body) > AVATAR_MAX_BYTES:
        raise PayloadTooLarge(details={"max_bytes": AVATAR_MAX_BYTES})
    if not body:
        raise AppError("The image is empty.", code="empty_upload")

    filename = f"{secrets.token_urlsafe(8)}.{ext}"

    async def _once() -> AsyncIterator[bytes]:
        yield body

    await get_storage().write_stream(_avatar_key(user.id, filename), _once())
    await _discard_own_avatar(user)
    user.avatar_url = f"{settings.api_prefix}/users/{user.id}/avatar/{filename}"
    await db.commit()
    await _broadcast_user(db, user)
    return UserOut.model_validate(user)


@router.delete("/me/avatar", response_model=UserOut)
async def delete_avatar(db: DbSession, user: CurrentUser) -> UserOut:
    await _discard_own_avatar(user)
    user.avatar_url = None
    await db.commit()
    await _broadcast_user(db, user)
    return UserOut.model_validate(user)


@router.get("/users/{user_id}/avatar/{filename}", include_in_schema=False)
async def get_avatar(user_id: str, filename: str, db: DbSession):
    """Public: the bytes behind a user's current avatar URL."""
    if not AVATAR_FILENAME_RE.match(filename):
        raise NotFound("Avatar not found.", code="avatar_not_found")
    user = await db.get(User, user_id)
    if user is None or _own_avatar_filename(user) != filename:
        raise NotFound("Avatar not found.", code="avatar_not_found")

    storage = get_storage()
    key = _avatar_key(user_id, filename)
    presigned = await storage.presigned_get_url(key)
    if presigned:
        return RedirectResponse(presigned, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return StreamingResponse(
        storage.read_stream(key),
        media_type=AVATAR_MEDIA[filename.rsplit(".", 1)[1]],
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.put("/me/status", response_model=UserOut)
async def update_status(
    payload: UpdateStatusRequest, db: DbSession, user: CurrentUser
) -> UserOut:
    data = payload.model_dump(exclude_unset=True)
    presence = data.pop("presence", None)
    for field, value in data.items():
        setattr(user, field, value)
    if presence is not None:
        user.presence = PresenceState(presence).value
        await get_presence_store().touch(user.id, PresenceState(presence))
    await db.commit()

    out = UserOut.model_validate(user)
    for workspace, _role in await list_user_workspaces(db, user_id=user.id):
        await emit_to_workspace(
            workspace.id,
            ServerEvent.PRESENCE_UPDATED,
            {
                "user_id": user.id,
                "presence": out.presence,
                "status_emoji": user.status_emoji,
                "status_text": user.status_text,
            },
        )
    return out


@router.get("/workspaces/{workspace_id}/users", response_model=list[UserOut])
async def list_workspace_users(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    include_bots: Annotated[bool, Query()] = True,
) -> list[UserOut]:
    """Directory search — powers @-mention autocomplete and the DM picker."""
    stmt = (
        select(User)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(
            WorkspaceMember.workspace_id == ctx.workspace.id,
            WorkspaceMember.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if not include_bots:
        stmt = stmt.where(User.is_bot.is_(False))
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.display_name).like(pattern),
                func.lower(User.handle).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )
    rows = list((await db.scalars(stmt.order_by(User.display_name).limit(limit))).all())

    presence = await get_presence_store().get_many([u.id for u in rows])
    out: list[UserOut] = []
    for row in rows:
        item = UserOut.model_validate(row)
        item.presence = presence.get(row.id, PresenceState.OFFLINE)
        out.append(item)
    return out


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str, db: DbSession, viewer: CurrentUser) -> UserOut:
    """Fetch a user the viewer shares at least one workspace with."""
    from app.core.errors import NotFound

    shared = await db.scalar(
        select(WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == viewer.id,
            WorkspaceMember.is_active.is_(True),
            WorkspaceMember.workspace_id.in_(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.is_active.is_(True),
                )
            ),
        )
        .limit(1)
    )
    if shared is None and user_id != viewer.id:
        raise NotFound("User not found.", code="user_not_found")

    row = await db.get(User, user_id)
    if row is None or row.deleted_at is not None:
        raise NotFound("User not found.", code="user_not_found")

    out = UserOut.model_validate(row)
    out.presence = await get_presence_store().get(row.id)
    return out
