"""Monthly partitions for `messages` on Postgres.

A ULID starts with 48 bits of millisecond timestamp encoded as ten Crockford
base32 characters, so the primary key *is* a time key: `RANGE (id)` partitions
by month without adding a column, the primary key stays `(id)`, and every
foreign key that points at `messages.id` keeps working (a unique key on a
partitioned table must contain the partition key — `id` does).

What this buys: retention becomes `DROP TABLE messages_y2024m01` instead of a
million-row DELETE, autovacuum works per month, and the hot partition stays
small. What it costs: a unique constraint on `(channel_id, client_msg_id)` is
no longer possible, so idempotent sends live in `message_client_keys`.

Everything here is a no-op on SQLite — the development default — so nothing
in the request path branches on the dialect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.logging import get_logger

log = get_logger(__name__)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_PARTITION_RE = re.compile(r"^messages_y(\d{4})m(\d{2})$")
DEFAULT_PARTITION = "messages_default"


def ulid_lower_bound(moment: datetime) -> str:
    """The smallest ULID that can be minted at `moment`.

    Ten timestamp characters (most significant first) followed by sixteen
    zeros — the lowest random tail. Used as partition bounds, so a bound is
    exactly "every id minted from this instant on".
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    ms = int(moment.timestamp() * 1000)
    if ms < 0 or ms >= 1 << 48:
        raise ValueError("timestamp out of ULID range")
    out = []
    for _ in range(10):
        out.append(_CROCKFORD[ms & 0x1F])
        ms >>= 5
    return "".join(reversed(out)) + "0" * 16


def month_start(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(moment: datetime) -> datetime:
    start = month_start(moment)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def partition_name(moment: datetime) -> str:
    start = month_start(moment)
    return f"messages_y{start.year:04d}m{start.month:02d}"


def ulid_timestamp(ulid: str) -> datetime:
    """The mint time encoded in a ULID (first ten characters)."""
    value = 0
    for char in ulid[:10].upper():
        value = (value << 5) | _CROCKFORD.index(char)
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def months_between(first: datetime, last: datetime) -> list[datetime]:
    """Month starts from `first`'s month through `last`'s month, inclusive."""
    cursor = month_start(first)
    end = month_start(last)
    months: list[datetime] = []
    while cursor <= end:
        months.append(cursor)
        cursor = next_month(cursor)
    return months


@dataclass
class PartitionInfo:
    name: str
    from_id: str | None
    to_id: str | None
    rows: int
    bytes: int


async def is_partitioned(conn: AsyncConnection) -> bool:
    if conn.dialect.name != "postgresql":
        return False
    # `relkind` is a "char" column; asyncpg hands it back as bytes, so cast.
    row = await conn.execute(
        text(
            "SELECT relkind::text FROM pg_class WHERE relname = 'messages' "
            "AND relnamespace = 'public'::regnamespace"
        )
    )
    return row.scalar() == "p"


async def ensure_partition(conn: AsyncConnection, start: datetime) -> bool:
    """Create the partition for `start`'s month. Returns True if created.

    The plain `CREATE TABLE … PARTITION OF` fails when the DEFAULT partition
    already holds rows in the new range (they arrived before the partition
    existed — a worker that was down for a month). Postgres refuses rather
    than moving them, so the fallback builds the partition standalone, moves
    those rows across, and attaches it.
    """
    start = month_start(start)
    name = partition_name(start)
    low, high = ulid_lower_bound(start), ulid_lower_bound(next_month(start))
    exists = await conn.execute(
        text("SELECT 1 FROM pg_class WHERE relname = :name"), {"name": name}
    )
    if exists.scalar() is not None:
        return False
    try:
        async with conn.begin_nested():
            await conn.execute(
                text(
                    f"CREATE TABLE {name} PARTITION OF messages "
                    f"FOR VALUES FROM ('{low}') TO ('{high}')"
                )
            )
        return True
    except Exception as exc:  # noqa: BLE001 — Postgres: default partition has rows here
        log.info("partitions.default_has_rows", partition=name, error=str(exc)[:120])
    await conn.execute(
        text(f"CREATE TABLE {name} (LIKE messages INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")
    )
    await conn.execute(
        text(
            f"WITH moved AS (DELETE FROM {DEFAULT_PARTITION} "
            f"WHERE id >= '{low}' AND id < '{high}' RETURNING *) "
            f"INSERT INTO {name} SELECT * FROM moved"
        )
    )
    await conn.execute(
        text(
            f"ALTER TABLE messages ATTACH PARTITION {name} "
            f"FOR VALUES FROM ('{low}') TO ('{high}')"
        )
    )
    return True


async def ensure_partitions(
    conn: AsyncConnection, *, months_ahead: int = 2, now: datetime | None = None
) -> list[str]:
    """Make sure this month and the next `months_ahead` exist. Idempotent.

    Also backfills any month between the oldest message and now that is
    missing — a database restored from a dump, or one that ran without the
    worker, gets its rows out of the default partition.
    """
    if not await is_partitioned(conn):
        return []
    now = now or datetime.now(UTC)
    oldest = (await conn.execute(text("SELECT min(id) FROM messages"))).scalar()
    first = ulid_timestamp(oldest) if oldest else now
    last = now
    for _ in range(months_ahead):
        last = next_month(last)
    created: list[str] = []
    for start in months_between(first, last):
        if await ensure_partition(conn, start):
            created.append(partition_name(start))
    default = await conn.execute(
        text("SELECT 1 FROM pg_class WHERE relname = :name"), {"name": DEFAULT_PARTITION}
    )
    if default.scalar() is None:
        await conn.execute(text(f"CREATE TABLE {DEFAULT_PARTITION} PARTITION OF messages DEFAULT"))
        created.append(DEFAULT_PARTITION)
    if created:
        log.info("partitions.created", partitions=created)
    return created


async def list_partitions(conn: AsyncConnection) -> list[PartitionInfo]:
    if not await is_partitioned(conn):
        return []
    rows = await conn.execute(
        text(
            """
            SELECT c.relname AS name,
                   pg_get_expr(c.relpartbound, c.oid) AS bound,
                   GREATEST(c.reltuples, 0)::bigint AS rows,
                   pg_total_relation_size(c.oid) AS bytes
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            WHERE i.inhparent = 'messages'::regclass
            ORDER BY c.relname
            """
        )
    )
    out: list[PartitionInfo] = []
    for name, bound, count, size in rows.all():
        from_id = to_id = None
        match = re.search(r"FROM \('([^']+)'\) TO \('([^']+)'\)", bound or "")
        if match:
            from_id, to_id = match.group(1), match.group(2)
        out.append(
            PartitionInfo(
                name=name, from_id=from_id, to_id=to_id, rows=int(count), bytes=int(size)
            )
        )
    return out


async def ensure_partitions_session(db: AsyncSession) -> list[str]:
    """Session-flavoured entry point for the worker and lifespan."""
    conn = await db.connection()
    created = await ensure_partitions(conn)
    await db.commit()
    return created
