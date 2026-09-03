"""Audit log: administrative acts leave a record; the record is admin-only."""

from __future__ import annotations

from tests.conftest import Actor
from tests.test_channels import _join_workspace


async def _member_id(alice: Actor, workspace: dict, user_id: str) -> str:
    members = (await alice.get(f"/workspaces/{workspace['id']}/members")).json()
    return next(m["id"] for m in members if m["user"]["id"] == user_id)


async def test_role_change_and_removal_are_audited(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    member_id = await _member_id(alice, workspace, bob.id)

    promoted = await alice.patch(
        f"/workspaces/{workspace['id']}/members/{member_id}",
        json={"role": "admin"},
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    assert promoted.status_code == 200

    page = (await alice.get(f"/workspaces/{workspace['id']}/audit")).json()
    actions = [e["action"] for e in page["items"]]
    assert "member.role_changed" in actions
    # The invite that admitted bob was recorded too.
    assert "invite.created" in actions

    event = next(e for e in page["items"] if e["action"] == "member.role_changed")
    assert event["actor"]["id"] == alice.id
    assert event["target_type"] == "user"
    assert event["target_id"] == bob.id
    assert event["target_label"] == "이밥"
    assert event["details"] == {"from": "member", "to": "admin"}
    assert event["ip"] == "203.0.113.9"

    removed = await alice.delete(f"/workspaces/{workspace['id']}/members/{member_id}")
    assert removed.status_code == 200
    page = (await alice.get(f"/workspaces/{workspace['id']}/audit?action=member.removed")).json()
    assert [e["target_id"] for e in page["items"]] == [bob.id]


async def test_only_admins_read_the_log_and_pages_are_keyset(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    denied = await bob.get(f"/workspaces/{workspace['id']}/audit")
    assert denied.status_code == 403

    # Several events, then walk them two at a time.
    channel = (
        await alice.post(f"/workspaces/{workspace['id']}/channels", json={"name": "감사"})
    ).json()
    for name in ("감사-1", "감사-2", "감사-3"):
        assert (
            await alice.patch(f"/channels/{channel['id']}", json={"name": name})
        ).status_code == 200

    first = (await alice.get(f"/workspaces/{workspace['id']}/audit?limit=2")).json()
    assert len(first["items"]) == 2 and first["has_more"] is True
    assert first["next_before"] == first["items"][-1]["id"]
    second = (
        await alice.get(
            f"/workspaces/{workspace['id']}/audit?limit=2&before={first['next_before']}"
        )
    ).json()
    assert {e["id"] for e in first["items"]}.isdisjoint({e["id"] for e in second["items"]})
    renames = [e for e in first["items"] + second["items"] if e["action"] == "channel.renamed"]
    assert renames and renames[0]["details"]["to"] == "감사-3"


async def test_csv_export_is_excel_friendly(alice: Actor, bob: Actor, workspace: dict) -> None:
    await _join_workspace(alice, bob, workspace)
    response = await alice.get(f"/workspaces/{workspace['id']}/audit/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.content
    assert body.startswith("﻿".encode()), "BOM so Excel decodes Korean"
    text = body.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0].startswith('"시각(UTC)","행위","행위자"')
    assert any("invite.created" in line and "김앨리스" in line for line in lines[1:])


async def test_channel_archive_role_change_and_removal_are_audited(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "감사채널", "member_ids": [bob.id]},
        )
    ).json()
    assert (
        await alice.patch(f"/channels/{channel['id']}/members/{bob.id}", json={"role": "admin"})
    ).status_code == 200
    assert (await alice.delete(f"/channels/{channel['id']}/members/{bob.id}")).status_code == 200
    assert (
        await alice.patch(f"/channels/{channel['id']}", json={"is_archived": True})
    ).status_code == 200

    page = (await alice.get(f"/workspaces/{workspace['id']}/audit?limit=10")).json()
    actions = [e["action"] for e in page["items"]]
    for expected in ("channel.member_role_changed", "channel.member_removed", "channel.archived"):
        assert expected in actions, actions
    archived = next(e for e in page["items"] if e["action"] == "channel.archived")
    assert archived["target_label"] == "감사채널"


async def test_smtp_change_is_visible_to_owners_as_a_server_event(
    alice: Actor, workspace: dict
) -> None:
    saved = await alice.put(
        "/admin/smtp",
        json={"host": "smtp.example.com", "port": 587, "mail_from": "llack@example.com"},
    )
    assert saved.status_code == 200
    page = (await alice.get(f"/workspaces/{workspace['id']}/audit?action=smtp.updated")).json()
    assert len(page["items"]) == 1
    event = page["items"][0]
    assert event["target_type"] == "server"
    assert event["details"]["host"] == "smtp.example.com"
    assert event["details"]["password_changed"] is False
    assert "password" not in event["details"]
