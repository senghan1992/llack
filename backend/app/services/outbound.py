"""Signed HTTP calls from Llack to an app.

Every outbound call — slash command, block interaction, event webhook — goes
through `post_signed`, so the signing scheme, the timeout and the SSRF guard
are decided once:

    X-Llack-Timestamp: <unix seconds>
    X-Llack-Signature: sha256=HMAC_SHA256(app_secret, f"{timestamp}.{body}")

The app recomputes the HMAC over the exact bytes it received and rejects
anything older than a few minutes. The body is canonical JSON (sorted keys,
no whitespace) so what we sign is what we send.

The destination is a URL an app author typed, so the same public-host guard
as link probes applies, on every redirect hop.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.linkprobe import ensure_public_url

log = get_logger(__name__)

TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 256 * 1024
SIGNATURE_MAX_SKEW_SECONDS = 300

# Swapped by tests for an httpx.MockTransport; None means real network.
_transport: httpx.AsyncBaseTransport | None = None


def canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def verify(
    secret: str, timestamp: str, body: bytes, signature: str, *, now: float | None = None
) -> bool:
    """For the inbound half (`response_url`): the app signs, we check."""
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs((now or time.time()) - sent_at) > SIGNATURE_MAX_SKEW_SECONDS:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature or "")


@dataclass(slots=True)
class Outcome:
    ok: bool
    status_code: int | None
    body: dict[str, Any] | None
    error: str | None


async def post_signed(url: str, *, secret: str, payload: dict[str, Any]) -> Outcome:
    """POST canonical JSON with the signature headers; never raises."""
    try:
        await ensure_public_url(url)
    except Exception as exc:  # noqa: BLE001 — a Forbidden from the guard
        return Outcome(ok=False, status_code=None, body=None, error=f"url_not_allowed: {exc}")

    body = canonical_body(payload)
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Llack-Apps/1.0",
        "X-Llack-Timestamp": timestamp,
        "X-Llack-Signature": sign(secret, timestamp, body),
    }

    async def _guard(request: httpx.Request) -> None:
        await ensure_public_url(str(request.url))

    kwargs: dict[str, Any] = {
        "timeout": TIMEOUT_SECONDS,
        "follow_redirects": True,
        "max_redirects": MAX_REDIRECTS,
        "event_hooks": {"request": [_guard]},
    }
    if _transport is not None:
        kwargs["transport"] = _transport

    try:
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.post(url, content=body, headers=headers)
    except Exception as exc:  # noqa: BLE001 — network, timeout, guard on a hop
        log.info("outbound.failed", url=url, error=str(exc)[:200])
        return Outcome(ok=False, status_code=None, body=None, error=str(exc)[:500])

    raw = response.content[:MAX_RESPONSE_BYTES]
    parsed: dict[str, Any] | None = None
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                parsed = decoded
        except ValueError:
            parsed = None
    if response.status_code >= 400:
        return Outcome(
            ok=False,
            status_code=response.status_code,
            body=parsed,
            error=f"HTTP {response.status_code}",
        )
    return Outcome(ok=True, status_code=response.status_code, body=parsed, error=None)
