"""The schema grows one column at a time: the tests for `ensure_columns`."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import db
from app.core.db import Base, ensure_columns, ensure_schema

# The shape of ``projects`` and ``tasks`` before the description and the
# roadmap link were added.
OLD_PROJECTS = """
CREATE TABLE projects (
    id VARCHAR(40) PRIMARY KEY,
    workspace_id VARCHAR(40),
    name VARCHAR(120),
    purpose TEXT,
    deliverables TEXT,
    channel_id VARCHAR(40),
    created_by VARCHAR(40),
    is_archived BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME
)
"""

OLD_TASKS = """
CREATE TABLE tasks (
    id VARCHAR(40) PRIMARY KEY,
    project_id VARCHAR(40),
    title VARCHAR(200),
    description TEXT,
    status VARCHAR(16),
    assignee_id VARCHAR(40),
    created_by VARCHAR(40),
    start_at DATETIME,
    due_at DATETIME,
    position INTEGER,
    created_at DATETIME,
    updated_at DATETIME
)
"""


async def _old_database(tmp_path, monkeypatch):
    """A database written before the description and the roadmaps existed."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("DROP TABLE tasks"))
        await connection.execute(text("DROP TABLE projects"))
        await connection.execute(text(OLD_PROJECTS))
        await connection.execute(text(OLD_TASKS))
        await connection.execute(
            text(
                "INSERT INTO projects (id, workspace_id, name, purpose, deliverables, created_by) "
                "VALUES ('prj_old', 'wsp_old', '구독 결제', '구독 결제를 다시 만든다', "
                "'결제 모듈', 'usr_old')"
            )
        )
    monkeypatch.setattr(db, "engine", engine)
    return engine


async def test_an_old_project_keeps_its_purpose_as_a_description(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _old_database(tmp_path, monkeypatch)
    try:
        await ensure_columns()

        async with engine.begin() as connection:
            rows = (
                await connection.execute(text("SELECT description, purpose FROM projects"))
            ).all()
        assert rows == [("구독 결제를 다시 만든다", "구독 결제를 다시 만든다")]
    finally:
        await engine.dispose()


async def test_the_description_is_copied_once(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = await _old_database(tmp_path, monkeypatch)
    try:
        await ensure_columns()

        # A team that clears the description keeps it cleared: the purpose is
        # only carried over once.
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE projects SET description = ''"))
        await ensure_columns()

        async with engine.begin() as connection:
            rows = (await connection.execute(text("SELECT description FROM projects"))).all()
        assert rows == [("",)]
    finally:
        await engine.dispose()


async def test_tasks_get_a_roadmap_column(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = await _old_database(tmp_path, monkeypatch)
    try:
        await ensure_columns()

        async with engine.begin() as connection:
            columns = {
                row[1] for row in (await connection.execute(text("PRAGMA table_info(tasks)"))).all()
            }
            indexes = {
                row[1] for row in (await connection.execute(text("PRAGMA index_list(tasks)"))).all()
            }
        assert "roadmap_id" in columns
        assert "ix_tasks_roadmap_id" in indexes
    finally:
        await engine.dispose()


async def test_tasks_get_a_milestone_column(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = await _old_database(tmp_path, monkeypatch)
    try:
        await ensure_columns()

        async with engine.begin() as connection:
            columns = {
                row[1] for row in (await connection.execute(text("PRAGMA table_info(tasks)"))).all()
            }
            indexes = {
                row[1] for row in (await connection.execute(text("PRAGMA index_list(tasks)"))).all()
            }
        assert "milestone_id" in columns
        assert "ix_tasks_milestone_id" in indexes
    finally:
        await engine.dispose()


async def test_a_database_from_another_version_is_refused(tmp_path, monkeypatch) -> None:
    """A table the models do not know is a database from another version."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # The shape of ``users`` before the rewrite: a display name and a
        # handle, no ``name`` and no ``avatar_color``.
        await connection.execute(text("DROP TABLE users"))
        await connection.execute(
            text(
                "CREATE TABLE users ("
                "id VARCHAR(40) PRIMARY KEY, "
                "email VARCHAR(320), "
                "password_hash TEXT, "
                "display_name VARCHAR(120), "
                "handle VARCHAR(64))"
            )
        )
    monkeypatch.setattr(db, "engine", engine)
    try:
        with pytest.raises(db.SchemaMismatch) as failure:
            await ensure_schema()
        message = str(failure.value)
        assert "users" in message
        assert "name" in message
        assert "avatar_color" in message
    finally:
        await engine.dispose()


async def test_a_database_that_matches_is_accepted(tmp_path, monkeypatch) -> None:
    """The check does not get in the way of a database that is fine."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ok.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(db, "engine", engine)
    try:
        await ensure_schema()
    finally:
        await engine.dispose()
