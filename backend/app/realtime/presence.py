"""Presence tracking.

Presence is ephemeral and high-churn, so it lives in Redis with a TTL when
Redis is configured, and in a plain dict otherwise. Either way the durable
`users.presence` column is only refreshed on transitions, not on heartbeats.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.enums import PresenceState

_PREFIX = "presence:"


class PresenceStore:
    def __init__(self) -> None:
        self._redis: Any = None
        # user_id -> (state, expires_at, touched_at); all monotonic seconds.
        self._local: dict[str, tuple[str, float, float]] = {}

    async def start(self) -> None:
        if settings.redis_url:
            import redis.asyncio as redis

            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()

    async def stop(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._local.clear()

    async def touch(self, user_id: str, state: PresenceState = PresenceState.ACTIVE) -> None:
        ttl = settings.presence_ttl_seconds
        if self._redis is not None:
            await self._redis.set(f"{_PREFIX}{user_id}", state.value, ex=ttl)
            return
        now = time.monotonic()
        self._local[user_id] = (state.value, now + ttl, now)

    async def clear(self, user_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(f"{_PREFIX}{user_id}")
            return
        self._local.pop(user_id, None)

    async def get(self, user_id: str) -> PresenceState:
        if self._redis is not None:
            value = await self._redis.get(f"{_PREFIX}{user_id}")
            return PresenceState(value) if value else PresenceState.OFFLINE
        entry = self._local.get(user_id)
        if entry is None or entry[1] < time.monotonic():
            self._local.pop(user_id, None)
            return PresenceState.OFFLINE
        return PresenceState(entry[0])

    async def stale_users(self, *, max_age_seconds: float) -> list[str]:
        """Users whose last heartbeat is older than `max_age_seconds`.

        Only meaningful for the in-process store; Redis keys carry their own
        TTL and simply vanish, so there is nothing to clean there.
        """
        if self._redis is not None:
            return []
        cutoff = time.monotonic() - max_age_seconds
        return [uid for uid, (_state, _exp, touched) in self._local.items() if touched < cutoff]

    async def get_many(self, user_ids: list[str]) -> dict[str, PresenceState]:
        if not user_ids:
            return {}
        if self._redis is not None:
            values = await self._redis.mget([f"{_PREFIX}{uid}" for uid in user_ids])
            return {
                uid: PresenceState(v) if v else PresenceState.OFFLINE
                for uid, v in zip(user_ids, values, strict=True)
            }
        return {uid: await self.get(uid) for uid in user_ids}


_store: PresenceStore | None = None


def get_presence_store() -> PresenceStore:
    global _store
    if _store is None:
        _store = PresenceStore()
    return _store


async def reset_presence_store() -> None:
    global _store
    if _store is not None:
        await _store.stop()
    _store = None
