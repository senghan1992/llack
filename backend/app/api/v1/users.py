"""Current-user profile, presence and workspace-scoped user lookup."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, WorkspaceCtx
from app.core.enums import PresenceState
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.realtime.events import emit_to_workspace
from app.realtime.presence import get_presence_store
from app.schemas.realtime import ServerEvent
from app.schemas.user import UpdateProfileRequest, UpdateStatusRequest, UserBrief, UserOut
from app.services.workspaces import list_user_workspaces

router = APIRouter(tags=["users"])


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
