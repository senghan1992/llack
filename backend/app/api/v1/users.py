"""User directory."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
async def read_users(
    user: CurrentUser,
    session: DbSession,
    q: str = Query(default="", max_length=120),
) -> list[UserOut]:
    """People that share a workspace with the caller."""
    term = q.strip()
    peer_workspaces = select(WorkspaceMembership.workspace_id).where(
        WorkspaceMembership.user_id == user.id
    )
    query = select(User).where(
        User.id.in_(
            select(WorkspaceMembership.user_id).where(
                WorkspaceMembership.workspace_id.in_(peer_workspaces)
            )
        )
    )
    if term:
        pattern = f"%{term.replace('%', '')}%"
        query = query.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

    rows = await session.scalars(query.order_by(User.name, User.id).limit(50))
    return [UserOut.model_validate(row) for row in rows]
