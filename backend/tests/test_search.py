"""Workspace search."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def test_search_finds_messages(client: httpx.AsyncClient, session: AsyncSession) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels", headers=headers, json={"name": "general"}
    )
    channel_id = created.json()["id"]
    posted = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "배포 스크립트를 고쳤습니다"},
    )
    message_id = posted.json()["id"]

    response = await client.get(f"{API}/workspaces/{workspace_id}/search?q=배포", headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["message"]["id"] == message_id
    assert results[0]["channel"]["id"] == channel_id

    empty = await client.get(f"{API}/workspaces/{workspace_id}/search?q=없어야함", headers=headers)
    assert empty.json() == []


async def test_search_ignores_private_channels_of_others(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    private = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "release", "is_private": True},
    )
    channel_id = private.json()["id"]
    await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "롤백 스크립트 준비 완료"},
    )

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    response = await client.get(
        f"{API}/workspaces/{workspace_id}/search?q=롤백", headers=auth(other["access_token"])
    )
    assert response.status_code == 200
    assert response.json() == []
