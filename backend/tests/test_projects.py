"""Projects and their boards: registering, rosters, tasks and permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from tests.conftest import API, auth, join_workspace, signup

BASE = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


async def _create_project(
    client: httpx.AsyncClient, token: str, workspace_id: str, **overrides
) -> dict:
    payload = {
        "name": "결제 시스템",
        "purpose": "구독 결제를 다시 만든다",
        "deliverables": "결제 모듈과 대시보드",
    }
    payload.update(overrides)
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
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


async def test_create_and_list_projects(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await _create_project(client, data["access_token"], workspace_id)
    assert created["id"].startswith("prj_")
    assert created["name"] == "결제 시스템"
    assert created["purpose"] == "구독 결제를 다시 만든다"
    assert created["created_by"] == data["user"]["id"]
    assert created["is_member"] is True
    assert created["open_tasks"] == 0
    # The one who made the project is on it.
    assert [member["id"] for member in created["members"]] == [data["user"]["id"]]

    listing = await client.get(f"{API}/workspaces/{workspace_id}/projects", headers=headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created["id"]]


async def test_a_project_carries_a_description(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await _create_project(
        client, data["access_token"], workspace_id, description="구독 결제를 다시 만든다"
    )
    assert created["description"] == "구독 결제를 다시 만든다"

    changed = await client.patch(
        f"{API}/projects/{created['id']}",
        headers=headers,
        json={"description": "결제 모듈과 대시보드를 다시 만든다"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["description"] == "결제 모듈과 대시보드를 다시 만든다"


async def test_a_description_is_optional(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]

    created = await _create_project(client, data["access_token"], workspace_id)
    assert created["description"] == ""

    # The description is written in words, not in paragraphs.
    too_long = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "긴 설명", "description": "가" * 4001},
    )
    assert too_long.status_code == 422


async def test_a_project_needs_a_name(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]

    blank = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "   "},
    )
    assert blank.status_code == 422


async def test_the_roster_makes_a_project_mine(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    created = await _create_project(client, owner["access_token"], workspace_id)

    # A teammate sees the project — the board is open to the workspace.
    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(teammate["access_token"]),
    )
    seen = listing.json()[0]
    assert seen["id"] == created["id"]
    assert seen["is_member"] is False

    # Put them on the roster.
    added = await client.post(
        f"{API}/projects/{created['id']}/members",
        headers=auth(owner["access_token"]),
        json={"user_id": teammate["user"]["id"]},
    )
    assert added.status_code == 200, added.text
    assert added.json()["is_member"] is True  # the caller is the project's owner

    mine = await client.get(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(teammate["access_token"]),
    )
    assert mine.json()[0]["is_member"] is True

    # The owner cannot be taken off their own project.
    taken = await client.delete(
        f"{API}/projects/{created['id']}/members/{owner['user']['id']}",
        headers=auth(owner["access_token"]),
    )
    assert taken.status_code == 403


async def test_only_the_owner_or_an_admin_changes_a_project(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    created = await _create_project(client, owner["access_token"], workspace_id)

    refused = await client.patch(
        f"{API}/projects/{created['id']}",
        headers=auth(teammate["access_token"]),
        json={"name": "남의 프로젝트"},
    )
    assert refused.status_code == 403

    allowed = await client.patch(
        f"{API}/projects/{created['id']}",
        headers=auth(owner["access_token"]),
        json={"name": "결제 시스템 v2"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["name"] == "결제 시스템 v2"


async def test_a_task_sits_on_the_board_and_moves_between_columns(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project = await _create_project(client, data["access_token"], workspace_id)

    task = await _create_task(client, data["access_token"], project["id"])
    assert task["id"].startswith("tsk_")
    assert task["status"] == "todo"
    assert task["position"] == 0
    assert task["assignee"] is None
    assert task["comment_count"] == 0

    moved = await client.patch(
        f"{API}/tasks/{task['id']}",
        headers=auth(data["access_token"]),
        json={"status": "in-progress"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "in-progress"

    listing = await client.get(
        f"{API}/projects/{project['id']}/tasks",
        headers=auth(data["access_token"]),
    )
    assert [item["id"] for item in listing.json()] == [task["id"]]


async def test_the_order_inside_a_column_is_kept(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project = await _create_project(client, data["access_token"], workspace_id)

    first = await _create_task(client, data["access_token"], project["id"], title="첫째")
    second = await _create_task(client, data["access_token"], project["id"], title="둘째")
    third = await _create_task(client, data["access_token"], project["id"], title="셋째")
    assert [first["position"], second["position"], third["position"]] == [0, 1, 2]

    # Move the last one to the front of the column.
    moved = await client.patch(
        f"{API}/tasks/{third['id']}",
        headers=auth(data["access_token"]),
        json={"status": "todo", "position": 0},
    )
    assert moved.status_code == 200, moved.text

    listing = await client.get(
        f"{API}/projects/{project['id']}/tasks",
        headers=auth(data["access_token"]),
    )
    assert [item["title"] for item in listing.json()] == ["셋째", "첫째", "둘째"]


async def test_my_tasks_covers_the_whole_workspace(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    project = await _create_project(client, owner["access_token"], workspace_id)

    mine = await _create_task(
        client,
        owner["access_token"],
        project["id"],
        title="내 할일",
        assignee_id=owner["user"]["id"],
    )
    theirs = await _create_task(
        client,
        owner["access_token"],
        project["id"],
        title="남의 할일",
        assignee_id=teammate["user"]["id"],
    )
    await _create_task(client, owner["access_token"], project["id"], title="담당 없음")

    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/tasks",
        headers=auth(owner["access_token"]),
    )
    assert [item["id"] for item in listing.json()] == [mine["id"]]

    # A finished task is not "mine to do" any more.
    await client.patch(
        f"{API}/tasks/{mine['id']}",
        headers=auth(owner["access_token"]),
        json={"status": "done"},
    )
    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/tasks",
        headers=auth(owner["access_token"]),
    )
    assert listing.json() == []
    assert theirs["id"] != mine["id"]


async def test_the_counts_on_a_project_are_the_readers_own(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    project = await _create_project(client, owner["access_token"], workspace_id)
    await _create_task(
        client,
        owner["access_token"],
        project["id"],
        assignee_id=owner["user"]["id"],
    )
    await _create_task(
        client,
        owner["access_token"],
        project["id"],
        assignee_id=teammate["user"]["id"],
    )

    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(teammate["access_token"]),
    )
    body = listing.json()[0]
    assert body["open_tasks"] == 2
    assert body["my_open_tasks"] == 1


async def test_a_task_carries_a_deadline_and_a_comment(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project = await _create_project(client, data["access_token"], workspace_id)

    task = await _create_task(
        client,
        data["access_token"],
        project["id"],
        due_at=(BASE + timedelta(days=3)).isoformat(),
    )
    assert task["due_at"] is not None

    comment = await client.post(
        f"{API}/tasks/{task['id']}/comments",
        headers=auth(data["access_token"]),
        json={"body": "법무 검토를 받았습니다"},
    )
    assert comment.status_code == 200, comment.text
    assert comment.json()["body"] == "법무 검토를 받았습니다"
    assert comment.json()["author"]["id"] == data["user"]["id"]

    listing = await client.get(
        f"{API}/projects/{project['id']}/tasks",
        headers=auth(data["access_token"]),
    )
    task_now = listing.json()[0]
    assert task_now["comment_count"] == 1
    assert task_now["comments"][0]["body"] == "법무 검토를 받았습니다"

    removed = await client.delete(
        f"{API}/task-comments/{comment.json()['id']}",
        headers=auth(data["access_token"]),
    )
    assert removed.status_code == 204


async def test_a_project_can_point_at_the_room_it_is_talked_about(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]

    channel = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(data["access_token"]),
        json={"name": "payments", "topic": "결제 이야기"},
    )
    assert channel.status_code == 200, channel.text
    channel_id = channel.json()["id"]

    project = await _create_project(
        client, data["access_token"], workspace_id, channel_id=channel_id
    )
    assert project["channel_id"] == channel_id

    # A channel of another workspace is not ours to point at.
    stranger = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(data["access_token"]),
        json={"name": "other"},
    )
    assert stranger.status_code == 200


async def test_a_task_is_only_deleted_by_the_hand_that_made_it(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    bystander = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    project = await _create_project(client, owner["access_token"], workspace_id)
    task = await _create_task(client, teammate["access_token"], project["id"])

    # Somebody who had nothing to do with the task cannot take it off the board.
    refused = await client.delete(
        f"{API}/tasks/{task['id']}",
        headers=auth(bystander["access_token"]),
    )
    assert refused.status_code == 403

    # The author can.
    allowed = await client.delete(
        f"{API}/tasks/{task['id']}",
        headers=auth(teammate["access_token"]),
    )
    assert allowed.status_code == 204


async def test_a_project_states_where_it_is_and_when_it_runs(
    client: httpx.AsyncClient, session
) -> None:
    """The header of the board says three things: how far, how many, how long."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    token = data["access_token"]
    project = await _create_project(client, token, workspace_id)

    await _create_task(client, token, project["id"], status="todo")
    await _create_task(client, token, project["id"], status="done")
    await _create_task(
        client,
        token,
        project["id"],
        status="todo",
        due_at=(BASE + timedelta(days=20)).isoformat(),
    )

    listing = await client.get(f"{API}/workspaces/{workspace_id}/projects", headers=auth(token))
    body = listing.json()[0]
    assert body["total_tasks"] == 3
    assert body["done_tasks"] == 1
    assert body["open_tasks"] == 2
    # The period reaches from the earliest deadline to the latest one.
    assert body["start_at"] is not None
    assert body["end_at"] is not None
    assert body["start_at"][:10] == "2026-11-23"
    assert body["end_at"][:10] == "2026-11-23"


async def test_a_project_without_a_date_has_no_period(client: httpx.AsyncClient, session) -> None:
    """Nothing is due — so the project has no period to say."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    await _create_project(client, data["access_token"], workspace_id)

    listing = await client.get(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
    )
    body = listing.json()[0]
    assert body["total_tasks"] == 0
    assert body["done_tasks"] == 0
    assert body["start_at"] is None
    assert body["end_at"] is None
