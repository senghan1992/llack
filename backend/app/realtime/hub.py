"""The WebSocket connection registry.

The hub keeps every open socket in memory, grouped by user id, and fans
out server events to the users that are allowed to see them.  Deciding *who*
may see an event is the caller's job (the services compute the recipient set
from the database); the hub only routes.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("llack.realtime")


@dataclass(eq=False)
class Connection:
    user_id: str
    websocket: WebSocket
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Hub:
    def __init__(self) -> None:
        self._connections: dict[str, set[Connection]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def register(self, user_id: str, websocket: WebSocket) -> Connection:
        connection = Connection(user_id=user_id, websocket=websocket)
        async with self._lock:
            self._connections[user_id].add(connection)
        return connection

    async def unregister(self, connection: Connection) -> None:
        async with self._lock:
            sockets = self._connections.get(connection.user_id)
            if sockets is None:
                return
            sockets.discard(connection)
            if not sockets:
                self._connections.pop(connection.user_id, None)

    def socket_count(self, user_id: str) -> int:
        return len(self._connections.get(user_id, ()))

    def is_online(self, user_id: str) -> bool:
        return self.socket_count(user_id) > 0

    def online_user_ids(self) -> set[str]:
        return {user_id for user_id, sockets in self._connections.items() if sockets}

    async def send(self, connection: Connection, payload: dict[str, Any]) -> bool:
        """Send one payload to one socket.  Returns ``False`` when the socket died."""
        try:
            async with connection.lock:
                await connection.websocket.send_json(payload)
        except Exception:
            logger.debug("dropping dead socket for user %s", connection.user_id, exc_info=True)
            return False
        return True

    async def send_to_user(self, user_id: str, payload: dict[str, Any]) -> None:
        for connection in list(self._connections.get(user_id, ())):
            await self.send(connection, payload)

    async def send_to_users(self, user_ids: set[str], payload: dict[str, Any]) -> None:
        for user_id in user_ids:
            await self.send_to_user(user_id, payload)


hub = Hub()
