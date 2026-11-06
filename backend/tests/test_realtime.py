"""The WebSocket contract, exercised against a real server."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.core.ids import MEMBER_PREFIX, new_id
from app.models.workspace import WorkspaceMembership

BACKEND_ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(tmp_path_factory) -> dict:
    """Start uvicorn in a subprocess with its own database."""
    workdir = tmp_path_factory.mktemp("live")
    db_path = workdir / "live.db"
    port = _free_port()
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env["SECRET_KEY"] = "live-secret-key"
    env["UPLOAD_DIR"] = str(workdir / "uploads")

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_ROOT,
        env=env,
    )

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        if process.poll() is not None:
            pytest.fail("the server exited during startup")
        try:
            if httpx.get(f"{base_url}{API}/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail("the server did not start in time")

    try:
        yield {"base_url": base_url, "db_path": db_path, "port": port}
    finally:
        process.terminate()
        process.wait(timeout=10)


async def _add_member(live_server: dict, workspace_id: str, user_id: str) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{live_server['db_path']}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            WorkspaceMembership(
                id=new_id(MEMBER_PREFIX),
                workspace_id=workspace_id,
                user_id=user_id,
                role="member",
            )
        )
        await session.commit()
    await engine.dispose()


async def _collect(websocket, seconds: float = 1.5) -> list[dict]:
    """Drain every event that arrives within ``seconds``."""
    events: list[dict] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return events
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        except TimeoutError:
            return events
        events.append(json.loads(raw))


async def _wait_for(websocket, event_type: str, deadline_seconds: float = 5.0) -> dict:
    """Read events until one of ``event_type`` shows up."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + deadline_seconds
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AssertionError(f"no {event_type} event arrived")
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        payload = json.loads(raw)
        if payload.get("type") == event_type:
            return payload


async def test_websocket_delivers_hello_and_new_messages(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        first = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "hyunjin@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "김현진",
                    "workspace_name": "한빛",
                },
            )
        ).json()
        workspace_id = first["workspace"]["id"]
        channel_id = (
            await http.post(
                f"{API}/workspaces/{workspace_id}/channels",
                headers={"Authorization": f"Bearer {first['access_token']}"},
                json={"name": "general", "topic": "팀 공지"},
            )
        ).json()["id"]

        second = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "jimin@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "박지민",
                    "workspace_name": "디자인팀",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, second["user"]["id"])

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={first['access_token']}") as author_socket:
            hello = json.loads(await asyncio.wait_for(author_socket.recv(), timeout=5))
            assert hello["type"] == "hello"
            assert hello["user"]["id"] == first["user"]["id"]

            async with connect(f"{url}?token={second['access_token']}") as guest_socket:
                guest_hello = json.loads(await asyncio.wait_for(guest_socket.recv(), timeout=5))
                assert guest_hello["type"] == "hello"

                posted = await http.post(
                    f"{API}/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bearer {first['access_token']}"},
                    json={"body": "배포 준비 끝났습니다."},
                )
                assert posted.status_code == 200

                event = await _wait_for(guest_socket, "message.created")
                message = event["message"]
                assert message["id"] == posted.json()["id"]
                assert message["body"] == "배포 준비 끝났습니다."
                assert message["parent_id"] is None
                assert message["author"]["name"] == "김현진"
                assert message["author"]["id"] == first["user"]["id"]
                assert message["reactions"] == []


async def test_websocket_replies_carry_the_parent_id(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "chaewon@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "이채원",
                    "workspace_name": "프론트",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]
        headers = {"Authorization": f"Bearer {owner['access_token']}"}
        channel_id = (
            await http.post(
                f"{API}/workspaces/{workspace_id}/channels",
                headers=headers,
                json={"name": "engineering"},
            )
        ).json()["id"]
        root_id = (
            await http.post(
                f"{API}/channels/{channel_id}/messages",
                headers=headers,
                json={"body": "이거 어떠세요?"},
            )
        ).json()["id"]

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={owner['access_token']}") as socket:
            assert json.loads(await asyncio.wait_for(socket.recv(), timeout=5))["type"] == "hello"

            reply = await http.post(
                f"{API}/channels/{channel_id}/messages",
                headers=headers,
                json={"body": "답변입니다", "parent_id": root_id},
            )
            assert reply.status_code == 200

            event = await _wait_for(socket, "message.created")
            assert event["message"]["parent_id"] == root_id
            assert event["message"]["id"] == reply.json()["id"]


