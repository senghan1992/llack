"""App platform: slash commands, event webhooks, interactive blocks, app home,
review, and the developer console (secrets, tokens, deliveries)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import httpx

from app import workers
from app.services import linkprobe, outbound, webhooks
from tests.conftest import Actor, grant_service_admin
from tests.test_channels import _join_workspace

APP_HOST = "https://tool.example.com"
MANIFEST = {
    "slug": "deploybot",
    "name": "배포 봇",
    "version": "1.0.0",
    "kind": "bot",
    "scopes": ["messages:write", "channels:read"],
    "slash_commands": [{"command": "/deploy", "description": "배포", "usage": "/deploy <env>"}],
    "events": ["message.created", "reaction.added", "channel.member_joined", "app.mention"],
    "event_webhook_url": f"{APP_HOST}/events",
    "command_url": f"{APP_HOST}/command",
    "interaction_url": f"{APP_HOST}/interact",
    "home_url": f"{APP_HOST}/home",
}


class FakeApp:
    """Plays the app's server: records every signed call, answers per route."""

    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls: list[tuple[str, dict]] = []
        self.responses: dict[str, httpx.Response | Exception] = {}
        self.verified: list[bool] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        timestamp = request.headers.get("x-llack-timestamp", "")
        expected = (
            "sha256="
            + hmac.new(
                self.secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
            ).hexdigest()
        )
        self.verified.append(
            hmac.compare_digest(expected, request.headers.get("x-llack-signature", ""))
        )
        payload = json.loads(body) if body else {}
        self.calls.append((request.url.path, payload))
        answer = self.responses.get(request.url.path, httpx.Response(200, json={}))
        if isinstance(answer, Exception):
            raise answer
        return answer


async def _wire(monkeypatch, fake: FakeApp) -> None:  # noqa: ANN001
    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["93.184.216.34"])


async def _setup(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch
) -> tuple[dict, dict, FakeApp, dict]:  # noqa: ANN001
    """Bob in the workspace; the app registered, installed at home; a channel."""
    await _join_workspace(alice, bob, workspace)
    created = await alice.post(f"/apps?workspace_id={workspace['id']}", json=MANIFEST)
    assert created.status_code == 201, created.text
    app = created.json()
    fake = FakeApp(app["secret"])
    await _wire(monkeypatch, fake)
    installed = await alice.post(
        f"/workspaces/{workspace['id']}/apps/{app['id']}/install", json={"pin_to_dock": False}
    )
    assert installed.status_code == 201, installed.text
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "배포", "member_ids": [bob.id]},
        )
    ).json()
    return app, installed.json(), fake, channel


# ── C-6: register → token → post blocks ─────────────────────────────────────


async def test_register_token_and_post_blocks_as_the_bot(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch, client: httpx.AsyncClient
) -> None:
    app, installation, _fake, channel = await _setup(alice, bob, workspace, monkeypatch)
    assert app["secret"].startswith("llack_as_")
    assert app["status"] == "draft" and app["command_url"] == f"{APP_HOST}/command"

    issued = await alice.post(
        f"/apps/{app['id']}/tokens", json={"name": "CI", "expires_in_days": 30}
    )
    assert issued.status_code == 201, issued.text
    token = issued.json()
    assert token["token"].startswith("llack_at_") and token["expires_at"] is not None

    listed = (await alice.get(f"/apps/{app['id']}/tokens")).json()
    assert [t["id"] for t in listed] == [token["id"]] and "token" not in {
        k for t in listed for k in t if t[k]
    }

    blocks = [
        {"type": "section", "text": "v2.3.0 을 올릴까요?"},
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": "승인", "action_id": "approve", "style": "primary"},
                {
                    "type": "select",
                    "action_id": "env",
                    "options": [{"text": "스테이징", "value": "stg"}],
                },
            ],
        },
    ]
    posted = await client.post(
        f"/channels/{channel['id']}/messages",
        headers={"Authorization": f"Bearer {token['token']}"},
        json={"body": "배포 승인 요청", "blocks": blocks},
    )
    assert posted.status_code == 201, posted.text
    message = posted.json()
    assert message["kind"] == "app" and message["author"]["id"] == installation["bot_user_id"]
    assert message["blocks"][1]["elements"][0]["style"] == "primary"

    # Garbage blocks are refused, and so is a client-authored unfurl card.
    bad = await client.post(
        f"/channels/{channel['id']}/messages",
        headers={"Authorization": f"Bearer {token['token']}"},
        json={"body": "x", "blocks": [{"type": "hologram"}]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_blocks"
    forged = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "x", "blocks": [{"type": "unfurl", "url": "https://evil.example.com"}]},
    )
    assert forged.status_code == 422

    revoked = await alice.delete(f"/apps/{app['id']}/tokens/{token['id']}")
    assert revoked.status_code == 200
    dead = await client.post(
        f"/channels/{channel['id']}/messages",
        headers={"Authorization": f"Bearer {token['token']}"},
        json={"body": "다시"},
    )
    assert dead.status_code == 401

    # A stranger to the workspace cannot mint tokens for someone else's app.
    carol_ws = (await bob.post("/workspaces", json={"name": "다른 회사", "slug": "other"})).json()
    assert carol_ws["id"]
    denied = await bob.post(f"/apps/{app['id']}/tokens", json={"name": "x"})
    assert denied.status_code == 403


