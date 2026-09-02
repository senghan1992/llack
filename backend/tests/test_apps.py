"""The mini-app platform: manifests, scopes, panel sessions and the bridge API."""

from __future__ import annotations

import httpx

from tests.conftest import Actor
from tests.test_channels import _join_workspace

MANIFEST = {
    "slug": "standup",
    "name": "데일리 스탠드업",
    "version": "1.0.0",
    "tagline": "매일 아침 진행 상황을 모읍니다",
    "kind": "both",
    "panel_url": "https://apps.example.com/standup",
    "scopes": ["identity:read", "channels:read", "messages:write", "storage", "panel:ui"],
    "slash_commands": [{"command": "/standup", "description": "스탠드업 시작"}],
    "events": ["message.created"],
}


async def _publish(alice: Actor, workspace: dict, manifest: dict | None = None) -> dict:
    body = {**MANIFEST, **(manifest or {})}
    created = await alice.post(
        f"/apps?owner_workspace_id={workspace['id']}", json=body
    )
    assert created.status_code == 201, created.text
    app = created.json()
    published = await alice.put(f"/apps/{app['id']}/status", json={"status": "published"})
    assert published.status_code == 200
    return published.json()


async def test_register_requires_a_panel_url_for_a_panel_app(
    alice: Actor, workspace: dict
) -> None:
    broken = {**MANIFEST, "slug": "no-panel", "kind": "panel", "panel_url": None}
    response = await alice.post(f"/apps?owner_workspace_id={workspace['id']}", json=broken)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "manifest_missing_panel_url"


async def test_a_draft_app_is_not_in_the_directory_until_published(
    alice: Actor, workspace: dict
) -> None:
    created = await alice.post(f"/apps?owner_workspace_id={workspace['id']}", json=MANIFEST)
    app = created.json()
    assert app["status"] == "draft"

    listed = await alice.get(f"/workspaces/{workspace['id']}/apps/available")
    assert app["id"] not in {a["id"] for a in listed.json()}

    with_drafts = await alice.get(
        f"/workspaces/{workspace['id']}/apps/available?include_drafts=true"
    )
    assert app["id"] in {a["id"] for a in with_drafts.json()}


