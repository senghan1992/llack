"""Thumbnails for image uploads.

The file browser and the transcript used to fetch the *original* to show a
52px square, which for a 8 MB comp is 8 MB per row per viewer. This renders a
320px (long edge) copy once, at upload, into `thumbs/{file_id}.{ext}`. It is
a nicety, so nothing here may fail an upload: any error is logged and the
file simply has no thumbnail.
"""

from __future__ import annotations

import io

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.file import FileObject
from app.services.storage import get_storage

log = get_logger(__name__)

MAX_EDGE = 320
MAX_SOURCE_BYTES = 25 * 1024 * 1024
# Formats Pillow decodes without extra system libraries.
SUPPORTED = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/tiff"}


def _render(data: bytes) -> tuple[bytes, str, tuple[int, int]]:
    """CPU work, run in a thread. Returns (bytes, ext, (w, h))."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)  # phone photos carry rotation in EXIF
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        image.thumbnail((MAX_EDGE, MAX_EDGE))
        out = io.BytesIO()
        if has_alpha:
            image.convert("RGBA").save(out, format="PNG", optimize=True)
            return out.getvalue(), "png", image.size
        image.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), "jpg", image.size


async def generate(db: AsyncSession, file_id: str) -> str | None:
    """Create and store a thumbnail; returns the storage key or None."""
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None or not file.is_ready:
        return None
    if file.mime_type not in SUPPORTED or file.size_bytes > MAX_SOURCE_BYTES:
        return None

    storage = get_storage()
    try:
        chunks: list[bytes] = []
        async for chunk in storage.read_stream(file.storage_key):
            chunks.append(chunk)
        rendered, ext, size = await anyio.to_thread.run_sync(_render, b"".join(chunks))

        async def _one() -> bytes:
            return rendered

        async def _stream():  # noqa: ANN202
            yield await _one()

        key = f"thumbs/{file.id}.{ext}"
        await storage.write_stream(key, _stream())
    except Exception as exc:  # noqa: BLE001 — never fail the upload for a preview
        log.info("thumbnail.skipped", file_id=file_id, error=str(exc))
        return None

    file.thumbnail_key = key
    file.metadata_ = {**(file.metadata_ or {}), "thumbnail": {"w": size[0], "h": size[1]}}
    await db.commit()
    return key
