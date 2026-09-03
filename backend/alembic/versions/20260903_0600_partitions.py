"""messages: monthly ULID-range partitions (Postgres) + message_client_keys

Revision ID: d44ce0000004
Revises: c33ce0000003

Two things, in this order because the second depends on the first:

1. `message_client_keys` — the idempotency key for sends, moved out of the
   `messages` unique constraint. A unique constraint on a partitioned table
   must include the partition key, so `(channel_id, client_msg_id)` cannot
   stay on `messages`. Every dialect gets this table and loses the constraint.

2. Postgres only: rebuild `messages` as `PARTITION BY RANGE (id)`. ULIDs are
   time-ordered, so the primary key doubles as the partition key: the PK stays
   `(id)` and every foreign key pointing at `messages.id` keeps working. Rows
   are copied into monthly partitions covering the existing data plus two
   months of headroom, with a DEFAULT partition as the safety net. Foreign keys
   and indexes are re-created from the catalog so nothing is hand-listed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "d44ce0000004"
down_revision: str | None = "c33ce0000003"
branch_labels = None
depends_on = None

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid_lower_bound(moment: datetime) -> str:
    ms = int(moment.timestamp() * 1000)
    out = []
    for _ in range(10):
        out.append(_CROCKFORD[ms & 0x1F])
        ms >>= 5
    return "".join(reversed(out)) + "0" * 16


def _ulid_timestamp(ulid: str) -> datetime:
    value = 0
    for char in ulid[:10].upper():
        value = (value << 5) | _CROCKFORD.index(char)
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _month_start(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(moment: datetime) -> datetime:
    start = _month_start(moment)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_client_keys() -> None:
    op.create_table(
        "message_client_keys",
        sa.Column("channel_id", sa.String(26), nullable=False),
        sa.Column("client_msg_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(26), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("channel_id", "client_msg_id", name="pk_message_client_keys"),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            ondelete="CASCADE",
            name="fk_message_client_keys_channel_id_channels",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
            name="fk_message_client_keys_message_id_messages",
        ),
    )
    op.create_index("ix_message_client_keys_message_id", "message_client_keys", ["message_id"])
    op.execute(
        "INSERT INTO message_client_keys "
        "(channel_id, client_msg_id, message_id, created_at, updated_at) "
        "SELECT channel_id, client_msg_id, id, created_at, created_at FROM messages "
        "WHERE client_msg_id IS NOT NULL"
    )


def _partition_messages() -> None:
    bind = op.get_bind()

    # Catalog snapshots before anything moves: foreign keys pointing at
    # messages, foreign keys on messages, and every non-PK index on messages.
    fks_in = bind.execute(
        sa.text(
            "SELECT conname, conrelid::regclass::text AS rel, pg_get_constraintdef(oid) AS def "
            "FROM pg_constraint WHERE contype = 'f' AND confrelid = 'messages'::regclass "
            "AND conparentid = 0 "  # not the per-partition clones Postgres derives
            "AND conrelid <> 'messages'::regclass "  # the self-reference is in fks_out
            "AND conrelid NOT IN (SELECT inhrelid FROM pg_inherits "
            "WHERE inhparent = 'messages'::regclass)"  # partitions inherit it
        )
    ).all()
    fks_out = bind.execute(
        sa.text(
            "SELECT conname, pg_get_constraintdef(oid) AS def "
            "FROM pg_constraint WHERE contype = 'f' AND conrelid = 'messages'::regclass "
            "AND conparentid = 0"  # a FK to a partitioned table has one clone per partition
        )
    ).all()
    pk_name = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE contype = 'p' "
            "AND conrelid = 'messages'::regclass"
        )
    ).scalar()
    indexes = bind.execute(
        sa.text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'messages' AND indexname <> :pk"
        ),
        {"pk": pk_name},
    ).all()
    uniques = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE contype = 'u' "
            "AND conrelid = 'messages'::regclass"
        )
    ).all()
    unique_names = {row[0] for row in uniques}
    # A unique constraint's index cannot be dropped on its own, and a unique
    # key on a partitioned table would have to include `id` — so the
    # (channel_id, client_msg_id) constraint goes for good; see
    # message_client_keys.
    indexes = [(name, definition) for name, definition in indexes if name not in unique_names]
    oldest = bind.execute(sa.text("SELECT min(id) FROM messages")).scalar()
    total = bind.execute(sa.text("SELECT count(*) FROM messages")).scalar()

    # Detach the old table: every constraint and index goes with it under a
    # name that will not collide with the new table's.
    for conname, rel, _ in fks_in:
        op.execute(f'ALTER TABLE {rel} DROP CONSTRAINT "{conname}"')
    for conname, _ in fks_out:
        op.execute(f'ALTER TABLE messages DROP CONSTRAINT "{conname}"')
    for conname in unique_names:
        op.execute(f'ALTER TABLE messages DROP CONSTRAINT "{conname}"')
    for indexname, _ in indexes:
        op.execute(f'DROP INDEX IF EXISTS "{indexname}"')
    op.execute(f'ALTER TABLE messages RENAME CONSTRAINT "{pk_name}" TO "{pk_name}_old"')
    op.execute("ALTER TABLE messages RENAME TO messages_old")

    op.execute(
        "CREATE TABLE messages (LIKE messages_old INCLUDING DEFAULTS, "
        f'CONSTRAINT "{pk_name}" PRIMARY KEY (id)) PARTITION BY RANGE (id)'
    )

    now = datetime.now(UTC)
    first = _ulid_timestamp(oldest) if oldest else now
    last = _next_month(_next_month(now))
    cursor = _month_start(first)
    while cursor <= _month_start(last):
        low, high = _ulid_lower_bound(cursor), _ulid_lower_bound(_next_month(cursor))
        op.execute(
            f"CREATE TABLE messages_y{cursor.year:04d}m{cursor.month:02d} PARTITION OF messages "
            f"FOR VALUES FROM ('{low}') TO ('{high}')"
        )
        cursor = _next_month(cursor)
    op.execute("CREATE TABLE messages_default PARTITION OF messages DEFAULT")

    op.execute("INSERT INTO messages SELECT * FROM messages_old")
    copied = bind.execute(sa.text("SELECT count(*) FROM messages")).scalar()
    if copied != total:
        raise RuntimeError(f"partition copy lost rows: {copied} != {total}")

    for conname, definition in fks_out:
        # A self-reference (parent_id) was captured as REFERENCES messages(id)
        # before the rename, so the definition already names the new table.
        op.execute(f'ALTER TABLE messages ADD CONSTRAINT "{conname}" {definition}')
    for _indexname, indexdef in indexes:
        # Captured before the rename, so each definition already targets
        # `public.messages`; on a partitioned parent it cascades to partitions.
        op.execute(indexdef)
    op.execute("DROP TABLE messages_old")
    for conname, rel, definition in fks_in:
        op.execute(f'ALTER TABLE {rel} ADD CONSTRAINT "{conname}" {definition}')


def upgrade() -> None:
    if _is_postgres():
        # The old unique constraint vanishes with messages_old; the rebuilt
        # table never had it.
        _partition_messages()
    else:
        with op.batch_alter_table("messages") as batch:
            batch.drop_constraint("uq_messages_channel_id_client_msg_id", type_="unique")
    _create_client_keys()


def _unpartition_messages() -> None:
    bind = op.get_bind()
    fks_in = bind.execute(
        sa.text(
            "SELECT conname, conrelid::regclass::text AS rel, pg_get_constraintdef(oid) AS def "
            "FROM pg_constraint WHERE contype = 'f' AND confrelid = 'messages'::regclass "
            "AND conparentid = 0 "  # not the per-partition clones Postgres derives
            "AND conrelid <> 'messages'::regclass "  # the self-reference is in fks_out
            "AND conrelid NOT IN (SELECT inhrelid FROM pg_inherits "
            "WHERE inhparent = 'messages'::regclass)"  # partitions inherit it
        )
    ).all()
    fks_out = bind.execute(
        sa.text(
            "SELECT conname, pg_get_constraintdef(oid) AS def "
            "FROM pg_constraint WHERE contype = 'f' AND conrelid = 'messages'::regclass "
            "AND conparentid = 0"  # a FK to a partitioned table has one clone per partition
        )
    ).all()
    pk_name = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE contype = 'p' "
            "AND conrelid = 'messages'::regclass"
        )
    ).scalar()
    indexes = bind.execute(
        sa.text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'messages' AND indexname <> :pk"
        ),
        {"pk": pk_name},
    ).all()
    for conname, rel, _ in fks_in:
        op.execute(f'ALTER TABLE {rel} DROP CONSTRAINT "{conname}"')
    for conname, _ in fks_out:
        op.execute(f'ALTER TABLE messages DROP CONSTRAINT "{conname}"')
    for indexname, _ in indexes:
        op.execute(f'DROP INDEX IF EXISTS "{indexname}"')
    op.execute(f'ALTER TABLE messages RENAME CONSTRAINT "{pk_name}" TO "{pk_name}_part"')
    op.execute("ALTER TABLE messages RENAME TO messages_part")
    op.execute(
        "CREATE TABLE messages (LIKE messages_part INCLUDING DEFAULTS, "
        f'CONSTRAINT "{pk_name}" PRIMARY KEY (id))'
    )
    op.execute("INSERT INTO messages SELECT * FROM messages_part")
    for conname, definition in fks_out:
        op.execute(f'ALTER TABLE messages ADD CONSTRAINT "{conname}" {definition}')
    for _indexname, indexdef in indexes:
        op.execute(indexdef)
    op.execute("DROP TABLE messages_part")  # drops its partitions too
    for conname, rel, definition in fks_in:
        op.execute(f'ALTER TABLE {rel} ADD CONSTRAINT "{conname}" {definition}')
    op.create_unique_constraint(
        "uq_messages_channel_id_client_msg_id", "messages", ["channel_id", "client_msg_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_message_client_keys_message_id", table_name="message_client_keys")
    op.drop_table("message_client_keys")
    if _is_postgres():
        _unpartition_messages()
    else:
        with op.batch_alter_table("messages") as batch:
            batch.create_unique_constraint(
                "uq_messages_channel_id_client_msg_id", ["channel_id", "client_msg_id"]
            )
