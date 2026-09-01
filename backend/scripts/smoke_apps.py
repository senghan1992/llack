"""End-to-end check of the mini-app platform against the running server.

Follows the exact path a panel app takes: the host mints a panel session, the
panel uses only the bridge token, and every boundary is probed.
"""
import asyncio
import sys

import httpx

API = "http://127.0.0.1:8000/api/v1"
PW = "llack-dev-password"
results = {}

def check(name, value):
    results[name] = value

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": PW})
        alice = r.json()
        ah = {"Authorization": f"Bearer {alice['tokens']['access_token']}"}

        ws_id = (await c.get(f"{API}/workspaces", headers=ah)).json()[0]["id"]
        installs = (await c.get(f"{API}/workspaces/{ws_id}/apps", headers=ah)).json()
        check("app_installed", len(installs) == 1)
        inst = installs[0]
        check("bot_identity_created", bool(inst["bot_user_id"]))
        check("scopes_granted", set(inst["granted_scopes"]) == {
            "identity:read", "channels:read", "messages:write", "storage", "panel:ui"})

        channels = (await c.get(f"{API}/workspaces/{ws_id}/channels", headers=ah)).json()
        deploy = next(ch for ch in channels if ch["name"] == "배포")
        dm = next(ch for ch in channels if ch["kind"] == "dm")

        # ── Host mints a panel session ───────────────────────────────────
        ps = await c.post(
            f"{API}/app-installations/{inst['id']}/panel-session?channel_id={deploy['id']}",
            headers=ah)
        ps.raise_for_status()
        session = ps.json()
        check("panel_url_present", session["panel_url"].startswith("http"))
        check("bridge_token_is_not_user_token",
              session["bridge_token"] != alice["tokens"]["access_token"])
        check("context_carries_channel", session["context"]["channel_id"] == deploy["id"])
        check("context_carries_user", session["context"]["user"]["id"] == alice["user"]["id"])

        # From here on, only the bridge token — as the sandboxed panel would.
        ph = {"Authorization": f"Bearer {session['bridge_token']}"}

        ctx = await c.get(f"{API}/app-bridge/context", headers=ph)
        check("bridge_context_ok", ctx.status_code == 200)
        check("bridge_context_workspace", ctx.json()["workspace_id"] == ws_id)

        # ── Bridge token must NOT open user endpoints ────────────────────
        leak = await c.get(f"{API}/workspaces", headers=ph)
        check("bridge_token_cannot_list_workspaces", leak.status_code != 200)
        leak2 = await c.get(f"{API}/auth/sessions", headers=ph)
        check("bridge_token_cannot_read_sessions", leak2.status_code != 200)

        # ── Channels: DMs must be invisible to an app ────────────────────
        chans = await c.get(f"{API}/app-bridge/channels", headers=ph)
        ids = {ch["id"] for ch in chans.json()}
        check("bridge_lists_channels", deploy["id"] in ids)
        check("bridge_hides_dms", dm["id"] not in ids)

        # ── Post as the bot, idempotently ───────────────────────────────
        payload = {"channel_id": deploy["id"], "body": "브릿지 스모크 테스트 ✅",
                   "client_msg_id": "e2e-bridge-1"}
        first = await c.post(f"{API}/app-bridge/messages", headers=ph, json=payload)
        check("bridge_post_ok", first.status_code == 201)
        msg = first.json()["message"]
        check("posted_as_app_kind", msg["kind"] == "app")
        check("posted_as_bot", msg["author"]["id"] == inst["bot_user_id"])
        check("posted_author_is_bot", msg["author"]["is_bot"] is True)

        retry = await c.post(f"{API}/app-bridge/messages", headers=ph, json=payload)
        check("bridge_post_idempotent",
              retry.status_code == 201 and retry.json()["message"]["id"] == msg["id"])
        check("idempotent_reports_not_created", retry.json()["created"] is False)

        # ── Storage: workspace vs per-user namespaces ────────────────────
        await c.put(f"{API}/app-bridge/storage/cfg", headers=ph,
                    json={"value": {"time": "09:30"}})
        shared = await c.get(f"{API}/app-bridge/storage/cfg", headers=ph)
        check("storage_round_trip", shared.json()["value"]["time"] == "09:30")

        uid = alice["user"]["id"]
        await c.put(f"{API}/app-bridge/storage/cfg", headers=ph,
                    json={"value": {"time": "10:00"}, "scope_key": f"user:{uid}"})
        mine = await c.get(f"{API}/app-bridge/storage/cfg?scope_key=user:{uid}", headers=ph)
        again = await c.get(f"{API}/app-bridge/storage/cfg", headers=ph)
        check("storage_scopes_isolated",
              mine.json()["value"]["time"] == "10:00"
              and again.json()["value"]["time"] == "09:30")

        missing = await c.get(f"{API}/app-bridge/storage/nope", headers=ph)
        check("storage_missing_key_404", missing.status_code == 404)

        # ── Narrowing scopes invalidates an already-minted token ─────────
        await c.patch(f"{API}/app-installations/{inst['id']}", headers=ah,
                      json={"granted_scopes": ["identity:read"]})
        revoked = await c.get(f"{API}/app-bridge/channels", headers=ph)
        check("narrowing_scopes_takes_effect_immediately", revoked.status_code == 403)
        check("revocation_names_the_scope",
              revoked.json()["error"]["details"]["required_scope"] == "channels:read")

        # Restore, so the dev workspace stays usable.
        await c.patch(f"{API}/app-installations/{inst['id']}", headers=ah,
                      json={"granted_scopes": [
                          "identity:read", "channels:read", "messages:write",
                          "storage", "panel:ui"]})

        # ── The message really is in the channel for a human ─────────────
        hist = await c.get(f"{API}/channels/{deploy['id']}/messages?limit=5", headers=ah)
        bodies = [m["body"] for m in hist.json()["items"]]
        check("app_message_visible_to_humans", "브릿지 스모크 테스트 ✅" in bodies)

    print()
    failures = [k for k, v in results.items() if v is not True]
    for k, v in results.items():
        print(f"  [{'PASS' if v is True else 'FAIL'}] {k} = {v}")
    print()
    if failures:
        print("FAILURES:", ", ".join(failures))
        sys.exit(1)
    print("all mini-app platform end-to-end checks passed")

asyncio.run(main())
