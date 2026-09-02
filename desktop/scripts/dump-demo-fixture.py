"""Re-record `src/lib/demo/fixture.json` from a running, seeded backend.

    make seed && make backend            # in another shell
    python3 scripts/dump-demo-fixture.py > src/lib/demo/fixture.json

Hand-written fixtures drift from the API they imitate, and the first symptom is
a demo rendering a shape the server never returns — which makes the demo
actively misleading rather than merely incomplete. So this records the real
responses instead. Edit the recording by re-running this, never by hand.

Only read routes are captured. Writes (sending, reacting, editing) are answered
from memory by `src/lib/demo/index.ts`, because a recording cannot represent
"and then the thing you just did appears".
"""
import json, sys
import httpx

API = "http://127.0.0.1:8000/api/v1"
c = httpx.Client(base_url=API, timeout=20)

auth = c.post("/auth/login", json={
    "email": "alice@example.com",
    "password": "llack-dev-password",
    "device": {"device_name": "demo-dump", "platform": "linux"},
}).raise_for_status().json()
tok = auth["tokens"]["access_token"]
H = {"authorization": f"Bearer {tok}"}

out = {}
def grab(method, path, **kw):
    r = c.request(method, path, headers=H, **kw)
    if r.status_code >= 400:
        print(f"  skip {method} {path} -> {r.status_code}", file=sys.stderr)
        return None
    body = r.json() if r.content else None
    out[f"{method} {path}"] = body
    return body

me = grab("GET", "/me")
workspaces = grab("GET", "/workspaces")
ws = workspaces[0]["id"]
print("workspace", ws, workspaces[0]["name"], file=sys.stderr)

channels = grab("GET", f"/workspaces/{ws}/channels")
grab("GET", f"/workspaces/{ws}/users?limit=200")
grab("GET", f"/workspaces/{ws}/channels/browse")
grab("GET", f"/workspaces/{ws}/apps")
grab("GET", f"/workspaces/{ws}/apps/available")
grab("GET", f"/workspaces/{ws}/search?q=인증")

for ch in channels:
    page = grab("GET", f"/channels/{ch['id']}/messages?limit=80")
    if not page:
        continue
    for m in page.get("items", []):
        if m.get("reply_count", 0) > 0:
            grab("GET", f"/messages/{m['id']}/replies?limit=200")

print(json.dumps({"me": me, "workspace_id": ws, "responses": out}, ensure_ascii=False))
