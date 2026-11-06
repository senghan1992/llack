"""The v1 router: every route of the API contract lives here."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    channels,
    files,
    invites,
    me,
    messages,
    milestones,
    org,
    projects,
    realtime,
    schedule,
    search,
    users,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(workspaces.router)
api_router.include_router(channels.router)
api_router.include_router(messages.router)
api_router.include_router(users.router)
api_router.include_router(files.router)
api_router.include_router(search.router)
api_router.include_router(schedule.router)
api_router.include_router(projects.router)
api_router.include_router(milestones.router)
api_router.include_router(org.router)
api_router.include_router(realtime.router)
api_router.include_router(invites.router)

__all__ = ["api_router"]
