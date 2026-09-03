"""Usability batch: 방해 금지, 나중에/리마인더, 초대 메일, 링크 카드, @here."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app import workers
from app.core.config import settings
from app.core.enums import PresenceState
from app.realtime.presence import get_presence_store
from app.services import linkprobe, unfurl
from app.services.dnd import in_dnd
from tests.conftest import Actor, register
from tests.test_channels import _join_workspace


async def _setup(alice: Actor, bob: Actor, workspace: dict) -> dict:
    await _join_workspace(alice, bob, workspace)
    return (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "팀 채널", "member_ids": [bob.id]},
        )
    ).json()


# ── B-1 방해 금지 ────────────────────────────────────────────────────────────


def test_dnd_window_crossing_midnight_in_the_users_timezone() -> None:
    seoul = {"dnd_start": "22:00", "dnd_end": "08:00", "dnd_days": [0, 1, 2, 3, 4]}
    # Tuesday 23:30 KST == Tuesday 14:30 UTC → inside (evening half of Tue).
    assert in_dnd(
        **seoul,
        paused_until=None,
        timezone="Asia/Seoul",
        now=datetime(2026, 9, 8, 14, 30, tzinfo=UTC),
    )
    # Wednesday 07:00 KST == Tue 22:00 UTC → inside (morning half of Tue's window).
    assert in_dnd(
        **seoul,
        paused_until=None,
        timezone="Asia/Seoul",
        now=datetime(2026, 9, 8, 22, 0, tzinfo=UTC),
    )
    # Wednesday 09:00 KST → outside.
    assert not in_dnd(
        **seoul,
        paused_until=None,
        timezone="Asia/Seoul",
        now=datetime(2026, 9, 9, 0, 0, tzinfo=UTC),
    )
    # Saturday 23:30 KST (weekday 5) → not a DND day.
    assert not in_dnd(
        **seoul,
        paused_until=None,
        timezone="Asia/Seoul",
        now=datetime(2026, 9, 12, 14, 30, tzinfo=UTC),
    )
    # Sunday 07:00 KST belongs to Saturday's window → not a DND day either.
    assert not in_dnd(
        **seoul,
        paused_until=None,
        timezone="Asia/Seoul",
        now=datetime(2026, 9, 12, 22, 0, tzinfo=UTC),
    )
    # A pause wins regardless of day or window.
    assert in_dnd(
        dnd_start=None,
        dnd_end=None,
        dnd_days=[],
        timezone="Asia/Seoul",
        paused_until=datetime.now(UTC) + timedelta(hours=1),
    )
    assert not in_dnd(
        dnd_start=None,
        dnd_end=None,
        dnd_days=[],
        timezone="Asia/Seoul",
        paused_until=datetime.now(UTC) - timedelta(hours=1),
    )


async def test_notification_schedule_is_saved_validated_and_reported(bob: Actor) -> None:
    bad = await bob.patch("/me/notifications", json={"dnd_start": "25:00", "dnd_end": "08:00"})
    assert bad.status_code == 422

    paused_until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    updated = await bob.patch(
        "/me/notifications",
        json={
            "dnd_start": "22:00",
            "dnd_end": "08:00",
            "dnd_days": [4, 0, 0],
            "paused_until": paused_until,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["dnd_start"] == "22:00" and body["dnd_days"] == [0, 4]
    assert body["in_dnd"] is True  # paused

    me = (await bob.get("/me")).json()
    assert me["notify_paused_until"] is not None and me["in_dnd"] is True

    cleared = await bob.patch("/me/notifications", json={"paused_until": None, "dnd_start": None})
    assert cleared.json()["notify_paused_until"] is None
    # Half a window is no window: clearing the start also clears the end.
    assert cleared.json()["dnd_end"] is None


async def test_dnd_silences_notifications_but_not_counters(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = await _setup(alice, bob, workspace)
    sent: list[tuple[list[str], dict]] = []

    async def capture(user_ids, event, data, *, workspace_id=None):  # noqa: ANN001
        sent.append((list(user_ids), data))

    monkeypatch.setattr("app.api.v1.messages.emit_to_users", capture)

    await alice.post(f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 하나"})
    assert any(bob.id in ids for ids, _ in sent)

    sent.clear()
    paused = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    await bob.patch("/me/notifications", json={"paused_until": paused})
    await alice.post(f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 둘"})
    assert not any(bob.id in ids for ids, _ in sent), "DND 중에는 알림이 가면 안 됩니다"

    membership = (await bob.get(f"/channels/{channel['id']}")).json()["membership"]
    assert membership["mention_count"] == 2, "배지는 그대로 세야 합니다"


# ── B-2 저장 · 리마인더 ─────────────────────────────────────────────────────


async def test_saved_items_round_trip(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "나중에 볼 것"})
    ).json()

    saved = await bob.put(f"/messages/{message['id']}/save", json={"note": "월요일에 답하기"})
    assert saved.status_code == 200, saved.text
    item = saved.json()
    assert item["note"] == "월요일에 답하기" and item["message"]["is_saved"] is True
    assert item["channel"]["id"] == channel["id"]

    # The flag rides on every serialisation for the viewer — and only the viewer.
    page = (await bob.get(f"/channels/{channel['id']}/messages")).json()
    assert page["items"][0]["is_saved"] is True
    assert (await alice.get(f"/messages/{message['id']}")).json()["is_saved"] is False

    listed = (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()
    assert [row["id"] for row in listed["items"]] == [item["id"]]
    assert listed["has_more"] is False

    done = await bob.post(f"/saved/{item['id']}/done")
    assert done.json()["done_at"] is not None
    assert (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()["items"] == []
    assert (
        len((await bob.get(f"/workspaces/{workspace['id']}/saved?done=true")).json()["items"]) == 1
    )

    reopened = await bob.post(f"/saved/{item['id']}/reopen")
    assert reopened.json()["done_at"] is None

    # Someone else cannot touch my saved item.
    assert (await alice.post(f"/saved/{item['id']}/done")).status_code == 404

    assert (await bob.delete(f"/messages/{message['id']}/save")).status_code == 200
    assert (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()["items"] == []


async def test_saved_list_hides_messages_from_channels_i_left(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "비밀"})
    ).json()
    await bob.put(f"/messages/{message['id']}/save", json={})
    await bob.post(f"/channels/{channel['id']}/leave")
    assert (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()["items"] == []


async def test_reminders_fire_once_with_a_reminder_frame(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "배포 전에 **확인**"})
    ).json()
    sent: list[tuple[list[str], str, dict]] = []

    async def capture(user_ids, event, data, *, workspace_id=None):  # noqa: ANN001
        sent.append((list(user_ids), event, data))

    monkeypatch.setattr("app.services.reminders.emit_to_users", capture)

    due = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    saved = (await bob.put(f"/messages/{message['id']}/save", json={"remind_at": due})).json()
    await alice.put(f"/messages/{message['id']}/save", json={"remind_at": future})

    assert "reminders_due" in workers.registered()
    assert await workers.run_once("reminders_due")
    assert len(sent) == 1
    ids, event, data = sent[0]
    assert ids == [bob.id] and event == "notification"
    assert data["kind"] == "reminder" and data["title"] == "리마인더"
    assert data["message_id"] == message["id"] and data["channel_id"] == channel["id"]
    assert data["saved_id"] == saved["id"]
    assert "확인" in data["body"] and "**" not in data["body"]

    # A second tick does not fire the same reminder again.
    await workers.run_once("reminders_due")
    assert len(sent) == 1
    listed = (await bob.get(f"/workspaces/{workspace['id']}/saved")).json()["items"]
    assert listed[0]["reminded_at"] is not None

    # Saving again with a new time re-arms it.
    again = (await bob.put(f"/messages/{message['id']}/save", json={"remind_at": due})).json()
    assert again["reminded_at"] is None
    await workers.run_once("reminders_due")
    assert len(sent) == 2


# ── B-3 초대 메일 ───────────────────────────────────────────────────────────


async def test_invites_are_mailed_when_a_relay_and_web_url_exist(
    alice: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    mails: list[tuple[str, str, str]] = []

    async def capture(to, subject, body, config):  # noqa: ANN001
        mails.append((to, subject, body))

    monkeypatch.setattr("app.core.mailer.send_email", capture)

    # No relay: created, but not mailed — and the UI is told.
    created = (
        await alice.post(
            f"/workspaces/{workspace['id']}/invites",
            json={"emails": ["dana@example.com"], "role": "member"},
        )
    ).json()
    assert created[0]["emailed"] is False and mails == []

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "public_web_url", "https://llack.example.com/")
    created = (
        await alice.post(
            f"/workspaces/{workspace['id']}/invites",
            json={"emails": ["erin@example.com"], "role": "member"},
        )
    ).json()
    assert created[0]["emailed"] is True
    to, subject, body = mails[-1]
    token = created[0]["invite_url"].split("token=")[1].split("&")[0]
    assert to == "erin@example.com"
    assert "테스트 회사" in subject and "김앨리스" in subject
    assert f"https://llack.example.com/?invite={token}" in body

    # Resend rotates the token: the old link dies, the new one works.
    invite_id = created[0]["id"]
    resent = await alice.post(f"/workspaces/{workspace['id']}/invites/{invite_id}/resend")
    assert resent.status_code == 200, resent.text
    new_token = resent.json()["invite_url"].split("token=")[1].split("&")[0]
    assert new_token != token and resent.json()["emailed"] is True
    assert f"?invite={new_token}" in mails[-1][2]

    audit = (await alice.get(f"/workspaces/{workspace['id']}/audit")).json()
    assert "invite.resent" in {row["action"] for row in audit["items"]}


async def test_invite_mail_falls_back_to_the_request_origin(
    alice: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    mails: list[str] = []

    async def capture(to, subject, body, config):  # noqa: ANN001
        mails.append(body)

    monkeypatch.setattr("app.core.mailer.send_email", capture)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "public_web_url", "")
    created = (
        await alice.post(
            f"/workspaces/{workspace['id']}/invites",
            json={"emails": ["frank@example.com"]},
            headers={"Origin": "https://chat.acme.test"},
        )
    ).json()
    assert created[0]["emailed"] is True
    assert "https://chat.acme.test/?invite=" in mails[0]


# ── B-4 링크 카드 ───────────────────────────────────────────────────────────

PAGE = b"""<!doctype html><html><head>
<title>Fallback title</title>
<meta property="og:title" content="Llack &amp; friends">
<meta property="og:description" content="A   team   chat.">
<meta property="og:image" content="/static/card.png">
<meta property="og:site_name" content="Example Site">
</head><body><p>body text</p></body></html>"""


def _public(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # noqa: ANN001
    monkeypatch.setattr(unfurl, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["93.184.216.34"])


def test_first_url_ignores_code_spans_and_trailing_punctuation() -> None:
    assert unfurl.first_url("봐요 `https://in.code/x` 그리고 https://example.com/a).") == (
        "https://example.com/a"
    )
    assert unfurl.first_url("```\nhttps://only.in/code\n```") is None
    assert unfurl.first_url("링크 없음") is None


async def test_a_pasted_link_gets_an_unfurl_block_and_an_update_event(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = await _setup(alice, bob, workspace)
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=PAGE
        )

    _public(monkeypatch, handler)
    updates: list[dict] = []

    async def capture(channel_id, event, data, *, workspace_id=None):  # noqa: ANN001
        updates.append({"channel_id": channel_id, "event": str(event), "data": data})

    monkeypatch.setattr("app.realtime.events.emit_to_channel", capture)

    posted = (
        await alice.post(
            f"/channels/{channel['id']}/messages",
            json={"body": "이거 보세요 https://example.com/post?id=1"},
        )
    ).json()
    await unfurl.drain_background()

    message = (await bob.get(f"/messages/{posted['id']}")).json()
    block = message["blocks"][0]
    assert block == {
        "type": "unfurl",
        "url": "https://example.com/post?id=1",
        "title": "Llack & friends",
        "description": "A team chat.",
        "image_url": "https://example.com/static/card.png",
        "site_name": "Example Site",
    }
    assert [u["event"] for u in updates if u["data"].get("message", {}).get("id") == posted["id"]]
    assert updates[-1]["data"]["message"]["blocks"][0]["type"] == "unfurl"

    # The second message with the same link is served from the cache.
    await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "다시 https://example.com/post?id=1"},
    )
    await unfurl.drain_background()
    assert len(hits) == 1


async def test_private_and_failed_links_get_no_card(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = await _setup(alice, bob, workspace)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    monkeypatch.setattr(unfurl, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["10.0.0.5"])

    posted = (
        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": "http://intranet.local/admin"}
        )
    ).json()
    await unfurl.drain_background()
    assert calls == [], "사설 주소는 연결조차 하지 않습니다"
    assert (await bob.get(f"/messages/{posted['id']}")).json()["blocks"] is None

    monkeypatch.setattr(linkprobe, "_resolve_addresses", lambda host: ["93.184.216.34"])
    posted = (
        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": "https://example.com/500"}
        )
    ).json()
    await unfurl.drain_background()
    assert (await bob.get(f"/messages/{posted['id']}")).json()["blocks"] is None

    monkeypatch.setattr(settings, "unfurl_enabled", False)
    calls.clear()
    await alice.post(f"/channels/{channel['id']}/messages", json={"body": "https://example.com/x"})
    await unfurl.drain_background()
    assert calls == []


# ── B-5 @here / @channel ────────────────────────────────────────────────────


async def test_here_reaches_only_people_who_are_present(
    alice: Actor, bob: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    channel = await _setup(alice, bob, workspace)
    carol = await register(client, "carol@example.com", "박캐롤")
    await _join_workspace(alice, carol, workspace)
    await carol.post(f"/channels/{channel['id']}/join")

    await get_presence_store().touch(bob.id, PresenceState.ACTIVE)
    await get_presence_store().clear(carol.id)

    here = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "@here 배포합니다"})
    ).json()
    assert here["broadcast"] == "here" and here["mentions_everyone"] is True
    assert (await bob.get(f"/channels/{channel['id']}")).json()["membership"]["mention_count"] == 1
    assert (await carol.get(f"/channels/{channel['id']}")).json()["membership"][
        "mention_count"
    ] == 0

    everyone = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "@channel 회식 공지"})
    ).json()
    assert everyone["broadcast"] == "channel"
    assert (await carol.get(f"/channels/{channel['id']}")).json()["membership"][
        "mention_count"
    ] == 1

    plain = (await alice.post(f"/channels/{channel['id']}/messages", json={"body": "평범"})).json()
    assert plain["broadcast"] is None


async def test_here_notifies_only_present_members(
    alice: Actor,
    bob: Actor,
    workspace: dict,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = await _setup(alice, bob, workspace)
    carol = await register(client, "carol2@example.com", "박캐롤")
    await _join_workspace(alice, carol, workspace)
    await carol.post(f"/channels/{channel['id']}/join")
    # Both on "mentions only" so a plain message would reach neither.
    for actor in (bob, carol):
        await actor.patch(
            f"/channels/{channel['id']}/membership", json={"notification_level": "mentions"}
        )
    await get_presence_store().touch(bob.id, PresenceState.ACTIVE)
    await get_presence_store().clear(carol.id)

    sent: list[list[str]] = []

    async def capture(user_ids, event, data, *, workspace_id=None):  # noqa: ANN001
        sent.append(list(user_ids))

    monkeypatch.setattr("app.api.v1.messages.emit_to_users", capture)
    await alice.post(f"/channels/{channel['id']}/messages", json={"body": "@here 지금 봐주세요"})
    assert sent == [[bob.id]]
