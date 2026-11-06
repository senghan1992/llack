"""Shared pytest fixtures.

The environment is configured before the application is imported so that the
engine of the test process points at a throw-away SQLite file.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="llack-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_ROOT / 'test.db'}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hmac-sha256"
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")

import httpx  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.ids import MEMBER_PREFIX, new_id  # noqa: E402
from app.main import app  # noqa: E402
from app.models.workspace import WorkspaceMembership  # noqa: E402

API = "/api/v1"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client bound to the app, with a freshly created schema."""
    async with LifespanManager(app):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db


async def signup(
    client: httpx.AsyncClient,
    email: str = "hyunjin@hanbit.co.kr",
    name: str = "김현진",
    workspace_name: str = "한빛",
    password: str = "hanbit2026",
) -> dict:
    response = await client.post(
        f"{API}/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": name,
            "workspace_name": workspace_name,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def add_workspace_member(
    session: AsyncSession, workspace_id: str, user_id: str, role: str = "member"
) -> None:
    session.add(
        WorkspaceMembership(
            id=new_id(MEMBER_PREFIX),
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )
    )
    await session.commit()


async def join_workspace(
    client: httpx.AsyncClient,
    session: AsyncSession,
    workspace_id: str,
    email: str,
    name: str,
    role: str = "member",
) -> dict:
    """Sign a second person up and attach them to an existing workspace."""
    data = await signup(client, email=email, name=name, workspace_name=f"{name}의 워크스페이스")
    await add_workspace_member(session, workspace_id, data["user"]["id"], role)
    return data
