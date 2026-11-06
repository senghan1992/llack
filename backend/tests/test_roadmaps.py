"""Roadmaps — the lanes of work on a project's board.

A roadmap is no longer opened through the API: it is *given*, and the board
filters the cards by it. These tests cover what the app still does with one —
listing it, renaming it, taking it away, and pinning a card to it.
"""

from __future__ import annotations

import httpx

from app.core.ids import ROADMAP_PREFIX, new_id
from app.models.project import Roadmap
from tests.conftest import API, auth, join_workspace, signup


async def _given_roadmap(
    session, project_id: str, user_id: str, name: str, position: int = 0
) -> str:
    """Put a roadmap on a project's board — the way a team is given one."""
    roadmap = Roadmap(
        id=new_id(ROADMAP_PREFIX),
        project_id=project_id,
        name=name,
        position=position,
        created_by=user_id,
    )
    session.add(roadmap)
    await session.commit()
    return roadmap.id


async def test_the_roadmaps_of_a_project_are_listed(client: httpx.AsyncClient, session) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project_id = data["workspace"]["id"]
    project = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "결제 시스템"},
    )
    project_id = project.json()["id"]
    await _given_roadmap(session, project_id, data["user"]["id"], "2분기", position=1)
    await _given_roadmap(session, project_id, data["user"]["id"], "기본", position=0)

    listing = await client.get(
        f"{API}/projects/{project_id}/roadmaps", headers=auth(data["access_token"])
    )
    assert listing.status_code == 200
    body = listing.json()
    # The order they are shown in — the first one comes first.
    assert [item["name"] for item in body] == ["기본", "2분기"]
    assert body[0]["task_count"] == 0


async def test_a_roadmap_is_renamed_by_the_one_who_owns_the_project(
    client: httpx.AsyncClient, session
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "결제 시스템"},
    )
    project_id = project.json()["id"]
    roadmap_id = await _given_roadmap(session, project_id, data["user"]["id"], "2분기")

    response = await client.patch(
        f"{API}/roadmaps/{roadmap_id}",
        headers=auth(data["access_token"]),
        json={"name": "3분기"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "3분기"


async def test_a_roadmap_is_not_renamed_by_a_teammate(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    project = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(owner["access_token"]),
        json={"name": "결제 시스템"},
    )
    project_id = project.json()["id"]
    roadmap_id = await _given_roadmap(session, project_id, owner["user"]["id"], "2분기")

    response = await client.patch(
        f"{API}/roadmaps/{roadmap_id}",
        headers=auth(teammate["access_token"]),
        json={"name": "3분기"},
    )
    assert response.status_code == 403


async def test_taking_a_roadmap_away_leaves_its_cards_on_the_board(
    client: httpx.AsyncClient, session
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    project = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "결제 시스템"},
    )
    project_id = project.json()["id"]
    roadmap_id = await _given_roadmap(session, project_id, data["user"]["id"], "2분기")

    task = await client.post(
        f"{API}/projects/{project_id}/tasks",
        headers=auth(data["access_token"]),
        json={"title": "PG사 계약서 정리", "roadmap_id": roadmap_id},
    )
    assert task.status_code == 200
    assert task.json()["roadmap_id"] == roadmap_id
    assert task.json()["roadmap_name"] == "2분기"

    removed = await client.delete(
        f"{API}/roadmaps/{roadmap_id}", headers=auth(data["access_token"])
    )
    assert removed.status_code == 204

    listing = await client.get(
        f"{API}/projects/{project_id}/tasks", headers=auth(data["access_token"])
    )
    body = listing.json()
    # The card stays on the board — only the link to the lane goes.
    assert len(body) == 1
    assert body[0]["title"] == "PG사 계약서 정리"
    assert body[0]["roadmap_id"] is None
    assert body[0]["roadmap_name"] is None


async def test_a_card_cannot_be_pinned_to_a_lane_of_another_project(
    client: httpx.AsyncClient, session
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    first = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "결제 시스템"},
    )
    second = await client.post(
        f"{API}/workspaces/{workspace_id}/projects",
        headers=auth(data["access_token"]),
        json={"name": "디자인 시스템"},
    )
    roadmap_id = await _given_roadmap(session, first.json()["id"], data["user"]["id"], "2분기")

    response = await client.post(
        f"{API}/projects/{second.json()['id']}/tasks",
        headers=auth(data["access_token"]),
        json={"title": "로고 고치기", "roadmap_id": roadmap_id},
    )
    assert response.status_code == 422
