"""Workspaces, channels, DMs, membership and read state."""

from __future__ import annotations

from tests.conftest import Actor


async def test_creating_a_workspace_seeds_default_channels(alice: Actor) -> None:
    created = await alice.post("/workspaces", json={"name": "우리 회사", "slug": "our-co"})
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["my_role"] == "owner"
    assert workspace["member_count"] == 1

    channels = (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()
    names = {c["name"] for c in channels}
    assert names == {"general", "random"}
    assert all(c["membership"] is not None for c in channels)


async def test_workspace_slug_must_be_unique(alice: Actor, workspace: dict) -> None:
    response = await alice.post("/workspaces", json={"name": "또 다른", "slug": "test-co"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slug_taken"


async def test_a_non_member_cannot_see_the_workspace(bob: Actor, workspace: dict) -> None:
    response = await bob.get(f"/workspaces/{workspace['id']}")
    # 404 rather than 403 — its existence should not leak.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


async def test_invite_flow_admits_a_member_to_default_channels(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    invites = await alice.post(
        f"/workspaces/{workspace['id']}/invites",
        json={"emails": ["bob@example.com"], "role": "member"},
    )
    assert invites.status_code == 201
    invite_url = invites.json()[0]["invite_url"]
    token = invite_url.split("token=")[1].split("&")[0]

    accepted = await bob.post("/invites/accept", json={"token": token})
    assert accepted.status_code == 200
    assert accepted.json()["my_role"] == "member"

    # Auto-joined #general (the default channel), but not #random.
    channels = (await bob.get(f"/workspaces/{workspace['id']}/channels")).json()
    assert {c["name"] for c in channels} == {"general"}

    # A token cannot be reused.
    replay = await bob.post("/invites/accept", json={"token": token})
    assert replay.status_code == 409


async def test_an_invite_is_bound_to_its_email(
    alice: Actor, bob: Actor, workspace: dict, client
) -> None:
    invites = await alice.post(
        f"/workspaces/{workspace['id']}/invites", json={"emails": ["someone.else@example.com"]}
    )
    token = invites.json()[0]["invite_url"].split("token=")[1].split("&")[0]
    response = await bob.post("/invites/accept", json={"token": token})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invite_email_mismatch"


async def test_public_channel_can_be_browsed_then_joined(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)

    created = await alice.post(
        f"/workspaces/{workspace['id']}/channels",
        json={"name": "배포 공지", "kind": "public", "topic": "릴리스 알림"},
    )
    assert created.status_code == 201
    channel = created.json()
    assert channel["slug"] == "배포-공지"

    listed = await bob.get(f"/workspaces/{workspace['id']}/channels/browse")
    found = next(c for c in listed.json() if c["id"] == channel["id"])
    assert found["membership"] is None

    joined = await bob.post(f"/channels/{channel['id']}/join")
    assert joined.status_code == 200
    assert joined.json()["membership"] is not None
    assert (await alice.get(f"/channels/{channel['id']}")).json()["member_count"] == 2


async def test_private_channel_is_invisible_and_unjoinable(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "임원 회의", "kind": "private"},
        )
    ).json()

    browsable = (await bob.get(f"/workspaces/{workspace['id']}/channels/browse")).json()
    assert channel["id"] not in {c["id"] for c in browsable}
    assert (await bob.get(f"/channels/{channel['id']}")).status_code == 404
    assert (await bob.post(f"/channels/{channel['id']}/join")).status_code == 404


async def test_opening_a_dm_is_idempotent(alice: Actor, bob: Actor, workspace: dict) -> None:
    await _join_workspace(alice, bob, workspace)

    first = await alice.post(
        f"/workspaces/{workspace['id']}/channels/dm", json={"user_ids": [bob.id]}
    )
    assert first.status_code == 200
    assert first.json()["kind"] == "dm"
    assert {p["id"] for p in first.json()["peers"]} == {bob.id}

    # Same pair, opened from the other side, is the same channel.
    second = await bob.post(
        f"/workspaces/{workspace['id']}/channels/dm", json={"user_ids": [alice.id]}
    )
    assert second.json()["id"] == first.json()["id"]


async def test_dm_with_someone_outside_the_workspace_is_rejected(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    response = await alice.post(
        f"/workspaces/{workspace['id']}/channels/dm", json={"user_ids": [bob.id]}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_in_workspace"


async def test_channel_rename_requires_channel_admin(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "기획", "member_ids": [bob.id]},
        )
    ).json()

    # Bob is a plain member: topic yes, rename no.
    topic_change = await bob.patch(f"/channels/{channel['id']}", json={"topic": "새 주제"})
    assert topic_change.status_code == 200
    denied = await bob.patch(f"/channels/{channel['id']}", json={"name": "새이름"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_channel_admin"

    rename = await alice.patch(f"/channels/{channel['id']}", json={"name": "새이름"})
    assert rename.status_code == 200


async def test_membership_preferences_are_per_user(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()[0]
    await bob.post(f"/channels/{channel['id']}/join")

    updated = await bob.patch(
        f"/channels/{channel['id']}/membership",
        json={"is_muted": True, "notification_level": "mentions", "section": "나중에"},
    )
    assert updated.status_code == 200
    assert updated.json()["is_muted"] is True
    assert updated.json()["section"] == "나중에"

    # Alice's own membership is untouched.
    mine = (await alice.get(f"/channels/{channel['id']}")).json()["membership"]
    assert mine["is_muted"] is False
    assert mine["notification_level"] == "all"


async def test_last_owner_cannot_be_demoted(alice: Actor, workspace: dict) -> None:
    members = (await alice.get(f"/workspaces/{workspace['id']}/members")).json()
    owner = next(m for m in members if m["role"] == "owner")
    response = await alice.patch(
        f"/workspaces/{workspace['id']}/members/{owner['id']}", json={"role": "member"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_owner"


async def _join_workspace(admin: Actor, guest: Actor, workspace: dict) -> None:
    """Invite `guest` into `workspace` and accept, so tests can share setup."""
    invites = await admin.post(
        f"/workspaces/{workspace['id']}/invites",
        json={"emails": [guest.user["email"]], "role": "member"},
    )
    token = invites.json()[0]["invite_url"].split("token=")[1].split("&")[0]
    accepted = await guest.post("/invites/accept", json={"token": token})
    assert accepted.status_code == 200


async def test_only_a_channel_admin_can_remove_members(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "정리 대상", "member_ids": [bob.id]},
        )
    ).json()

    # A plain member cannot remove anyone.
    denied = await bob.delete(f"/channels/{channel['id']}/members/{alice.id}")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_channel_admin"

    # The admin cannot remove themselves — that is leave, and the events differ.
    self_removal = await alice.delete(f"/channels/{channel['id']}/members/{alice.id}")
    assert self_removal.status_code == 403
    assert self_removal.json()["error"]["code"] == "cannot_remove_self"

    # The admin removes bob; bob is out and can no longer post.
    removed = await alice.delete(f"/channels/{channel['id']}/members/{bob.id}")
    assert removed.status_code == 200
    members = (await alice.get(f"/channels/{channel['id']}/members")).json()
    assert bob.id not in {m["user"]["id"] for m in members}
    blocked = await bob.post(f"/channels/{channel['id']}/messages", json={"body": "?"})
    assert blocked.status_code == 403


async def test_nobody_can_be_removed_from_a_dm(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    dm = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels/dm", json={"user_ids": [bob.id]}
        )
    ).json()
    response = await alice.delete(f"/channels/{dm['id']}/members/{bob.id}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "cannot_edit_dm"
