"""Authentication, session rotation and revocation."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PASSWORD, Actor, register


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


# ── Admin password reset ─────────────────────────────────────────────────────


async def test_an_admin_can_reset_a_members_password_and_kill_their_sessions(
    client: httpx.AsyncClient, alice: Actor, bob: Actor, workspace: dict
) -> None:
    from tests.test_channels import _join_workspace

    await _join_workspace(alice, bob, workspace)
    old_token = bob.tokens["access_token"]

    reset = await alice.post(
        f"/workspaces/{workspace['id']}/members/{bob.id}/reset-password"
    )
    assert reset.status_code == 200, reset.text
    temp = reset.json()["temp_password"]
    assert len(temp) >= 10

    # The old password and every old session are dead.
    old_login = await client.post(
        "/auth/login", json={"email": "bob@example.com", "password": PASSWORD}
    )
    assert old_login.status_code == 401
    stale = await client.get(
        "/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert stale.status_code == 401

    # The temporary password works.
    fresh = await client.post(
        "/auth/login", json={"email": "bob@example.com", "password": temp}
    )
    assert fresh.status_code == 200


async def test_password_reset_only_reaches_downward(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from tests.test_channels import _join_workspace

    await _join_workspace(alice, bob, workspace)
    # A member cannot reset anyone.
    denied = await bob.post(
        f"/workspaces/{workspace['id']}/members/{alice.id}/reset-password"
    )
    assert denied.status_code == 403
    # The owner cannot reset themselves through this door.
    self_denied = await alice.post(
        f"/workspaces/{workspace['id']}/members/{alice.id}/reset-password"
    )
    assert self_denied.status_code == 403
    assert self_denied.json()["error"]["code"] == "cannot_reset_self"


def test_production_refuses_dev_secrets() -> None:
    from app.core.config import Settings, validate_production_settings

    bad = Settings(
        env="production",
        secret_key="dev-secret-not-for-production-0123456789",
        database_url="postgresql+asyncpg://x/x",
    )
    try:
        validate_production_settings(bad)
        raise AssertionError("dev 키로 프로덕션 기동이 허용되면 안 됩니다")
    except RuntimeError:
        pass

    sqlite = Settings(
        env="production",
        secret_key="x" * 48,
        database_url="sqlite+aiosqlite:///./x.db",
    )
    try:
        validate_production_settings(sqlite)
        raise AssertionError("프로덕션 SQLite 기동이 허용되면 안 됩니다")
    except RuntimeError:
        pass

    good = Settings(
        env="production",
        secret_key="x" * 48,
        database_url="postgresql+asyncpg://x/x",
    )
    validate_production_settings(good)


# ── Self-service password reset (mailed code) ────────────────────────────────


async def test_forgot_password_mails_a_code_that_resets_and_kills_sessions(
    client: httpx.AsyncClient, alice: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict] = []

    async def capture(to: str, subject: str, body: str, config=None) -> None:  # noqa: ANN001
        sent.append({"to": to, "body": body})

    monkeypatch.setattr("app.core.mailer.send_email", capture)
    old_token = alice.tokens["access_token"]

    asked = await client.post(
        "/auth/forgot-password", json={"email": "alice@example.com"}
    )
    assert asked.status_code == 200
    assert sent and sent[0]["to"] == "alice@example.com"
    import re

    code = re.search(r"\b(\d{6})\b", sent[0]["body"]).group(1)

    reset = await client.post(
        "/auth/reset-password",
        json={
            "email": "alice@example.com",
            "code": code,
            "new_password": "brand-new-password-1",
        },
    )
    assert reset.status_code == 200, reset.text

    # Old password and old sessions are dead; the new password works.
    assert (
        await client.post(
            "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.get("/me", headers={"Authorization": f"Bearer {old_token}"})
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "brand-new-password-1"},
        )
    ).status_code == 200

    # The code is single-use.
    again = await client.post(
        "/auth/reset-password",
        json={
            "email": "alice@example.com",
            "code": code,
            "new_password": "another-password-1",
        },
    )
    assert again.status_code == 401


async def test_forgot_password_does_not_reveal_whether_an_account_exists(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    async def capture(to: str, subject: str, body: str, config=None) -> None:  # noqa: ANN001
        sent.append(to)

    monkeypatch.setattr("app.core.mailer.send_email", capture)
    response = await client.post(
        "/auth/forgot-password", json={"email": "nobody-here@example.com"}
    )
    assert response.status_code == 200
    assert sent == [], "없는 계정에는 메일이 가지 않되, 응답은 같아야 합니다"


async def test_reset_codes_are_attempt_limited_and_superseded(
    client: httpx.AsyncClient, alice: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    import re

    sent: list[str] = []

    async def capture(to: str, subject: str, body: str, config=None) -> None:  # noqa: ANN001
        sent.append(body)

    monkeypatch.setattr("app.core.mailer.send_email", capture)
    monkeypatch.setattr(
        "app.core.config.settings.rate_limit_forgot_per_hour", 50
    )

    await client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    first = re.search(r"\b(\d{6})\b", sent[0]).group(1)

    # A newer code voids the old one.
    await client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    second = re.search(r"\b(\d{6})\b", sent[1]).group(1)
    stale = await client.post(
        "/auth/reset-password",
        json={"email": "alice@example.com", "code": first, "new_password": "x" * 12},
    )
    if first != second:  # 두 코드가 우연히 같으면 이 단언은 성립하지 않음
        assert stale.status_code == 401

    # Five wrong guesses burn the code even if the sixth is right.
    for _ in range(5):
        wrong = await client.post(
            "/auth/reset-password",
            json={
                "email": "alice@example.com",
                "code": "000000" if second != "000000" else "111111",
                "new_password": "x" * 12,
            },
        )
        assert wrong.status_code == 401
    burned = await client.post(
        "/auth/reset-password",
        json={"email": "alice@example.com", "code": second, "new_password": "x" * 12},
    )
    assert burned.status_code == 401


# ── Admin SMTP settings ──────────────────────────────────────────────────────


async def test_a_workspace_owner_manages_smtp_and_the_password_never_echoes(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    from tests.test_channels import _join_workspace

    await _join_workspace(alice, bob, workspace)

    # A plain member is refused.
    denied = await bob.get("/admin/smtp")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "server_admin_required"

    # Before anything is stored: env is empty in tests → source none.
    initial = (await alice.get("/admin/smtp")).json()
    assert initial["source"] in ("none", "env")

    saved = await alice.put(
        "/admin/smtp",
        json={
            "host": "smtp.acme.example",
            "port": 465,
            "username": "mailer@acme.example",
            "password": "relay-secret",
            "starttls": False,
            "mail_from": "llack@acme.example",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["source"] == "database"
    assert body["password_set"] is True
    assert "relay-secret" not in saved.text, "비밀번호는 어떤 응답에도 나오면 안 됩니다"

    # Editing without retyping the password keeps the stored secret.
    edited = await alice.put(
        "/admin/smtp",
        json={
            "host": "smtp.acme.example",
            "port": 587,
            "username": "mailer@acme.example",
            "password": None,
            "starttls": True,
            "mail_from": "llack@acme.example",
        },
    )
    assert edited.json()["password_set"] is True

    # The reset-mail path now resolves the stored relay.
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import get_engine
    from app.services.server_settings import resolve_smtp

    async with AsyncSession(get_engine()) as db:
        config = await resolve_smtp(db)
    assert config.host == "smtp.acme.example"
    assert config.port == 587
    assert config.password == "relay-secret"

    # An empty host clears the override.
    cleared = await alice.put(
        "/admin/smtp",
        json={"host": "", "mail_from": "llack@acme.example"},
    )
    assert cleared.json()["source"] in ("none", "env")


async def test_smtp_test_endpoint_reports_failure_instead_of_500(
    alice: Actor, workspace: dict
) -> None:
    result = await alice.post(
        "/admin/smtp/test",
        json={
            "host": "127.0.0.1",
            "port": 9,  # discard port: nothing listens
            "mail_from": "llack@acme.example",
        },
    )
    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is False
    assert body["error"]
