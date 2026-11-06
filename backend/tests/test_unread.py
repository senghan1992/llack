"""Unread counters are computed per user."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def test_unread_count_is_per_user(client: httpx.AsyncClient, session: AsyncSession) -> None:
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
    other_headers = auth(other["access_token"])

    await client.post(
        f"{API}/channels/{channel_id}/messages", headers=other_headers, json={"body": "첫 번째"}
    )
    await client.post(
        f"{API}/channels/{channel_id}/messages", headers=other_headers, json={"body": "두 번째"}
    )
    # the author's own message never counts
    await client.post(
        f"{API}/channels/{channel_id}/messages", headers=headers, json={"body": "제 것"}
    )

    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 2

    # the other user only has the one message written by the owner
    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=other_headers)
    assert channels.json()[0]["unread_count"] == 1


async def test_marking_a_channel_read_clears_the_counter(
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
    posted = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=auth(other["access_token"]),
        json={"body": "읽어주세요"},
    )
    message_id = posted.json()["id"]

    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 1

    read = await client.post(
        f"{API}/channels/{channel_id}/read", headers=headers, json={"message_id": message_id}
    )
    assert read.status_code == 204

    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 0

    # a new message after the read point counts again
    await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=auth(other["access_token"]),
        json={"body": "새로운 메시지"},
    )
    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 1


async def test_marking_read_without_a_message_reads_everything(
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
    for index in range(3):
        await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=auth(other["access_token"]),
            json={"body": f"메시지 {index}"},
        )

    read = await client.post(f"{API}/channels/{channel_id}/read", headers=headers, json={})
    assert read.status_code == 204

    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 0


async def test_marking_read_twice_at_once_does_not_fail(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Two reads racing for the same (channel, user) must both succeed.

    The client marks a channel read over the socket and over REST, so the
    second insert used to break the unique constraint and answer 500.
    """
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
    await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=auth(other["access_token"]),
        json={"body": "안 읽은 메시지"},
    )

    import asyncio

    responses = await asyncio.gather(
        *[
            client.post(f"{API}/channels/{channel_id}/read", headers=headers, json={})
            for _ in range(5)
        ]
    )
    assert [r.status_code for r in responses] == [204] * 5

    channels = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channels.json()[0]["unread_count"] == 0
