"""The caller's own profile."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models.base import utcnow
from app.realtime import events
from app.schemas.user import PRESENCE_SELECTABLE, UserOut, UserUpdate

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UserUpdate, user: CurrentUser, session: DbSession) -> UserOut:
    data = payload.model_dump(exclude_unset=True)
    status_text = data.pop("status_text", None)

    if "name" in data and data["name"]:
        user.name = data["name"].strip()
    if "title" in data:
        user.title = data["title"]
    if "avatar_color" in data and data["avatar_color"]:
        user.avatar_color = data["avatar_color"]
    if status_text is not None:
        user.status_text = status_text

    presence = data.get("presence")
    if presence in PRESENCE_SELECTABLE:
        user.presence = presence
        user.last_seen_at = utcnow()

    await session.commit()
    await session.refresh(user)
    if presence in PRESENCE_SELECTABLE:
        # Tell the team straight away — presence that only changes on
        # reconnect is presence nobody can rely on.
        await events.emit_presence(session, user, presence)
    # A new face, a new colour: the roster should show it at once.
    await events.emit_user_updated(session, user)
    return UserOut.model_validate(user)
