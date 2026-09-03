"""Operations: Redis rate limiting, metrics, workers, full-text search plan."""

from __future__ import annotations

import fakeredis
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from app import workers
from app.core.config import settings
from app.core.db import get_sessionmaker
from app.core.errors import RateLimited
from app.core.ratelimit import RateLimiter
from app.models.channel import ChannelMember
from app.services.messages import search_statement
from tests.conftest import Actor
from tests.test_channels import _join_workspace

# ── A-1 rate limiting ───────────────────────────────────────────────────────


def test_redis_buckets_are_shared_and_refill() -> None:
    node_a = RateLimiter()
    node_b = RateLimiter()
    fake = fakeredis.FakeRedis()
    node_a.use_redis(fake)
    node_b.use_redis(fake)
    assert node_a.backend == "redis"

    # Two "nodes" draw from one allowance of 3.
    node_a.check("login", "1.2.3.4", capacity=3, per_seconds=60)
    node_b.check("login", "1.2.3.4", capacity=3, per_seconds=60)
    node_a.check("login", "1.2.3.4", capacity=3, per_seconds=60)
    with pytest.raises(RateLimited) as blocked:
        node_b.check("login", "1.2.3.4", capacity=3, per_seconds=60)
    assert blocked.value.details["retry_after_seconds"] > 0
    # A different key is a different bucket.
    node_b.check("login", "5.6.7.8", capacity=3, per_seconds=60)
    # Keys expire on their own.
    assert fake.pttl("llack:ratelimit:login:1.2.3.4") > 0


def test_redis_outage_falls_back_to_in_process_and_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Broken:
        def register_script(self, _lua: str):  # noqa: ANN202
            def run(keys, args):  # noqa: ANN001, ANN202
                raise ConnectionError("redis is down")

            return run

    limiter = RateLimiter()
    limiter.use_redis(Broken())
    # Falls through to the local bucket: 2 allowed, 3rd refused.
    limiter.check("x", "k", capacity=2, per_seconds=60)
    limiter.check("x", "k", capacity=2, per_seconds=60)
    with pytest.raises(RateLimited):
        limiter.check("x", "k", capacity=2, per_seconds=60)
    assert limiter._redis_failed_logged is True


# ── A-5 metrics ─────────────────────────────────────────────────────────────


async def test_metrics_page_counts_requests_by_route_template(
    alice: Actor, client: httpx.AsyncClient
) -> None:
    await alice.get("/me")
    root = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
    )
    async with root:
        page = await root.get("/metrics")
        assert page.status_code == 200
        text = page.text
        series = 'llack_http_requests_total{method="GET",path_template="/api/v1/me",status="200"}'
        assert series in text
        assert "llack_http_request_seconds_bucket" in text
        assert "llack_ws_connections" in text
        assert "llack_messages_created_total" in text


async def test_metrics_require_the_token_when_one_is_set(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "metrics_token", "scrape-me")
    root = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
    )
    async with root:
        assert (await root.get("/metrics")).status_code == 401
        ok = await root.get("/metrics", headers={"Authorization": "Bearer scrape-me"})
        assert ok.status_code == 200


# ── A-6 workers ─────────────────────────────────────────────────────────────


async def test_run_once_runs_registered_jobs_and_counts_failures() -> None:
    calls: list[str] = []

    async def fine() -> None:
        calls.append("fine")

    async def broken() -> None:
        raise RuntimeError("boom")

    workers.register("test_fine", 10, fine)
    workers.register("test_broken", 10, broken)
    assert await workers.run_once("test_fine")
    assert await workers.run_once("test_broken")
    assert calls == ["fine"]
    assert workers.registered()["test_fine"].runs == 1
    assert workers.registered()["test_broken"].last_error == "boom"
    for name in ("unread_recompute", "retention_sweep", "presence_cleanup"):
        assert name in workers.registered()


async def test_unread_recompute_repairs_a_drifted_counter(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    general = next(
        c
        for c in (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()
        if c["name"] == "general"
    )
    for i in range(3):
        await alice.post(f"/channels/{general['id']}/messages", json={"body": f"m{i}"})

    async with get_sessionmaker()() as db:
        membership = await db.scalar(
            select(ChannelMember).where(
                ChannelMember.channel_id == general["id"], ChannelMember.user_id == bob.id
            )
        )
        membership.unread_count = 99  # drift
        await db.commit()

    assert (await bob.get(f"/channels/{general['id']}")).json()["membership"]["unread_count"] == 99
    assert await workers.run_once("unread_recompute")
    assert (await bob.get(f"/channels/{general['id']}")).json()["membership"]["unread_count"] == 3


async def test_presence_cleanup_runs_without_sockets() -> None:
    assert await workers.run_once("presence_cleanup")
    assert workers.registered()["presence_cleanup"].last_error is None


# ── A-9 search ──────────────────────────────────────────────────────────────


def test_search_uses_full_text_on_postgres_and_like_elsewhere() -> None:
    pg = str(
        search_statement(workspace_id="w", user_id="u", term="배포 계획", dialect="postgresql")
        .compile(dialect=postgresql.dialect())
    )
    assert "to_tsvector" in pg and "plainto_tsquery" in pg and "ts_rank" in pg
    assert "@@" in pg

    lite = str(
        search_statement(workspace_id="w", user_id="u", term="배포 계획", dialect="sqlite")
        .compile(dialect=sqlite.dialect())
    )
    assert "LIKE" in lite and "to_tsvector" not in lite


async def test_sqlite_search_still_finds_messages(alice: Actor, workspace: dict) -> None:
    general = next(
        c
        for c in (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()
        if c["name"] == "general"
    )
    await alice.post(f"/channels/{general['id']}/messages", json={"body": "전문검색 대상 문장"})
    hits = (await alice.get(f"/workspaces/{workspace['id']}/search?q=전문검색")).json()
    assert [h["message"]["body"] for h in hits["messages"]] == ["전문검색 대상 문장"]
