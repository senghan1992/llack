"""Async engine, session factory and the declarative base."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import BACKEND_ROOT, get_settings
from app.models.base import Base

__all__ = [
    "Base",
    "DATABASE_URL",
    "SchemaMismatch",
    "SessionLocal",
    "create_all",
    "drop_all",
    "engine",
    "ensure_schema",
    "get_session",
]


class SchemaMismatch(RuntimeError):
    """The database in front of us was made by another version of the app."""


def _resolved_database_url(raw_url: str) -> str:
    """Make relative SQLite paths absolute so the DB file never wanders."""
    prefix = "sqlite+aiosqlite:///"
    if not raw_url.startswith(prefix):
        return raw_url
    path_part = raw_url[len(prefix) :]
    if not path_part or path_part == ":memory:" or path_part.startswith(":memory:"):
        return raw_url
    path = Path(path_part)
    if path.is_absolute():
        return raw_url
    return f"{prefix}{BACKEND_ROOT / path}"


settings = get_settings()
DATABASE_URL = _resolved_database_url(settings.database_url)

engine = create_async_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        yield session


async def create_all() -> None:
    """Create every table declared on :class:`Base`."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_all() -> None:
    """Drop every table declared on :class:`Base` (used by the test suite)."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def ensure_columns() -> None:
    """Add the columns that arrived after a database was first created.

    This project has no migration tool: the schema is made by
    :func:`create_all` and then grows, one ``ALTER TABLE`` at a time. Each
    statement is checked first, so this is safe to run on every start.
    """

    async with engine.begin() as connection:

        def columns(sync_connection) -> set[str]:
            return {c["name"] for c in inspect(sync_connection).get_columns("messages")}

        present = await connection.run_sync(columns)
        if "reply_to_id" not in present:
            await connection.execute(
                text("ALTER TABLE messages ADD COLUMN reply_to_id VARCHAR(40)")
            )
        if "inline" not in present:
            default = "false" if connection.dialect.name == "postgresql" else "0"
            await connection.execute(
                text(f"ALTER TABLE messages ADD COLUMN inline BOOLEAN NOT NULL DEFAULT {default}")
            )

        def file_columns(sync_connection) -> set[str]:
            return {c["name"] for c in inspect(sync_connection).get_columns("files")}

        present = await connection.run_sync(file_columns)
        if "workspace_id" not in present:
            # Files keep the workspace that owns them — the rule that decides
            # where they live and how much room they may take.
            await connection.execute(text("ALTER TABLE files ADD COLUMN workspace_id VARCHAR(40)"))

        def project_columns(sync_connection) -> set[str]:
            return {c["name"] for c in inspect(sync_connection).get_columns("projects")}

        present = await connection.run_sync(project_columns)
        if "description" not in present:
            await connection.execute(
                text("ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT ''")
            )
            # Projects written before the description existed keep the
            # purpose they were made with; the description takes it over.
            await connection.execute(
                text(
                    "UPDATE projects SET description = purpose "
                    "WHERE purpose IS NOT NULL AND purpose <> ''"
                )
            )

        def task_columns(sync_connection) -> set[str]:
            return {c["name"] for c in inspect(sync_connection).get_columns("tasks")}

        present = await connection.run_sync(task_columns)
        if "roadmap_id" not in present:
            await connection.execute(text("ALTER TABLE tasks ADD COLUMN roadmap_id VARCHAR(40)"))
        if "milestone_id" not in present:
            await connection.execute(text("ALTER TABLE tasks ADD COLUMN milestone_id VARCHAR(40)"))

        def task_indexes(sync_connection) -> set[str]:
            return {i["name"] for i in inspect(sync_connection).get_indexes("tasks")}

        indexes = await connection.run_sync(task_indexes)
        if "ix_tasks_roadmap_id" not in indexes:
            await connection.execute(text("CREATE INDEX ix_tasks_roadmap_id ON tasks (roadmap_id)"))
        if "ix_tasks_milestone_id" not in indexes:
            await connection.execute(
                text("CREATE INDEX ix_tasks_milestone_id ON tasks (milestone_id)")
            )


async def ensure_schema() -> None:
    """Make sure the database has the shape the models describe.

    :func:`create_all` creates the tables that are missing but never changes
    a table that already exists. A database left behind by another version of
    the app therefore starts up happily and then fails at the first query —
    and a login that answers "internal server error" is a hard end for the
    person in front of the screen. This check says what is wrong while there
    is still someone to read it.
    """

    async with engine.begin() as connection:

        def present_columns(sync_connection, table: str) -> set[str]:
            try:
                return {c["name"] for c in inspect(sync_connection).get_columns(table)}
            except NoSuchTableError:
                return set()

        problems: list[str] = []
        for table, model_table in Base.metadata.tables.items():
            expected = {column.name for column in model_table.columns}
            present = await connection.run_sync(present_columns, table)
            missing = expected - present
            if missing:
                problems.append(f"{table}: {', '.join(sorted(missing))}")

        if problems:
            raise SchemaMismatch(
                "이 데이터베이스는 현재 코드와 맞지 않는 스키마를 가지고 있습니다.\n"
                + "\n".join(f"  · {problem}" for problem in problems)
                + "\n이 프로젝트에는 스키마를 옮겨주는 도구가 없습니다."
                "\n개발용 SQLite 는 `make db-reset` 으로 파일을 지우고 다시 만들고,"
                "\nPostgres 는 스키마를 새로 만드세요."
            )
