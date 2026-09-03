"""Typed application errors that render as a stable JSON error envelope.

Every non-2xx response from the API has the same shape, so the desktop client
has exactly one error path to implement:

    {"error": {"code": "channel_not_found", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for errors the API deliberately exposes to clients."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return {"error": body}


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Resource already exists."


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Authentication required."


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have access to this resource."


class ValidationFailed(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_failed"
    message = "Request payload is invalid."


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests."


class Gone(AppError):
    """The resource existed and was removed on purpose (quarantine, retention)."""

    status_code = status.HTTP_410_GONE
    code = "gone"
    message = "This resource is no longer available."


class PayloadTooLarge(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"
    message = "Upload exceeds the maximum allowed size."


# ── Handlers ────────────────────────────────────────────────────────────────


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed."
    code = {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(
        exc.status_code, "http_error"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
            "reason": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "validation_failed",
                "message": "Request payload is invalid.",
                "details": {"fields": fields},
            }
        },
    )
