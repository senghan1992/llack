"""Alembic 환경.

데이터베이스 주소는 여기 적지 않습니다. `app.core.db` 가 환경설정에서 읽은
주소를 그대로 씁니다 — 서버와 마이그레이션이 서로 다른 데이터베이스를
가리키는 일이 없도록, 같은 해석을 공유하는 것입니다.

스키마는 두 가지 경로로 만들어집니다.

* `alembic upgrade head` — 마이그레이션이 만든다(운영의 정식 경로).
* 서버 기동 — `app.core.migrations` 가 같은 `upgrade head` 를 부른다.

SQLite 는 ALTER 를 거의 못 하므로 batch 모드로 쓴다 — 같은 마이그레이션이
SQLite 와 Postgres 양쪽에서 그대로 돌아간다.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core import db
from app.core.db import Base
import app.models  # noqa: F401  (모든 모델을 불러와 autogenerate 가 보게 한다)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 환경설정에서 읽은 주소(상대 SQLite 경로의 기준까지 같게). `db` 모듈을 통해
# 읽으므로 서버가 가리키는 데이터베이스와 마이그레이션이 어긋나지 않습니다.
DATABASE_URL = db.DATABASE_URL

config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=DATABASE_URL.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=DATABASE_URL.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
