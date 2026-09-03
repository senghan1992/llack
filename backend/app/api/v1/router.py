"""Mounts every v1 router under the configured API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    apps,
    auth,
    channels,
    files,
    invites,
    messages,
    realtime,
    search,
    users,
    workspaces,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(users.router)
api_router.include_router(workspaces.router)
api_router.include_router(invites.router)
api_router.include_router(channels.router)
api_router.include_router(messages.router)
api_router.include_router(files.router)
api_router.include_router(search.router)
api_router.include_router(activity.router)
api_router.include_router(apps.router)
api_router.include_router(apps.bridge)
api_router.include_router(realtime.router)
