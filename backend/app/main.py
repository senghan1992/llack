"""Llack backend entrypoint.

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core import db as database
from app.core.config import settings, validate_production_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.ids import new_ulid
from app.core.logging import configure_logging, get_logger
from app.realtime.bus import get_bus, reset_bus
from app.realtime.hub import reset_hub
from app.realtime.presence import get_presence_store, reset_presence_store

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fails the boot, not the first user: a production server on dev
    # defaults must never start serving.
    validate_production_settings(settings)
    if settings.is_production and not settings.require_invite:
        log.warning(
            "sign_up_is_open",
            hint="LLACK_REQUIRE_INVITE=true 로 가입을 초대 필수로 잠글 수 있습니다",
        )
    log.info(
        "startup",
        env=settings.env,
        database=settings.database_url.split("://", 1)[0],
        redis="configured" if settings.redis_url else "in-process",
        storage=settings.storage_backend,
    )
    await database.ping()
    await get_bus().start()
    await get_presence_store().start()
    try:
        yield
    finally:
        log.info("shutdown")
        await reset_hub()
        await reset_presence_store()
        await reset_bus()
        await database.dispose_engine()


app = FastAPI(
    title="Llack API",
    version="0.1.0",
    summary="사내 협업 OS — 채팅, 파일 공유, 사내 앱 패널",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # noqa: ANN001, ANN201
    """Attach a request id, bind it to the logger, and log one line per request."""
    request_id = request.headers.get("x-request-id") or new_ulid()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception(
            "request.failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-Id"] = request_id
    # Health checks would otherwise dominate the log.
    if request.url.path not in ("/health", "/health/ready"):
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
    return response


app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/health/ready", tags=["ops"])
async def readiness() -> dict[str, object]:
    """Readiness probe: fails if the database is unreachable."""
    checks: dict[str, object] = {}
    try:
        await database.ping()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}
