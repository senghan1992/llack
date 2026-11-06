"""Milestones: the dated markers of what a project is to deliver."""

from __future__ import annotations

import httpx

from tests.conftest import API, auth, join_workspace, signup

START = "2026-03-01T00:00:00Z"
END = "2026-06-30T00:00:00Z"


async def _create_project(
    client: httpx.AsyncClient, token: str, workspace_id: str, **overrides
) -> dict:
    payload = {"name": "결제 시스템"}
    payload.update(overrides)
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_milestone(
    client: httpx.AsyncClient,
    token: str,
    project_id: str,
    title: str = "v1.0 출시",
    **overrides,
) -> dict:
    payload = {"title": title, "start_at": START, "end_at": END}
    payload.update(overrides)
    response = await client.post(
        f"{API}/projects/{project_id}/milestones",
        headers=auth(token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_task(client: httpx.AsyncClient, token: str, project_id: str, **overrides) -> dict:
    payload = {"title": "PG사 계약서 정리"}
    payload.update(overrides)
    response = await client.post(
        f"{API}/projects/{project_id}/tasks",
        headers=auth(token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_milestone_is_opened_and_closed_again(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    milestone = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        color="#e0803a",
        description="구독 결제를 customers에게 연다.",
    )
    assert milestone["id"].startswith("mst_")
    assert milestone["project_id"] == project["id"]
    assert milestone["title"] == "v1.0 출시"
    assert milestone["color"] == "#e0803a"
    assert milestone["description"] == "구독 결제를 customers에게 연다."
    assert milestone["start_at"] == "2026-03-01T00:00:00Z"
    assert milestone["end_at"] == "2026-06-30T00:00:00Z"
    assert milestone["progress"] == 0
    assert milestone["manual_progress"] == 0
    assert milestone["auto_progress"] is False
    assert milestone["task_count"] == 0
    assert milestone["done_count"] == 0
    assert milestone["task_ids"] == []
    assert milestone["created_by"] == data["user"]["id"]

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert listing.status_code == 200, listing.text
    assert [item["id"] for item in listing.json()] == [milestone["id"]]

    edited = await client.patch(
        f"{API}/milestones/{milestone['id']}",
        headers=headers,
        json={"title": "v1.1 출시", "color": "#2f9e6f"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "v1.1 출시"
    assert edited.json()["color"] == "#2f9e6f"

    removed = await client.delete(f"{API}/milestones/{milestone['id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert listing.json() == []

    missing = await client.patch(
        f"{API}/milestones/{milestone['id']}",
        headers=headers,
        json={"title": "gone"},
    )
    assert missing.status_code == 404


async def test_the_milestones_are_listed_in_the_order_they_start(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    late = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        title="결제 연동",
        start_at="2026-07-01T00:00:00Z",
        end_at="2026-09-30T00:00:00Z",
    )
    early = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        title="v1.0 출시",
        start_at="2026-03-01T00:00:00Z",
    )

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert [item["id"] for item in listing.json()] == [early["id"], late["id"]]


async def test_the_progress_follows_the_cards_of_the_milestone(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    milestone = await _create_milestone(client, data["access_token"], project["id"], progress=80)
    # With no cards of its own the milestone shows the progress by hand.
    assert milestone["progress"] == 80
    assert milestone["manual_progress"] == 80
    assert milestone["auto_progress"] is False

    first = await _create_task(client, data["access_token"], project["id"], title="카드 하나")
    second = await _create_task(client, data["access_token"], project["id"], title="카드 둘")
    third = await _create_task(client, data["access_token"], project["id"], title="카드 셋")
    await client.patch(
        f"{API}/tasks/{second['id']}",
        headers=headers,
        json={"status": "done"},
    )

    linked = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        title="결제 연동",
        task_ids=[first["id"], second["id"], third["id"]],
    )
    assert linked["task_count"] == 3
    assert linked["done_count"] == 1
    assert linked["auto_progress"] is True
    assert linked["progress"] == 33
    # The progress by hand is kept, but it is not the one that is shown.
    assert linked["manual_progress"] == 0
    assert set(linked["task_ids"]) == {first["id"], second["id"], third["id"]}


async def test_linking_cards_replaces_the_previous_set(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    first = await _create_task(client, data["access_token"], project["id"], title="카드 하나")
    second = await _create_task(client, data["access_token"], project["id"], title="카드 둘")

    one = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        title="v1.0 출시",
        task_ids=[first["id"], second["id"]],
    )
    two = await _create_milestone(
        client,
        data["access_token"],
        project["id"],
        title="결제 연동",
        task_ids=[first["id"]],
    )

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    milestones = {item["id"]: item for item in listing.json()}
    assert milestones[one["id"]]["task_ids"] == [second["id"]]
    assert milestones[two["id"]]["task_ids"] == [first["id"]]

    # The card moved to the other milestone, so it is no longer counted here.
    assert milestones[one["id"]]["task_count"] == 1

    tasks = await client.get(f"{API}/projects/{project['id']}/tasks", headers=headers)
    cards = {item["id"]: item for item in tasks.json()}
    assert cards[first["id"]]["milestone_id"] == two["id"]
    assert cards[second["id"]]["milestone_id"] == one["id"]

    # The set of a milestone may also be emptied.
    emptied = await client.patch(
        f"{API}/milestones/{two['id']}",
        headers=headers,
        json={"task_ids": []},
    )
    assert emptied.status_code == 200, emptied.text
    assert emptied.json()["task_ids"] == []
    assert emptied.json()["task_count"] == 0
    assert emptied.json()["auto_progress"] is False

    tasks = await client.get(f"{API}/projects/{project['id']}/tasks", headers=headers)
    cards = {item["id"]: item for item in tasks.json()}
    assert cards[first["id"]]["milestone_id"] is None


async def test_deleting_a_milestone_keeps_its_cards(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    task = await _create_task(client, data["access_token"], project["id"])
    milestone = await _create_milestone(
        client, data["access_token"], project["id"], task_ids=[task["id"]]
    )

    removed = await client.delete(f"{API}/milestones/{milestone['id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert listing.json() == []

    # The card stays on the board; only the link to the milestone is cut.
    tasks = await client.get(f"{API}/projects/{project['id']}/tasks", headers=headers)
    remaining = tasks.json()
    assert [item["id"] for item in remaining] == [task["id"]]
    assert remaining[0]["milestone_id"] is None
    assert remaining[0]["milestone_name"] is None
    assert remaining[0]["milestone_color"] is None


async def test_a_card_is_given_a_milestone_through_the_task(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    milestone = await _create_milestone(client, data["access_token"], project["id"])
    task = await _create_task(client, data["access_token"], project["id"])

    given = await client.patch(
        f"{API}/tasks/{task['id']}",
        headers=headers,
        json={"milestone_id": milestone["id"]},
    )
    assert given.status_code == 200, given.text
    assert given.json()["milestone_id"] == milestone["id"]
    assert given.json()["milestone_name"] == milestone["title"]
    assert given.json()["milestone_color"] == milestone["color"]

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert listing.json()[0]["task_count"] == 1
    assert listing.json()[0]["task_ids"] == [task["id"]]

    # A card may also leave every milestone.
    loose = await client.patch(
        f"{API}/tasks/{task['id']}",
        headers=headers,
        json={"milestone_id": None},
    )
    assert loose.status_code == 200, loose.text
    assert loose.json()["milestone_id"] is None
    assert loose.json()["milestone_name"] is None

    listing = await client.get(f"{API}/projects/{project['id']}/milestones", headers=headers)
    assert listing.json()[0]["task_count"] == 0


async def test_a_milestone_of_another_project_is_refused(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)
    other = await _create_project(client, data["access_token"], workspace_id, name="구독 결제")
    milestone = await _create_milestone(client, data["access_token"], project["id"])

    refused = await client.post(
        f"{API}/projects/{other['id']}/tasks",
        headers=headers,
        json={"title": "남의 마일스톤", "milestone_id": milestone["id"]},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_error"
    assert refused.json()["error"]["field"] == "milestone_id"

    task = await _create_task(client, data["access_token"], other["id"])
    moved = await client.patch(
        f"{API}/tasks/{task['id']}",
        headers=headers,
        json={"milestone_id": milestone["id"]},
    )
    assert moved.status_code == 422, moved.text
    assert moved.json()["error"]["field"] == "milestone_id"


async def test_only_the_owner_or_an_admin_changes_a_milestone(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    admin = await join_workspace(
        client, session, workspace_id, "sua@hanbit.co.kr", "최수아", role="admin"
    )
    project = await _create_project(client, owner["access_token"], workspace_id)

    refused = await client.post(
        f"{API}/projects/{project['id']}/milestones",
        headers=auth(teammate["access_token"]),
        json={"title": "남의 마일스톤", "start_at": START, "end_at": END},
    )
    assert refused.status_code == 403, refused.text

    milestone = await _create_milestone(client, owner["access_token"], project["id"])

    refused = await client.patch(
        f"{API}/milestones/{milestone['id']}",
        headers=auth(teammate["access_token"]),
        json={"title": "남의 마일스톤"},
    )
    assert refused.status_code == 403, refused.text

    refused = await client.delete(
        f"{API}/milestones/{milestone['id']}",
        headers=auth(teammate["access_token"]),
    )
    assert refused.status_code == 403, refused.text

    allowed = await client.patch(
        f"{API}/milestones/{milestone['id']}",
        headers=auth(admin["access_token"]),
        json={"title": "관리자가 고친 마일스톤"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["title"] == "관리자가 고친 마일스톤"

    # Reading the milestones is for everybody who sees the project.
    listing = await client.get(
        f"{API}/projects/{project['id']}/milestones",
        headers=auth(teammate["access_token"]),
    )
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1


async def test_the_end_may_not_be_before_the_start(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    refused = await client.post(
        f"{API}/projects/{project['id']}/milestones",
        headers=headers,
        json={
            "title": "v1.0 출시",
            "start_at": "2026-06-30T00:00:00Z",
            "end_at": "2026-03-01T00:00:00Z",
        },
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_error"
    assert refused.json()["error"]["field"] == "end_at"

    milestone = await _create_milestone(client, data["access_token"], project["id"])
    refused = await client.patch(
        f"{API}/milestones/{milestone['id']}",
        headers=headers,
        json={"end_at": "2026-01-01T00:00:00Z"},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["field"] == "end_at"


async def test_a_milestone_needs_a_title_and_its_dates(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)

    blank = await client.post(
        f"{API}/projects/{project['id']}/milestones",
        headers=headers,
        json={"title": "   ", "start_at": START, "end_at": END},
    )
    assert blank.status_code == 422, blank.text
    assert blank.json()["error"]["field"] == "title"

    without_dates = await client.post(
        f"{API}/projects/{project['id']}/milestones",
        headers=headers,
        json={"title": "v1.0 출시"},
    )
    assert without_dates.status_code == 422, without_dates.text
    assert without_dates.json()["error"]["field"] == "start_at"


async def test_a_card_of_another_project_is_refused(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    project = await _create_project(client, data["access_token"], workspace_id)
    other = await _create_project(client, data["access_token"], workspace_id, name="구독 결제")
    task = await _create_task(client, data["access_token"], other["id"])

    refused = await client.post(
        f"{API}/projects/{project['id']}/milestones",
        headers=headers,
        json={"title": "v1.0 출시", "start_at": START, "end_at": END, "task_ids": [task["id"]]},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_error"
    assert refused.json()["error"]["field"] == "task_ids"
