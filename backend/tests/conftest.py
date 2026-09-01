"""Test fixtures: an isolated SQLite database and storage root per test."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Settings are read at import time, so the environment must be set before any
# application module is imported.
_TMP = Path(tempfile.mkdtemp(prefix="llack-test-"))
os.environ.update(
    LLACK_ENV="development",
    LLACK_SECRET_KEY="test-secret-key-not-used-anywhere-else-0123456789",
    LLACK_DATABASE_URL=f"sqlite+aiosqlite:///{_TMP / 'test.db'}",
    LLACK_REDIS_URL="",
    LLACK_STORAGE_BACKEND="local",
    LLACK_STORAGE_LOCAL_DIR=str(_TMP / "uploads"),
)

import httpx  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402

from app.core.db import dispose_engine, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def _fresh_schema() -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


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
