"""structlog configuration: pretty console in dev, JSON lines in production."""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

# Third-party loggers that are useful only when actively debugging them.
_NOISY = ("aiosqlite", "asyncio", "sqlalchemy.engine", "botocore", "aiobotocore", "urllib3")


def configure_logging() -> None:
    app_level = logging.DEBUG if settings.env == "development" else logging.INFO

    renderer = (
        structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        if settings.env == "development"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(app_level),
        # PrintLoggerFactory writes straight to the stream, bypassing the
        # stdlib logging machinery. Note this is why `add_logger_name` is not
        # in the processor chain — it needs a stdlib logger; `get_logger`
        # binds the name itself instead.
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Keep the stdlib root at INFO regardless: a DEBUG root turns every
    # aiosqlite round-trip into a log line.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr, force=True)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    # Duplicates the request line emitted by our own middleware.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Bound logger tagged with the module name."""
    return structlog.get_logger().bind(logger=name)
