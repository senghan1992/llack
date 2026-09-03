"""Attachment scanning through ClamAV's clamd.

The moment files move between colleagues, someone asks whether they are
checked. This talks the clamd INSTREAM protocol directly over TCP — no
python-clamd dependency, no shell-out — and treats the daemon's absence as a
configuration choice, not an error: with `LLACK_CLAMAV_HOST` empty every file
is stored as `scan_status="skipped"` and nothing is contacted.

Infected files are *quarantined*: bytes removed, row soft-deleted, attachment
links cut, the uploader told through a `notification` frame, and an audit
event written. The transcript keeps the message; the chip says why the file
is gone.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.file import FileObject
from app.models.message import MessageAttachment
from app.realtime.events import emit_to_users
from app.services import audit
from app.services.storage import get_storage

log = get_logger(__name__)

CHUNK = 64 * 1024


def configured() -> bool:
    return bool(settings.clamav_host)


async def scan_stream(stream: AsyncIterator[bytes]) -> tuple[str, str | None]:
    """INSTREAM the bytes to clamd. Returns (verdict, signature)."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(settings.clamav_host, settings.clamav_port),
        timeout=settings.clamav_timeout_seconds,
    )
    try:
        writer.write(b"zINSTREAM\0")
        async for chunk in stream:
            if not chunk:
                continue
            for offset in range(0, len(chunk), CHUNK):
                piece = chunk[offset : offset + CHUNK]
                writer.write(struct.pack("!I", len(piece)) + piece)
            await writer.drain()
        writer.write(struct.pack("!I", 0))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(4096), timeout=settings.clamav_timeout_seconds)
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    reply = raw.decode("utf-8", "replace").strip("\0\n ")
    # "stream: OK" | "stream: Eicar-Test-Signature FOUND" | "stream: ... ERROR"
    if reply.endswith("OK"):
        return "clean", None
    if reply.endswith("FOUND"):
        signature = reply.split(":", 1)[-1].strip().removesuffix("FOUND").strip()
        return "infected", signature or "unknown"
    return "error", reply[:200] or None


async def scan_file(db: AsyncSession, file_id: str) -> str:
    """Scan a stored file and act on the verdict. Returns the final status."""
    file = await db.get(FileObject, file_id)
    if file is None:
        return "missing"
    if not configured():
        file.scan_status = "skipped"
        await db.commit()
        return file.scan_status

    storage = get_storage()
    try:
        verdict, detail = await scan_stream(storage.read_stream(file.storage_key))
    except Exception as exc:  # noqa: BLE001
        log.warning("scan.failed", file_id=file_id, error=str(exc))
        file.scan_status = "error"
        await db.commit()
        return file.scan_status

    if verdict != "infected":
        file.scan_status = verdict
        await db.commit()
        log.info("scan.done", file_id=file_id, verdict=verdict)
        return verdict

    await quarantine(db, file, signature=detail or "unknown")
    return "infected"


async def quarantine(db: AsyncSession, file: FileObject, *, signature: str) -> None:
    """Remove the bytes, cut the links, tell the uploader, write it down."""
    storage = get_storage()
    try:
        await storage.delete(file.storage_key)
        if file.thumbnail_key:
            await storage.delete(file.thumbnail_key)
    except Exception:  # noqa: BLE001
        log.warning("scan.quarantine_delete_failed", file_id=file.id)
    file.scan_status = "infected"
    file.deleted_at = datetime.now(UTC)
    await db.execute(delete(MessageAttachment).where(MessageAttachment.file_id == file.id))
    await audit.record(
        db,
        workspace_id=file.workspace_id,
        actor=None,
        action="file.quarantined",
        target_type="file",
        target_id=file.id,
        target_label=file.filename,
        details={"signature": signature, "uploader_id": file.uploader_id},
    )
    await db.commit()
    log.warning("scan.quarantined", file_id=file.id, signature=signature)

    if file.uploader_id:
        await emit_to_users(
            [file.uploader_id],
            "notification",
            {
                "kind": "quarantine",
                "title": "첨부 파일이 차단되었습니다",
                "body": f"{file.filename} 에서 악성 코드({signature})가 발견되어 삭제했습니다.",
                "file_id": file.id,
                "channel_id": None,
                "message_id": None,
            },
            workspace_id=file.workspace_id,
        )