async def test_a_private_app_is_invisible_to_another_workspace(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    app = await _publish(alice, workspace)
    other = (await bob.post("/workspaces", json={"name": "다른 회사", "slug": "other-co"})).json()

    listed = await bob.get(f"/workspaces/{other['id']}/apps/available")
    assert app["id"] not in {a["id"] for a in listed.json()}

    denied = await bob.post(
        f"/workspaces/{other['id']}/apps/{app['id']}/install", json={}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "app_private"


async def test_install_grants_the_manifest_scopes_and_a_bot_identity(
    alice: Actor, workspace: dict
) -> None:
    app = await _publish(alice, workspace)
    installed = await alice.post(
        f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={"pin_to_dock": True}
    )
    assert installed.status_code == 201
    installation = installed.json()
    assert set(installation["granted_scopes"]) == set(MANIFEST["scopes"])
    assert installation["is_pinned"] is True
    # kind=both means the app posts messages, so it needs a bot user.
    assert installation["bot_user_id"] is not None

    dock = (await alice.get(f"/workspaces/{workspace['id']}/apps")).json()
    assert [i["app"]["slug"] for i in dock] == ["standup"]


async def test_scopes_can_be_narrowed_but_not_widened(alice: Actor, workspace: dict) -> None:
    app = await _publish(alice, workspace)

    narrowed = await alice.post(
        f"/workspaces/{workspace['id']}/apps/{app['id']}/install",
        json={"granted_scopes": ["identity:read", "storage"]},
    )
    assert narrowed.status_code == 201
    assert set(narrowed.json()["granted_scopes"]) == {"identity:read", "storage"}

    widened = await alice.patch(
        f"/app-installations/{narrowed.json()['id']}",
        json={"granted_scopes": ["identity:read", "files:write"]},
    )
    assert widened.status_code == 409
    assert widened.json()["error"]["code"] == "scope_not_requested"


async def test_only_a_workspace_admin_can_install(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    app = await _publish(alice, workspace)

    denied = await bob.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"


async def test_panel_session_mints_a_scoped_bridge_token(
    alice: Actor, workspace: dict
) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()

    session = await alice.post(f"/app-installations/{installation['id']}/panel-session")
    assert session.status_code == 200
    body = session.json()
    assert body["panel_url"] == MANIFEST["panel_url"]
    assert body["bridge_token"]
    assert body["context"]["user"]["id"] == alice.id
    assert body["context"]["workspace_id"] == workspace["id"]

    # The bridge token must not be usable as a normal user token.
    assert body["bridge_token"] != alice.tokens["access_token"]


async def test_bridge_context_and_scope_enforcement(
    alice: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/{app['id']}/install",
            json={"granted_scopes": ["identity:read", "channels:read"]},
        )
    ).json()
    token = (
        await alice.post(f"/app-installations/{installation['id']}/panel-session")
    ).json()["bridge_token"]
    app_headers = {"Authorization": f"Bearer {token}"}

    context = await client.get("/app-bridge/context", headers=app_headers)
    assert context.status_code == 200
    assert context.json()["workspace_id"] == workspace["id"]
    assert set(context.json()["granted_scopes"]) == {"identity:read", "channels:read"}

    # channels:read was granted.
    channels = await client.get("/app-bridge/channels", headers=app_headers)
    assert channels.status_code == 200
    assert {c["name"] for c in channels.json()} == {"general", "random"}

    # storage was not.
    denied = await client.get("/app-bridge/storage/anything", headers=app_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "missing_scope"
    assert denied.json()["error"]["details"]["required_scope"] == "storage"


async def test_narrowing_scopes_invalidates_an_already_minted_token(
    alice: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    """The installation row is authoritative, not the token's copy of scopes."""
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()
    token = (
        await alice.post(f"/app-installations/{installation['id']}/panel-session")
    ).json()["bridge_token"]
    app_headers = {"Authorization": f"Bearer {token}"}

    assert (await client.get("/app-bridge/channels", headers=app_headers)).status_code == 200

    await alice.patch(
        f"/app-installations/{installation['id']}", json={"granted_scopes": ["identity:read"]}
    )
    # Same token, scope now revoked.
    revoked = await client.get("/app-bridge/channels", headers=app_headers)
    assert revoked.status_code == 403
    assert revoked.json()["error"]["code"] == "missing_scope"


async def test_bridge_never_exposes_direct_messages(
    alice: Actor, bob: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    await _join_workspace(alice, bob, workspace)
    dm = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels/dm", json={"user_ids": [bob.id]}
        )
    ).json()

    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()
    token = (
        await alice.post(f"/app-installations/{installation['id']}/panel-session")
    ).json()["bridge_token"]

    channels = await client.get(
        "/app-bridge/channels", headers={"Authorization": f"Bearer {token}"}
    )
    assert dm["id"] not in {c["id"] for c in channels.json()}


async def test_app_posts_as_its_bot_user(
    alice: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()
    token = (
        await alice.post(f"/app-installations/{installation['id']}/panel-session")
    ).json()["bridge_token"]

    channel = (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()[0]
    posted = await client.post(
        "/app-bridge/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel_id": channel["id"], "body": "오늘 스탠드업을 시작합니다"},
    )
    assert posted.status_code == 201, posted.text
    message = posted.json()["message"]
    assert message["kind"] == "app"
    assert message["author"]["id"] == installation["bot_user_id"]
    assert message["author"]["is_bot"] is True
    assert message["app_id"] == app["id"]

    # It shows up in the channel for a human reader.
    history = (await alice.get(f"/channels/{channel['id']}/messages")).json()
    assert history["items"][0]["body"] == "오늘 스탠드업을 시작합니다"


async def test_server_token_lets_an_app_post_without_a_panel(
    alice: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()

    issued = await alice.post(
        f"/app-installations/{installation['id']}/tokens", json={"name": "ci"}
    )
    assert issued.status_code == 201
    raw = issued.json()["token"]
    assert raw.startswith("llack_at_")
    assert issued.json()["token_prefix"] == raw[:14]

    channel = (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()[0]
    posted = await client.post(
        "/app-bridge/messages",
        headers={"Authorization": f"Bearer {raw}"},
        json={"channel_id": channel["id"], "body": "빌드가 통과했습니다 ✅"},
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["message"]["kind"] == "app"


async def test_app_storage_round_trip_and_isolation(
    alice: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()
    token = (
        await alice.post(f"/app-installations/{installation['id']}/panel-session")
    ).json()["bridge_token"]
    app_headers = {"Authorization": f"Bearer {token}"}

    stored = await client.put(
        "/app-bridge/storage/schedule",
        headers=app_headers,
        json={"value": {"time": "09:30", "days": ["mon", "tue"]}},
    )
    assert stored.status_code == 200
    assert stored.json()["value"]["time"] == "09:30"

    fetched = await client.get("/app-bridge/storage/schedule", headers=app_headers)
    assert fetched.json()["value"]["days"] == ["mon", "tue"]

    # Per-user scope is a separate namespace from the shared workspace scope.
    await client.put(
        "/app-bridge/storage/schedule",
        headers=app_headers,
        json={"value": {"time": "10:00"}, "scope_key": f"user:{alice.id}"},
    )
    shared = await client.get("/app-bridge/storage/schedule", headers=app_headers)
    assert shared.json()["value"]["time"] == "09:30"
    mine = await client.get(
        f"/app-bridge/storage/schedule?scope_key=user:{alice.id}", headers=app_headers
    )
    assert mine.json()["value"]["time"] == "10:00"

    assert (
        await client.delete("/app-bridge/storage/schedule", headers=app_headers)
    ).status_code == 200
    assert (
        await client.get("/app-bridge/storage/schedule", headers=app_headers)
    ).status_code == 404


async def test_uninstall_removes_from_the_dock(alice: Actor, workspace: dict) -> None:
    app = await _publish(alice, workspace)
    installation = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()

    assert (await alice.delete(f"/app-installations/{installation['id']}")).status_code == 200
    assert (await alice.get(f"/workspaces/{workspace['id']}/apps")).json() == []


async def test_reinstall_upgrades_in_place(alice: Actor, workspace: dict) -> None:
    app = await _publish(alice, workspace)
    first = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/{app['id']}/install",
            json={"granted_scopes": ["identity:read"]},
        )
    ).json()
    second = (
        await alice.post(f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={})
    ).json()

    assert second["id"] == first["id"]
    assert set(second["granted_scopes"]) == set(MANIFEST["scopes"])
    assert len((await alice.get(f"/workspaces/{workspace['id']}/apps")).json()) == 1


# ── Link apps: a URL is enough ───────────────────────────────────────────────


async def test_a_url_becomes_a_pinned_link_app_in_one_post(
    alice: Actor, workspace: dict
) -> None:
    added = await alice.post(
        f"/workspaces/{workspace['id']}/apps/link",
        json={"name": "사내 위키", "url": "https://wiki.example.com/home"},
    )
    assert added.status_code == 201, added.text
    installation = added.json()
    assert installation["is_pinned"] is True
    assert installation["app"]["kind"] == "link"
    assert installation["app"]["panel_url"] == "https://wiki.example.com/home"
    assert installation["app"]["tagline"] == "wiki.example.com"
    assert installation["granted_scopes"] == []

    listed = (await alice.get(f"/workspaces/{workspace['id']}/apps")).json()
    assert any(i["id"] == installation["id"] for i in listed)


async def test_adding_a_link_app_requires_a_workspace_admin(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    denied = await bob.post(
        f"/workspaces/{workspace['id']}/apps/link",
        json={"name": "위키", "url": "https://wiki.example.com"},
    )
    assert denied.status_code == 403


async def test_a_link_app_refuses_non_http_urls(alice: Actor, workspace: dict) -> None:
    for url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.example.com"):
        response = await alice.post(
            f"/workspaces/{workspace['id']}/apps/link",
            json={"name": "이상한 앱", "url": url},
        )
        assert response.status_code == 422, url


async def test_a_link_app_never_gets_a_bridge_token(alice: Actor, workspace: dict) -> None:
    installation = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/link",
            json={"name": "사내 위키", "url": "https://wiki.example.com"},
        )
    ).json()
    session = await alice.post(
        f"/app-installations/{installation['id']}/panel-session"
    )
    assert session.status_code == 403
    assert session.json()["error"]["code"] == "app_without_panel"
