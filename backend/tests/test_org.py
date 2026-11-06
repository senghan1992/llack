"""The organization of a workspace: units, people in them, and their managers."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.models.org import OrgUnitManager
from tests.conftest import API, auth, join_workspace, signup


async def _unit(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: str,
    name: str,
    parent_id: str | None = None,
    **overrides,
) -> dict:
    payload: dict = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    payload.update(overrides)
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/org/units",
        headers=auth(token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_owner_builds_an_org_tree(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    token = owner["access_token"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    unit = await _unit(client, token, workspace_id, "프로덕트 개발부")
    assert unit["id"].startswith("org_")
    assert unit["parent_id"] is None
    assert unit["kind"] == "team"
    assert unit["depth"] == 0
    assert unit["member_count"] == 0
    assert unit["child_count"] == 0

    renamed = await client.patch(
        f"{API}/org/units/{unit['id']}",
        headers=auth(token),
        json={"name": "프로덕트 개발팀", "description": "만드는 곳"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "프로덕트 개발팀"
    assert renamed.json()["description"] == "만드는 곳"

    added = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=auth(token),
        json={"user_id": teammate["user"]["id"]},
    )
    assert added.status_code == 204, added.text

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=auth(token))
    assert overview.status_code == 200
    body = overview.json()
    assert len(body["units"]) == 1
    shown = body["units"][0]
    assert shown["id"] == unit["id"]
    assert shown["member_count"] == 1
    assert [person["id"] for person in shown["members"]] == [teammate["user"]["id"]]
    assert shown["can_manage"] is True
    # The owner looks after every unit, but is not *appointed* to this one.
    assert shown["is_manager"] is False
    assert body["my_role"] == "owner"
    assert body["can_manage_admins"] is True
    assert body["managed_unit_ids"] == [unit["id"]]
    assert [admin["user"]["id"] for admin in body["admins"]] == [owner["user"]["id"]]


async def test_a_plain_member_may_not_change_the_org(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    member = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    unit = await _unit(client, owner["access_token"], workspace_id, "개발팀")

    headers = auth(member["access_token"])

    reading = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=headers)
    assert reading.status_code == 200

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/org/units",
        headers=headers,
        json={"name": "새 조직"},
    )
    assert created.status_code == 403

    renamed = await client.patch(
        f"{API}/org/units/{unit['id']}",
        headers=headers,
        json={"name": "남의 조직"},
    )
    assert renamed.status_code == 403

    removed = await client.delete(f"{API}/org/units/{unit['id']}", headers=headers)
    assert removed.status_code == 403

    added = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=headers,
        json={"user_id": owner["user"]["id"]},
    )
    assert added.status_code == 403

    taken = await client.delete(
        f"{API}/org/units/{unit['id']}/members/{owner['user']['id']}",
        headers=headers,
    )
    assert taken.status_code == 403

    appointed = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=headers,
        json={"user_id": member["user"]["id"]},
    )
    assert appointed.status_code == 403

    dismissed = await client.delete(
        f"{API}/org/units/{unit['id']}/managers/{owner['user']['id']}",
        headers=headers,
    )
    assert dismissed.status_code == 403


async def test_a_unit_manager_looks_after_their_own_subtree(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    manager = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    manager_headers = auth(manager["access_token"])

    root = await _unit(client, owner_token, workspace_id, "프로덕트 개발부")
    team = await _unit(client, owner_token, workspace_id, "개발팀", parent_id=root["id"])
    design = await _unit(client, owner_token, workspace_id, "디자인팀", parent_id=root["id"])
    squad = await _unit(client, owner_token, workspace_id, "백엔드 파트", parent_id=team["id"])

    appointed = await client.post(
        f"{API}/org/units/{team['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": manager["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    # The manager looks after their own unit and everything below it.
    renamed = await client.patch(
        f"{API}/org/units/{squad['id']}",
        headers=manager_headers,
        json={"name": "백엔드 파트 (개편)"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "백엔드 파트 (개편)"

    # A unit below their own is theirs to open.
    opened = await client.post(
        f"{API}/workspaces/{workspace_id}/org/units",
        headers=manager_headers,
        json={"name": "플랫폼 파트", "parent_id": squad["id"]},
    )
    assert opened.status_code == 200, opened.text

    # A sibling unit is not.
    refused = await client.patch(
        f"{API}/org/units/{design['id']}",
        headers=manager_headers,
        json={"name": "디자인팀 개편"},
    )
    assert refused.status_code == 403

    refused = await client.post(
        f"{API}/workspaces/{workspace_id}/org/units",
        headers=manager_headers,
        json={"name": "기획팀", "parent_id": design["id"]},
    )
    assert refused.status_code == 403

    # The top of the tree belongs to the workspace admins alone.
    refused = await client.post(
        f"{API}/workspaces/{workspace_id}/org/units",
        headers=manager_headers,
        json={"name": "새 본부"},
    )
    assert refused.status_code == 403

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=manager_headers)
    body = overview.json()
    assert body["my_role"] == "member"
    assert body["can_manage_admins"] is False
    assert set(body["managed_unit_ids"]) == {team["id"], squad["id"], opened.json()["id"]}
    assert design["id"] not in body["managed_unit_ids"]


async def test_a_unit_manager_may_appoint_a_manager_below_themselves(
    client: httpx.AsyncClient, session
) -> None:
    """Each level looks after the level below it — that is the whole point."""
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    manager = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    deputy = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    manager_headers = auth(manager["access_token"])

    team = await _unit(client, owner_token, workspace_id, "개발팀")
    squad = await _unit(client, owner_token, workspace_id, "백엔드 파트", parent_id=team["id"])
    other = await _unit(client, owner_token, workspace_id, "디자인팀")

    appointed = await client.post(
        f"{API}/org/units/{team['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": manager["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    # A manager of a level may name a manager of the level below.
    delegated = await client.post(
        f"{API}/org/units/{squad['id']}/managers",
        headers=manager_headers,
        json={"user_id": deputy["user"]["id"]},
    )
    assert delegated.status_code == 204, delegated.text

    # But not of a unit outside their own tree.
    refused = await client.post(
        f"{API}/org/units/{other['id']}/managers",
        headers=manager_headers,
        json={"user_id": deputy["user"]["id"]},
    )
    assert refused.status_code == 403

    # The deputy now looks after the squad alone.
    overview = await client.get(
        f"{API}/workspaces/{workspace_id}/org", headers=auth(deputy["access_token"])
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["managed_unit_ids"] == [squad["id"]]


async def test_a_unit_manager_may_not_change_workspace_roles(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    manager = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    manager_headers = auth(manager["access_token"])

    unit = await _unit(client, owner_token, workspace_id, "개발팀")
    appointed = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": manager["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    # Looking after an organization is not looking after the workspace.
    refused = await client.patch(
        f"{API}/workspaces/{workspace_id}/members/{owner['user']['id']}",
        headers=manager_headers,
        json={"role": "member"},
    )
    assert refused.status_code == 403


async def test_moving_a_unit_never_folds_the_tree(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    manager = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    root = await _unit(client, owner_token, workspace_id, "프로덕트 개발부")
    team = await _unit(client, owner_token, workspace_id, "개발팀", parent_id=root["id"])
    design = await _unit(client, owner_token, workspace_id, "디자인팀", parent_id=root["id"])
    squad = await _unit(client, owner_token, workspace_id, "백엔드 파트", parent_id=team["id"])

    appointed = await client.post(
        f"{API}/org/units/{team['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": manager["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    # A unit may not be hung below one of its own units.
    cycle = await client.patch(
        f"{API}/org/units/{root['id']}",
        headers=auth(owner_token),
        json={"parent_id": squad["id"]},
    )
    assert cycle.status_code == 409

    # A unit manager may not move a unit out of their own reach.
    out_of_scope = await client.patch(
        f"{API}/org/units/{squad['id']}",
        headers=auth(manager["access_token"]),
        json={"parent_id": design["id"]},
    )
    assert out_of_scope.status_code == 403

    # The workspace owner may.
    moved = await client.patch(
        f"{API}/org/units/{squad['id']}",
        headers=auth(owner_token),
        json={"parent_id": design["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] == design["id"]
    assert moved.json()["depth"] == 2


async def test_a_unit_with_people_or_children_is_not_deleted(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")

    root = await _unit(client, owner_token, workspace_id, "프로덕트 개발부")
    team = await _unit(client, owner_token, workspace_id, "개발팀", parent_id=root["id"])

    appointed = await client.post(
        f"{API}/org/units/{team['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": teammate["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    added = await client.post(
        f"{API}/org/units/{root['id']}/members",
        headers=auth(owner_token),
        json={"user_id": teammate["user"]["id"]},
    )
    assert added.status_code == 204, added.text

    # A unit with people in it stays.
    refused = await client.delete(f"{API}/org/units/{root['id']}", headers=auth(owner_token))
    assert refused.status_code == 409

    # A unit with a unit below it stays too.
    refused = await client.delete(f"{API}/org/units/{root['id']}", headers=auth(owner_token))
    assert refused.status_code == 409

    taken = await client.delete(
        f"{API}/org/units/{root['id']}/members/{teammate['user']['id']}",
        headers=auth(owner_token),
    )
    assert taken.status_code == 204, taken.text

    refused = await client.delete(f"{API}/org/units/{root['id']}", headers=auth(owner_token))
    assert refused.status_code == 409

    # The child unit goes first.
    removed_child = await client.delete(f"{API}/org/units/{team['id']}", headers=auth(owner_token))
    assert removed_child.status_code == 204, removed_child.text

    # Its managers go with it.
    rows = await session.scalars(
        select(OrgUnitManager).where(OrgUnitManager.org_unit_id == team["id"])
    )
    assert list(rows.all()) == []

    removed = await client.delete(f"{API}/org/units/{root['id']}", headers=auth(owner_token))
    assert removed.status_code == 204, removed.text

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=auth(owner_token))
    assert overview.json()["units"] == []


async def test_a_member_of_a_unit_gains_no_authority(client: httpx.AsyncClient, session) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    teammate = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    teammate_headers = auth(teammate["access_token"])

    unit = await _unit(client, owner_token, workspace_id, "개발팀")
    added = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=auth(owner_token),
        json={"user_id": teammate["user"]["id"]},
    )
    assert added.status_code == 204, added.text

    refused = await client.patch(
        f"{API}/org/units/{unit['id']}",
        headers=teammate_headers,
        json={"name": "자기 조직"},
    )
    assert refused.status_code == 403

    refused = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=teammate_headers,
        json={"user_id": owner["user"]["id"]},
    )
    assert refused.status_code == 403

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=teammate_headers)
    shown = overview.json()["units"][0]
    assert shown["member_count"] == 1
    assert shown["can_manage"] is False
    assert shown["can_appoint_managers"] is False
    assert overview.json()["managed_unit_ids"] == []


async def test_a_manager_cannot_appoint_themselves_but_may_dismiss_themselves(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    manager = await join_workspace(client, session, workspace_id, "jimin@hanbit.co.kr", "박지민")
    manager_headers = auth(manager["access_token"])

    unit = await _unit(client, owner_token, workspace_id, "개발팀")
    appointed = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": manager["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    # The manager is already the manager — they may not appoint themselves.
    refused = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=manager_headers,
        json={"user_id": manager["user"]["id"]},
    )
    assert refused.status_code == 403

    # But they may step down.
    dismissed = await client.delete(
        f"{API}/org/units/{unit['id']}/managers/{manager['user']['id']}",
        headers=manager_headers,
    )
    assert dismissed.status_code == 204, dismissed.text

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=manager_headers)
    assert overview.json()["units"][0]["managers"] == []
    assert overview.json()["managed_unit_ids"] == []


async def test_a_person_outside_the_workspace_is_not_put_in_a_unit(
    client: httpx.AsyncClient, session
) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    outsider = await signup(client, email="stranger@other.co.kr", name="외부인")

    unit = await _unit(client, owner["access_token"], workspace_id, "개발팀")
    refused = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=auth(owner["access_token"]),
        json={"user_id": outsider["user"]["id"]},
    )
    assert refused.status_code == 404


async def test_the_workspace_owner_may_stand_as_a_unit_manager(
    client: httpx.AsyncClient,
) -> None:
    """The owner often runs a unit themselves — the appointment is theirs to make."""
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    headers = auth(owner["access_token"])

    unit = await _unit(client, owner["access_token"], workspace_id, "개발팀")
    appointed = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=headers,
        json={"user_id": owner["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=headers)
    shown = overview.json()["units"][0]
    assert [person["id"] for person in shown["managers"]] == [owner["user"]["id"]]
    assert shown["is_manager"] is True


async def test_the_bootstrap_carries_the_organization(client: httpx.AsyncClient) -> None:
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    await _unit(client, owner["access_token"], workspace_id, "개발팀")

    bootstrap = await client.get(
        f"{API}/workspaces/{workspace_id}/bootstrap",
        headers=auth(owner["access_token"]),
    )
    assert bootstrap.status_code == 200, bootstrap.text
    org = bootstrap.json()["org"]
    assert org["unit_count"] == 1
    assert len(org["managed_unit_ids"]) == 1


async def test_a_removed_member_leaves_the_organization(client: httpx.AsyncClient, session) -> None:
    """A person who leaves the workspace leaves their seat and their
    appointment behind — otherwise the org keeps a ghost."""
    owner = await signup(client)
    workspace_id = owner["workspace"]["id"]
    owner_token = owner["access_token"]
    member = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")

    unit = await _unit(client, owner_token, workspace_id, "개발팀")
    seated = await client.post(
        f"{API}/org/units/{unit['id']}/members",
        headers=auth(owner_token),
        json={"user_id": member["user"]["id"]},
    )
    assert seated.status_code == 204, seated.text
    appointed = await client.post(
        f"{API}/org/units/{unit['id']}/managers",
        headers=auth(owner_token),
        json={"user_id": member["user"]["id"]},
    )
    assert appointed.status_code == 204, appointed.text

    removed = await client.delete(
        f"{API}/workspaces/{workspace_id}/members/{member['user']['id']}",
        headers=auth(owner_token),
    )
    assert removed.status_code == 204, removed.text

    overview = await client.get(f"{API}/workspaces/{workspace_id}/org", headers=auth(owner_token))
    shown = overview.json()["units"][0]
    assert shown["members"] == []
    assert shown["managers"] == []
    assert shown["member_count"] == 0
