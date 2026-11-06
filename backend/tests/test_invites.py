"""Workspace invitations: creating, listing, accepting and revoking them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite
from tests.conftest import API, auth, join_workspace, signup


async def test_admin_can_create_and_list_invites(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    admin = await join_workspace(
        client, session, workspace_id, "han@hanbit.co.kr", "한예진", role="admin"
    )
    headers = auth(admin["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "Newcomer@Hanbit.co.kr", "role": "member"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["id"].startswith("inv_")
    assert body["workspace_id"] == workspace_id
    assert body["email"] == "newcomer@hanbit.co.kr"
    assert body["role"] == "member"
    assert body["token"]
    assert body["created_by"] == admin["user"]["id"]

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert listing.status_code == 200
    assert [invite["id"] for invite in listing.json()] == [body["id"]]
    assert listing.json()[0]["token"] == body["token"]


async def test_reinviting_the_same_email_reuses_the_pending_invite(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    first = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    second = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "Newcomer@Hanbit.co.kr"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["token"] == first.json()["token"]

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert len(listing.json()) == 1


async def test_plain_members_cannot_manage_invites(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    member = await join_workspace(
        client, session, workspace_id, "sua@hanbit.co.kr", "최수아", role="member"
    )
    headers = auth(member["access_token"])

    denied = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert listing.status_code == 403


async def test_a_signed_in_user_accepts_an_invite_and_joins_the_workspace(
    client: httpx.AsyncClient,
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    assert invite.status_code == 200

    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    newcomer_headers = auth(newcomer["access_token"])

    accepted = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert accepted.status_code == 200
    assert accepted.json()["id"] == workspace_id

    workspaces = await client.get(f"{API}/workspaces", headers=newcomer_headers)
    assert workspaces.status_code == 200
    assert workspace_id in [workspace["id"] for workspace in workspaces.json()]

    bootstrap = await client.get(
        f"{API}/workspaces/{workspace_id}/bootstrap", headers=newcomer_headers
    )
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["workspace"]["id"] == workspace_id
    assert body["me"]["id"] == newcomer["user"]["id"]
    assert newcomer["user"]["id"] in [member["user"]["id"] for member in body["members"]]


async def test_accepting_joins_public_channels_but_not_private_ones(
    client: httpx.AsyncClient,
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    public = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general", "topic": "팀 공지"},
    )
    public_id = public.json()["id"]
    private = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "secret", "topic": "비공개", "is_private": True},
    )
    private_id = private.json()["id"]

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    newcomer_headers = auth(newcomer["access_token"])
    accepted = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert accepted.status_code == 200

    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/channels", headers=newcomer_headers
    )
    assert listing.status_code == 200
    assert [channel["name"] for channel in listing.json()] == ["general"]

    roster = await client.get(f"{API}/channels/{public_id}/members", headers=newcomer_headers)
    assert roster.status_code == 200
    assert newcomer["user"]["id"] in [member["user"]["id"] for member in roster.json()]

    hidden = await client.get(f"{API}/channels/{private_id}", headers=newcomer_headers)
    assert hidden.status_code == 403


async def test_an_admin_invite_makes_the_newcomer_an_admin(client: httpx.AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr", "role": "admin"},
    )
    assert invite.status_code == 200
    assert invite.json()["role"] == "admin"

    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    newcomer_headers = auth(newcomer["access_token"])
    accepted = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert accepted.status_code == 200

    members = await client.get(f"{API}/workspaces/{workspace_id}/members", headers=headers)
    roles = {member["user"]["id"]: member["role"] for member in members.json()}
    assert roles[newcomer["user"]["id"]] == "admin"


async def test_an_expired_invite_cannot_be_accepted(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    invite_id = invite.json()["id"]

    row = await session.get(Invite, invite_id)
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    await session.commit()

    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    response = await client.post(
        f"{API}/invites/accept",
        headers=auth(newcomer["access_token"]),
        json={"token": invite.json()["token"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert listing.json() == []


async def test_an_unknown_token_is_not_found_and_a_revoked_invite_conflicts(
    client: httpx.AsyncClient,
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    invite_id = invite.json()["id"]

    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    newcomer_headers = auth(newcomer["access_token"])

    unknown = await client.post(
        f"{API}/invites/accept", headers=newcomer_headers, json={"token": "no-such-token"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"

    revoked = await client.delete(
        f"{API}/workspaces/{workspace_id}/invites/{invite_id}", headers=headers
    )
    assert revoked.status_code == 204
    again = await client.delete(
        f"{API}/workspaces/{workspace_id}/invites/{invite_id}", headers=headers
    )
    assert again.status_code == 204

    refused = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "conflict"

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert listing.json() == []


async def test_an_invite_of_another_workspace_cannot_be_revoked(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )

    other = await join_workspace(
        client, session, workspace_id, "sua@hanbit.co.kr", "최수아", role="admin"
    )
    other_workspace = await client.post(
        f"{API}/workspaces", headers=auth(other["access_token"]), json={"name": "다른 곳"}
    )
    other_workspace_id = other_workspace.json()["id"]

    missing = await client.delete(
        f"{API}/workspaces/{other_workspace_id}/invites/{invite.json()['id']}",
        headers=auth(other["access_token"]),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_an_invite_cannot_be_accepted_twice(client: httpx.AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    invite = await client.post(
        f"{API}/workspaces/{workspace_id}/invites",
        headers=headers,
        json={"email": "newcomer@hanbit.co.kr"},
    )
    newcomer = await signup(
        client,
        email="newcomer@hanbit.co.kr",
        name="신입사원",
        workspace_name="신입의 워크스페이스",
    )
    newcomer_headers = auth(newcomer["access_token"])

    first = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert first.status_code == 200

    second = await client.post(
        f"{API}/invites/accept",
        headers=newcomer_headers,
        json={"token": invite.json()["token"]},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"

    listing = await client.get(f"{API}/workspaces/{workspace_id}/invites", headers=headers)
    assert listing.json() == []
