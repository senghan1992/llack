"""File uploads and downloads.

A shared file is checked twice: the bytes have to match the type they claim
to be, and the type has to be one a team actually shares.  The browser sends
the MIME type, so it is a hint, never the truth — the truth is the first
bytes of the file.

Where a file lives is decided here too, not by the client:

    <UPLOAD_DIR>/<workspace_id>/<bucket>/<file_id><suffix>

* ``workspace_id`` — the workspace the file was uploaded into. A workspace
  owns its files, and its quota counts them.
* ``bucket`` — the first two characters of the file id, so no directory ever
  holds thousands of entries.
* ``file_id`` — the name on disk. Never the user's filename: a name is
  text a person typed, and text can carry a path.
* ``suffix`` — the extension of the **verified** type, not of the name. A
  file called ``report.exe`` whose bytes are a PNG is stored and named as a
  PNG.

The whole policy is written down in ``docs/FILES.md``.
"""

from __future__ import annotations

import zipfile
from datetime import timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import not_found, validation_error
from app.core.ids import FILE_PREFIX, new_id
from app.models.base import utcnow
from app.models.file import File
from app.models.message import message_attachments
from app.models.user import User

CHUNK_BYTES = 1024 * 1024
HEAD_BYTES = 8192

# The longest name we keep. A name is a label for people, not a title.
NAME_LIMIT = 120

# ── what a team may share ────────────────────────────────────────────────
IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/svg+xml",
}

# These are shown in the browser itself.  SVG stays out of it on purpose: an
# SVG is a document that can carry script.
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}

TEXT_TYPES = {"text/plain", "text/markdown", "text/csv"}

ZIP_TYPES = {
    "application/zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/x-hwp+zip",
}

OLE_TYPES = {
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
}

ALLOWED_MIME_TYPES = (
    IMAGE_TYPES
    | TEXT_TYPES
    | ZIP_TYPES
    | OLE_TYPES
    | {
        "application/pdf",
        "application/rtf",
        "application/gzip",
        "application/x-hwp",
    }
)

# The extension each type is stored and named with. The extension follows
# the truth, so this table is part of the policy.
MIME_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/rtf": ".rtf",
    "application/gzip": ".gz",
    "application/x-hwp": ".hwp",
    "application/zip": ".zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    "application/vnd.oasis.opendocument.presentation": ".odp",
    "application/x-hwp+zip": ".hwpx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
}

# The marker that proves a zip really is the office format it claims.
_ZIP_MARKERS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/document.xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/workbook.xml",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        "ppt/presentation.xml"
    ),
    "application/x-hwp+zip": "Contents/header.xml",
}

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_PDF = b"%PDF-"
_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_GZIP = b"\x1f\x8b"
_HWP = b"HWP Document File"


def is_allowed_mime(mime: str) -> bool:
    return mime in ALLOWED_MIME_TYPES


def storage_path_for(workspace_id: str, file_id: str, mime: str) -> Path:
    """Where a file of this workspace and type is kept on disk."""
    suffix = MIME_SUFFIX.get(mime, "")
    bucket = file_id[:2] or "00"
    return get_settings().upload_root / workspace_id / bucket / f"{file_id}{suffix}"


