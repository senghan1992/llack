"""Bringing people into a room."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def test_a_member_can_bring_someone_into_a_public_room(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general"},
    )
    channel_id = created.json()["id"]

    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    added = await client.post(
        f"{API}/channels/{channel_id}/members",
        headers=headers,
        json={"user_id": other["user"]["id"]},
    )
    assert added.status_code == 204, added.text

    roster = await client.get(f"{API}/channels/{channel_id}/members", headers=headers)
    assert roster.status_code == 200
    assert {member["user"]["name"] for member in roster.json()} == {"김현진", "박지민"}


async def test_someone_outside_the_room_cannot_add_people(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general"},
    )
    channel_id = created.json()["id"]

    outsider = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    newcomer = await join_workspace(client, session, workspace_id, "chaewon@hanbit.co.kr", "이채원")

    refused = await client.post(
        f"{API}/channels/{channel_id}/members",
        headers=auth(outsider["access_token"]),
        json={"user_id": newcomer["user"]["id"]},
    )
    assert refused.status_code == 403


async def test_only_an_admin_can_add_people_to_a_private_room(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "design", "is_private": True},
    )
    channel_id = created.json()["id"]

    member = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    newcomer = await join_workspace(client, session, workspace_id, "chaewon@hanbit.co.kr", "이채원")

    # A plain member of the workspace cannot invite into a private room.
    refused = await client.post(
        f"{API}/channels/{channel_id}/members",
        headers=auth(member["access_token"]),
        json={"user_id": newcomer["user"]["id"]},
    )
    assert refused.status_code == 403

    # The creator (an owner) can.
    allowed = await client.post(
        f"{API}/channels/{channel_id}/members",
        headers=headers,
        json={"user_id": newcomer["user"]["id"]},
    )
    assert allowed.status_code == 204, allowed.text


async def test_adding_someone_outside_the_workspace_is_not_found(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general"},
    )
    channel_id = created.json()["id"]

    stranger = await signup(client, email="stranger@hanbit.co.kr", name="나그네")

    missing = await client.post(
        f"{API}/channels/{channel_id}/members",
        headers=headers,
        json={"user_id": stranger["user"]["id"]},
    )
    assert missing.status_code == 404
