"""Channel membership: the rail's list, joining and leaving."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def test_channel_reports_whether_the_viewer_is_a_member(
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
    assert created.status_code == 200
    assert created.json()["is_member"] is True

    # Another member of the workspace sees a public channel they are not in.
    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    other_headers = auth(other["access_token"])
    listed = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=other_headers)
    assert listed.status_code == 200
    channels = {channel["name"]: channel for channel in listed.json()}
    assert channels["general"]["is_member"] is False


async def test_leaving_a_channel_drops_the_membership(
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

    left = await client.post(f"{API}/channels/{channel_id}/leave", headers=headers)
    assert left.status_code == 204, left.text

    listed = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    channels = {channel["id"]: channel for channel in listed.json()}
    # A public channel stays in the workspace's directory — the rail is what
    # filters it out.
    assert channels[channel_id]["is_member"] is False

    joined = await client.post(f"{API}/channels/{channel_id}/join", headers=headers)
    assert joined.status_code == 200
    assert joined.json()["is_member"] is True


async def test_leaving_a_private_channel_hides_it(
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

    left = await client.post(f"{API}/channels/{channel_id}/leave", headers=headers)
    assert left.status_code == 204

    listed = await client.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
    assert channel_id not in {channel["id"] for channel in listed.json()}


async def test_a_room_can_be_made_with_people_in_it(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The room can be made with people in it — they are in it from the start."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    other = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    third = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={
            "name": "launch",
            "topic": "출시 준비",
            "member_ids": [other["user"]["id"], third["user"]["id"]],
        },
    )
    assert created.status_code == 200, created.text
    channel_id = created.json()["id"]

    roster = await client.get(f"{API}/channels/{channel_id}/members", headers=headers)
    assert roster.status_code == 200
    names = {member["user"]["name"] for member in roster.json()}
    assert names == {"김현진", "박지민", "최수아"}

    # The people who were in the room from the start can open it.
    listed = await client.get(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(other["access_token"]),
    )
    channels = {channel["id"]: channel for channel in listed.json()}
    assert channels[channel_id]["is_member"] is True


async def test_a_room_cannot_be_made_with_a_stranger(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """A room is not a way around the workspace invite."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    stranger = await signup(client, email="outsider@hanbit.co.kr", name="외부인")

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "launch", "member_ids": [stranger["user"]["id"]]},
    )
    assert created.status_code == 404
