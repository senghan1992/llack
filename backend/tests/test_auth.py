"""Authentication, session rotation and revocation."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import Actor, register


async def test_register_derives_a_handle_and_returns_tokens(client: httpx.AsyncClient) -> None:
    actor = await register(client, "chan.park@example.com", "박찬")
    assert actor.user["handle"] == "chan.park"
    assert actor.tokens["access_token"]
    assert actor.tokens["refresh_token"]
    assert actor.tokens["token_type"] == "Bearer"


async def test_duplicate_email_is_rejected(client: httpx.AsyncClient) -> None:
    await register(client, "dup@example.com", "중복")
    response = await client.post(
        "/auth/register",
        json={
            "email": "dup@example.com",
            "password": "correct-horse-battery",
            "display_name": "중복2",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_handle_collision_gets_a_suffix(client: httpx.AsyncClient) -> None:
    first = await register(client, "same@a.example.com", "동일")
    second = await register(client, "same@b.example.com", "동일2")
    assert first.user["handle"] == "same"
    assert second.user["handle"] == "same2"


async def test_wrong_password_is_unauthorized(client: httpx.AsyncClient, alice: Actor) -> None:
    response = await client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "wrong-password-here"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_unknown_email_gives_the_same_error_as_a_wrong_password(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_refresh_rotates_and_invalidates_the_old_token(
    client: httpx.AsyncClient, alice: Actor
) -> None:
    original = alice.tokens["refresh_token"]

    first = await client.post("/auth/refresh", json={"refresh_token": original})
    assert first.status_code == 200
    rotated = first.json()["refresh_token"]
    assert rotated != original

    # The rotated-away token must not work a second time.
    replay = await client.post("/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401

    # The new one does.
    again = await client.post("/auth/refresh", json={"refresh_token": rotated})
    assert again.status_code == 200


async def test_logout_revokes_the_access_token_immediately(
    client: httpx.AsyncClient, alice: Actor
) -> None:
    assert (await alice.get("/me")).status_code == 200
    assert (await alice.post("/auth/logout")).status_code == 200
    # Same (unexpired) access token, but its session is gone.
    response = await alice.get("/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_revoked"


async def test_missing_and_malformed_credentials(client: httpx.AsyncClient) -> None:
    assert (await client.get("/me")).json()["error"]["code"] == "missing_credentials"
    response = await client.get("/me", headers={"Authorization": "Token abc"})
    assert response.json()["error"]["code"] == "malformed_credentials"
    response = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_password_change_signs_other_devices_out(
    client: httpx.AsyncClient, alice: Actor
) -> None:
    second_login = await client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery",
            "device": {"device_name": "다른 노트북", "platform": "macos"},
        },
    )
    other = Actor(client, second_login.json()["user"], second_login.json()["tokens"])
    assert (await other.get("/me")).status_code == 200

    changed = await alice.post(
        "/auth/password",
        json={
            "current_password": "correct-horse-battery",
            "new_password": "a-brand-new-passphrase",
        },
    )
    assert changed.status_code == 200

    # The device that changed the password keeps working; the other does not.
    assert (await alice.get("/me")).status_code == 200
    assert (await other.get("/me")).status_code == 401


async def test_sessions_list_marks_the_current_device(
    client: httpx.AsyncClient, alice: Actor
) -> None:
    await client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-horse-battery",
            "device": {"device_name": "데스크톱", "platform": "windows"},
        },
    )
    response = await alice.get("/auth/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s["is_current"]) == 1


# ── Invite-gated sign-up ─────────────────────────────────────────────────────


async def _invite_token(alice: Actor, workspace: dict, email: str) -> str:
    created = await alice.post(
        f"/workspaces/{workspace['id']}/invites",
        json={"emails": [email], "role": "member"},
    )
    assert created.status_code == 201, created.text
    url = created.json()[0]["invite_url"]
    return url.split("token=")[1].split("&")[0]


async def test_signing_up_with_an_invite_joins_the_workspace_in_one_step(
    client: httpx.AsyncClient, alice: Actor, workspace: dict
) -> None:
    token = await _invite_token(alice, workspace, "joiner@example.com")
    signed_up = await client.post(
        "/auth/register",
        json={
            "email": "joiner@example.com",
            "password": "joiner-password-1",
            "display_name": "합류자",
            "invite_token": token,
        },
    )
    assert signed_up.status_code == 201, signed_up.text
    access = signed_up.json()["tokens"]["access_token"]
    listed = await client.get(
        "/workspaces", headers={"Authorization": f"Bearer {access}"}
    )
    assert [w["id"] for w in listed.json()] == [workspace["id"]]


async def test_invite_gated_signup_refuses_without_a_token(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_invite", True)
    refused = await client.post(
        "/auth/register",
        json={
            "email": "walkin@example.com",
            "password": "walkin-password-1",
            "display_name": "무단입장",
        },
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "invite_required"


async def test_a_bad_invite_fails_signup_without_creating_an_orphan_account(
    client: httpx.AsyncClient, alice: Actor, workspace: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "require_invite", True)
    # The invite was issued to someone else's email.
    token = await _invite_token(alice, workspace, "intended@example.com")
    mismatched = await client.post(
        "/auth/register",
        json={
            "email": "someone-else@example.com",
            "password": "someone-password-1",
            "display_name": "다른사람",
            "invite_token": token,
        },
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["error"]["code"] == "invite_email_mismatch"

    # No orphan: the refused email cannot log in.
    login = await client.post(
        "/auth/login",
        json={"email": "someone-else@example.com", "password": "someone-password-1"},
    )
    assert login.status_code == 401


async def test_a_revoked_invite_cannot_be_used(
    client: httpx.AsyncClient, alice: Actor, workspace: dict
) -> None:
    token = await _invite_token(alice, workspace, "cancelled@example.com")
    invites = (await alice.get(f"/workspaces/{workspace['id']}/invites")).json()
    target = next(i for i in invites if i["email"] == "cancelled@example.com")

    revoked = await alice.delete(
        f"/workspaces/{workspace['id']}/invites/{target['id']}"
    )
    assert revoked.status_code == 200

    refused = await client.post(
        "/auth/register",
        json={
            "email": "cancelled@example.com",
            "password": "cancelled-password-1",
            "display_name": "회수됨",
            "invite_token": token,
        },
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "invite_expired"
