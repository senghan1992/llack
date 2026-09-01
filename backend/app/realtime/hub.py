"""Per-process WebSocket connection registry.

A `Connection` wraps one socket and owns a bounded outbound queue plus a writer
task. Backpressure policy: if a client is too slow to drain the queue we drop
the connection rather than buffer without limit — the client reconnects and
does a catch-up fetch, which is cheaper than an unbounded queue on the server.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import orjson
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.realtime.bus import EventBus, channel_topic, get_bus, user_topic, workspace_topic

log = get_logger(__name__)

OUTBOUND_QUEUE_SIZE = 512


class Connection:
    def __init__(self, websocket: WebSocket, *, user_id: str) -> None:
        self.id = new_ulid()
        self.websocket = websocket
        self.user_id = user_id
        self.topics: set[str] = set()
        self.seq = 0
        self.opened_at = datetime.now(UTC)
        self.last_seen_at = self.opened_at
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=OUTBOUND_QUEUE_SIZE)
        self._writer: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._writer = asyncio.create_task(self._write_loop(), name=f"ws-writer-{self.id}")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._writer:
            self._writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer
        if self.websocket.client_state is WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await self.websocket.close(code=code, reason=reason)

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    # ── sending ─────────────────────────────────────────────────────────

    async def _write_loop(self) -> None:
        try:
            while True:
                payload = await self._queue.get()
                if self.websocket.client_state is not WebSocketState.CONNECTED:
                    return
                await self.websocket.send_text(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.debug("ws.write_failed", connection_id=self.id, error=str(exc))
            self._closed.set()

    def enqueue(self, event: dict[str, Any]) -> bool:
        """Queue an event. Returns False if the client is too far behind."""
        if self._closed.is_set():
            return False
        self.seq += 1
        frame = {**event, "seq": self.seq}
        frame.setdefault("ts", datetime.now(UTC).isoformat())
        try:
            # Text frames, not binary: a browser/webview delivers a binary
            # frame as a Blob that has to be read asynchronously, while a text
            # frame arrives as a plain string.
            self._queue.put_nowait(orjson.dumps(frame).decode())
        except asyncio.QueueFull:
            log.warning("ws.slow_consumer", connection_id=self.id, user_id=self.user_id)
            self._closed.set()
            return False
        return True

    async def send_now(self, event: dict[str, Any]) -> None:
        """Bypass the queue — used for `hello` before the writer is running."""
        self.seq += 1
        frame = {**event, "seq": self.seq}
        frame.setdefault("ts", datetime.now(UTC).isoformat())
        await self.websocket.send_text(orjson.dumps(frame).decode())


class Hub:
    """Routes bus events to the sockets held by this process."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or get_bus()
        self._by_topic: dict[str, set[Connection]] = {}
        self._by_user: dict[str, set[Connection]] = {}
        self._connections: dict[str, Connection] = {}
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    # ── registration ────────────────────────────────────────────────────

    async def register(self, conn: Connection, topics: list[str]) -> None:
        async with self._lock:
            self._connections[conn.id] = conn
            self._by_user.setdefault(conn.user_id, set()).add(conn)
        await self.subscribe(conn, topics)
        conn.start()
        log.info(
            "ws.connected",
            connection_id=conn.id,
            user_id=conn.user_id,
            topics=len(topics),
            total=self.connection_count,
        )

    async def unregister(self, conn: Connection) -> None:
        topics = list(conn.topics)
        await self.unsubscribe(conn, topics)
        async with self._lock:
            self._connections.pop(conn.id, None)
            user_bucket = self._by_user.get(conn.user_id)
            if user_bucket is not None:
                user_bucket.discard(conn)
                if not user_bucket:
                    self._by_user.pop(conn.user_id, None)
        await conn.close()
        log.info("ws.disconnected", connection_id=conn.id, user_id=conn.user_id,
                 total=self.connection_count)

    def has_user(self, user_id: str) -> bool:
        return bool(self._by_user.get(user_id))

    # ── topic fan-out ───────────────────────────────────────────────────

    async def subscribe(self, conn: Connection, topics: list[str]) -> None:
        new_topics: list[str] = []
        async with self._lock:
            for topic in topics:
                if topic in conn.topics:
                    continue
                conn.topics.add(topic)
                bucket = self._by_topic.setdefault(topic, set())
                if not bucket:
                    new_topics.append(topic)
                bucket.add(conn)
        for topic in new_topics:
            await self._bus.subscribe(topic, self._on_bus_event)

    async def unsubscribe(self, conn: Connection, topics: list[str]) -> None:
        empty_topics: list[str] = []
        async with self._lock:
            for topic in topics:
                conn.topics.discard(topic)
                bucket = self._by_topic.get(topic)
                if bucket is None:
                    continue
                bucket.discard(conn)
                if not bucket:
                    self._by_topic.pop(topic, None)
                    empty_topics.append(topic)
        for topic in empty_topics:
            await self._bus.unsubscribe(topic, self._on_bus_event)

    async def _on_bus_event(self, topic: str, payload: dict[str, Any]) -> None:
        targets = list(self._by_topic.get(topic, ()))
        if not targets:
            return
        # An event can be excluded for the actor who caused it — the desktop
        # client already applied it optimistically.
        exclude_connection = payload.pop("_exclude_connection", None)
        exclude_user = payload.pop("_exclude_user", None)

        dead: list[Connection] = []
        for conn in targets:
            if conn.id == exclude_connection or conn.user_id == exclude_user:
                continue
            if not conn.enqueue(payload):
                dead.append(conn)
        for conn in dead:
            await self.unregister(conn)

    # ── convenience publishers ──────────────────────────────────────────

    async def publish_to_channel(self, channel_id: str, event: dict[str, Any]) -> None:
        await self._bus.publish(channel_topic(channel_id), event)

    async def publish_to_workspace(self, workspace_id: str, event: dict[str, Any]) -> None:
        await self._bus.publish(workspace_topic(workspace_id), event)

    async def publish_to_users(self, user_ids: list[str], event: dict[str, Any]) -> None:
        await self._bus.publish_many([user_topic(uid) for uid in user_ids], event)

    async def close_all(self) -> None:
        for conn in list(self._connections.values()):
            await self.unregister(conn)


_hub: Hub | None = None


def get_hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub


async def reset_hub() -> None:
    global _hub
    if _hub is not None:
        await _hub.close_all()
    _hub = None


def heartbeat_seconds() -> int:
    return settings.ws_heartbeat_seconds