async def test_websocket_typing_and_presence(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "sua@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "최수아",
                    "workspace_name": "기획",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]
        headers = {"Authorization": f"Bearer {owner['access_token']}"}
        channel_id = (
            await http.post(
                f"{API}/workspaces/{workspace_id}/channels",
                headers=headers,
                json={"name": "general"},
            )
        ).json()["id"]

        guest = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "woojin@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "정우진",
                    "workspace_name": "데브옵스",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, guest["user"]["id"])

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={owner['access_token']}") as owner_socket:
            assert (
                json.loads(await asyncio.wait_for(owner_socket.recv(), timeout=5))["type"]
                == "hello"
            )

            async with connect(f"{url}?token={guest['access_token']}") as guest_socket:
                assert (
                    json.loads(await asyncio.wait_for(guest_socket.recv(), timeout=5))["type"]
                    == "hello"
                )

                presence = await _wait_for(owner_socket, "presence")
                assert presence["user_id"] == guest["user"]["id"]
                assert presence["presence"] == "online"

                await guest_socket.send(
                    json.dumps({"type": "typing", "channel_id": channel_id, "on": True})
                )
                typing = await _wait_for(owner_socket, "typing")
                assert typing["channel_id"] == channel_id
                assert typing["user_id"] == guest["user"]["id"]
                assert typing["name"] == "정우진"
                assert typing["on"] is True

                await guest_socket.send(json.dumps({"type": "ping"}))
                pong = json.loads(await asyncio.wait_for(guest_socket.recv(), timeout=5))
                assert pong == {"type": "pong"}


async def test_websocket_rejects_a_bad_token(live_server: dict) -> None:
    url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
    with pytest.raises(ConnectionClosed) as error:
        async with connect(f"{url}?token=not-a-real-token") as socket:
            await asyncio.wait_for(socket.recv(), timeout=5)
    closed = error.value
    code = closed.rcvd.code if closed.rcvd is not None else closed.code
    assert code == 4401


async def test_websocket_requires_a_token(live_server: dict) -> None:
    url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
    with pytest.raises(ConnectionClosed) as error:
        async with connect(url) as socket:
            await asyncio.wait_for(socket.recv(), timeout=5)
    closed = error.value
    code = closed.rcvd.code if closed.rcvd is not None else closed.code
    assert code == 4401


async def test_presence_goes_offline_when_the_last_socket_closes(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "presence@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "정우진",
                    "workspace_name": "데브옵스",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]

        guest = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "watcher@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "김현진",
                    "workspace_name": "한빛",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, guest["user"]["id"])

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={guest['access_token']}") as watcher:
            assert json.loads(await asyncio.wait_for(watcher.recv(), timeout=5))["type"] == "hello"

            async with connect(f"{url}?token={owner['access_token']}") as socket:
                assert (
                    json.loads(await asyncio.wait_for(socket.recv(), timeout=5))["type"] == "hello"
                )
                online = await _wait_for(watcher, "presence")
                assert online["user_id"] == owner["user"]["id"]
                assert online["presence"] == "online"

            offline = await _wait_for(watcher, "presence")
            assert offline["user_id"] == owner["user"]["id"]
            assert offline["presence"] == "offline"


