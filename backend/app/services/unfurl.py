"""Link unfurls: the title card under a pasted URL.

After a message lands, its first http(s) link (outside code spans) is fetched
once by the server — through the same SSRF guard the link-app probe uses, so
"paste http://10.0.0.5/admin" cannot make Llack read the intranet for you —
and the Open Graph / Twitter / plain HTML metadata becomes an `unfurl` block
on the message. Clients learn about it through the ordinary MESSAGE_UPDATED
event, so nothing new travels over the socket.

Fetches are cached in `link_previews` for a day (an hour when they failed):
a link pasted into five channels is fetched once.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Forbidden
from app.core.logging import get_logger
from app.models.message import Message, MessageAttachment
from app.models.saved import LinkPreview
from app.services import linkprobe
from app.services.text import strip_code

log = get_logger(__name__)

URL_RE = re.compile(r"https?://[^\s<>()\"']+")
MAX_BODY_BYTES = 128 * 1024
TIMEOUT_SECONDS = 5.0
CACHE_OK = timedelta(hours=24)
CACHE_FAILED = timedelta(hours=1)

# Swapped by tests for an httpx.MockTransport; None means real network.
_transport: httpx.AsyncBaseTransport | None = None

_background: set[asyncio.Task] = set()


def first_url(body: str) -> str | None:
    """The first link a person can see — code spans do not count."""
    match = URL_RE.search(strip_code(body))
    if not match:
        return None
    # Trailing punctuation belongs to the sentence, not the URL.
    return match.group(0).rstrip(".,;:!?」』)]")


class _MetaParser(HTMLParser):
    """Collect og:/twitter:/name= meta tags and <title>. Stdlib only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._in_title = False
        self._head_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._head_done:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            attributes = {k.lower(): (v or "") for k, v in attrs}
            key = (attributes.get("property") or attributes.get("name") or "").lower()
            content = attributes.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "body":
            # Everything we want lives in <head>; stop parsing the body.
            self._head_done = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def parse_metadata(html: str, base_url: str) -> dict[str, str | None]:
    parser = _MetaParser()
    with contextlib.suppress(Exception):  # tolerate any broken markup
        parser.feed(html)
    meta = parser.meta

    def pick(*keys: str) -> str | None:
        for key in keys:
            value = meta.get(key)
            if value:
                return re.sub(r"\s+", " ", value).strip()
        return None

    title = pick("og:title", "twitter:title") or (
        re.sub(r"\s+", " ", "".join(parser.title_parts)).strip() or None
    )
    description = pick("og:description", "twitter:description", "description")
    image = pick("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    image_url: str | None = None
    if image:
        absolute = urljoin(base_url, image)
        if urlsplit(absolute).scheme in ("http", "https"):
            image_url = absolute
    site_name = pick("og:site_name") or (urlsplit(base_url).hostname or None)
    return {
        "title": title[:300] if title else None,
        "description": description[:1000] if description else None,
        "image_url": image_url,
        "site_name": site_name[:200] if site_name else None,
    }


async def fetch_metadata(url: str) -> dict[str, str | None] | None:
    """GET the page (≤128 KiB) and parse it. None when it cannot be fetched.

    Raises Forbidden for a non-public URL — the caller treats that as a
    permanent "no card", never as a retry.
    """
    await linkprobe.ensure_public_url(url)

    async def _guard(request: httpx.Request) -> None:
        await linkprobe.ensure_public_url(str(request.url))

    client_kwargs: dict[str, Any] = {
        "timeout": TIMEOUT_SECONDS,
        "follow_redirects": True,
        "max_redirects": linkprobe.MAX_REDIRECTS,
        "event_hooks": {"request": [_guard]},
        "headers": {
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "User-Agent": "Llack-Unfurl/1.0 (+https://llack)",
        },
    }
    if _transport is not None:
        client_kwargs["transport"] = _transport
    try:
        async with (
            httpx.AsyncClient(**client_kwargs) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code >= 400:
                return None
            content_type = (response.headers.get("content-type") or "").lower()
            if content_type and "html" not in content_type and not content_type.startswith(
                "text/"
            ):
                return None
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk
                if len(buffer) >= MAX_BODY_BYTES:
                    break
            charset = response.charset_encoding or "utf-8"
            try:
                html = buffer.decode(charset, errors="ignore")
            except LookupError:
                html = buffer.decode("utf-8", errors="ignore")
            return parse_metadata(html, str(response.url))
    except Forbidden:
        raise
    except (httpx.HTTPError, OSError, ValueError):
        return None


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def preview_for(db: AsyncSession, url: str) -> LinkPreview | None:
    """Cached preview for `url`, fetching when missing or stale."""
    now = datetime.now(UTC)
    key = _url_hash(url)
    cached = await db.get(LinkPreview, key)
    if cached is not None:
        fetched = cached.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        ttl = CACHE_OK if cached.ok else CACHE_FAILED
        if fetched + ttl > now:
            return cached

    try:
        meta = await fetch_metadata(url)
    except Forbidden:
        meta = None
    ok = bool(meta and (meta.get("title") or meta.get("description")))
    if cached is None:
        cached = LinkPreview(url_hash=key, url=url, fetched_at=now, ok=ok)
        db.add(cached)
    cached.fetched_at = now
    cached.ok = ok
    cached.title = meta.get("title") if meta else None
    cached.description = meta.get("description") if meta else None
    cached.image_url = meta.get("image_url") if meta else None
    cached.site_name = meta.get("site_name") if meta else None
    await db.flush()
    return cached


def block_for(preview: LinkPreview) -> dict[str, Any]:
    return {
        "type": "unfurl",
        "url": preview.url,
        "title": preview.title,
        "description": preview.description,
        "image_url": preview.image_url,
        "site_name": preview.site_name,
    }


async def unfurl_message(message_id: str, body: str) -> None:
    """Attach an unfurl block to the message and announce the update.

    Runs on its own session after the create request returned, like the file
    scanner: the person who pressed Enter should never wait for a stranger's
    web server.
    """
    from sqlalchemy.orm import selectinload

    from app.api.v1.messages import serialise_message
    from app.core.db import get_sessionmaker
    from app.models.channel import Channel
    from app.realtime.events import emit_to_channel
    from app.schemas.realtime import ServerEvent

    url = first_url(body)
    if not url:
        return
    async with get_sessionmaker()() as db:
        try:
            preview = await preview_for(db, url)
            if preview is None or not preview.ok:
                await db.commit()
                return
            message = await db.scalar(
                select(Message)
                .where(Message.id == message_id)
                .options(
                    selectinload(Message.author),
                    selectinload(Message.reactions),
                    selectinload(Message.attachments).selectinload(MessageAttachment.file),
                )
                .limit(1)
            )
            if message is None or message.deleted_at is not None:
                await db.commit()
                return
            # Replace any previous unfurl (an edit may have changed the link),
            # keep every other block an app may have authored.
            others = [b for b in (message.blocks or []) if b.get("type") != "unfurl"]
            message.blocks = [*others, block_for(preview)]
            channel = await db.get(Channel, message.channel_id)
            await db.commit()
            out = serialise_message(message, viewer_id=None)
            await emit_to_channel(
                message.channel_id,
                ServerEvent.MESSAGE_UPDATED,
                {"message": out.model_dump(mode="json")},
                workspace_id=channel.workspace_id if channel else None,
            )
        except Exception:  # noqa: BLE001
            log.exception("unfurl.failed", message_id=message_id)


def schedule(message_id: str, body: str) -> asyncio.Task | None:
    """Kick off an unfurl in the background; None when disabled or linkless."""
    if not settings.unfurl_enabled or not first_url(body):
        return None
    task = asyncio.create_task(unfurl_message(message_id, body), name=f"unfurl:{message_id}")
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def drain_background() -> None:
    """Wait for in-flight unfurls. For tests and shutdown."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
