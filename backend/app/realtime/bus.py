"""Cross-process event bus.

The WebSocket hub only knows about connections held by *this* process. With
more than one uvicorn worker (or more than one node), an event published by the
worker that handled `POST /messages` has to reach the workers holding the other
subscribers' sockets. That is what the bus is for.

Two implementations behind one interface:

* `RedisEventBus`   — Redis pub/sub. Use in production.
* `LocalEventBus`   — in-process only. Correct for a single worker, and keeps
                      development free of infrastructure.

`get_bus()` picks based on whether LLACK_REDIS_URL is set.
"""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

import orjson

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]

# Topic naming: everything a socket may care about is a topic.
#   ws:workspace:<id>   — workspace-wide events (channel created, app installed)
#   ws:channel:<id>     — channel traffic (messages, typing, reactions)
#   ws:user:<id>        — user-targeted events (their own read state, DMs)
def workspace_topic(workspace_id: str) -> str:
    return f"ws:workspace:{workspace_id}"


def channel_topic(channel_id: str) -> str:
    return f"ws:channel:{channel_id}"


def user_topic(user_id: str) -> str:
    return f"ws:user:{user_id}"


class EventBus(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    async def subscribe(self, topic: str, handler: Handler) -> None: ...

    @abstractmethod
    async def unsubscribe(self, topic: str, handler: Handler) -> None: ...

    async def publish_many(self, topics: list[str], payload: dict[str, Any]) -> None:
        seen: set[str] = set()
        for topic in topics:
            if topic in seen:
                continue
            seen.add(topic)
            await self.publish(topic, payload)


class LocalEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, set[Handler]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        log.info("event_bus.started", backend="local")

    async def stop(self) -> None:
        async with self._lock:
            self._handlers.clear()

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        handlers = list(self._handlers.get(topic, ()))
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(topic, payload) for h in handlers), return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                log.warning("event_bus.handler_failed", topic=topic, error=str(r))

    async def subscribe(self, topic: str, handler: Handler) -> None:
        async with self._lock:
            self._handlers.setdefault(topic, set()).add(handler)

    async def unsubscribe(self, topic: str, handler: Handler) -> None:
        async with self._lock:
            bucket = self._handlers.get(topic)
            if bucket is None:
                return
            bucket.discard(handler)
            if not bucket:
                self._handlers.pop(topic, None)


class RedisEventBus(EventBus):
    def __init__(self, url: str) -> None:
        self._url = url
        self._redis: Any = None
        self._pubsub: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._handlers: dict[str, set[Handler]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(self._url, decode_responses=False)
        await self._redis.ping()
        self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        self._reader = asyncio.create_task(self._read_loop(), name="event-bus-reader")
        log.info("event_bus.started", backend="redis")

    async def stop(self) -> None:
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
        async with self._lock:
            self._handlers.clear()

    async def _read_loop(self) -> None:
        assert self._pubsub is not None
        while True:
            try:
                message = await self._pubsub.get_message(timeout=1.0)
                if message is None:
                    continue
                topic = message["channel"]
                if isinstance(topic, bytes):
                    topic = topic.decode()
                payload = orjson.loads(message["data"])
                for handler in list(self._handlers.get(topic, ())):
                    try:
                        await handler(topic, payload)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("event_bus.handler_failed", topic=topic, error=str(exc))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("event_bus.read_loop_error", error=str(exc))
                await asyncio.sleep(1.0)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._redis is not None, "bus not started"
        await self._redis.publish(topic, orjson.dumps(payload))

    async def subscribe(self, topic: str, handler: Handler) -> None:
        async with self._lock:
            first = topic not in self._handlers
            self._handlers.setdefault(topic, set()).add(handler)
            if first and self._pubsub is not None:
                await self._pubsub.subscribe(topic)

    async def unsubscribe(self, topic: str, handler: Handler) -> None:
        async with self._lock:
            bucket = self._handlers.get(topic)
            if bucket is None:
                return
            bucket.discard(handler)
            if not bucket:
                self._handlers.pop(topic, None)
                if self._pubsub is not None:
                    with contextlib.suppress(Exception):
                        await self._pubsub.unsubscribe(topic)


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus(settings.redis_url) if settings.redis_url else LocalEventBus()
    return _bus


async def reset_bus() -> None:
    """Test helper: tear the bus down so the next get_bus() builds a fresh one."""
    global _bus
    if _bus is not None:
        await _bus.stop()
    _bus = None
