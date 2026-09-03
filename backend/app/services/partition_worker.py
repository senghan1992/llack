"""The `partition_maintenance` worker: tomorrow's partition exists today.

Registered at import (like reminders and webhook retries) so it shares the
worker loop, leader lock and metric. Daily is plenty — partitions are monthly
and the service keeps two months of headroom — and the lifespan runs it once
at boot so a server that was down over a month boundary catches up before
serving its first message.
"""

from __future__ import annotations

from app import workers
from app.core.config import settings
from app.core.db import get_sessionmaker
from app.core.logging import get_logger
from app.services import partitions

log = get_logger(__name__)


async def _partition_maintenance() -> None:
    if settings.is_sqlite:
        return
    async with get_sessionmaker()() as db:
        created = await partitions.ensure_partitions_session(db)
        if created:
            log.info("partitions.maintained", created=created)


async def ensure_partitions_on_startup() -> None:
    """Best effort at boot: a failure is logged, never fatal — the API can
    serve from the default partition until the next tick."""
    if settings.is_sqlite:
        return
    try:
        await _partition_maintenance()
    except Exception:  # noqa: BLE001
        log.exception("partitions.startup_failed")


workers.register("partition_maintenance", 24 * 60 * 60, _partition_maintenance)
