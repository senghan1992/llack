"""Message partitioning: ULID bound maths, the client-key idempotency table,
the admin view, and — on Postgres only — partition placement and maintenance."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.core.db import get_engine, get_sessionmaker
from app.core.ids import new_ulid
from app.models.message import MessageClientKey
from app.services import partitions
from tests.conftest import Actor, grant_service_admin
from tests.test_messages import _setup

PG = bool(os.environ.get("LLACK_TEST_DATABASE_URL"))
requires_pg = pytest.mark.skipif(not PG, reason="Postgres-only behaviour")


def test_ulid_lower_bound_is_the_timestamp_prefix_and_zero_tail() -> None:
    moment = datetime(2026, 9, 1, tzinfo=UTC)
    bound = partitions.ulid_lower_bound(moment)
    assert len(bound) == 26 and bound.endswith("0" * 16)
    # A ULID minted in that instant sorts at or after the bound, and one from
    # a millisecond earlier sorts before it — string order is time order.
    ms = int(moment.timestamp() * 1000)
    assert new_ulid(ms) >= bound
    assert new_ulid(ms - 1) < bound
    assert partitions.ulid_timestamp(bound) == moment


def test_partition_names_and_month_arithmetic() -> None:
    assert partitions.partition_name(datetime(2026, 12, 15, 3, tzinfo=UTC)) == "messages_y2026m12"
    assert partitions.next_month(datetime(2026, 12, 15, tzinfo=UTC)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )
    months = partitions.months_between(
        datetime(2026, 11, 20, tzinfo=UTC), datetime(2027, 2, 1, tzinfo=UTC)
    )
    assert [m.month for m in months] == [11, 12, 1, 2]


async def test_client_key_row_backs_idempotent_sends(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    client_msg_id = new_ulid()
    first = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "한 번만", "client_msg_id": client_msg_id},
    )
    retry = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "한 번만", "client_msg_id": client_msg_id},
    )
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]

    async with get_sessionmaker()() as db:
        keys = (await db.scalars(select(MessageClientKey))).all()
    assert [(k.client_msg_id, k.message_id) for k in keys] == [(client_msg_id, first.json()["id"])]

    # Same client id in another channel is a different send.
    other = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "다른 채널"}
        )
    ).json()
    elsewhere = await alice.post(
        f"/channels/{other['id']}/messages",
        json={"body": "다른 곳", "client_msg_id": client_msg_id},
    )
    assert elsewhere.status_code == 201 and elsewhere.json()["id"] != first.json()["id"]


async def test_admin_partitions_view(alice: Actor, workspace: dict) -> None:
    denied = await alice.get("/admin/partitions")
    # A workspace owner counts as a server admin (ServerAdmin dependency).
    assert denied.status_code == 200
    await grant_service_admin(alice)
    body = (await alice.get("/admin/partitions")).json()
    assert body["partitioned"] is PG
    assert body["dialect"] == ("postgresql" if PG else "sqlite")
    if PG:
        names = [p["name"] for p in body["partitions"]]
        assert "messages_default" in names
        assert any(name.startswith("messages_y") for name in names)


@requires_pg
async def test_rows_land_in_their_month(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    posted = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "지금"})
    ).json()
    engine = get_engine()
    async with engine.begin() as conn:
        # A message from 2024 has no partition (the chain covers min(id)..now+2
        # only when data existed); it must fall into the default partition,
        # and maintenance must then move it into a real one.
        old_id = new_ulid(int(datetime(2024, 3, 15, tzinfo=UTC).timestamp() * 1000))
        await conn.execute(
            text(
                "INSERT INTO messages (id, channel_id, user_id, kind, body, blocks, "
                "mentioned_user_ids, mentions_everyone, reply_count, reply_user_ids, "
                "also_sent_to_channel, edit_count, is_pinned, created_at, updated_at) "
                "VALUES (:id, :channel_id, :user_id, 'user', '옛날', NULL, '[]', false, 0, "
                "'[]', false, 0, false, now(), now())"
            ),
            {"id": old_id, "channel_id": channel["id"], "user_id": alice.id},
        )
        where = await conn.execute(
            text("SELECT id, tableoid::regclass::text FROM messages WHERE id IN (:a, :b)"),
            {"a": posted["id"], "b": old_id},
        )
        placement = dict(where.all())
        assert placement[posted["id"]] == partitions.partition_name(datetime.now(UTC))
        assert placement[old_id] == partitions.DEFAULT_PARTITION

        created = await partitions.ensure_partition(conn, datetime(2024, 3, 1, tzinfo=UTC))
        assert created is True
        moved = await conn.execute(
            text("SELECT tableoid::regclass::text FROM messages WHERE id = :id"), {"id": old_id}
        )
        assert moved.scalar() == "messages_y2024m03"
        # Idempotent: a second call creates nothing.
        assert await partitions.ensure_partition(conn, datetime(2024, 3, 1, tzinfo=UTC)) is False


@requires_pg
async def test_ensure_partitions_keeps_two_months_of_headroom() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        created = await partitions.ensure_partitions(conn, months_ahead=2)
        listed = {p.name for p in await partitions.list_partitions(conn)}
        now = datetime.now(UTC)
        for offset in range(3):
            month = now
            for _ in range(offset):
                month = partitions.next_month(month)
            assert partitions.partition_name(month) in listed
        assert partitions.DEFAULT_PARTITION in listed
        # Second run: nothing new.
        assert await partitions.ensure_partitions(conn, months_ahead=2) == []
        assert isinstance(created, list)
