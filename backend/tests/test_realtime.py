"""The WebSocket gateway: fan-out, auth, typing, presence and read sync."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient

from app.main import app
from tests.conftest import Actor
from tests.test_channels import _join_workspace


class Socket:
    """Thin wrapper that reads typed frames with a timeout."""

    def __init__(self, ws) -> None:  # noqa: ANN001
        self._ws = ws

    def send(self, type_: str, **data) -> None:  # noqa: ANN003
        self._ws.send_text(json.dumps({"type": type_, "data": data}))

    def recv(self) -> dict:
        return json.loads(self._ws.receive_text())

    def wait_for(self, type_: str, *, max_frames: int = 20) -> dict:
        """Read frames until one matches, so unrelated events do not fail a test."""
        for _ in range(max_frames):
            frame = self.recv()
            if frame["type"] == type_:
                return frame
        raise AssertionError(f"never received a {type_!r} frame")


@asynccontextmanager
async def connect(actor: Actor, workspace_id: str):  # noqa: ANN201
    """Open an authenticated gateway connection and consume `hello`."""
    # Starlette's WebSocket test client is sync, so it runs in a worker thread
    # alongside the async HTTP client.
    with TestClient(app) as client:
        token = actor.tokens["access_token"]
        with client.websocket_connect(
            f"/api/v1/ws?token={token}&workspace_id={workspace_id}"
        ) as ws:
            socket = Socket(ws)
            hello = socket.recv()
            assert hello["type"] == "hello"
            assert hello["data"]["user_id"] == actor.id
            assert hello["seq"] == 1
            yield socket


async def test_handshake_rejects_a_bad_token(workspace: dict) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(Exception),  # noqa: B017, PT011
        client.websocket_connect("/api/v1/ws?token=not-a-real-token") as ws,
    ):
        ws.receive_text()


async def test_hello_reports_the_users_workspaces(alice: Actor, workspace: dict) -> None:
    with TestClient(app) as client:
        token = alice.tokens["access_token"]
        with client.websocket_connect(
            f"/api/v1/ws?token={token}&workspace_id={workspace['id']}"
        ) as ws:
            hello = Socket(ws).recv()
            assert hello["data"]["workspace_ids"] == [workspace["id"]]
            assert hello["data"]["protocol_version"] == 1
            assert hello["data"]["heartbeat_seconds"] > 0


async def test_own_presence_is_echoed_for_multi_device_sync(
    alice: Actor, workspace: dict
) -> None:
    """A user's other devices need to see their own presence change."""
    async with connect(alice, workspace["id"]) as socket:
        presence = socket.wait_for("presence.updated")
        assert presence["data"] == {"user_id": alice.id, "presence": "active"}


async def test_ping_pong_and_monotonic_seq(alice: Actor, workspace: dict) -> None:
    async with connect(alice, workspace["id"]) as socket:
        seqs = []
        for _ in range(3):
            socket.send("ping")
            seqs.append(socket.wait_for("pong")["seq"])
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 3


async def test_unknown_command_returns_an_error_frame(alice: Actor, workspace: dict) -> None:
    async with connect(alice, workspace["id"]) as socket:
        socket.send("no-such-command")
        error = socket.wait_for("error")
        assert error["data"]["code"] == "unknown_command"


async def test_malformed_frame_returns_an_error_and_keeps_the_socket_open(
    alice: Actor, workspace: dict
) -> None:
    with TestClient(app) as client:
        token = alice.tokens["access_token"]
        with client.websocket_connect(
            f"/api/v1/ws?token={token}&workspace_id={workspace['id']}"
        ) as ws:
            socket = Socket(ws)
            socket.recv()  # hello
            ws.send_text("{not json")
            error = socket.wait_for("error")
            assert error["data"]["code"] == "bad_frame"
            # Still alive.
            socket.send("ping")
            assert socket.wait_for("pong")


async def test_subscribe_only_admits_channels_the_user_belongs_to(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    mine = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "내 채널", "member_ids": [bob.id]},
        )
    ).json()
    not_mine = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "남의 채널", "kind": "private"},
        )
    ).json()

    async with connect(bob, workspace["id"]) as socket:
        socket.send("subscribe", channel_ids=[mine["id"], not_mine["id"]])
        confirmed = socket.wait_for("subscribed")
        # The private channel Bob is not in is silently dropped.
        assert confirmed["data"]["channel_ids"] == [mine["id"]]


# ── Event fan-out ───────────────────────────────────────────────────────────
#
# The gateway tests above cover the socket protocol. These cover *routing*:
# which topics an action publishes to, and what the payload looks like. They
# subscribe to the event bus directly, which keeps everything in one event loop
# (the sync WebSocket test client runs its own, so it cannot observe events
# published by the async HTTP client).


