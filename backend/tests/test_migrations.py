"""스키마의 이력 — Alembic 을 쓰는 방법과, 옛 방식(`ensure_columns`)의 계약."""

from __future__ import annotations

import shutil

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import db
from app.core.db import Base, ensure_columns, ensure_schema
from app.core.migrations import ALEMBIC_DIR, ALEMBIC_INI, current_revision, prepare_schema

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


# ── Alembic ─────────────────────────────────────────────────────────────


def _alembic_config():
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def _head_revision() -> str:
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    assert head is not None
    return head


async def _database(tmp_path, monkeypatch: pytest.MonkeyPatch, name: str = "m.db"):
    """A database on its own file, with both the engine and the URL pointed at it."""
    url = f"sqlite+aiosqlite:///{tmp_path / name}"
    engine = create_async_engine(url)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATABASE_URL", url)
    return engine


async def test_the_migrations_produce_the_schema_the_models_describe(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migrations and the models must not drift apart.

    This is the one that keeps the migration tool honest: a model changed
    without a matching migration would leave deployed databases behind, and
    nothing else in the suite would notice.
    """
    engine = await _database(tmp_path, monkeypatch, "fresh.db")
    try:
        await prepare_schema()

        async with engine.connect() as connection:

            def compare(sync):
                context = MigrationContext.configure(sync, opts={"compare_type": True})
                return compare_metadata(context, Base.metadata)

            diff = await connection.run_sync(compare)
        assert diff == []
    finally:
        await engine.dispose()


async def test_a_fresh_database_gets_the_current_revision(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _database(tmp_path, monkeypatch, "new.db")
    try:
        await prepare_schema()
        async with engine.connect() as connection:
            revision = await current_revision(connection)
        assert revision == _head_revision()
    finally:
        await engine.dispose()


async def test_a_database_from_before_alembic_is_adopted_without_losing_data(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database made by the old ``create_all`` way keeps its rows."""
    engine = await _database(tmp_path, monkeypatch, "legacy.db")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "INSERT INTO workspaces (id, name, slug, created_at) "
                    "VALUES ('wsp_old', '한빛', 'hanbit', '2026-11-14 00:00:00')"
                )
            )
        async with engine.connect() as connection:
            assert await current_revision(connection) is None

        await prepare_schema()

        async with engine.connect() as connection:
            assert await current_revision(connection) == _head_revision()
            rows = (await connection.execute(text("SELECT name FROM workspaces"))).all()
        assert rows == [("한빛",)]
    finally:
        await engine.dispose()


async def test_a_database_behind_the_current_revision_is_brought_up(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed database is upgraded, not left behind.

    A second revision is written into a copy of the script directory so the
    upgrade has something to do.
    """
    engine = await _database(tmp_path, monkeypatch, "behind.db")
    scripts = tmp_path / "alembic"
    shutil.copytree(ALEMBIC_DIR, scripts)
    (scripts / "versions" / "20261114_1500_test_column.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "\n"
        "revision = '0002_test'\n"
        "down_revision = '0001_initial'\n"
        "branch_labels = None\n"
        "depends_on = None\n"
        "\n"
        "\n"
        "def upgrade() -> None:\n"
        "    op.add_column('users', sa.Column('nickname', sa.String(length=40), nullable=True))\n"
        "\n"
        "\n"
        "def downgrade() -> None:\n"
        "    op.drop_column('users', 'nickname')\n"
    )
    try:
        await prepare_schema(scripts)
        async with engine.connect() as connection:
            assert await current_revision(connection) == "0002_test"
            columns = {
                row[1] for row in (await connection.execute(text("PRAGMA table_info(users)"))).all()
            }
        assert "nickname" in columns
    finally:
        await engine.dispose()
