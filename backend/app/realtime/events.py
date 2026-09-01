"""Helpers for building and dispatching realtime events.

Route handlers call `emit_*` rather than talking to the hub directly, so the
topic each event fans out to is decided in exactly one place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.realtime.hub import get_hub
from app.schemas.realtime import ServerEvent


def envelope(
    event: ServerEvent | str,
    data: dict[str, Any],
    *,
    workspace_id: str | None = None,
    exclude_connection: str | None = None,
    exclude_user: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": str(event),
        "ts": datetime.now(UTC).isoformat(),
        "data": data,
    }
    if workspace_id:
        payload["workspace_id"] = workspace_id
    if exclude_connection:
        payload["_exclude_connection"] = exclude_connection
    if exclude_user:
        payload["_exclude_user"] = exclude_user
    return payload


async def emit_to_channel(
    channel_id: str,
    event: ServerEvent | str,
    data: dict[str, Any],
    *,
    workspace_id: str | None = None,
    exclude_connection: str | None = None,
) -> None:
    await get_hub().publish_to_channel(
        channel_id,
        envelope(
            event, data, workspace_id=workspace_id, exclude_connection=exclude_connection
        ),
    )


async def emit_to_workspace(
    workspace_id: str,
    event: ServerEvent | str,
    data: dict[str, Any],
    *,
    exclude_connection: str | None = None,
) -> None:
    await get_hub().publish_to_workspace(
        workspace_id,
        envelope(
            event, data, workspace_id=workspace_id, exclude_connection=exclude_connection
        ),
    )


async def emit_to_users(
    user_ids: list[str],
    event: ServerEvent | str,
    data: dict[str, Any],
    *,
    workspace_id: str | None = None,
) -> None:
    if not user_ids:
        return
    await get_hub().publish_to_users(
        user_ids, envelope(event, data, workspace_id=workspace_id)
    )
