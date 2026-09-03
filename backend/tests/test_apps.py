"""The mini-app platform: manifests, scopes, panel sessions and the bridge API."""

from __future__ import annotations

import httpx

from tests.conftest import Actor, grant_service_admin
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
    """Register, submit and approve — publication is a review outcome now."""
    body = {**MANIFEST, **(manifest or {})}
    created = await alice.post(
        f"/apps?owner_workspace_id={workspace['id']}", json=body
    )
    assert created.status_code == 201, created.text
    app = created.json()
    submitted = await alice.post(f"/apps/{app['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    await grant_service_admin(alice)
    approved = await alice.post(f"/apps/{app['id']}/review", json={"decision": "approve"})
    assert approved.status_code == 200, approved.text
    return approved.json()


async def test_register_requires_a_panel_url_for_a_panel_app(
    alice: Actor, workspace: dict
) -> None:
    broken = {**MANIFEST, "slug": "no-panel", "kind": "panel", "panel_url": None}
    response = await alice.post(f"/apps?owner_workspace_id={workspace['id']}", json=broken)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "manifest_missing_panel_url"


async def test_a_draft_app_is_in_its_own_directory_only(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    """A team tries its own app long before review: at home it is listed and
    installable as a draft; elsewhere it does not exist until published."""
    created = await alice.post(f"/apps?owner_workspace_id={workspace['id']}", json=MANIFEST)
    app = created.json()
    assert app["status"] == "draft"
    assert app["secret"].startswith("llack_as_")  # shown once, here

    listed = await alice.get(f"/workspaces/{workspace['id']}/apps/available")
    assert app["id"] in {a["id"] for a in listed.json()}

    # An author cannot publish by fiat any more.
    fiat = await alice.put(f"/apps/{app['id']}/status", json={"status": "published"})
    assert fiat.status_code == 403
    assert fiat.json()["error"]["code"] == "review_required"

    other = (await bob.post("/workspaces", json={"name": "다른 회사", "slug": "other-co"})).json()
    elsewhere = await bob.get(f"/workspaces/{other['id']}/apps/available")
    assert app["id"] not in {a["id"] for a in elsewhere.json()}


async def test_an_unpublished_app_is_invisible_to_another_workspace(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    """Before review an app belongs to the team that wrote it; after approval
    it is in every directory. `owner_workspace_id` records authorship."""
    created = await alice.post(f"/apps?owner_workspace_id={workspace['id']}", json=MANIFEST)
    app = created.json()
    other = (await bob.post("/workspaces", json={"name": "다른 회사", "slug": "other-co"})).json()

    listed = await bob.get(f"/workspaces/{other['id']}/apps/available")
    assert app["id"] not in {a["id"] for a in listed.json()}

    denied = await bob.post(
        f"/workspaces/{other['id']}/apps/{app['id']}/install", json={}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "app_not_published"


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


async def test_members_add_link_apps_and_guests_do_not(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    """A link app holds no permissions, so any member may add one; a guest is
    a visitor and does not get to furnish the dock."""
    await _join_workspace(alice, bob, workspace)
    added = await bob.post(
        f"/workspaces/{workspace['id']}/apps/link",
        json={"name": "위키", "url": "https://wiki.example.com"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["app"]["kind"] == "link"

    members = (await alice.get(f"/workspaces/{workspace['id']}/members")).json()
    bob_member = next(m for m in members if m["user"]["id"] == bob.id)
    demoted = await alice.patch(
        f"/workspaces/{workspace['id']}/members/{bob_member['id']}", json={"role": "guest"}
    )
    assert demoted.status_code == 200
    denied = await bob.post(
        f"/workspaces/{workspace['id']}/apps/link",
        json={"name": "피그마", "url": "https://figma.example.com"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "guest_cannot_add_apps"


async def test_the_person_who_added_a_link_app_can_rename_and_remove_it(
    alice: Actor, bob: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    from tests.conftest import register

    await _join_workspace(alice, bob, workspace)
    carol = await register(client, "carol@example.com", "박캐롤")
    await _join_workspace(alice, carol, workspace)

    installation = (
        await bob.post(
            f"/workspaces/{workspace['id']}/apps/link",
            json={"name": "피그마", "url": "https://figma.example.com/file/abc"},
        )
    ).json()
    iid = installation["id"]

    # Another member: hands off.
    assert (
        await carol.patch(f"/app-installations/{iid}", json={"name": "내 것"})
    ).status_code == 403
    assert (await carol.delete(f"/app-installations/{iid}")).status_code == 403

    # The installer: rename + icon.
    renamed = await bob.patch(
        f"/app-installations/{iid}",
        json={"name": "디자인 시스템", "icon_url": "https://figma.example.com/favicon.ico"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["app"]["name"] == "디자인 시스템"
    assert renamed.json()["app"]["icon_url"] == "https://figma.example.com/favicon.ico"
    listed = (await alice.get(f"/workspaces/{workspace['id']}/apps")).json()
    assert any(i["app"]["name"] == "디자인 시스템" for i in listed)

    # The installer may remove it; an admin always may (checked on a second tile).
    assert (await bob.delete(f"/app-installations/{iid}")).status_code == 200
    second = (
        await bob.post(
            f"/workspaces/{workspace['id']}/apps/link",
            json={"name": "대시보드", "url": "https://grafana.example.com"},
        )
    ).json()
    assert (await alice.delete(f"/app-installations/{second['id']}")).status_code == 200


async def test_renaming_is_for_link_apps_only(alice: Actor, workspace: dict) -> None:
    app = await _publish(alice, workspace)
    installed = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/{app['id']}/install",
            json={"granted_scopes": [], "config": {}, "pin_to_dock": True},
        )
    ).json()
    denied = await alice.patch(f"/app-installations/{installed['id']}", json={"name": "다른 이름"})
    assert denied.status_code == 422
    assert denied.json()["error"]["code"] == "not_a_link_app"


async def _mock_probe(monkeypatch, handler) -> None:  # noqa: ANN001
    from app.services import linkprobe

    monkeypatch.setattr(linkprobe, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["93.184.216.34"])


async def test_link_probe_reads_frame_headers_and_title(
    alice: Actor, workspace: dict, monkeypatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "deny.example.com":
            return httpx.Response(200, headers={"X-Frame-Options": "DENY"}, text="<title>x</title>")
        if host == "csp.example.com":
            return httpx.Response(
                200,
                headers={"Content-Security-Policy": "default-src 'self'; frame-ancestors 'self'"},
                text="<html><title>CSP</title></html>",
            )
        if host == "open.example.com":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                text="<html><head><title>  우리 &amp; 대시보드 </title></head></html>",
            )
        return httpx.Response(200, text="")

    await _mock_probe(monkeypatch, handler)
    probe = f"/workspaces/{workspace['id']}/apps/link/probe"

    deny = (await alice.post(probe, json={"url": "https://deny.example.com/"})).json()
    assert deny == {
        "embeddable": False,
        "reason": "x_frame_options",
        "final_url": "https://deny.example.com/",
        "title": "x",
    }
    csp = (await alice.post(probe, json={"url": "https://csp.example.com/app"})).json()
    assert csp["embeddable"] is False and csp["reason"] == "csp_frame_ancestors"
    open_site = (await alice.post(probe, json={"url": "https://open.example.com/"})).json()
    assert open_site["embeddable"] is True
    assert open_site["reason"] is None
    assert open_site["title"] == "우리 & 대시보드"


async def test_link_probe_reports_unreachable_and_refuses_private_hosts(
    alice: Actor, workspace: dict, monkeypatch
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise httpx.ConnectError("boom")

    await _mock_probe(monkeypatch, handler)
    probe = f"/workspaces/{workspace['id']}/apps/link/probe"

    down = (await alice.post(probe, json={"url": "https://down.example.com/"})).json()
    assert down == {"embeddable": None, "reason": "unreachable", "final_url": None, "title": None}

    # Loopback, RFC1918, link-local and localhost never reach the transport.
    for url in (
        "http://127.0.0.1:8000/admin",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost/",
        "http://[::1]/",
    ):
        refused = await alice.post(probe, json={"url": url})
        assert refused.status_code == 403, url
        assert refused.json()["error"]["code"] == "url_not_allowed"
    assert calls == ["https://down.example.com/"]

    # A public hostname that resolves to a private address is refused too.
    from app.services import linkprobe

    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["10.1.2.3"])
    sneaky = await alice.post(probe, json={"url": "https://intranet.example.com/"})
    assert sneaky.status_code == 403
    assert calls == ["https://down.example.com/"]


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


async def test_the_same_url_does_not_become_a_second_link_app(
    alice: Actor, workspace: dict
) -> None:
    first = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/link",
            json={"name": "위키", "url": "https://wiki.example.com/home"},
        )
    ).json()
    second = await alice.post(
        f"/workspaces/{workspace['id']}/apps/link",
        json={"name": "위키 다시", "url": "https://wiki.example.com/home"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first["id"], "같은 URL 은 같은 설치여야 합니다"
    listed = (await alice.get(f"/workspaces/{workspace['id']}/apps")).json()
    assert sum(1 for i in listed if i["app"]["panel_url"] == "https://wiki.example.com/home") == 1