async def test_a_second_socket_keeps_the_user_online(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "twosockets@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "이채원",
                    "workspace_name": "프론트",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]

        watcher = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "watcher2@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "박지민",
                    "workspace_name": "디자인",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, watcher["user"]["id"])

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={watcher['access_token']}") as watcher_socket:
            assert (
                json.loads(await asyncio.wait_for(watcher_socket.recv(), timeout=5))["type"]
                == "hello"
            )

            async with connect(f"{url}?token={owner['access_token']}") as first:
                assert (
                    json.loads(await asyncio.wait_for(first.recv(), timeout=5))["type"] == "hello"
                )
                online = await _wait_for(watcher_socket, "presence")
                assert online["presence"] == "online"

                async with connect(f"{url}?token={owner['access_token']}") as second:
                    assert (
                        json.loads(await asyncio.wait_for(second.recv(), timeout=5))["type"]
                        == "hello"
                    )
                    # the second socket announces the user as online again
                    again = await _wait_for(watcher_socket, "presence")
                    assert again["presence"] == "online"

                    await first.close()

                    # the remaining socket keeps the user online
                    events = await _collect(watcher_socket, 1.5)
                    assert not [
                        event
                        for event in events
                        if event.get("type") == "presence" and event.get("presence") == "offline"
                    ]


async def test_read_event_clears_the_unread_counter(live_server: dict) -> None:
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "reader@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "최수아",
                    "workspace_name": "기획",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]
        headers = {"Authorization": f"Bearer {owner['access_token']}"}
        channel_id = (
            await http.post(
                f"{API}/workspaces/{workspace_id}/channels",
                headers=headers,
                json={"name": "general"},
            )
        ).json()["id"]

        other = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "writer@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "박지민",
                    "workspace_name": "디자인",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, other["user"]["id"])
        posted = await http.post(
            f"{API}/channels/{channel_id}/messages",
            headers={"Authorization": f"Bearer {other['access_token']}"},
            json={"body": "읽어주세요"},
        )
        message_id = posted.json()["id"]

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={owner['access_token']}") as socket:
            assert json.loads(await asyncio.wait_for(socket.recv(), timeout=5))["type"] == "hello"

            channels = (
                await http.get(f"{API}/workspaces/{workspace_id}/channels", headers=headers)
            ).json()
            assert channels[0]["unread_count"] == 1

            await socket.send(
                json.dumps({"type": "read", "channel_id": channel_id, "message_id": message_id})
            )
            unread = await _wait_for(socket, "unread")
            assert unread["channel_id"] == channel_id
            assert unread["count"] == 0


async def test_websocket_carries_a_changed_profile(live_server: dict) -> None:
    """A new face or a new colour reaches the rest of the team at once."""
    async with httpx.AsyncClient(base_url=live_server["base_url"]) as http:
        owner = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "profilepick@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "이채원",
                    "workspace_name": "프론트",
                },
            )
        ).json()
        workspace_id = owner["workspace"]["id"]
        headers = {"Authorization": f"Bearer {owner['access_token']}"}
        await http.post(
            f"{API}/workspaces/{workspace_id}/channels",
            headers=headers,
            json={"name": "general"},
        )

        guest = (
            await http.post(
                f"{API}/auth/signup",
                json={
                    "email": "profilemate@hanbit.co.kr",
                    "password": "hanbit2026",
                    "name": "김민",
                    "workspace_name": "백엔드",
                },
            )
        ).json()
        await _add_member(live_server, workspace_id, guest["user"]["id"])

        url = f"ws://127.0.0.1:{live_server['port']}{API}/ws"
        async with connect(f"{url}?token={owner['access_token']}") as owner_socket:
            assert (
                json.loads(await asyncio.wait_for(owner_socket.recv(), timeout=5))["type"]
                == "hello"
            )

            async with connect(f"{url}?token={guest['access_token']}") as guest_socket:
                assert (
                    json.loads(await asyncio.wait_for(guest_socket.recv(), timeout=5))["type"]
                    == "hello"
                )
                await _wait_for(owner_socket, "presence")

                changed = await http.patch(
                    f"{API}/me",
                    headers={"Authorization": f"Bearer {guest['access_token']}"},
                    json={"avatar_color": "#295e90", "title": "데브옵스"},
                )
                assert changed.status_code == 200
                assert changed.json()["avatar_color"] == "#295e90"

                updated = await _wait_for(owner_socket, "user.updated")
                assert updated["user"]["id"] == guest["user"]["id"]
                assert updated["user"]["avatar_color"] == "#295e90"
                assert updated["user"]["title"] == "데브옵스"
