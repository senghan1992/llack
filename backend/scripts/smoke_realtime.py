"""End-to-end realtime check against the running server.

Bob holds a WebSocket; Alice posts over HTTP; Bob must receive the frame.
This is the path pytest could not cover, because the sync WebSocket test
client runs its own event loop.
"""
import asyncio
import json
import sys

import httpx
import websockets

API = "http://127.0.0.1:8000/api/v1"
WSU = "ws://127.0.0.1:8000/api/v1/ws"
PW = "llack-dev-password"

async def login(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    d = r.json()
    return d["tokens"]["access_token"], d["user"]

async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        alice_tok, alice = await login(client, "alice@example.com")
        bob_tok, bob = await login(client, "bob@example.com")
        ah = {"Authorization": f"Bearer {alice_tok}"}

        ws_id = (await client.get(f"{API}/workspaces", headers=ah)).json()[0]["id"]
        channels = (await client.get(f"{API}/workspaces/{ws_id}/channels", headers=ah)).json()
        dev = next(c for c in channels if c["name"] == "개발")

        results = {}
        async with websockets.connect(f"{WSU}?token={bob_tok}&workspace_id={ws_id}") as sock:
            hello = json.loads(await asyncio.wait_for(sock.recv(), 10))
            assert hello["type"] == "hello", hello
            results["hello_seq"] = hello["seq"]
            results["hello_user_matches"] = hello["data"]["user_id"] == bob["id"]
            results["hello_workspaces"] = hello["data"]["workspace_ids"] == [ws_id]

            # ping/pong
            await sock.send(json.dumps({"type": "ping", "id": "p1", "data": {}}))
            seen_pong = False
            for _ in range(6):
                f = json.loads(await asyncio.wait_for(sock.recv(), 10))
                if f["type"] == "pong":
                    seen_pong = True
                    results["pong_echoes_id"] = f.get("id") == "p1"
                    break
            results["pong"] = seen_pong

            # Alice mentions Bob; Bob must get message.created AND notification.
            body = f"<@{bob['id']}> 실시간 확인 부탁드립니다"
            posted = await client.post(
                f"{API}/channels/{dev['id']}/messages",
                headers=ah, json={"body": body, "client_msg_id": None},
            )
            posted.raise_for_status()
            message_id = posted.json()["id"]

            got_message = got_notification = False
            deadline = asyncio.get_event_loop().time() + 12
            seqs = []
            while (got_message and got_notification) is False:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                f = json.loads(await asyncio.wait_for(sock.recv(), remaining))
                seqs.append(f.get("seq"))
                if f["type"] == "message.created" and f["data"]["message"]["id"] == message_id:
                    got_message = True
                    results["fanout_body"] = f["data"]["message"]["body"] == body
                    results["fanout_author"] = f["data"]["message"]["author"]["id"] == alice["id"]
                    results["fanout_workspace"] = f.get("workspace_id") == ws_id
                elif f["type"] == "notification":
                    got_notification = True
                    results["notification_channel"] = f["data"]["channel_id"] == dev["id"]

            results["received_message_created"] = got_message
            results["received_notification"] = got_notification
            results["seqs_monotonic"] = seqs == sorted(s for s in seqs if s is not None)

            # Alice reacts; Bob must see reaction.added.
            await client.put(f"{API}/messages/{message_id}/reactions", headers=ah,
                             json={"emoji": "👍"})
            got_reaction = False
            deadline = asyncio.get_event_loop().time() + 8
            while not got_reaction:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                f = json.loads(await asyncio.wait_for(sock.recv(), remaining))
                if f["type"] == "reaction.added":
                    got_reaction = f["data"]["emoji"] == "👍"
            results["received_reaction_added"] = got_reaction

            # Bob marks read over the socket.
            await sock.send(json.dumps({
                "type": "mark_read", "id": "r1",
                "data": {"channel_id": dev["id"], "message_id": message_id},
            }))
            got_read = False
            deadline = asyncio.get_event_loop().time() + 8
            while not got_read:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                f = json.loads(await asyncio.wait_for(sock.recv(), remaining))
                if f["type"] == "channel.read":
                    got_read = f["data"]["unread_count"] == 0
            results["mark_read_over_socket"] = got_read

            # Typing from Bob must NOT come back to Bob (exclude_connection).
            await sock.send(json.dumps({
                "type": "typing", "data": {"channel_id": dev["id"]}}))
            echoed = False
            try:
                for _ in range(3):
                    f = json.loads(await asyncio.wait_for(sock.recv(), 2))
                    if f["type"] == "typing" and f["data"]["user_id"] == bob["id"]:
                        echoed = True
            except TimeoutError:
                pass
            results["own_typing_not_echoed"] = not echoed

            # Unknown command -> error frame, socket stays alive.
            await sock.send(json.dumps({"type": "bogus", "id": "b1", "data": {}}))
            got_err = False
            deadline = asyncio.get_event_loop().time() + 6
            while not got_err:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                f = json.loads(await asyncio.wait_for(sock.recv(), remaining))
                if f["type"] == "error":
                    got_err = f["data"]["code"] == "unknown_command"
            results["unknown_command_errors"] = got_err

        # Bad token must be refused at the handshake.
        try:
            async with websockets.connect(f"{WSU}?token=garbage-token-value") as bad:
                await asyncio.wait_for(bad.recv(), 5)
            results["bad_token_refused"] = False
        except Exception:
            results["bad_token_refused"] = True

    print()
    failures = []
    for key, value in results.items():
        ok = value is True or (isinstance(value, int) and not isinstance(value, bool))
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failures.append(key)
        print(f"  [{mark}] {key} = {value}")
    print()
    if failures:
        print("FAILURES:", ", ".join(failures))
        sys.exit(1)
    print("all realtime end-to-end checks passed")

asyncio.run(main())
