"""Schedule events: creating, managing, guests, RSVP and visibility."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from tests.conftest import API, auth, join_workspace, signup

BASE = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _event(**overrides) -> dict:
    payload = {
        "title": "주간 회의",
        "description": "진행 상황 공유",
        "location": "3층 회의실",
        "starts_at": _iso(BASE),
        "ends_at": _iso(BASE + timedelta(hours=1)),
    }
    payload.update(overrides)
    # Moving the start moves the end with it, unless the end was named too.
    if "starts_at" in overrides and "ends_at" not in overrides:
        start = datetime.fromisoformat(overrides["starts_at"])
        payload["ends_at"] = _iso(start + timedelta(hours=1))
    return payload


async def _create(client: httpx.AsyncClient, token: str, workspace_id: str, **overrides) -> dict:
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/events",
        headers=auth(token),
        json=_event(**overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_and_list_events(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await _create(client, data["access_token"], workspace_id)
    assert created["id"].startswith("evt_")
    assert created["title"] == "주간 회의"
    assert created["location"] == "3층 회의실"
    assert created["all_day"] is False
    assert created["is_private"] is False
    assert created["created_by"] == data["user"]["id"]
    assert created["channel_id"] is None
    assert created["my_response"] == "accepted"
    assert [item["user"]["id"] for item in created["attendees"]] == [data["user"]["id"]]

    listing = await client.get(f"{API}/workspaces/{workspace_id}/events", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert [item["id"] for item in body] == [created["id"]]


async def test_event_requires_a_title_and_a_sane_window(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    blank = await client.post(
        f"{API}/workspaces/{workspace_id}/events",
        headers=headers,
        json=_event(title="   "),
    )
    assert blank.status_code == 422

    backwards = await client.post(
        f"{API}/workspaces/{workspace_id}/events",
        headers=headers,
        json=_event(ends_at=_iso(BASE - timedelta(hours=1))),
    )
    assert backwards.status_code == 422


async def test_events_are_listed_in_time_order_and_filtered_by_window(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    later = await _create(
        client,
        data["access_token"],
        workspace_id,
        title="나중",
        starts_at=_iso(BASE + timedelta(days=3)),
    )
    sooner = await _create(
        client,
        data["access_token"],
        workspace_id,
        title="먼저",
        starts_at=_iso(BASE + timedelta(days=1)),
    )

    listing = await client.get(f"{API}/workspaces/{workspace_id}/events", headers=headers)
    assert [item["id"] for item in listing.json()] == [sooner["id"], later["id"]]

    windowed = await client.get(
        f"{API}/workspaces/{workspace_id}/events",
        headers=headers,
        params={"from": _iso(BASE), "to": _iso(BASE + timedelta(days=2))},
    )
    assert [item["id"] for item in windowed.json()] == [sooner["id"]]


async def test_private_events_stay_between_the_invited(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    guest = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    created = await _create(
        client,
        owner["access_token"],
        workspace_id,
        title="비밀 회의",
        is_private=True,
        attendee_ids=[guest["user"]["id"]],
    )
    assert created["is_private"] is True

    owner_list = await client.get(
        f"{API}/workspaces/{workspace_id}/events", headers=auth(owner["access_token"])
    )
    assert [item["id"] for item in owner_list.json()] == [created["id"]]

    guest_list = await client.get(
        f"{API}/workspaces/{workspace_id}/events", headers=auth(guest["access_token"])
    )
    assert [item["id"] for item in guest_list.json()] == [created["id"]]

    outsider = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    outsider_list = await client.get(
        f"{API}/workspaces/{workspace_id}/events", headers=auth(outsider["access_token"])
    )
    assert outsider_list.json() == []

    blocked = await client.get(
        f"{API}/events/{created['id']}", headers=auth(outsider["access_token"])
    )
    assert blocked.status_code == 403


async def test_only_the_creator_or_an_admin_may_change_an_event(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    created = await _create(client, owner["access_token"], workspace_id)

    peer = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    peer_headers = auth(peer["access_token"])

    denied = await client.patch(
        f"{API}/events/{created['id']}",
        headers=peer_headers,
        json={"title": "다른 이름"},
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"{API}/events/{created['id']}",
        headers=auth(owner["access_token"]),
        json={"title": "월간 회의"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "월간 회의"

    admin = await join_workspace(
        client, session, workspace_id, "woojin@hanbit.co.kr", "정우진", role="admin"
    )
    admin_edit = await client.patch(
        f"{API}/events/{created['id']}",
        headers=auth(admin["access_token"]),
        json={"title": "관리자가 바꾼 제목"},
    )
    assert admin_edit.status_code == 200


async def test_delete_an_event(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    created = await _create(client, owner["access_token"], workspace_id)

    peer = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    denied = await client.delete(
        f"{API}/events/{created['id']}", headers=auth(peer["access_token"])
    )
    assert denied.status_code == 403

    removed = await client.delete(
        f"{API}/events/{created['id']}", headers=auth(owner["access_token"])
    )
    assert removed.status_code == 204

    gone = await client.get(f"{API}/events/{created['id']}", headers=auth(owner["access_token"]))
    assert gone.status_code == 404


async def test_guests_can_be_added_and_removed(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    guest = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    created = await _create(client, owner["access_token"], workspace_id)

    added = await client.post(
        f"{API}/events/{created['id']}/attendees",
        headers=auth(owner["access_token"]),
        json={"user_id": guest["user"]["id"]},
    )
    assert added.status_code == 200
    assert [item["user"]["id"] for item in added.json()["attendees"]] == [
        owner["user"]["id"],
        guest["user"]["id"],
    ]

    removed = await client.delete(
        f"{API}/events/{created['id']}/attendees/{guest['user']['id']}",
        headers=auth(owner["access_token"]),
    )
    assert removed.status_code == 204

    after = await client.get(f"{API}/events/{created['id']}", headers=auth(owner["access_token"]))
    assert [item["user"]["id"] for item in after.json()["attendees"]] == [owner["user"]["id"]]


async def test_an_attendee_must_be_a_workspace_member(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    created = await _create(client, data["access_token"], workspace_id)

    response = await client.post(
        f"{API}/events/{created['id']}/attendees",
        headers=auth(data["access_token"]),
        json={"user_id": "usr_does_not_exist"},
    )
    assert response.status_code == 422


async def test_rsvp_records_the_answer(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    guest = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    created = await _create(
        client,
        owner["access_token"],
        workspace_id,
        attendee_ids=[guest["user"]["id"]],
    )

    accepted = await client.post(
        f"{API}/events/{created['id']}/rsvp",
        headers=auth(guest["access_token"]),
        json={"response": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["my_response"] == "accepted"

    declined = await client.post(
        f"{API}/events/{created['id']}/rsvp",
        headers=auth(guest["access_token"]),
        json={"response": "declined"},
    )
    assert declined.status_code == 200
    assert declined.json()["my_response"] == "declined"

    answers = {item["user"]["id"]: item["response"] for item in declined.json()["attendees"]}
    assert answers[owner["user"]["id"]] == "accepted"
    assert answers[guest["user"]["id"]] == "declined"


async def test_a_linked_channel_is_kept_on_the_event(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    channel = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(data["access_token"]),
        json={"name": "general"},
    )
    channel_id = channel.json()["id"]

    created = await _create(client, data["access_token"], workspace_id, channel_id=channel_id)
    assert created["channel_id"] == channel_id

    bogus = await client.post(
        f"{API}/workspaces/{workspace_id}/events",
        headers=auth(data["access_token"]),
        json=_event(channel_id="chl_nope"),
    )
    assert bogus.status_code == 422


async def test_a_stranger_cannot_read_the_calendar(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    await _create(client, owner["access_token"], workspace_id)

    stranger = await signup(client, email="stranger@elsewhere.co.kr", name="외부인")
    response = await client.get(
        f"{API}/workspaces/{workspace_id}/events",
        headers=auth(stranger["access_token"]),
    )
    assert response.status_code == 403


async def test_the_creator_stays_on_their_own_roster(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    created = await _create(client, data["access_token"], workspace_id)

    updated = await client.patch(
        f"{API}/events/{created['id']}",
        headers=auth(data["access_token"]),
        json={"attendee_ids": []},
    )
    assert updated.status_code == 200
    assert [item["user"]["id"] for item in updated.json()["attendees"]] == [data["user"]["id"]]
