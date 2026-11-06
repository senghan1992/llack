"""Reactions: one emoji per user per message, toggled on and off."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def _setup(client: httpx.AsyncClient) -> tuple[dict, str, str]:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(data["access_token"]),
        json={"name": "general"},
    )
    channel_id = created.json()["id"]
    posted = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=auth(data["access_token"]),
        json={"body": "오늘 배포 잘 끝났나요?"},
    )
    return data, channel_id, posted.json()["id"]


async def test_reaction_is_aggregated(client: httpx.AsyncClient, session: AsyncSession) -> None:
    data, channel_id, message_id = await _setup(client)
    headers = auth(data["access_token"])

    reacted = await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "👍"}
    )
    assert reacted.status_code == 200
    reactions = reacted.json()["reactions"]
    assert len(reactions) == 1
    assert reactions[0]["emoji"] == "👍"
    assert reactions[0]["count"] == 1
    assert reactions[0]["user_ids"] == [data["user"]["id"]]
    assert reactions[0]["me"] is True

    other = await join_workspace(
        client, session, data["workspace"]["id"], "sua@hanbit.co.kr", "최수아"
    )
    other_reaction = await client.post(
        f"{API}/messages/{message_id}/reactions",
        headers=auth(other["access_token"]),
        json={"emoji": "👍"},
    )
    assert other_reaction.status_code == 200
    reactions = other_reaction.json()["reactions"]
    assert reactions[0]["count"] == 2
    assert set(reactions[0]["user_ids"]) == {data["user"]["id"], other["user"]["id"]}
    assert reactions[0]["me"] is True

    seen_by_first = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert seen_by_first.json()["messages"][0]["reactions"][0]["me"] is True


async def test_reacting_twice_removes_the_reaction(client: httpx.AsyncClient) -> None:
    data, _channel_id, message_id = await _setup(client)
    headers = auth(data["access_token"])

    first = await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "🎉"}
    )
    assert first.json()["reactions"][0]["count"] == 1

    second = await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "🎉"}
    )
    assert second.status_code == 200
    assert second.json()["reactions"] == []


async def test_reaction_can_be_deleted(client: httpx.AsyncClient) -> None:
    data, _channel_id, message_id = await _setup(client)
    headers = auth(data["access_token"])

    await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "👀"}
    )
    removed = await client.delete(f"{API}/messages/{message_id}/reactions/👀", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["reactions"] == []


async def test_different_emojis_coexist(client: httpx.AsyncClient) -> None:
    data, _channel_id, message_id = await _setup(client)
    headers = auth(data["access_token"])

    await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "👍"}
    )
    response = await client.post(
        f"{API}/messages/{message_id}/reactions", headers=headers, json={"emoji": "🔥"}
    )
    emojis = {reaction["emoji"] for reaction in response.json()["reactions"]}
    assert emojis == {"👍", "🔥"}