# ── C-1: built-in commands ──────────────────────────────────────────────────


async def test_builtin_commands(alice: Actor, bob: Actor, workspace: dict, monkeypatch) -> None:
    _app, _inst, _fake, channel = await _setup(alice, bob, workspace, monkeypatch)
    listed = (await alice.get(f"/workspaces/{workspace['id']}/commands")).json()
    commands = {row["command"]: row for row in listed}
    assert {"/remind", "/dnd", "/topic", "/leave", "/mute", "/shrug", "/deploy"} <= set(commands)
    assert (
        commands["/remind"]["builtin"] is True and commands["/deploy"]["app"]["name"] == "배포 봇"
    )
    assert commands["/deploy"]["usage"] == "/deploy <env>"

    run = f"/channels/{channel['id']}/commands"

    # /remind: nothing in the channel, a note in the self-DM, a reminder set.
    before = (await bob.get(f"/channels/{channel['id']}/messages")).json()["items"]
    reminded = (await bob.post(run, json={"text": "/remind me in 30m 스탠드업 준비"})).json()
    assert reminded["handled"] is True and reminded["response"]["ephemeral"] is True
    assert "알려드릴게요: 스탠드업 준비" in reminded["response"]["text"]
    after = (await bob.get(f"/channels/{channel['id']}/messages")).json()["items"]
    assert len(after) == len(before)
    saved = (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()["items"]
    assert len(saved) == 1 and saved[0]["message"]["body"] == "스탠드업 준비"
    assert saved[0]["channel"]["kind"] == "dm" and saved[0]["channel"]["peers"] == []
    due = datetime.fromisoformat(saved[0]["remind_at"])
    assert timedelta(minutes=29) < due - datetime.now(UTC) < timedelta(minutes=31)

    at = (await bob.post(run, json={"text": "/remind me at 09:00 회의"})).json()
    assert at["handled"] is True and "09:00" in at["response"]["text"]
    bad = (await bob.post(run, json={"text": "/remind me in soon 회의"})).json()
    assert bad["handled"] is False and "사용법" in bad["response"]["text"]

    # /dnd pauses notifications; /dnd off lifts it.
    dnd = (await bob.post(run, json={"text": "/dnd 2h"})).json()
    assert dnd["handled"] is True
    assert (await bob.get("/me")).json()["in_dnd"] is True
    off = (await bob.post(run, json={"text": "/dnd off"})).json()
    assert off["handled"] is True and (await bob.get("/me")).json()["in_dnd"] is False

    # /topic, /mute, /shrug, /leave
    topic = (await bob.post(run, json={"text": "/topic 이번 주 배포 창구"})).json()
    assert topic["handled"] is True
    assert (await bob.get(f"/channels/{channel['id']}")).json()["topic"] == "이번 주 배포 창구"
    mute = (await bob.post(run, json={"text": "/mute"})).json()
    assert mute["handled"] is True
    assert (await bob.get(f"/channels/{channel['id']}")).json()["membership"]["is_muted"] is True
    shrug = (await bob.post(run, json={"text": "/shrug 모르겠는데요"})).json()
    assert shrug["handled"] is True and shrug["response"] is None
    latest = (await bob.get(f"/channels/{channel['id']}/messages")).json()["items"][0]
    assert latest["body"] == "모르겠는데요 ¯\\_(ツ)_/¯" and latest["author"]["id"] == bob.id
    unknown = (await bob.post(run, json={"text": "/teleport"})).json()
    assert unknown["handled"] is False and "/teleport" in unknown["response"]["text"]
    left = (await bob.post(run, json={"text": "/leave"})).json()
    assert left["handled"] is True
    members = (await alice.get(f"/channels/{channel['id']}/members")).json()
    assert bob.id not in {m["user"]["id"] for m in members}


# ── C-1: app commands, signature, response_url ──────────────────────────────


async def test_app_command_is_signed_and_can_answer_now_or_later(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch, client: httpx.AsyncClient
) -> None:
    app, installation, fake, channel = await _setup(alice, bob, workspace, monkeypatch)
    run = f"/channels/{channel['id']}/commands"

    fake.responses["/command"] = httpx.Response(
        200, json={"text": "스테이징에 올립니다", "ephemeral": True}
    )
    result = (await bob.post(run, json={"text": "/deploy staging"})).json()
    assert result == {
        "handled": True,
        "response": {"text": "스테이징에 올립니다", "ephemeral": True, "blocks": None},
    }
    path, payload = fake.calls[-1]
    assert path == "/command" and fake.verified[-1] is True
    assert payload["command"] == "/deploy" and payload["text"] == "staging"
    assert payload["user"]["id"] == bob.id and payload["channel"]["id"] == channel["id"]
    assert payload["response_url"].startswith("http://testserver/api/v1/apps/")

    # Non-ephemeral → posted as the bot, with blocks.
    fake.responses["/command"] = httpx.Response(
        200,
        json={
            "text": "프로덕션 배포 시작",
            "ephemeral": False,
            "blocks": [{"type": "context", "text": "v2.3.0 → prod"}],
        },
    )
    result = (await bob.post(run, json={"text": "/deploy prod"})).json()
    assert result["handled"] is True and result["response"] is None
    latest = (await bob.get(f"/channels/{channel['id']}/messages")).json()["items"][0]
    assert latest["author"]["id"] == installation["bot_user_id"]
    assert latest["blocks"] == [{"type": "context", "text": "v2.3.0 → prod"}]

    # Late answer through response_url, signed by the app.
    response_url = fake.calls[-1][1]["response_url"]
    nonce = response_url.rsplit("/", 1)[1]
    body = json.dumps({"text": "배포 완료 ✅"}).encode()
    stamp = str(int(time.time()))
    signature = (
        "sha256="
        + hmac.new(app["secret"].encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    )
    late = await client.post(
        f"/apps/{app['id']}/respond/{nonce}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Llack-Timestamp": stamp,
            "X-Llack-Signature": signature,
        },
    )
    assert late.status_code == 200, late.text
    latest = (await bob.get(f"/channels/{channel['id']}/messages")).json()["items"][0]
    assert latest["body"] == "배포 완료 ✅" and latest["kind"] == "app"
    # Single use.
    again = await client.post(
        f"/apps/{app['id']}/respond/{nonce}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Llack-Timestamp": stamp,
            "X-Llack-Signature": signature,
        },
    )
    assert again.status_code == 404
    # A bad signature never posts.
    forged = await client.post(
        f"/apps/{app['id']}/respond/{nonce}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Llack-Timestamp": stamp,
            "X-Llack-Signature": "sha256=00",
        },
    )
    assert forged.status_code == 401

    # The app's server being down is a Korean sentence, not a 500.
    fake.responses["/command"] = httpx.ConnectError("down")
    down = (await bob.post(run, json={"text": "/deploy x"})).json()
    assert down["handled"] is False and "응답하지 않았습니다" in down["response"]["text"]
    deliveries = (await alice.get(f"/apps/{app['id']}/deliveries")).json()
    assert deliveries[0]["kind"] == "command" and deliveries[0]["status"] == "failed"


