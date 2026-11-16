"""요청의 속도를 재는 자리.

비밀번호를 Thousands of 번 맞혀 보거나, 메시지를 잔뜩 보내거나, 검색을
끌없이 돌리는 것을 막습니다.

진실은 프로세스 안에 있습니다. 이 프로젝트는 인스턴스당 프로세스 하나가
정답입니다(실시간 허브가 프로세스 안에 있습니다), 그래서 여기서 센 한도도
그대로 지킵니다.

사용하는 법은 두 가지입니다.

    limiter.check("login", key, capacity=10, per_seconds=60)

    # 엔드포인트에 붙이는 법 — app/api/deps.py 의 두 도우미를 씁니다.
    Depends(limit_by_ip("login"))

한도(몇 번까지)는 `RATE_LIMIT_*` 환경변수로, 켜고 끄는 것은
`RATE_LIMIT_ENABLED` 로 정합니다 — 사내망에서 주소를 공유할 때는 값을
키우면 됩니다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.errors import rate_limited

# 아무도 건드리지 않은 지 오래된 버킷은 다시 가득 차 있습니다 — 차 있는
# 버킷과 없는 버킷은 같으므로 지워도 정확도가 흔들리지 않습니다.
_PRUNE_AFTER_SECONDS = 3_600.0
_PRUNE_THRESHOLD = 10_000

# 각 동작의 창(period) — 초. 몇 번까지는 `RATE_LIMIT_*` 설정이 정합니다.
POLICY_PERIODS: dict[str, float] = {
    "signup": 3_600.0,
    "login": 60.0,
    "login-account": 60.0,
    "refresh": 60.0,
    "message": 60.0,
    "upload": 60.0,
    "search": 60.0,
}


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """토큰 통 — 한 창에 정해진 수만큼만 통과시킵니다."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def reset(self) -> None:
        """모든 기억을 지웁니다 (테스트용)."""
        self._buckets.clear()

    def check(self, scope: str, key: str | None, *, capacity: int, per_seconds: float) -> None:
        """토큰 하나를 꺼냅니다. 없으면 :func:`rate_limited` 를 던집니다.

        ``capacity <= 0`` 이면 제한을 끕니다. 주소를 알 수 없는 요청(``key``
        가 ``None``)은 같은 칸(scope)을 함께 씁니다 — 주소를 모르는 요청도
        여전히 요청입니다.
        """
        if capacity <= 0:
            return

        bucket_key = (scope, key or "-")
        now = time.monotonic()
        bucket = self._buckets.get(bucket_key)
        if bucket is None:
            bucket = _Bucket(tokens=float(capacity), updated_at=now)
            self._buckets[bucket_key] = bucket

        refill = capacity / per_seconds
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(float(capacity), bucket.tokens + elapsed * refill)
        bucket.updated_at = now

        if bucket.tokens < 1.0:
            wait = (1.0 - bucket.tokens) / refill
            raise rate_limited(f"너무 자주 요청했습니다. {int(wait) + 1}초 뒤에 다시 시도하세요.")
        bucket.tokens -= 1.0

        self._prune(now)

    def _prune(self, now: float) -> None:
        if len(self._buckets) < _PRUNE_THRESHOLD:
            return
        stale = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.updated_at > _PRUNE_AFTER_SECONDS
        ]
        for key in stale:
            self._buckets.pop(key, None)


limiter = RateLimiter()
