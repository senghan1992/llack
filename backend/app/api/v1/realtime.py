"""The WebSocket endpoint that powers live updates."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.security import authenticate_query_token
from app.models.base import utcnow
from app.models.channel import Channel
from app.models.user import PRESENCE_CLAIMED, User
from app.realtime import events
from app.realtime.hub import Connection, hub
from app.schemas.user import UserOut
from app.services.members import require_channel_access
from app.services.messages import mark_read, unread_counts

logger = logging.getLogger("llack.realtime")

router = APIRouter(tags=["realtime"])

AUTH_FAILED = 4401


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    async with SessionLocal() as session:
        user = await authenticate_query_token(session, token)

    if user is None:
        await websocket.accept()
        await websocket.close(code=AUTH_FAILED)
        return

    await websocket.accept()
    connection = await hub.register(user.id, websocket)

    async with SessionLocal() as session:
        row = await session.get(User, user.id)
        if row is not None:
            # A status a person chose for themselves survives the socket — only
            # the plain "online" state is the app's to give and take back.
            if row.presence not in PRESENCE_CLAIMED:
                row.presence = "online"
            row.last_seen_at = utcnow()
            await session.commit()
            await events.emit_presence(session, row, row.presence)
            current = row
        else:
            current = user

    # The greeting carries the state the person is really in, so the client
    # does not have to guess whether it is "online" or still "busy".
    await hub.send(
        connection,
        {
            "type": "hello",
            "user": UserOut.model_validate(current).model_dump(mode="json"),
        },
    )

    try:
        while True:
            payload = await websocket.receive_json()
            await _handle_client_event(websocket, connection, payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("websocket loop ended", exc_info=True)
    finally:
        await hub.unregister(connection)
        if hub.socket_count(user.id) == 0:
            async with SessionLocal() as session:
                row = await session.get(User, user.id)
                if row is not None:
                    row.presence = "offline"
                    row.last_seen_at = utcnow()
                    await session.commit()
                    await events.emit_presence(session, row, "offline")


async def _handle_client_event(websocket: WebSocket, connection: Connection, payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    event_type = payload.get("type")

    if event_type == "ping":
        await hub.send(connection, {"type": "pong"})
        return

    if event_type == "typing":
        await _handle_typing(connection, payload)
        return

    if event_type == "read":
        await _handle_read(connection, payload)
        return


async def _handle_typing(connection: Connection, payload: dict) -> None:
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str):
        return
    on = bool(payload.get("on", True))

    async with SessionLocal() as session:
        user = await session.get(User, connection.user_id)
        channel = await session.get(Channel, channel_id)
        if user is None or channel is None:
            return
        try:
            await require_channel_access(session, channel, user.id)
        except AppError:
            return
        await events.emit_typing(session, channel, user, on)


async def _handle_read(connection: Connection, payload: dict) -> None:
    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if not isinstance(channel_id, str):
        return
    if message_id is not None and not isinstance(message_id, str):
        return

    async with SessionLocal() as session:
        user = await session.get(User, connection.user_id)
        channel = await session.get(Channel, channel_id)
        if user is None or channel is None:
            return
        try:
            await require_channel_access(session, channel, user.id)
        except AppError:
            return
        try:
            await mark_read(session, channel, user.id, message_id)
        except AppError:
            return
        await session.commit()
        counts = await unread_counts(session, [channel.id], user.id)
        await hub.send_to_user(
            user.id,
            {
                "type": "unread",
                "channel_id": channel.id,
                "count": counts.get(channel.id, 0),
            },
        )