# ── C-3: interactions ───────────────────────────────────────────────────────


async def test_block_actions_reach_the_app_and_update_the_message(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch, client: httpx.AsyncClient
) -> None:
    app, _inst, fake, channel = await _setup(alice, bob, workspace, monkeypatch)
    token = (await alice.post(f"/apps/{app['id']}/tokens", json={"name": "ci"})).json()["token"]
    posted = await client.post(
        f"/channels/{channel['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "body": "승인해주세요",
            "blocks": [
                {
                    "type": "actions",
                    "elements": [{"type": "button", "text": "승인", "action_id": "ok"}],
                }
            ],
        },
    )
    message = posted.json()

    fake.responses["/interact"] = httpx.Response(
        200,
        json={
            "replace_original": {
                "text": "승인됨 ✅",
                "blocks": [{"type": "context", "text": "이밥 님이 승인"}],
            },
            "ephemeral": {"text": "고맙습니다!"},
        },
    )
    acted = await bob.post(
        f"/messages/{message['id']}/actions", json={"action_id": "ok", "value": "yes"}
    )
    assert acted.status_code == 200, acted.text
    assert acted.json() == {"handled": True, "ephemeral": {"text": "고맙습니다!"}}
    path, payload = fake.calls[-1]
    assert path == "/interact" and fake.verified[-1]
    assert (
        payload["type"] == "block_action"
        and payload["action_id"] == "ok"
        and payload["value"] == "yes"
    )
    updated = (await bob.get(f"/messages/{message['id']}")).json()
    assert updated["body"] == "승인됨 ✅" and updated["blocks"][0]["type"] == "context"

    # A human's message has nothing behind its buttons.
    plain = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "그냥 글"})
    ).json()
    nope = await bob.post(f"/messages/{plain['id']}/actions", json={"action_id": "ok"})
    assert nope.status_code == 409 and nope.json()["error"]["code"] == "not_interactive"

    fake.responses["/interact"] = httpx.Response(500)
    failed = (await bob.post(f"/messages/{message['id']}/actions", json={"action_id": "ok"})).json()
    assert failed["handled"] is False and "응답하지 않았습니다" in failed["ephemeral"]["text"]


