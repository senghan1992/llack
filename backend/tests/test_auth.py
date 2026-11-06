"""Sign-up, sign-in, refresh and the caller's profile."""

from __future__ import annotations

import httpx

from tests.conftest import API, auth, signup


async def test_signup_returns_session(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/signup",
        json={
            "email": "HyunJin@Hanbit.co.kr",
            "password": "hanbit2026",
            "name": "김현진",
            "workspace_name": "한빛",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "hyunjin@hanbit.co.kr"
    assert body["user"]["name"] == "김현진"
    assert body["user"]["id"].startswith("usr_")
    assert body["workspace"]["id"].startswith("wsp_")
    assert body["workspace"]["name"] == "한빛"
    assert body["workspace"]["slug"] == "hanbit"
    assert body["user"]["created_at"].endswith("Z")


async def test_signup_rejects_duplicate_email(client: httpx.AsyncClient) -> None:
    await signup(client)
    response = await client.post(
        f"{API}/auth/signup",
        json={
            "email": "hyunjin@hanbit.co.kr",
            "password": "hanbit2026",
            "name": "다른사람",
            "workspace_name": "다른 곳",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_login_and_refresh(client: httpx.AsyncClient) -> None:
    await signup(client)

    login = await client.post(
        f"{API}/auth/login", json={"email": "hyunjin@hanbit.co.kr", "password": "hanbit2026"}
    )
    assert login.status_code == 200
    session_body = login.json()
    assert session_body["user"]["email"] == "hyunjin@hanbit.co.kr"

    refreshed = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": session_body["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert refreshed.json()["refresh_token"]


async def test_login_with_wrong_password_is_unauthorized(client: httpx.AsyncClient) -> None:
    await signup(client)
    response = await client.post(
        f"{API}/auth/login", json={"email": "hyunjin@hanbit.co.kr", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_refresh_rejects_access_token(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    response = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": data["access_token"]}
    )
    assert response.status_code == 401


async def test_me_requires_a_token(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_returns_and_updates_the_profile(client: httpx.AsyncClient) -> None:
    data = await signup(client)

    me = await client.get(f"{API}/me", headers=auth(data["access_token"]))
    assert me.status_code == 200
    assert me.json()["name"] == "김현진"

    updated = await client.patch(
        f"{API}/me",
        headers=auth(data["access_token"]),
        json={"name": "김현진2", "title": "백엔드 엔지니어", "avatar_color": "#123456"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "김현진2"
    assert updated.json()["title"] == "백엔드 엔지니어"
    assert updated.json()["avatar_color"] == "#123456"
