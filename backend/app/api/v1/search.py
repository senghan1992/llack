"""Message search."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.schemas.search import SearchResult
from app.services.search import search_messages

router = APIRouter(prefix="/workspaces", tags=["search"])


@router.get("/{workspace_id}/search", response_model=list[SearchResult])
async def search(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=30, ge=1),
) -> list[SearchResult]:
    return await search_messages(session, workspace_id, user.id, q, limit)