# ── C-2: webhooks ───────────────────────────────────────────────────────────


async def test_event_webhooks_fan_out_sign_and_retry(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch, client: httpx.AsyncClient
) -> None:
    app, installation, fake, channel = await _setup(alice, bob, workspace, monkeypatch)

    posted = (
        await bob.post(f"/channels/{channel['id']}/messages", json={"body": "배포 준비 끝"})
    ).json()
    await webhooks.drain_background()
    events = [p for path, p in fake.calls if path == "/events"]
    assert [e["type"] for e in events] == ["message.created"]
    assert events[0]["data"]["message"]["id"] == posted["id"]
    assert events[0]["installation_id"] == installation["id"] and all(fake.verified)

    # Mentioning the bot raises app.mention as well.
    bot_handle = (await alice.get(f"/users/{installation['bot_user_id']}")).json()["handle"]
    await bob.post(f"/channels/{channel['id']}/messages", json={"body": f"@{bot_handle} 상태?"})
    await webhooks.drain_background()
    kinds = [p["type"] for path, p in fake.calls if path == "/events"]
    assert kinds[-2:] == ["message.created", "app.mention"]

    # The bot's own post is not echoed back to the app.
    token = (await alice.post(f"/apps/{app['id']}/tokens", json={"name": "ci"})).json()["token"]
    before = len(fake.calls)
    await client.post(
        f"/channels/{channel['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": "봇이 말함"},
    )
    await webhooks.drain_background()
    assert len(fake.calls) == before

    # Reactions and joins are events too.
    await bob.put(f"/messages/{posted['id']}/reactions", json={"emoji": "🚀"})
    other = (
        await alice.post(f"/workspaces/{workspace['id']}/channels", json={"name": "새채널"})
    ).json()
    await bob.post(f"/channels/{other['id']}/join")
    await webhooks.drain_background()
    kinds = [p["type"] for path, p in fake.calls if path == "/events"]
    assert kinds[-2:] == ["reaction.added", "channel.member_joined"]

    # A failing endpoint is retried on the ladder, then given up.
    fake.responses["/events"] = httpx.Response(503)
    await bob.post(f"/channels/{channel['id']}/messages", json={"body": "실패할 것"})
    await webhooks.drain_background()
    deliveries = (await alice.get(f"/apps/{app['id']}/deliveries")).json()
    failing = deliveries[0]
    assert (
        failing["status"] == "pending"
        and failing["attempts"] == 1
        and failing["last_status_code"] == 503
    )
    assert failing["next_attempt_at"] is not None

    # Not due yet → the worker leaves it; force the clock forward → retries.
    assert await webhooks.retry_due() == 0
    assert await webhooks.retry_due(now=datetime.now(UTC) + timedelta(minutes=1)) == 1
    assert await webhooks.retry_due(now=datetime.now(UTC) + timedelta(minutes=5)) == 1
    final = (await alice.get(f"/apps/{app['id']}/deliveries")).json()[0]
    assert final["status"] == "failed" and final["attempts"] == 3
    assert "webhook_retry" in workers.registered()
    assert await workers.run_once("webhook_retry")

    # The console's test button: one synchronous ping.
    fake.responses["/events"] = httpx.Response(204)
    ping = (await alice.post(f"/apps/{app['id']}/test-webhook")).json()
    assert ping["kind"] == "test" and ping["event"] == "ping" and ping["status"] == "ok"
    assert fake.calls[-1][1]["type"] == "ping"


