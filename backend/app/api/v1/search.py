"""Unified search — the Cmd+K palette's backend.

One endpoint returns messages, channels, people and installed apps for a single
query, so the client renders one ranked list instead of making the user pick a
category first.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, WorkspaceCtx
from app.api.v1.messages import serialise_message
from app.core.enums import ChannelKind
from app.models.app import AppInstallation
from app.models.channel import Channel, ChannelMember
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.message import SearchHit, SearchResponse
from app.services import messages as message_service

router = APIRouter(tags=["search"])


@router.get("/workspaces/{workspace_id}/search/messages", response_model=SearchResponse)
async def search_messages(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    channel_id: Annotated[str | None, Query(max_length=26)] = None,
    from_user_id: Annotated[str | None, Query(max_length=26)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=26)] = None,
) -> SearchResponse:
    hits, _has_more, took_ms = await message_service.search_messages(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        query=q,
        channel_id=channel_id,
        from_user_id=from_user_id,
        limit=limit,
        cursor=cursor,
    )
    return SearchResponse(
        query=q,
        took_ms=took_ms,
        total=len(hits),
        hits=[
            SearchHit(
                message=serialise_message(message, viewer_id=ctx.user.id),
                channel_id=channel.id,
                channel_name=channel.name or channel.slug,
                highlight=snippet,
            )
            for message, channel, snippet in hits
        ],
    )


@router.get("/workspaces/{workspace_id}/search", response_model=dict)
async def search_everything(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> dict[str, Any]:
    """Everything at once, capped per category — built for a command palette."""
    term = q.strip()
    pattern = f"%{term.lower()}%"

    channels = list(
        (
            await db.scalars(
                select(Channel)
                .outerjoin(
                    ChannelMember,
                    (ChannelMember.channel_id == Channel.id)
                    & (ChannelMember.user_id == ctx.user.id),
                )
                .where(
                    Channel.workspace_id == ctx.workspace.id,
                    Channel.is_archived.is_(False),
                    or_(
                        Channel.kind == ChannelKind.PUBLIC.value,
                        ChannelMember.id.isnot(None),
                    ),
                    or_(
                        func.lower(Channel.name).like(pattern),
                        func.lower(Channel.slug).like(pattern),
                        func.lower(Channel.topic).like(pattern),
                    ),
                )
                .order_by(Channel.member_count.desc())
                .limit(limit)
            )
        ).all()
    )

    people = list(
        (
            await db.scalars(
                select(User)
                .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
                .where(
                    WorkspaceMember.workspace_id == ctx.workspace.id,
                    WorkspaceMember.is_active.is_(True),
                    User.deleted_at.is_(None),
                    or_(
                        func.lower(User.display_name).like(pattern),
                        func.lower(User.handle).like(pattern),
                        func.lower(User.title).like(pattern),
                    ),
                )
                .order_by(User.display_name)
                .limit(limit)
            )
        ).all()
    )

    installations = list(
        (
            await db.scalars(
                select(AppInstallation)
                .where(
                    AppInstallation.workspace_id == ctx.workspace.id,
                    AppInstallation.is_enabled.is_(True),
                )
                .limit(50)
            )
        ).all()
    )
    matched_apps = [
        inst
        for inst in installations
        if term.lower() in inst.app.name.lower()
        or term.lower() in (inst.app.tagline or "").lower()
    ][:limit]

    message_hits, _, took_ms = await message_service.search_messages(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        query=term,
        limit=limit,
    )

    return {
        "query": term,
        "took_ms": took_ms,
        "channels": [
            {
                "id": c.id,
                "name": c.name or c.slug,
                "slug": c.slug,
                "kind": c.kind,
                "topic": c.topic,
                "member_count": c.member_count,
            }
            for c in channels
        ],
        "people": [
            {
                "id": u.id,
                "display_name": u.display_name,
                "handle": u.handle,
                "title": u.title,
                "avatar_url": u.avatar_url,
                "is_bot": u.is_bot,
            }
            for u in people
        ],
        "apps": [
            {
                "installation_id": i.id,
                "app_id": i.app_id,
                "name": i.app.name,
                "tagline": i.app.tagline,
                "icon_url": i.app.icon_url,
                "has_panel": i.app.has_panel,
            }
            for i in matched_apps
        ],
        "messages": [
            {
                "message": serialise_message(m, viewer_id=ctx.user.id).model_dump(mode="json"),
                "channel_id": c.id,
                "channel_name": c.name or c.slug,
                "highlight": snippet,
            }
            for m, c, snippet in message_hits
        ],
    }
