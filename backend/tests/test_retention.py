"""Retention policy: settings, channel override, and the hourly sweep."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app import workers
from app.core.db import get_sessionmaker
from app.models.file import FileObject
from app.models.message import Message
from app.services.storage import get_storage
from tests.conftest import Actor
from tests.test_channels import _join_workspace
from tests.test_files import _upload


async def _backdate_message(message_id: str, days: int) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(created_at=datetime.now(UTC) - timedelta(days=days))
        )
        await db.commit()


async def test_retention_settings_are_admin_only_and_audited(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    current = (await alice.get(f"/workspaces/{workspace['id']}/retention")).json()
    assert current == {"retention_days_messages": None, "retention_days_files": None}

    denied = await bob.patch(
        f"/workspaces/{workspace['id']}/retention", json={"retention_days_messages": 30}
    )
    assert denied.status_code == 403

    saved = await alice.patch(
        f"/workspaces/{workspace['id']}/retention", json={"retention_days_messages": 30}
    )
    assert saved.status_code == 200
    assert saved.json() == {"retention_days_messages": 30, "retention_days_files": None}

    # Only the field sent changes; an explicit null clears.
    cleared = await alice.patch(
        f"/workspaces/{workspace['id']}/retention",
        json={"retention_days_messages": None, "retention_days_files": 90},
    )
    assert cleared.json() == {"retention_days_messages": None, "retention_days_files": 90}

    workspace_out = (await alice.get(f"/workspaces/{workspace['id']}")).json()
    assert workspace_out["retention_days_files"] == 90

    audit = (
        await alice.get(f"/workspaces/{workspace['id']}/audit?action=retention.updated")
    ).json()
    assert len(audit["items"]) == 2
    assert audit["items"][0]["details"]["after"]["retention_days_files"] == 90


async def test_channel_override_needs_channel_admin(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "짧게", "member_ids": [bob.id]},
        )
    ).json()
    denied = await bob.patch(f"/channels/{channel['id']}", json={"retention_days": 7})
    assert denied.status_code == 403
    ok = await alice.patch(f"/channels/{channel['id']}", json={"retention_days": 7})
    assert ok.status_code == 200
    assert ok.json()["retention_days"] == 7


async def test_sweep_deletes_aged_messages_channel_override_first(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    assert (
        await alice.patch(
            f"/workspaces/{workspace['id']}/retention", json={"retention_days_messages": 30}
        )
    ).status_code == 200
    general = next(
        c
        for c in (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()
        if c["name"] == "general"
    )
    short = (
        await alice.post(f"/workspaces/{workspace['id']}/channels", json={"name": "짧게"})
    ).json()
    assert (
        await alice.patch(f"/channels/{short['id']}", json={"retention_days": 7})
    ).status_code == 200

    old_general = (
        await alice.post(f"/channels/{general['id']}/messages", json={"body": "40일 전"})
    ).json()
    mid_general = (
        await alice.post(f"/channels/{general['id']}/messages", json={"body": "10일 전"})
    ).json()
    old_short = (
        await alice.post(f"/channels/{short['id']}/messages", json={"body": "짧은 채널 10일 전"})
    ).json()
    fresh = (
        await alice.post(f"/channels/{short['id']}/messages", json={"body": "오늘"})
    ).json()
    await _backdate_message(old_general["id"], 40)
    await _backdate_message(mid_general["id"], 10)
    await _backdate_message(old_short["id"], 10)

    assert await workers.run_once("retention_sweep")

    async with get_sessionmaker()() as db:
        rows = {
            m.id: m
            for m in (
                await db.scalars(
                    select(Message).where(
                        Message.id.in_(
                            [old_general["id"], mid_general["id"], old_short["id"], fresh["id"]]
                        )
                    )
                )
            ).all()
        }
    assert rows[old_general["id"]].deleted_at is not None
    assert rows[old_general["id"]].body == ""
    # 10 days old: kept under the 30-day workspace rule …
    assert rows[mid_general["id"]].deleted_at is None
    # … but swept under the channel's 7-day override.
    assert rows[old_short["id"]].deleted_at is not None
    assert rows[fresh["id"]].deleted_at is None

    # The transcript still shows the row as a tombstone, not a hole.
    page = (await alice.get(f"/channels/{general['id']}/messages")).json()
    tomb = next(m for m in page["items"] if m["id"] == old_general["id"])
    assert tomb["deleted_at"] is not None


async def test_sweep_removes_aged_files_from_storage(alice: Actor, workspace: dict) -> None:
    assert (
        await alice.patch(
            f"/workspaces/{workspace['id']}/retention", json={"retention_days_files": 30}
        )
    ).status_code == 200
    file = await _upload(alice, workspace, name="오래된.csv")
    async with get_sessionmaker()() as db:
        row = await db.get(FileObject, file["id"])
        key = row.storage_key
        row.created_at = datetime.now(UTC) - timedelta(days=45)
        await db.commit()
    assert await get_storage().exists(key)

    assert await workers.run_once("retention_sweep")

    assert not await get_storage().exists(key)
    assert (await alice.get(f"/files/{file['id']}")).status_code == 404
