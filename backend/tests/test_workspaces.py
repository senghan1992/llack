"""Workspaces, channels, DMs and members."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def test_bootstrap_returns_channels_dms_and_members(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general", "topic": "팀 공지"},
    )
    assert created.status_code == 200

    private = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "design", "topic": "디자인", "is_private": True},
    )
    assert private.status_code == 200

    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    dm = await client.post(
        f"{API}/workspaces/{workspace_id}/dms",
        headers=headers,
        json={"user_id": other["user"]["id"]},
    )
    assert dm.status_code == 200

    bootstrap = await client.get(f"{API}/workspaces/{workspace_id}/bootstrap", headers=headers)
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["workspace"]["id"] == workspace_id
    assert body["me"]["id"] == data["user"]["id"]
    assert [channel["name"] for channel in body["channels"]] == ["general", "design"]
    assert [channel["is_private"] for channel in body["channels"]] == [False, True]
    assert [channel["kind"] for channel in body["dms"]] == ["dm"]
    assert body["dms"][0]["dm_user"]["name"] == "박지민"
    assert {member["user"]["name"] for member in body["members"]} == {"김현진", "박지민"}
    assert body["channels"][0]["member_count"] == 1


async def test_private_channels_are_hidden_from_outsiders(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    private = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "release", "topic": "배포", "is_private": True},
    )
    channel_id = private.json()["id"]

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    other_headers = auth(other["access_token"])

    listing = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=other_headers)
    assert listing.status_code == 200
    assert listing.json() == []

    detail = await client.get(f"{API}/channels/{channel_id}", headers=other_headers)
    assert detail.status_code == 403
    assert detail.json()["error"]["code"] == "forbidden"

    missing = await client.get(f"{API}/channels/chl_does_not_exist", headers=other_headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_public_channels_are_visible_to_every_workspace_member(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general", "topic": "팀 공지"},
    )
    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")

    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/channels", headers=auth(other["access_token"])
    )
    assert listing.status_code == 200
    assert [channel["name"] for channel in listing.json()] == ["general"]


async def test_only_owners_and_admins_create_private_channels(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    other_headers = auth(other["access_token"])

    denied = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=other_headers,
        json={"name": "secret", "is_private": True},
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=other_headers,
        json={"name": "public-ok", "is_private": False},
    )
    assert allowed.status_code == 200


async def test_dm_creation_is_idempotent(client: httpx.AsyncClient, session: AsyncSession) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    payload = {"user_id": other["user"]["id"]}

    first = await client.post(f"{API}/workspaces/{workspace_id}/dms", headers=headers, json=payload)
    second = await client.post(
        f"{API}/workspaces/{workspace_id}/dms", headers=headers, json=payload
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "dm"

    dms = await client.get(f"{API}/workspaces/{workspace_id}/dms", headers=headers)
    assert len(dms.json()) == 1


async def test_member_roles_can_be_changed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    other_id = other["user"]["id"]

    members = await client.get(f"{API}/workspaces/{workspace_id}/members", headers=headers)
    assert members.status_code == 200
    roles = {member["user"]["id"]: member["role"] for member in members.json()}
    assert roles[data["user"]["id"]] == "owner"
    assert roles[other_id] == "member"

    promoted = await client.patch(
        f"{API}/workspaces/{workspace_id}/members/{other_id}",
        headers=headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    removed = await client.delete(
        f"{API}/workspaces/{workspace_id}/members/{other_id}", headers=headers
    )
    assert removed.status_code == 204


async def test_users_endpoint_lists_workspace_mates(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    response = await client.get(f"{API}/users", headers=auth(data["access_token"]))
    assert response.status_code == 200
    names = {user["name"] for user in response.json()}
    assert names == {"김현진", "박지민"}

    filtered = await client.get(f"{API}/users?q=박지민", headers=auth(data["access_token"]))
    assert [user["name"] for user in filtered.json()] == ["박지민"]


async def test_a_person_can_say_they_are_away(client: httpx.AsyncClient) -> None:
    """Presence that nobody can set is presence nobody can rely on."""
    data = await signup(client)
    headers = auth(data["access_token"])

    away = await client.patch(f"{API}/me", headers=headers, json={"presence": "away"})
    assert away.status_code == 200
    assert away.json()["presence"] == "away"

    back = await client.patch(f"{API}/me", headers=headers, json={"presence": "online"})
    assert back.status_code == 200
    assert back.json()["presence"] == "online"


async def test_a_person_can_pick_any_status(client: httpx.AsyncClient) -> None:
    """The states a menu offers are states the server keeps."""
    data = await signup(client)
    headers = auth(data["access_token"])

    for state in ("busy", "dnd", "brb", "away", "online"):
        response = await client.patch(f"{API}/me", headers=headers, json={"presence": state})
        assert response.status_code == 200, response.text
        assert response.json()["presence"] == state


async def test_a_person_cannot_claim_to_be_offline(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    response = await client.patch(
        f"{API}/me", headers=auth(data["access_token"]), json={"presence": "offline"}
    )
    assert response.status_code == 422
