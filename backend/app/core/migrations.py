"""스키마의 이력 — Alembic 이 DDL 의 유일한 출처.

이 모듈은 서버가 기동할 때 스키마를 준비합니다. 세 가지 경우가 있습니다.

1. **빈 데이터베이스** — 테이블이 하나도 없으면 `upgrade head` 로 전부 만듭니다.
2. **Alembic 이 관리하는 데이터베이스** — 현재 리비전이 head 보다 오래면
   `upgrade head` 로 앞당깁니다. 서버를 다시 켜는 것만으로 업그레이드가
   끝나야 합니다 — 배포가 "코드 교체 + 재시작" 하나로 되어야 하기 때문입니다.
3. **Alembic 이전에 만들어진 데이터베이스** — `alembic_version` 표가 없는
   데이터베이스입니다. 메타데이터와 모양을 맞춘 뒤(없는 표와 열을 만들고)
   현재 리비전으로 찍습니다(stamp). 데이터는 그대로 남습니다.

여기서 다루는 마이그레이션은 인스턴스당 하나가 전제입니다 — 두 프로세스가
같은 데이터베이스를 동시에 고치면 서로의 작업을 엎습니다. 이 프로젝트는
실시간 허브가 프로세스 안이라 애초에 인스턴스 하나가 정답입니다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.core import db
from app.core.db import Base

logger = logging.getLogger("llack.migrations")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
ALEMBIC_DIR = BACKEND_ROOT / "alembic"

__all__ = [
    "MigrationError",
    "current_revision",
    "prepare_schema",
]


class MigrationError(RuntimeError):
    """스키마를 현재 리비전까지 올리지 못했습니다."""


def _config(script_location: Path) -> Config:
    """Alembic 설정 — 스크립트 위치를 절대 경로로 고정합니다."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(script_location))
    return config


def _run(command_call: Callable[..., Any], script_location: Path, *args: Any) -> Any:
    """Alembic 명령은 동기식입니다.

    이벤트 루프 안에서 직접 부르면 Alembic 안의 `asyncio.run` 이 겹쳐
    죽습니다. 스레드로 넘깁니다 — 데이터베이스는 Alembic 이 따로 엽니다.
    """
    return asyncio.to_thread(command_call, _config(script_location), *args)


async def _tables(connection) -> set[str]:
    return await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))


async def current_revision(connection) -> str | None:
    """데이터베이스가 지금 어느 리비전인지. 관리 밖이면 ``None``."""
    if "alembic_version" not in await _tables(connection):
        return None
    rows = await connection.execute(text("SELECT version_num FROM alembic_version"))
    versions = [row[0] for row in rows if row[0]]
    return max(versions) if versions else None


async def _upgrade_to_head(script_location: Path) -> None:
    logger.info("스키마를 현재 리비전으로 올립니다 (alembic upgrade head)")
    try:
        await _run(command.upgrade, script_location, "head")
    except Exception as exc:
        raise MigrationError(
            "스키마를 현재 리비전으로 올리지 못했습니다.\n"
            f"{exc}\n"
            "마이그레이션은 되돌릴 수 있습니다 — 서버를 내리고 "
            "`make db-migrate` 를 다시 실행하세요."
        ) from exc


async def _adopt_legacy_database(script_location: Path) -> None:
    """Alembic 이전에 만들어진 데이터베이스를 지금의 모양에 맞춥니다.

    없는 표는 만들고(`create_all`), 뒤늦게 생긴 열은 더하고(`ensure_columns`),
    모양이 맞는지는 `ensure_schema` 가 봅니다 — 맞지 않으면 여기서 부팅이
    멈추고, 그때는 사람이 직접 손대야 합니다.
    """
    from app.core.db import create_all, ensure_columns, ensure_schema

    logger.warning(
        "이 데이터베이스는 Alembic 이 관리하기 전에 만들어졌습니다. "
        "모양을 현재 스키마에 맞춘 뒤 현재 리비전으로 찍습니다."
    )
    await create_all()
    await ensure_columns()
    await ensure_schema()
    await _run(command.stamp, script_location, "head")
    logger.info("데이터베이스를 현재 리비전으로 찍었습니다 (alembic stamp head)")


async def prepare_schema(script_location: Path | None = None) -> None:
    """기동 시 스키마를 준비합니다. 실패하면 서버가 뜨지 않습니다."""
    location = script_location or ALEMBIC_DIR
    async with db.engine.connect() as connection:
        revision = await current_revision(connection)
        tables = await _tables(connection)

    if revision is None and (tables & set(Base.metadata.tables)):
        await _adopt_legacy_database(location)
        return

    await _upgrade_to_head(location)
