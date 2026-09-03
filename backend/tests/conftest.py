"""Test fixtures: an isolated SQLite database and storage root per test."""

from __future__ import annotations

import os
import tempfile
import warnings
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Settings are read at import time, so the environment must be set before any
# application module is imported.
_TMP = Path(tempfile.mkdtemp(prefix="llack-test-"))
# `LLACK_TEST_DATABASE_URL` points the whole suite at a Postgres database (the
# schema is built by the alembic chain, so the migrations are exercised too).
# Unset, the suite runs on a throwaway SQLite file as before.
_PG_URL = os.environ.get("LLACK_TEST_DATABASE_URL", "")
os.environ.update(
    LLACK_ENV="development",
    LLACK_SECRET_KEY="test-secret-key-not-used-anywhere-else-0123456789",
    LLACK_DATABASE_URL=_PG_URL or f"sqlite+aiosqlite:///{_TMP / 'test.db'}",
    LLACK_REDIS_URL="",
    LLACK_STORAGE_BACKEND="local",
    LLACK_STORAGE_LOCAL_DIR=str(_TMP / "uploads"),
    # Workers are exercised through `workers.run_once`, not on a timer.
    LLACK_RUN_WORKERS="false",
)

import httpx  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402

from app.core.db import dispose_engine, get_engine  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


async def _build_postgres_schema() -> None:
    """Once per session: empty `public` and rebuild it through alembic.

    Not `create_all`: on Postgres the point is the partitioned `messages`
    table, which only the migration knows how to build. Alembic runs in a
    subprocess so its own event loop and settings import stay separate.
    """
    import asyncio
    import subprocess
    import sys

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_PG_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()

    env = {**os.environ, "LLACK_DATABASE_URL": _PG_URL}
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed on Postgres:\n{result.stderr[-4000:]}")


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PG_READY = False


@pytest.fixture(autouse=True)
async def _fresh_schema() -> AsyncIterator[None]:
    global _PG_READY
    engine = get_engine()
    if _PG_URL:
        if not _PG_READY:
            await dispose_engine()
            await _build_postgres_schema()
            _PG_READY = True
            engine = get_engine()
        # TRUNCATE the whole graph in one statement: dependency order is the
        # database's problem, and truncating the partitioned parent empties
        # its partitions.
        from sqlalchemy import text

        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        async with engine.begin() as conn:
            # A connection left "idle in transaction" by the previous test (a
            # background task cut off at loop shutdown) would block TRUNCATE
            # forever. The test database is private: end such sessions and say
            # so, because a leak here is a leak in production too.
            leaked = await conn.execute(
                text(
                    "SELECT pid, left(query, 120) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                    "AND state = 'idle in transaction'"
                )
            )
            for pid, query in leaked.all():
                warnings.warn(
                    f"idle-in-transaction connection left behind (pid {pid}): {query}",
                    stacklevel=1,
                )
                await conn.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
            await conn.execute(text("SET LOCAL lock_timeout = '30s'"))
            await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        # asyncpg connections belong to the loop that opened them. Tests that
        # drive the app through Starlette's sync TestClient run it on another
        # loop, so hand back a pool with no live connections.
        await dispose_engine()
        engine = get_engine()
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    # The limiter is process-global; without this, the whole suite shares one
    # register bucket and the 30th test's sign-up gets a spurious 429.
    limiter.reset()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver/api/v1"
        ) as ac:
            yield ac


class Actor:
    """A signed-in user plus a client that sends its bearer token."""

    def __init__(self, client: httpx.AsyncClient, user: dict, tokens: dict) -> None:
        self._client = client
        self.user = user
        self.tokens = tokens

    @property
    def id(self) -> str:
        return self.user["id"]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:  # noqa: ANN003
        headers = {**self.headers, **kwargs.pop("headers", {})}
        return await self._client.request(method, url, headers=headers, **kwargs)

    async def get(self, url: str, **kw) -> httpx.Response:  # noqa: ANN003
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:  # noqa: ANN003
        return await self.request("POST", url, **kw)

    async def put(self, url: str, **kw) -> httpx.Response:  # noqa: ANN003
        return await self.request("PUT", url, **kw)

    async def patch(self, url: str, **kw) -> httpx.Response:  # noqa: ANN003
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw) -> httpx.Response:  # noqa: ANN003
        return await self.request("DELETE", url, **kw)


PASSWORD = "correct-horse-battery"


async def register(
    client: httpx.AsyncClient, email: str, display_name: str, password: str = PASSWORD
) -> Actor:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return Actor(client, body["user"], body["tokens"])


async def grant_service_admin(actor: Actor) -> None:
    """Flip the flag the way an operator would (directly in the database)."""
    from sqlalchemy import update

    from app.core.db import get_sessionmaker
    from app.models.user import User

    async with get_sessionmaker()() as db:
        await db.execute(update(User).where(User.id == actor.id).values(is_service_admin=True))
        await db.commit()


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> Actor:
    return await register(client, "alice@example.com", "김앨리스")


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> Actor:
    return await register(client, "bob@example.com", "이밥")


@pytest.fixture
async def workspace(alice: Actor) -> dict:
    response = await alice.post(
        "/workspaces", json={"name": "테스트 회사", "slug": "test-co"}
    )
    assert response.status_code == 201, response.text
    return response.json()
