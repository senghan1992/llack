"""In-process token-bucket rate limiting.

The truth lives inside one process: with a single worker (the dev stack, and
any small deployment) the limits hold exactly; with N workers each worker keeps
its own buckets, so the effective limit relaxes to N× — still far better than
the nothing that was here before. The multi-node answer (a Redis token bucket,
ROADMAP priority 1) slots in behind this same function signature.

A bucket exists per (scope, key). Memory stays bounded by pruning buckets that
have not been touched for a long time — an untouched bucket has refilled to
capacity, and a full bucket is indistinguishable from an absent one, so
pruning loses no accuracy.
"""

from __future__ import annotations

import time

from app.core.errors import RateLimited

# Prune when the table grows past this; buckets idle longer than the horizon
# are full again for every limit this app configures (largest window is 1h).
_PRUNE_THRESHOLD = 10_000
_PRUNE_IDLE_SECONDS = 3_600.0


class _Bucket:
    __slots__ = ("tokens", "updated_at")

    def __init__(self, tokens: float, updated_at: float) -> None:
        self.tokens = tokens
        self.updated_at = updated_at


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def reset(self) -> None:
        """Forget everything. For tests."""
        self._buckets.clear()

    def check(self, scope: str, key: str | None, *, capacity: int, per_seconds: float) -> None:
        """Take one token, raising :class:`RateLimited` when there is none.

        ``capacity <= 0`` disables the limit (the settings' off switch). A
        ``None`` key — no client address to blame — shares one bucket per
        scope rather than being waved through: an anonymous flood is still a
        flood.
        """
        if capacity <= 0:
            return
        now = time.monotonic()
        refill_per_second = capacity / per_seconds
        bucket_key = (scope, key or "-")

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