class Collector:
    """Collects events published to a set of bus topics."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, topic: str, payload: dict) -> None:
        self.events.append((topic, payload))

    def types(self) -> list[str]:
        return [payload["type"] for _, payload in self.events]

    def first(self, type_: str) -> dict:
        for _, payload in self.events:
            if payload["type"] == type_:
                return payload
        raise AssertionError(f"no {type_!r} event was published; got {self.types()}")


@asynccontextmanager
async def watching(*topics: str):  # noqa: ANN201
    from app.realtime.bus import get_bus

    bus = get_bus()
    await bus.start()
    collector = Collector()
    for topic in topics:
        await bus.subscribe(topic, collector)
    try:
        yield collector
    finally:
        for topic in topics:
            await bus.unsubscribe(topic, collector)


async def test_posting_publishes_message_created_to_the_channel_topic(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from app.realtime.bus import channel_topic

    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "실시간", "member_ids": [bob.id]},
        )
    ).json()

    async with watching(channel_topic(channel["id"])) as events:
        posted = await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": "실시간으로 도착"}
        )
        assert posted.status_code == 201
        await asyncio.sleep(0)

        event = events.first("message.created")
        assert event["workspace_id"] == workspace["id"]
        assert event["data"]["message"]["id"] == posted.json()["id"]
        assert event["data"]["message"]["body"] == "실시간으로 도착"
        assert event["data"]["message"]["author"]["id"] == alice.id


async def test_a_mention_notifies_only_those_who_asked_for_it(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    """Bob sets notifications to mentions-only, so plain traffic is silent."""
    from app.realtime.bus import user_topic

    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "알림", "member_ids": [bob.id]},
        )
    ).json()
    await bob.patch(
        f"/channels/{channel['id']}/membership", json={"notification_level": "mentions"}
    )

    async with watching(user_topic(bob.id)) as events:
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "그냥 잡담"})
        await asyncio.sleep(0)
        assert "notification" not in events.types()

        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 확인 부탁"}
        )
        await asyncio.sleep(0)
        notification = events.first("notification")
        assert notification["data"]["channel_id"] == channel["id"]
        assert "확인 부탁" in notification["data"]["body"]


async def test_a_muted_channel_sends_no_notification(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from app.realtime.bus import user_topic

    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "음소거", "member_ids": [bob.id]},
        )
    ).json()
    await bob.patch(f"/channels/{channel['id']}/membership", json={"is_muted": True})

    async with watching(user_topic(bob.id)) as events:
        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 봐주세요"}
        )
        await asyncio.sleep(0)
        assert "notification" not in events.types()


async def test_reactions_and_edits_publish_to_the_channel(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from app.realtime.bus import channel_topic

    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "반응", "member_ids": [bob.id]},
        )
    ).json()
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "원본"})
    ).json()

    async with watching(channel_topic(channel["id"])) as events:
        await bob.put(f"/messages/{message['id']}/reactions", json={"emoji": "👀"})
        await alice.patch(f"/messages/{message['id']}", json={"body": "수정됨"})
        await alice.delete(f"/messages/{message['id']}")
        await asyncio.sleep(0)

        assert events.first("reaction.added")["data"]["emoji"] == "👀"
        assert events.first("message.updated")["data"]["message"]["body"] == "수정됨"
        assert events.first("message.deleted")["data"]["message_id"] == message["id"]


async def test_a_public_channel_is_announced_workspace_wide_but_a_private_one_is_not(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from app.realtime.bus import workspace_topic

    await _join_workspace(alice, bob, workspace)

    async with watching(workspace_topic(workspace["id"])) as events:
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "공개", "kind": "public"}
        )
        await asyncio.sleep(0)
        assert events.first("channel.created")["data"]["channel"]["name"] == "공개"

    async with watching(workspace_topic(workspace["id"])) as events:
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "비밀", "kind": "private"}
        )
        await asyncio.sleep(0)
        # A private channel must not be advertised to the whole workspace.
        assert "channel.created" not in events.types()


async def test_installing_an_app_is_announced_to_the_workspace(
    alice: Actor, workspace: dict
) -> None:
    from app.realtime.bus import workspace_topic
    from tests.test_apps import _publish

    app_row = await _publish(alice, workspace)

    async with watching(workspace_topic(workspace["id"])) as events:
        await alice.post(
            f"/workspaces/{workspace['id']}/apps/{app_row['id']}/install", json={}
        )
        await asyncio.sleep(0)
        event = events.first("app.installed")
        assert event["data"]["installation"]["app"]["slug"] == "standup"
