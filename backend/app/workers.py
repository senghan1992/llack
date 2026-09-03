"""Background workers: the jobs that keep the data honest over time.

Each worker is a coroutine run every `interval` seconds inside the API
process (no separate scheduler to deploy). Registration is open — other
modules call `register(...)` at import time — so retention, unread recounts,
presence cleanup, reminders (B) and webhook retries (C) all share one loop,
one leader lock and one metric.

Leadership: with Redis configured, a job runs only where `SET NX PX` on
`llack:worker:{name}` succeeds, so a four-node deployment sweeps retention
once, not four times. Without Redis there is one node by definition.

Every iteration is isolated: an exception is logged and counted, and the
next tick runs on schedule. A worker that dies silently is worse than one
that never existed, so failures are loud in both logs and metrics.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import workers_runs_total

log = get_logger(__name__)

Job = Callable[[], Awaitable[None]]


@dataclass
class Worker:
    name: str
    interval_seconds: float
    job: Job
    last_run_at: datetime | None = None
    last_error: str | None = None
    runs: int = 0
    task: asyncio.Task | None = field(default=None, repr=False)


_workers: dict[str, Worker] = {}
_redis = None


def register(name: str, interval_seconds: float, job: Job) -> Worker:
    """Add (or replace) a worker. Safe to call at import time."""
    worker = Worker(name=name, interval_seconds=interval_seconds, job=job)
    _workers[name] = worker
    return worker


def registered() -> dict[str, Worker]:
    return dict(_workers)


async def _acquire_lease(name: str, interval_seconds: float) -> bool:
    """True if this node should run the job now."""
    if _redis is None:
        return True
    try:
        ttl_ms = max(1000, int(interval_seconds * 1000 * 0.9))
        return bool(await _redis.set(f"llack:worker:{name}", "1", nx=True, px=ttl_ms))
    except Exception as exc:  # noqa: BLE001
        log.warning("workers.lease_failed", worker=name, error=str(exc))
        return True


async def run_once(name: str, *, force: bool = True) -> bool:
    """Run one iteration now. Returns True if the job ran."""
    worker = _workers[name]
    if not force and not await _acquire_lease(name, worker.interval_seconds):
        return False
    try:
        await worker.job()
    except Exception as exc:  # noqa: BLE001
        worker.last_error = str(exc)
        workers_runs_total.labels(name, "error").inc()
        log.exception("workers.run_failed", worker=name)
        return True
    worker.last_error = None
    worker.runs += 1
    worker.last_run_at = datetime.now(UTC)
    workers_runs_total.labels(name, "ok").inc()
    return True


async def _loop(worker: Worker) -> None:
    # Stagger the first run so a fleet restart does not fire every job at once.
    await asyncio.sleep(min(worker.interval_seconds, 5.0))
    while True:
        await run_once(worker.name, force=False)
        await asyncio.sleep(worker.interval_seconds)


async def start() -> None:
    global _redis
    if not settings.run_workers:
        log.info("workers.disabled")
        return
    if settings.redis_url:
        import redis.asyncio as redis

        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    for worker in _workers.values():
        if worker.task is None or worker.task.done():
            worker.task = asyncio.create_task(_loop(worker), name=f"worker:{worker.name}")
    log.info("workers.started", workers=sorted(_workers))


async def stop() -> None:
    global _redis
    for worker in _workers.values():
        if worker.task is not None:
            worker.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker.task
            worker.task = None
    if _redis is not None:
        with contextlib.suppress(Exception):
            await _redis.aclose()
        _redis = None


# ── Built-in jobs ───────────────────────────────────────────────────────────


async def _unread_recompute() -> None:
    """Recount unread/mention counters from the messages table.

    The live counters are incremented per message; a crashed request or a
    retention sweep can leave them drifting. Recounting everything every six
    hours in batches keeps "3 unread" meaning three messages.
    """
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.models.channel import ChannelMember
    from app.services.channels import recompute_unread

    async with get_sessionmaker()() as db:
        offset = 0
        batch = 500
        while True:
            rows = (
                await db.scalars(
                    select(ChannelMember).order_by(ChannelMember.id).offset(offset).limit(batch)
                )
            ).all()
            if not rows:
                break
            for membership in rows:
                await recompute_unread(db, membership=membership)
            await db.commit()
            offset += batch
            if len(rows) < batch:
                break


async def _retention_sweep() -> None:
    from app.core.db import get_sessionmaker
    from app.services.retention import sweep

    async with get_sessionmaker()() as db:
        await sweep(db)


async def _presence_cleanup() -> None:
    """Drop presence for people whose sockets are gone.

    The Redis store expires keys on its own (every touch sets a TTL). The
    in-process store also expires on read, but nobody *reads* a departed
    user's presence — so their dot stays green in every sidebar until someone
    happens to ask. This asks, on a schedule, and announces the change.
    """
    from app.core.enums import PresenceState
    from app.realtime.events import emit_to_workspace
    from app.realtime.hub import get_hub
    from app.realtime.presence import get_presence_store

    store = get_presence_store()
    hub = get_hub()
    stale = await store.stale_users(max_age_seconds=settings.ws_heartbeat_seconds * 3)
    for user_id in stale:
        if hub.has_user(user_id):
            continue
        await store.clear(user_id)
        from sqlalchemy import select

        from app.core.db import get_sessionmaker
        from app.models.workspace import WorkspaceMember

        async with get_sessionmaker()() as db:
            workspace_ids = (
                await db.scalars(
                    select(WorkspaceMember.workspace_id).where(
                        WorkspaceMember.user_id == user_id, WorkspaceMember.is_active.is_(True)
                    )
                )
            ).all()
        for wid in workspace_ids:
            await emit_to_workspace(
                wid,
                "presence.updated",
                {"user_id": user_id, "presence": PresenceState.OFFLINE.value},
            )


register("unread_recompute", 6 * 3600, _unread_recompute)
register("retention_sweep", 3600, _retention_sweep)
register("presence_cleanup", 60, _presence_cleanup)
