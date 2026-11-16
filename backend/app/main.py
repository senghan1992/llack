"""The FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings, validate_production_settings
from app.core.db import SchemaMismatch, SessionLocal, ensure_schema
from app.core.errors import register_exception_handlers
from app.core.migrations import prepare_schema
from app.services.files import purge_orphan_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("llack")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Bring the schema to the current revision before serving anyone."""
    # An insecure production server does not start at all — the check comes
    # before anything touches the database.
    validate_production_settings(settings)
    # The schema is Alembic's job: the database is migrated to the current
    # revision here, so deploying a new version is "replace the code and
    # restart" — nothing else to remember.
    await prepare_schema()
    try:
        await ensure_schema()
    except SchemaMismatch as exc:
        # A database from another version of the app: say so plainly,
        # instead of letting the first login answer "internal server error".
        logger.error("%s", exc)
        raise
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    # Uploads that never reached a message are taken away. The rule is in
    # docs/FILES.md; the sweep runs here so it happens without anyone asking.
    async with SessionLocal() as session:
        removed = await purge_orphan_files(session, settings.orphan_file_hours)
    if removed:
        logger.info("removed %s file(s) that were never shared", removed)
    logger.info("llack backend ready (database=%s)", settings.database_url)
    yield


app = FastAPI(
    title="Atrium",
    version="0.1.0",
    description="ArcheAI internal workspace & messenger API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}
