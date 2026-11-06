"""A direct message can be ended — for both of the people in it."""

from __future__ import annotations

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def _open_dm(client: httpx.AsyncClient, token: str, workspace_id: str, user_id: str) -> dict:
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/dms",
        headers=auth(token),
        json={"user_id": user_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_direct_message_can_be_deleted(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    dm = await _open_dm(client, data["access_token"], workspace_id, other["user"]["id"])
    channel_id = dm["id"]
    assert dm["kind"] == "dm"

    message = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "안녕하세요"},
    )
    assert message.status_code == 200, message.text

    removed = await client.delete(f"{API}/channels/{channel_id}", headers=headers)
    assert removed.status_code == 204, removed.text

    # The conversation is gone for both of them.
    dms = await client.get(f"{API}/workspaces/{workspace_id}/dms", headers=headers)
    assert dms.json() == []
    theirs = await client.get(
        f"{API}/workspaces/{workspace_id}/dms", headers=auth(other["access_token"])
    )
    assert theirs.json() == []

    gone = await client.get(f"{API}/channels/{channel_id}", headers=headers)
    assert gone.status_code == 404


async def test_the_messages_of_a_deleted_direct_message_are_gone(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    dm = await _open_dm(client, data["access_token"], workspace_id, other["user"]["id"])
    channel_id = dm["id"]

    message = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "안녕하세요"},
    )
    message_id = message.json()["id"]
    await client.post(
        f"{API}/messages/{message_id}/reactions",
        headers=headers,
        json={"emoji": "👋"},
    )
    await client.post(f"{API}/channels/{channel_id}/read", headers=headers, json={})

    removed = await client.delete(f"{API}/channels/{channel_id}", headers=headers)
    assert removed.status_code == 204, removed.text

    # The conversation is really gone, not hidden: no message, no reaction,
    # no read state and nobody left in the room.
    for table, column, value in (
        ("messages", "channel_id", channel_id),
        ("reactions", "message_id", message_id),
        ("read_states", "channel_id", channel_id),
        ("channel_memberships", "channel_id", channel_id),
    ):
        count = await session.scalar(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :value"), {"value": value}
        )
        assert count == 0, table


async def test_an_ordinary_channel_is_not_deleted(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    channel = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "payments"},
    )
    assert channel.status_code == 200, channel.text
    channel_id = channel.json()["id"]

    refused = await client.delete(f"{API}/channels/{channel_id}", headers=headers)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "forbidden"

    still_there = await client.get(f"{API}/channels/{channel_id}", headers=headers)
    assert still_there.status_code == 200


async def test_a_stranger_cannot_delete_a_direct_message(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    stranger = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")

    dm = await _open_dm(client, owner["access_token"], workspace_id, other["user"]["id"])

    refused = await client.delete(
        f"{API}/channels/{dm['id']}", headers=auth(stranger["access_token"])
    )
    assert refused.status_code == 403

    still_there = await client.get(
        f"{API}/channels/{dm['id']}", headers=auth(other["access_token"])
    )
    assert still_there.status_code == 200


async def test_a_project_that_pointed_at_a_deleted_direct_message_keeps_its_work(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    dm = await _open_dm(client, data["access_token"], workspace_id, other["user"]["id"])

    project = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=headers,
        json={"name": "구독 결제", "channel_id": dm["id"]},
    )
    assert project.status_code == 200, project.text
    assert project.json()["channel_id"] == dm["id"]

    removed = await client.delete(f"{API}/channels/{dm['id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    # The project stays; only the room it pointed at is gone.
    listing = await client.get(f"{API}/workspaces/{workspace_id}/projects", headers=headers)
    assert listing.json()[0]["id"] == project.json()["id"]
    assert listing.json()[0]["channel_id"] is None


async def test_a_direct_message_can_be_opened_again_afterwards(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    dm = await _open_dm(client, data["access_token"], workspace_id, other["user"]["id"])
    removed = await client.delete(f"{API}/channels/{dm['id']}", headers=headers)
    assert removed.status_code == 204

    again = await _open_dm(client, data["access_token"], workspace_id, other["user"]["id"])
    assert again["id"] != dm["id"]
    assert again["kind"] == "dm"
