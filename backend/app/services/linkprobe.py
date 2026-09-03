"""Can this URL be shown in a frame?

A cross-origin iframe gives the browser no way to tell "loaded" from "refused
to be framed" — the load event fires for both. The server can look, though:
`X-Frame-Options` and CSP `frame-ancestors` are plain response headers. The
probe fetches the page once, reads the headers (and the `<title>` from the
first 64 KiB), and reports back so the link-app dialog can say up front
"이 사이트는 임베드를 거부합니다" instead of leaving a blank pane.

Because the server is making requests to a URL a user typed, this is also an
SSRF surface. Every hop is resolved and checked against private, loopback,
link-local and other non-public ranges before a connection is made.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from typing import Literal
from urllib.parse import urlsplit

import httpx

from app.core.errors import Forbidden

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
MAX_BODY_BYTES = 64 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 5.0

Reason = Literal["x_frame_options", "csp_frame_ancestors", "unreachable"]

# Swapped by tests for an httpx.MockTransport; None means real network.
_transport: httpx.AsyncBaseTransport | None = None


def _resolve_addresses(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return list({info[4][0] for info in infos})


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 6 and ip.ipv4_mapped is not None and not _is_public(str(ip.ipv4_mapped)))
    )


async def ensure_public_url(url: str) -> None:
    """Refuse anything that would make the server talk to itself or the LAN."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host:
        raise Forbidden("Only public http(s) URLs can be probed.", code="url_not_allowed")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise Forbidden("Only public http(s) URLs can be probed.", code="url_not_allowed")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await asyncio.to_thread(_resolve_addresses, host)
        except OSError as exc:
            raise Forbidden("This host could not be resolved.", code="url_not_allowed") from exc
    if not addresses or not all(_is_public(a) for a in addresses):
        raise Forbidden("Only public http(s) URLs can be probed.", code="url_not_allowed")


def _frame_verdict(headers: httpx.Headers) -> tuple[bool, Reason | None]:
    xfo = (headers.get("x-frame-options") or "").strip().upper()
    if xfo in ("DENY", "SAMEORIGIN"):
        return False, "x_frame_options"
    csp = headers.get("content-security-policy") or ""
    for directive in csp.split(";"):
        name, _, value = directive.strip().partition(" ")
        if name.lower() == "frame-ancestors":
            sources = value.lower().split()
            if "*" in sources or "http:" in sources or "https:" in sources:
                return True, None
            return False, "csp_frame_ancestors"
    return True, None


async def probe(url: str) -> dict:
    """Return {embeddable, reason, final_url, title} for `url`."""
    await ensure_public_url(url)

    async def _guard(request: httpx.Request) -> None:
        # Each redirect hop is a new request; a public URL must not be allowed
        # to bounce us into the private network.
        await ensure_public_url(str(request.url))

    client_kwargs: dict = {
        "timeout": TIMEOUT_SECONDS,
        "follow_redirects": True,
        "max_redirects": MAX_REDIRECTS,
        "event_hooks": {"request": [_guard]},
        "headers": {
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "User-Agent": "Llack-LinkProbe/1.0",
        },
    }
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        async with (
            httpx.AsyncClient(**client_kwargs) as client,
            client.stream("GET", url) as response,
        ):
            buffer = b""
            content_type = (response.headers.get("content-type") or "").lower()
            if not content_type or "html" in content_type or content_type.startswith("text/"):
                async for chunk in response.aiter_bytes():
                    buffer += chunk
                    if len(buffer) >= MAX_BODY_BYTES:
                        break
            embeddable, reason = _frame_verdict(response.headers)
            title: str | None = None
            match = TITLE_RE.search(buffer.decode("utf-8", errors="ignore"))
            if match:
                title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()[:200] or None
            return {
                "embeddable": embeddable,
                "reason": reason,
                "final_url": str(response.url),
                "title": title,
            }
    except Forbidden:
        raise
    except (httpx.HTTPError, OSError, ValueError):
        return {"embeddable": None, "reason": "unreachable", "final_url": None, "title": None}
