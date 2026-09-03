"""Token-bucket rate limiting — in one process, or shared through Redis.

Two backends behind one `limiter.check(...)`:

* **In-process** (no `LLACK_REDIS_URL`): a dict of buckets. Exact for a single
  worker; with N workers each keeps its own buckets, so the effective limit
  relaxes to N×. That was the whole story before this file grew a second
  half, and it is still the right story for the single-node dev stack.
* **Redis** (when configured): the same bucket, kept as a hash in Redis and
  updated by one Lua script, so every worker on every node draws from the
  same allowance. If Redis is down the check falls back to the in-process
  bucket and warns once — a limiter that fails closed would turn a Redis
  outage into "nobody can log in", which is worse than a temporarily relaxed
  limit.

Memory in the in-process table stays bounded by pruning buckets idle longer
than the largest window: an untouched bucket has refilled to capacity, and a
full bucket is indistinguishable from an absent one, so pruning loses nothing.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.errors import RateLimited
from app.core.logging import get_logger

log = get_logger(__name__)

_PRUNE_THRESHOLD = 10_000
_PRUNE_IDLE_SECONDS = 3_600.0

# One round trip, atomic: refill by elapsed time, take a token if there is
# one, report how long until the next. Keys expire after a full refill, so
# Redis never accumulates buckets for clients that stopped calling.
#
#   KEYS[1] = bucket key
#   ARGV    = capacity, per_seconds, now_ms
# Returns {allowed(0|1), retry_after_ms}
_LUA = """
local capacity = tonumber(ARGV[1])
local per_ms = tonumber(ARGV[2]) * 1000
local now = tonumber(ARGV[3])
local refill_per_ms = capacity / per_ms

local data = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(data[1])
local updated = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  updated = now
end
local elapsed = math.max(0, now - updated)
tokens = math.min(capacity, tokens + elapsed * refill_per_ms)

local allowed = 0
local retry_ms = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_ms = math.ceil((1 - tokens) / refill_per_ms)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(per_ms) + 1000)
return {allowed, retry_ms}
"""


class _Bucket:
    __slots__ = ("tokens", "updated_at")

    def __init__(self, tokens: float, updated_at: float) -> None:
        self.tokens = tokens
        self.updated_at = updated_at


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._redis: Any = None
        self._script: Any = None
        self._redis_failed_logged = False

    # ── wiring ──────────────────────────────────────────────────────────

    def use_redis(self, client: Any) -> None:
        """Attach a (sync or fake) redis client. Called at startup when
        `LLACK_REDIS_URL` is set; tests attach a fake."""
        self._redis = client
        self._script = client.register_script(_LUA)
        self._redis_failed_logged = False

    def reset(self) -> None:
        """Forget everything. For tests."""
        self._buckets.clear()
        self._redis = None
        self._script = None
        self._redis_failed_logged = False

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "in-process"

    # ── the check ───────────────────────────────────────────────────────

    def check(self, scope: str, key: str | None, *, capacity: int, per_seconds: float) -> None:
        """Take one token, raising :class:`RateLimited` when there is none.

        ``capacity <= 0`` disables the limit (the settings' off switch). A
        ``None`` key — no client address to blame — shares one bucket per
        scope rather than being waved through: an anonymous flood is still a
        flood.
        """
        if capacity <= 0:
            return
        bucket_key = (scope, key or "-")

        if self._redis is not None:
            verdict = self._check_redis(bucket_key, capacity, per_seconds)
            if verdict is not None:
                allowed, retry_ms = verdict
                if not allowed:
                    raise RateLimited(details={"retry_after_seconds": round(retry_ms / 1000, 1)})
                return
            # Redis unreachable: fall through to the local bucket.

        self._check_local(bucket_key, capacity, per_seconds)

    def _check_redis(
        self, bucket_key: tuple[str, str], capacity: int, per_seconds: float
    ) -> tuple[bool, int] | None:
        redis_key = f"llack:ratelimit:{bucket_key[0]}:{bucket_key[1]}"
        try:
            allowed, retry_ms = self._script(
                keys=[redis_key], args=[capacity, per_seconds, int(time.time() * 1000)]
            )
        except Exception as exc:  # noqa: BLE001 — any Redis failure degrades, never blocks
            if not self._redis_failed_logged:
                self._redis_failed_logged = True
                log.warning("ratelimit.redis_unavailable", error=str(exc), fallback="in-process")
            return None
        if self._redis_failed_logged:
            self._redis_failed_logged = False
            log.info("ratelimit.redis_recovered")
        return bool(int(allowed)), int(retry_ms)

    def _check_local(
        self, bucket_key: tuple[str, str], capacity: int, per_seconds: float
    ) -> None:
        now = time.monotonic()
        refill_per_second = capacity / per_seconds

        bucket = self._buckets.get(bucket_key)
        if bucket is None:
            if len(self._buckets) >= _PRUNE_THRESHOLD:
                self._prune(now)
            bucket = _Bucket(tokens=float(capacity), updated_at=now)
            self._buckets[bucket_key] = bucket
        else:
            elapsed = now - bucket.updated_at
            bucket.tokens = min(float(capacity), bucket.tokens + elapsed * refill_per_second)
            bucket.updated_at = now

        if bucket.tokens < 1.0:
            retry_after = (1.0 - bucket.tokens) / refill_per_second
            raise RateLimited(details={"retry_after_seconds": round(retry_after, 1)})
        bucket.tokens -= 1.0

    def _prune(self, now: float) -> None:
        stale = [k for k, b in self._buckets.items() if now - b.updated_at > _PRUNE_IDLE_SECONDS]
        for key in stale:
            del self._buckets[key]


limiter = RateLimiter()


def configure_from_settings() -> None:
    """Attach Redis when the deployment has one. Called from the lifespan."""
    if not settings.redis_url:
        return
    import redis

    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=0.25,
        socket_connect_timeout=0.25,
    )
    limiter.use_redis(client)
    log.info("ratelimit.configured", backend="redis")
