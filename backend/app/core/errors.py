"""The error envelope used by every failing endpoint.

Every error response looks like::

    {"error": {"code": "not_found", "message": "channel not found", "field": null}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("llack.errors")

UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
VALIDATION_ERROR = "validation_error"
RATE_LIMITED = "rate_limited"
INTERNAL = "internal"

_STATUS_CODES = {
    400: VALIDATION_ERROR,
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    409: CONFLICT,
    413: VALIDATION_ERROR,
    415: VALIDATION_ERROR,
    422: VALIDATION_ERROR,
    429: RATE_LIMITED,
}


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """An error that maps directly onto the documented error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=ErrorEnvelope(
                error=ErrorBody(code=self.code, message=self.message, field=self.field)
            ).model_dump(),
        )


def unauthorized(message: str = "authentication required") -> AppError:
    return AppError(UNAUTHORIZED, message, 401)


def forbidden(message: str = "you do not have access to this resource") -> AppError:
    return AppError(FORBIDDEN, message, 403)


def not_found(message: str = "resource not found") -> AppError:
    return AppError(NOT_FOUND, message, 404)


def conflict(message: str) -> AppError:
    return AppError(CONFLICT, message, 409)


def validation_error(message: str, field: str | None = None) -> AppError:
    return AppError(VALIDATION_ERROR, message, 422, field)


def rate_limited(message: str = "too many requests") -> AppError:
    return AppError(RATE_LIMITED, message, 429)


def internal(message: str = "internal server error") -> AppError:
    return AppError(INTERNAL, message, 500)


def _envelope(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "field": field}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers that turn any exception into the error envelope."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        location = (
            ".".join(str(part) for part in first.get("loc", ()) if part != "body")
            if first
            else None
        )
        message = first.get("msg", "invalid request body") if first else "invalid request body"
        return JSONResponse(
            status_code=422,
            content=_envelope(VALIDATION_ERROR, message, location),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, INTERNAL)
        detail = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, detail))

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=_envelope(INTERNAL, "internal server error"))
