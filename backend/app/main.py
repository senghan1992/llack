"""Llack backend entrypoint.

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import workers
from app.api.v1.router import api_router
from app.core import db as database
from app.core import metrics
from app.core.config import settings, validate_production_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.ids import new_ulid
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import configure_from_settings as configure_rate_limiter
from app.realtime.bus import get_bus, reset_bus
from app.realtime.hub import get_hub, reset_hub
from app.realtime.presence import get_presence_store, reset_presence_store
from app.services import partition_worker as partition_service

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
    configure_rate_limiter()
    metrics.bind_ws_gauge(lambda: get_hub().connection_count)
    # Postgres only (a no-op elsewhere): the month's partition must exist
    # before the first message of the month, not after the first tick.
    await partition_service.ensure_partitions_on_startup()
    await workers.start()
    try:
        yield
    finally:
        log.info("shutdown")
        await workers.stop()
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
    # The route *template* — `/api/v1/channels/{channel_id}` — not the path.
    # Nested routers report their own path (`/me`), so the prefix is restored.
    route = request.scope.get("route")
    template = getattr(route, "path", None) or "unmatched"
    if (
        template != "unmatched"
        and request.url.path.startswith(settings.api_prefix)
        and not template.startswith(settings.api_prefix)
    ):
        template = settings.api_prefix + template
    if request.url.path not in ("/metrics",):
        metrics.observe_request(
            request.method, template, response.status_code, duration_ms / 1000
        )
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


@app.get("/metrics", tags=["ops"], include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus scrape target.

    With `LLACK_METRICS_TOKEN` set, a bearer token is required. Without one
    the page is open in development and does not exist in production — a
    metrics page names routes and counts people, which is not for the public.
    """
    if settings.metrics_token:
        supplied = request.headers.get("authorization", "").partition(" ")[2].strip()
        if not supplied or supplied != settings.metrics_token:
            raise HTTPException(status_code=401, detail="metrics token required")
    elif settings.is_production:
        raise HTTPException(status_code=404)
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)


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
