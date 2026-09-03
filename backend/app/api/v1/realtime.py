"""The WebSocket gateway.

Connection lifecycle:

1. Client opens `/api/v1/ws?token=<access token>&workspace_id=<id>`.
   (The token is a query parameter because browsers/webviews cannot set headers
   on a WebSocket handshake. It is short-lived, which is what makes that
   acceptable.)
2. Server authenticates, subscribes the socket to the user's topics, and sends
   `hello` with the current server time and heartbeat interval.
3. Client sends `ping` every `heartbeat_seconds`; the server replies `pong`. A
   socket that stops pinging for 2.5 intervals is closed.
4. Every frame carries a monotonic `seq`. A gap means the client missed events
   and should re-fetch the affected channels.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Annotated

import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.db import get_sessionmaker
from app.core.enums import PresenceState
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.models.channel import ChannelMember
from app.models.user import Session, User
from app.models.workspace import WorkspaceMember
from app.realtime.bus import channel_topic, user_topic, workspace_topic
from app.realtime.events import emit_to_channel, emit_to_workspace
from app.realtime.hub import Connection, get_hub
from app.realtime.presence import get_presence_store
from app.schemas.realtime import ClientCommand, HelloData, ServerEvent

log = get_logger(__name__)

router = APIRouter(tags=["realtime"])

# Close codes (4000-4999 is the application-defined range).
CLOSE_UNAUTHORIZED = 4001
CLOSE_IDLE = 4002
CLOSE_BAD_FRAME = 4003


async def _authenticate(token: str) -> User | None:
    """Validate the handshake token and load the user."""
    try:
        payload = decode_access_token(token)
    except AppError:
        return None

    async with get_sessionmaker()() as db:
        user = await db.get(User, payload["sub"])
        if user is None or not user.is_active or user.deleted_at is not None:
            return None
        session_id = payload.get("sid")
        if session_id:
            session_row = await db.get(Session, session_id)
            if session_row is None or not session_row.is_valid:
                return None
        # Detach so the object stays usable after the session closes.
        db.expunge_all()
        return user


async def _topics_for(user_id: str, *, workspace_id: str | None) -> tuple[list[str], list[str]]:
    """Return (topics, workspace_ids) this socket should follow."""
    async with get_sessionmaker()() as db:
        workspace_ids = list(
            (
                await db.scalars(
                    select(WorkspaceMember.workspace_id).where(
                        WorkspaceMember.user_id == user_id,
                        WorkspaceMember.is_active.is_(True),
                    )
                )
            ).all()
        )
        if workspace_id:
            # A client focused on one workspace only subscribes to that one, so
            # someone in ten workspaces does not pay for all ten.
            workspace_ids = [w for w in workspace_ids if w == workspace_id]

        channel_ids = list(
            (
                await db.scalars(
                    select(ChannelMember.channel_id)
                    .join(
                        WorkspaceMember,
                        WorkspaceMember.user_id == ChannelMember.user_id,
                    )
                    .where(
                        ChannelMember.user_id == user_id,
                        WorkspaceMember.workspace_id.in_(workspace_ids)
                        if workspace_ids
                        else WorkspaceMember.workspace_id.is_(None),
                    )
                    .distinct()
                )
            ).all()
        )

    topics = [user_topic(user_id)]
    topics += [workspace_topic(w) for w in workspace_ids]
    topics += [channel_topic(c) for c in channel_ids]
    return topics, workspace_ids


@router.websocket("/ws")
async def websocket_gateway(
    websocket: WebSocket,
    token: Annotated[str, Query(min_length=10, max_length=2048)],
    workspace_id: Annotated[str | None, Query(max_length=26)] = None,
) -> None:
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED, reason="unauthorized")
        return

    await websocket.accept()
    hub = get_hub()
    presence = get_presence_store()
    conn = Connection(websocket, user_id=user.id)

    topics, workspace_ids = await _topics_for(user.id, workspace_id=workspace_id)
    await hub.register(conn, topics)

    idle_timeout = settings.ws_heartbeat_seconds * 2.5

    # Everything after `register` lives inside this try: a tab closed between
    # the handshake and the hello frame used to raise out of `send_now` past
    # the `finally`, leaving the dead connection registered in the hub (and
    # the person "active" for as long as the process lived).
    try:
        await conn.send_now(
            {
                "type": ServerEvent.HELLO.value,
                "data": HelloData(
                    session_id=conn.id,
                    user_id=user.id,
                    workspace_ids=workspace_ids,
                    heartbeat_seconds=settings.ws_heartbeat_seconds,
                    server_time=datetime.now(UTC),
                ).model_dump(mode="json"),
            }
        )

        await presence.touch(user.id, PresenceState.ACTIVE)
        for wid in workspace_ids:
            await emit_to_workspace(
                wid,
                ServerEvent.PRESENCE_UPDATED,
                {"user_id": user.id, "presence": PresenceState.ACTIVE.value},
            )

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=idle_timeout)
            except TimeoutError:
                await conn.close(code=CLOSE_IDLE, reason="heartbeat timeout")
                break

            conn.last_seen_at = datetime.now(UTC)
            try:
                frame = orjson.loads(raw)
            except orjson.JSONDecodeError:
                conn.enqueue(
                    {
                        "type": ServerEvent.ERROR.value,
                        "data": {"code": "bad_frame", "message": "Frame is not valid JSON."},
                    }
                )
                continue

            await _handle_frame(conn, frame, user=user, hub=hub, presence=presence)

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws.loop_error", connection_id=conn.id, error=str(exc))
    finally:
        await hub.unregister(conn)
        # Only clear presence when this was the user's last socket on this node.
        if not hub.has_user(user.id):
            await presence.clear(user.id)
            for wid in workspace_ids:
                with contextlib.suppress(Exception):
                    await emit_to_workspace(
                        wid,
                        ServerEvent.PRESENCE_UPDATED,
                        {"user_id": user.id, "presence": PresenceState.OFFLINE.value},
                    )


async def _handle_frame(
    conn: Connection,
    frame: dict,
    *,
    user: User,
    hub,  # noqa: ANN001
    presence,  # noqa: ANN001
) -> None:
    command = frame.get("type")
    data = frame.get("data") or {}
    request_id = frame.get("id")

    if command == ClientCommand.PING.value:
        await presence.touch(user.id, PresenceState.ACTIVE)
        conn.enqueue({"type": ServerEvent.PONG.value, "id": request_id, "data": {}})
        return

    if command == ClientCommand.SUBSCRIBE.value:
        # Follow extra channels on navigation. Membership is verified before
        # subscribing so a client cannot listen to a channel it cannot read.
        channel_ids = [c for c in data.get("channel_ids", []) if isinstance(c, str)][:200]
        if channel_ids:
            allowed = await _verify_channel_membership(user.id, channel_ids)
            await hub.subscribe(conn, [channel_topic(c) for c in allowed])
            conn.enqueue(
                {
                    "type": "subscribed",
                    "id": request_id,
                    "data": {"channel_ids": allowed},
                }
            )
        return

    if command == ClientCommand.UNSUBSCRIBE.value:
        channel_ids = [c for c in data.get("channel_ids", []) if isinstance(c, str)][:200]
        await hub.unsubscribe(conn, [channel_topic(c) for c in channel_ids])
        return

    if command == ClientCommand.TYPING.value:
        channel_id = data.get("channel_id")
        if not isinstance(channel_id, str):
            return
        if not await _verify_channel_membership(user.id, [channel_id]):
            return
        await emit_to_channel(
            channel_id,
            ServerEvent.TYPING,
            {
                "channel_id": channel_id,
                "user_id": user.id,
                "parent_id": data.get("parent_id"),
            },
            exclude_connection=conn.id,
        )
        return

    if command == ClientCommand.PRESENCE.value:
        try:
            state = PresenceState(data.get("presence", PresenceState.ACTIVE.value))
        except ValueError:
            return
        await presence.touch(user.id, state)
        async with get_sessionmaker()() as db:
            workspace_ids = list(
                (
                    await db.scalars(
                        select(WorkspaceMember.workspace_id).where(
                            WorkspaceMember.user_id == user.id,
                            WorkspaceMember.is_active.is_(True),
                        )
                    )
                ).all()
            )
        for wid in workspace_ids:
            await emit_to_workspace(
                wid,
                ServerEvent.PRESENCE_UPDATED,
                {"user_id": user.id, "presence": state.value},
            )
        return

    if command == ClientCommand.MARK_READ.value:
        channel_id = data.get("channel_id")
        message_id = data.get("message_id")
        if not isinstance(channel_id, str):
            return
        async with get_sessionmaker()() as db:
            from app.services.channels import get_channel, get_channel_member, mark_read

            membership = await get_channel_member(db, channel_id=channel_id, user_id=user.id)
            if membership is None:
                return
            channel = await get_channel(db, channel_id)
            updated = await mark_read(
                db,
                membership=membership,
                message_id=message_id if isinstance(message_id, str) else None,
                channel=channel,
            )
            await db.commit()
            conn.enqueue(
                {
                    "type": ServerEvent.CHANNEL_READ.value,
                    "id": request_id,
                    "data": {
                        "channel_id": channel_id,
                        "last_read_message_id": updated.last_read_message_id,
                        "unread_count": updated.unread_count,
                        "mention_count": updated.mention_count,
                    },
                }
            )
        return

    conn.enqueue(
        {
            "type": ServerEvent.ERROR.value,
            "id": request_id,
            "data": {"code": "unknown_command", "message": f"Unknown command: {command!r}"},
        }
    )


async def _verify_channel_membership(user_id: str, channel_ids: list[str]) -> list[str]:
    async with get_sessionmaker()() as db:
        rows = await db.scalars(
            select(ChannelMember.channel_id).where(
                ChannelMember.user_id == user_id,
                ChannelMember.channel_id.in_(set(channel_ids)),
            )
        )
        return list(rows.all())
