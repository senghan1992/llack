"""Rate limits: login, register, messages, search.

Each test tightens one limit through the settings object so the flood is a
handful of requests, then checks three things: under the limit passes, over
the limit is a 429 with the stable error code, and the bucket is keyed
narrowly enough not to punish a bystander.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from tests.conftest import PASSWORD, Actor, register
from tests.test_channels import _join_workspace


async def test_login_floods_are_cut_off_per_email(
    client: httpx.AsyncClient, alice: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_login_per_minute", 3)

    # Wrong passwords fill the bucket — that is the point of checking before
    # authenticating.
    for _ in range(3):
        response = await client.post(
            "/auth/login", json={"email": "alice@example.com", "password": "wrong"}
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 429
    body = blocked.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["details"]["retry_after_seconds"] > 0

    # A different account from the same address is untouched.
    other = await client.post(
        "/auth/login", json={"email": "bob@example.com", "password": "wrong"}
    )
    assert other.status_code == 401


async def test_register_floods_are_cut_off(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_register_per_hour", 2)

    await register(client, "one@example.com", "하나")
    await register(client, "two@example.com", "둘")

    blocked = await client.post(
        "/auth/register",
        json={"email": "three@example.com", "password": PASSWORD, "display_name": "셋"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_message_floods_are_cut_off_per_user(
    alice: Actor, bob: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "속도", "member_ids": [bob.id]},
        )
    ).json()
    monkeypatch.setattr(settings, "rate_limit_messages_per_10s", 2)

    for i in range(2):
        posted = await alice.post(f"/channels/{channel['id']}/messages", json={"body": f"m{i}"})
        assert posted.status_code == 201

    blocked = await alice.post(f"/channels/{channel['id']}/messages", json={"body": "m2"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"

    # The bucket is per user: bob still posts.
    ok = await bob.post(f"/channels/{channel['id']}/messages", json={"body": "밥은 됩니다"})
    assert ok.status_code == 201


async def test_search_floods_are_cut_off_per_user(
    alice: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_search_per_minute", 2)

    for _ in range(2):
        assert (await alice.get(f"/workspaces/{workspace['id']}/search?q=팀")).status_code == 200

    blocked = await alice.get(f"/workspaces/{workspace['id']}/search?q=팀")
    assert blocked.status_code == 429


async def test_a_zero_capacity_disables_the_limit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_register_per_hour", 0)
    for i in range(5):
        await register(client, f"free{i}@example.com", f"자유{i}")
