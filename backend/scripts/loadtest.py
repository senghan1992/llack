"""Load test: how does message fan-out behave under N concurrent people?

    .venv/bin/python scripts/loadtest.py --api http://127.0.0.1:8000 \\
        --users 20 --messages 50

Registers `--users` throwaway accounts (or logs them in if they exist), puts
them in one fresh channel of one workspace, then has every user post
`--messages` messages concurrently. Prints latency percentiles and the error
rate. Run it against a staging server with the real database and Redis — the
numbers from a laptop SQLite are not the numbers that matter.

It is deliberately dependency-free beyond httpx so it can run from any box
with the backend's venv.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

import httpx

PASSWORD = "loadtest-password-0000"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
    return ordered[index]


async def login_or_register(
    client: httpx.AsyncClient, api: str, email: str, name: str
) -> dict[str, str]:
    r = await client.post(f"{api}/auth/login", json={"email": email, "password": PASSWORD})
    if r.status_code == 200:
        return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    r = await client.post(
        f"{api}/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="server root (no /api/v1)")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--messages", type=int, default=50, help="per user")
    parser.add_argument("--stamp", default=str(int(time.time())), help="unique run suffix")
    args = parser.parse_args()

    api = args.api.rstrip("/") + "/api/v1"
    stamp = args.stamp

    async with httpx.AsyncClient(timeout=30) as client:
        print(f"→ {args.users}명 로그인/가입 …", file=sys.stderr)
        headers = await asyncio.gather(
            *[
                login_or_register(client, api, f"load-{stamp}-{i}@example.com", f"부하{i:03d}")
                for i in range(args.users)
            ]
        )
        owner = headers[0]

        ws = await client.post(
            f"{api}/workspaces",
            headers=owner,
            json={"name": f"부하 테스트 {stamp}", "slug": f"load-{stamp}"},
        )
        ws.raise_for_status()
        workspace_id = ws.json()["id"]

        # Everyone else joins via invites (the only door when sign-up is closed).
        emails = [f"load-{stamp}-{i}@example.com" for i in range(1, args.users)]
        invites = await client.post(
            f"{api}/workspaces/{workspace_id}/invites",
            headers=owner,
            json={"emails": emails, "role": "member"},
        )
        invites.raise_for_status()
        tokens = {
            inv["email"]: inv["invite_url"].split("token=")[1].split("&")[0]
            for inv in invites.json()
        }
        await asyncio.gather(
            *[
                client.post(
                    f"{api}/invites/accept", headers=headers[i], json={"token": tokens[email]}
                )
                for i, email in enumerate(emails, start=1)
            ]
        )

        channel = await client.post(
            f"{api}/workspaces/{workspace_id}/channels",
            headers=owner,
            json={"name": f"부하-{stamp}"},
        )
        channel.raise_for_status()
        channel_id = channel.json()["id"]
        await asyncio.gather(
            *[client.post(f"{api}/channels/{channel_id}/join", headers=h) for h in headers[1:]]
        )

        latencies: list[float] = []
        errors: dict[str, int] = {}
        rate_limited = 0

        async def talker(index: int, h: dict[str, str]) -> None:
            nonlocal rate_limited
            for n in range(args.messages):
                started = time.perf_counter()
                try:
                    r = await client.post(
                        f"{api}/channels/{channel_id}/messages",
                        headers=h,
                        json={"body": f"부하 {index}-{n} {stamp}"},
                    )
                except httpx.HTTPError as exc:
                    errors[type(exc).__name__] = errors.get(type(exc).__name__, 0) + 1
                    continue
                latencies.append(time.perf_counter() - started)
                if r.status_code == 429:
                    rate_limited += 1
                    details = r.json().get("error", {}).get("details", {})
                    retry = float(details.get("retry_after_seconds", 1))
                    await asyncio.sleep(min(retry, 5))
                elif r.status_code >= 400:
                    errors[str(r.status_code)] = errors.get(str(r.status_code), 0) + 1

        print(f"→ {args.users} × {args.messages} 메시지 동시 전송 …", file=sys.stderr)
        wall = time.perf_counter()
        await asyncio.gather(*[talker(i, h) for i, h in enumerate(headers)])
        wall = time.perf_counter() - wall

    total = args.users * args.messages
    failed = sum(errors.values())
    print()
    print(f"메시지 {total}개 · {wall:.1f}s · {total / wall:.0f} msg/s (429 재시도 포함)")
    ms = lambda v: f"{v * 1000:.0f} ms"  # noqa: E731
    print(
        f"p50 {ms(percentile(latencies, 50))} · p95 {ms(percentile(latencies, 95))}"
        f" · p99 {ms(percentile(latencies, 99))} · max {ms(max(latencies or [0]))}"
        f" · mean {ms(statistics.fmean(latencies or [0]))}"
    )
    print(f"429 레이트 리밋 {rate_limited}회 · 오류 {failed}건 ({failed / max(total, 1):.2%})"
          + (f" — {errors}" if errors else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