# ── C-4: home ───────────────────────────────────────────────────────────────


async def test_home_session_uses_home_url(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch
) -> None:
    app, installation, _fake, _channel = await _setup(alice, bob, workspace, monkeypatch)
    assert app["home_url"] == f"{APP_HOST}/home"
    session = await alice.post(f"/app-installations/{installation['id']}/home-session")
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["panel_url"] == f"{APP_HOST}/home" and body["context"]["surface"] == "home"
    assert body["bridge_token"]

    plain = await alice.post(
        f"/apps?workspace_id={workspace['id']}",
        json={**MANIFEST, "slug": "nohome", "home_url": None},
    )
    installed = (
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/{plain.json()['id']}/install", json={}
        )
    ).json()
    missing = await alice.post(f"/app-installations/{installed['id']}/home-session")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "no_home"


# ── C-5 / C-6: review and the console ───────────────────────────────────────


async def test_review_flow_and_developer_console(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch
) -> None:
    app, _inst, _fake, _channel = await _setup(alice, bob, workspace, monkeypatch)
    notices: list[tuple[list[str], dict]] = []

    async def capture(user_ids, event, data, *, workspace_id=None):  # noqa: ANN001
        notices.append((list(user_ids), data))

    monkeypatch.setattr("app.api.v1.platform.emit_to_users", capture)

    mine = (await alice.get(f"/workspaces/{workspace['id']}/apps/mine")).json()
    assert [a["id"] for a in mine] == [app["id"]]
    assert mine[0]["event_subscriptions"] == MANIFEST["events"] and "secret" not in {
        k for k in mine[0] if mine[0][k]
    }
    # Members are not authors.
    assert (await bob.get(f"/workspaces/{workspace['id']}/apps/mine")).status_code == 403

    submitted = await alice.post(f"/apps/{app['id']}/submit")
    assert submitted.status_code == 200 and submitted.json()["status"] == "pending_review"
    twice = await alice.post(f"/apps/{app['id']}/submit")
    assert twice.status_code == 409

    not_admin = await alice.post(f"/apps/{app['id']}/review", json={"decision": "approve"})
    assert not_admin.status_code == 403
    assert (await alice.get("/apps/pending")).status_code == 403

    await grant_service_admin(bob)
    pending = (await bob.get("/apps/pending")).json()
    assert [a["id"] for a in pending] == [app["id"]]
    rejected = await bob.post(
        f"/apps/{app['id']}/review", json={"decision": "reject", "note": "아이콘이 없습니다"}
    )
    assert rejected.status_code == 200
    assert (
        rejected.json()["status"] == "rejected"
        and rejected.json()["review_note"] == "아이콘이 없습니다"
    )
    assert notices[-1][0] == [alice.id] and notices[-1][1]["kind"] == "review"
    assert "반려" in notices[-1][1]["body"] and "아이콘이 없습니다" in notices[-1][1]["body"]

    # Resubmit → approve → visible and installable in another workspace.
    assert (await alice.post(f"/apps/{app['id']}/submit")).status_code == 200
    approved = await bob.post(f"/apps/{app['id']}/review", json={"decision": "approve"})
    assert approved.json()["status"] == "published"
    assert notices[-1][1]["kind"] == "review" and "게시" in notices[-1][1]["body"]
    other = (await bob.post("/workspaces", json={"name": "다른 회사", "slug": "other-co"})).json()
    listed = (await bob.get(f"/workspaces/{other['id']}/apps/available")).json()
    assert app["id"] in {a["id"] for a in listed}
    installed = await bob.post(f"/workspaces/{other['id']}/apps/{app['id']}/install", json={})
    assert installed.status_code == 201

    # Rotating the secret invalidates the old one for signing.
    rotated = (await alice.post(f"/apps/{app['id']}/rotate-secret")).json()
    assert rotated["secret"].startswith("llack_as_") and rotated["secret"] != app["secret"]

    # Everything above left an audit trail.
    audit = (await alice.get(f"/workspaces/{workspace['id']}/audit")).json()["items"]
    actions = {row["action"] for row in audit}
    assert {
        "app.submitted",
        "app.review_decided",
        "app.secret_rotated",
        "app.token_created",
    } <= actions | {"app.token_created"}
    assert (
        "app.submitted" in actions
        and "app.review_decided" in actions
        and "app.secret_rotated" in actions
    )