def _looks_like_text(path: Path) -> bool:
    """True when the file reads as text rather than as a binary blob."""
    try:
        with path.open("rb") as handle:
            sample = handle.read(HEAD_BYTES)
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _verify_zip(path: Path, declared: str) -> str | None:
    """Open the archive and prove it is the format it claims to be."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())

            # OpenDocument keeps its real type in a plain "mimetype" member.
            if "mimetype" in names:
                try:
                    mimetype = archive.read("mimetype").decode("ascii", "ignore").strip()
                except (KeyError, OSError, RuntimeError, zipfile.BadZipFile):
                    mimetype = ""
                if not mimetype:
                    return None
                return mimetype if mimetype in ALLOWED_MIME_TYPES else None

            marker = _ZIP_MARKERS.get(declared)
            if marker is not None:
                return declared if marker in names else None
            if declared in ZIP_TYPES:
                return declared
            # A zip that names nothing we know is still a zip.
            return "application/zip"
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return None


def verify_mime(path: Path, head: bytes, declared: str) -> str | None:
    """Return the MIME type the bytes really are, or ``None`` when it is not shareable.

    The declared type only decides between siblings of one family (a docx and
    a zip are both zips); the family itself is read off the bytes.
    """
    if head.startswith(_PNG):
        return "image/png"
    if head.startswith(_JPEG):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"BM"):
        return "image/bmp"
    if head.startswith(_PDF):
        return "application/pdf"
    if head.startswith(_OLE):
        return declared if declared in OLE_TYPES else None
    if head.startswith(_GZIP):
        return "application/gzip"
    if head.startswith(_ZIP):
        return _verify_zip(path, declared)
    if head.startswith(_HWP):
        return "application/x-hwp"
    if head.lstrip()[:5] == b"{\\rtf":
        return "application/rtf"
    if b"<svg" in head[:2048].lower():
        return "image/svg+xml"

    if declared in TEXT_TYPES and _looks_like_text(path):
        return declared
    return None


def _same_family(declared: str, verified: str) -> bool:
    """True when the client's claim and the truth are two faces of one thing.

    A browser may call a CSV ``text/plain``; that is the same family and the
    name the person gave may be kept. A browser may also call a PNG
    ``application/x-msdownload``; that is a lie and the truth wins.
    """
    if declared == verified:
        return True
    if declared in TEXT_TYPES and verified in TEXT_TYPES:
        return True
    if declared == "application/zip" or verified == "application/zip":
        return declared in ZIP_TYPES or verified in ZIP_TYPES
    return False


def clean_name(raw: str, mime: str, declared: str) -> str:
    """The name people will see — cleaned, and with an extension that is true."""
    name = Path(raw or "").name.strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '\\/:*?"<>|').strip()
    stem = Path(name).stem.strip() or "file"
    suffix = MIME_SUFFIX.get(mime, "")
    if _same_family(declared, mime):
        # The person may keep the extension they chose — but only when it
        # agrees with the type the bytes turned out to be.
        given = Path(name).suffix.lower()
        if given and given in {s.lower() for s in MIME_SUFFIX.values()}:
            suffix = given
    return f"{stem[:NAME_LIMIT]}{suffix}"


def disposition_for(mime: str) -> str:
    """``inline`` only for the types the browser may render on its own."""
    if mime in INLINE_TYPES or mime == "application/pdf":
        return "inline"
    return "attachment"


async def workspace_usage(session: AsyncSession, workspace_id: str) -> int:
    """How many bytes a workspace keeps in files."""
    rows = await session.execute(select(File.size).where(File.workspace_id == workspace_id))
    return sum(size for size in rows.scalars() if size)


async def save_upload(
    session: AsyncSession, owner: User, upload: UploadFile, workspace_id: str
) -> File:
    settings = get_settings()
    limit = settings.max_upload_bytes
    declared = (upload.content_type or "").split(";")[0].strip().lower()

    used = await workspace_usage(session, workspace_id)
    if used >= settings.workspace_quota_bytes:
        raise validation_error("this workspace has no room left for files", "file")

    file_id = new_id(FILE_PREFIX)
    path = storage_path_for(workspace_id, file_id, declared)
    path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    head = b""
    try:
        with path.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise validation_error(
                        f"file exceeds the {limit // (1024 * 1024)} MB limit", "file"
                    )
                if used + total > settings.workspace_quota_bytes:
                    raise validation_error("this workspace has no room left for files", "file")
                if len(head) < HEAD_BYTES:
                    head += chunk[: HEAD_BYTES - len(head)]
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    if total == 0:
        path.unlink(missing_ok=True)
        raise validation_error("file is empty", "file")

    mime = verify_mime(path, head, declared)
    if mime is None:
        path.unlink(missing_ok=True)
        raise validation_error("that file type cannot be shared here", "file")

    # The truth decides the name and where the file sits.
    final_name = clean_name(upload.filename or "", mime, declared)
    final_path = storage_path_for(workspace_id, file_id, mime)
    if final_path != path:
        path.rename(final_path)

    record = File(
        id=file_id,
        name=final_name,
        mime=mime,
        size=total,
        owner_id=owner.id,
        workspace_id=workspace_id,
        storage_path=str(final_path),
    )
    session.add(record)
    await session.flush()
    return record


async def purge_orphan_files(session: AsyncSession, older_than_hours: int) -> int:
    """Remove uploads that never reached a message.

    A file is uploaded first and attached to a message a moment later. An
    upload that sits unattached for a day was never going to be shared — it
    is taken away, and its space with it.
    """
    if older_than_hours <= 0:
        return 0
    cutoff = utcnow() - timedelta(hours=older_than_hours)
    attached = select(message_attachments.c.file_id)
    rows = await session.execute(
        select(File).where(File.created_at < cutoff, File.id.not_in(attached))
    )
    removed = 0
    for record in rows.scalars():
        disk_path(record).unlink(missing_ok=True)
        await session.delete(record)
        removed += 1
    if removed:
        await session.commit()
    return removed


async def get_file_or_404(session: AsyncSession, file_id: str) -> File:
    record = await session.get(File, file_id)
    if record is None:
        raise not_found("file not found")
    return record


def disk_path(record: File) -> Path:
    return Path(record.storage_path)
