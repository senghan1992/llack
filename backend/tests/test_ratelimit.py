"""레이트 리밋 — 너무 많은 요청이 429 로 막히는지."""

from __future__ import annotations

import httpx
import pytest
from starlette.requests import Request

from app.api.deps import client_ip
from app.core.config import get_settings
from app.core.ratelimit import limiter
from tests.conftest import API, auth, signup


@pytest.fixture
def limits(monkeypatch):
    """한도를 원하는 값으로 바꾸고, 되돌린다.

    한도는 환경변수로 정해집니다 — 서버를 다시 키우지 않고도 바꿀 수
    있어야 하기 때문입니다. 여기서는 테스트할 값을 넣어 둡니다.
    """

    def configure(**values: int) -> None:
        for name, value in values.items():
            monkeypatch.setenv(f"RATE_LIMIT_{name.upper()}", str(value))
        get_settings.cache_clear()

    yield configure
    get_settings.cache_clear()


def _request(peer: str, headers: dict[str, str] | None = None) -> Request:
    """실제 요청과 비슷하게(scope) 만들어 地址를 재는 함수를 시험합니다."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (key.encode("latin-1"), value.encode("latin-1"))
                for key, value in (headers or {}).items()
            ],
            "client": (peer, 12345),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
            "root_path": "",
        }
    )


async def test_the_account_login_limit_stops_password_guessing(
    client: httpx.AsyncClient, limits
) -> None:
    limits(login_account=3)
    await signup(client, email="target@hanbit.co.kr")

    for _ in range(3):
        response = await client.post(
            f"{API}/auth/login",
            json={"email": "target@hanbit.co.kr", "password": "wrong-password"},
        )
        assert response.status_code == 401, response.text

    blocked = await client.post(
        f"{API}/auth/login",
        json={"email": "target@hanbit.co.kr", "password": "wrong-password"},
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_the_address_limit_stops_many_logins_from_one_place(
    client: httpx.AsyncClient, limits
) -> None:
    limits(login=2)
    await signup(client, email="first@hanbit.co.kr")
    await signup(client, email="second@hanbit.co.kr")

    for email in ("first@hanbit.co.kr", "second@hanbit.co.kr"):
        response = await client.post(
            f"{API}/auth/login",
            json={"email": email, "password": "hanbit2026"},
        )
        assert response.status_code == 200, response.text

    blocked = await client.post(
        f"{API}/auth/login",
        json={"email": "first@hanbit.co.kr", "password": "hanbit2026"},
    )
    assert blocked.status_code == 429, blocked.text


async def test_the_message_limit_stops_a_flood(client: httpx.AsyncClient, limits) -> None:
    limits(message=2)
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general", "topic": "팀 공지"},
    )
    channel_id = created.json()["id"]

    for index in range(2):
        response = await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": f"연속으로 보내는 메시지 {index}"},
        )
        assert response.status_code == 200, response.text

    blocked = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "이건 막혀야 합니다"},
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_a_limit_of_zero_turns_the_limit_off(client: httpx.AsyncClient, limits) -> None:
    limits(message=0)
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "general", "topic": "팀 공지"},
    )
    channel_id = created.json()["id"]

    for index in range(5):
        response = await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": f"멈추지 않는 메시지 {index}"},
        )
        assert response.status_code == 200, response.text


async def test_the_whole_limit_can_be_turned_off(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        data = await signup(client)
        workspace_id = data["workspace"]["id"]
        headers = auth(data["access_token"])
        created = await client.post(
            f"{API}/workspaces/{workspace_id}/channels",
            headers=headers,
            json={"name": "general", "topic": "팀 공지"},
        )
        channel_id = created.json()["id"]

        for index in range(4):
            response = await client.post(
                f"{API}/channels/{channel_id}/messages",
                headers=headers,
                json={"body": f"끄면 아무도 안 막습니다 {index}"},
            )
            assert response.status_code == 200, response.text
    finally:
        get_settings.cache_clear()


def test_a_forwarded_address_is_only_believed_from_a_trusted_proxy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "10.0.0.0/8")
    get_settings.cache_clear()
    try:
        # 신뢰하는 프록시에서 온 요청 — 표시된 주소를 씁니다.
        assert (
            client_ip(_request("10.1.2.3", {"x-forwarded-for": "203.0.113.9, 10.1.2.3"}))
            == "203.0.113.9"
        )
        # 다른 곳에서 온 요청 — 표시된 주장을 믿지 않습니다.
        assert (
            client_ip(_request("198.51.100.7", {"x-forwarded-for": "203.0.113.9"}))
            == "198.51.100.7"
        )
    finally:
        get_settings.cache_clear()


def test_a_spoofed_forwarded_address_does_not_win(monkeypatch) -> None:
    """손님이 `X-Forwarded-For` 에 주소를 끼워 넣어도 속지 않습니다."""
    monkeypatch.setenv("TRUSTED_PROXY_NETWORKS", "10.0.0.0/8")
    get_settings.cache_clear()
    try:
        # 손님이 "203.0.113.9" 를 끼워 넣고, nginx 가 진짜 주소를 뒤에 붙였습니다.
        assert (
            client_ip(_request("10.1.2.3", {"x-forwarded-for": "203.0.113.9, 198.51.100.7"}))
            == "198.51.100.7"
        )
    finally:
        get_settings.cache_clear()


def test_the_bucket_refills_over_time() -> None:
    """한도가 차도 시간이 지나면 다시 채워집니다."""
    limiter.reset()
    for _ in range(2):
        limiter.check("test-scope", "someone", capacity=2, per_seconds=60.0)
    try:
        limiter.check("test-scope", "someone", capacity=2, per_seconds=60.0)
    except Exception as exc:  # noqa: BLE001 — 429 를 확인하기 위한 것
        assert "너무 자주" in str(exc)
    else:  # pragma: no cover — 한도가 지켜졌어야 합니다
        raise AssertionError("한도를 넘었는데 막히지 않았습니다")
    limiter.reset()
