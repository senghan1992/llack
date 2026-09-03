"""File upload and download.

Two-step upload:

1. `POST /workspaces/{id}/files` reserves a row and returns an upload ticket.
2. The client sends the bytes — to `PUT /files/{id}/content` for the local
   backend, or straight to a presigned S3 URL.

The two steps let the client show a progress bar against a known file id, and
let a resumed or retried upload target the same row instead of creating a
duplicate.

After the bytes land, two things happen in the background: the file is
scanned (when a ClamAV daemon is configured — see services/scanner.py) and,
for images, a thumbnail is rendered. Neither delays the upload response.

Downloads take a bearer token *or* a short-lived media token in the query
string (`<video src>` cannot send headers), and honour `Range` so a recording
can be seeked without pulling the whole file.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import and_, select

from app.api.deps import CurrentUser, DbSession, WorkspaceCtx, get_current_user
from app.core.config import settings
from app.core.errors import Conflict, Forbidden, Gone, NotFound, PayloadTooLarge, Unauthorized
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.models.channel import Channel, ChannelMember
from app.models.file import FileObject
from app.models.message import Message, MessageAttachment
from app.models.workspace import WorkspaceMember
from app.schemas.common import OkResponse
from app.schemas.file import (
    FileOut,
    MediaTokenOut,
    RegisterUploadRequest,
    SharedIn,
    UploadTicket,
    WorkspaceFileOut,
)
from app.schemas.user import UserBrief
from app.services import files as file_service
from app.services import media_token, scanner, thumbnails
from app.services.storage import build_storage_key, display_filename, get_storage

router = APIRouter(tags=["files"])
log = get_logger(__name__)

UPLOAD_TICKET_TTL_SECONDS = 900

# Background work spawned per upload; kept so the tasks are not garbage
# collected mid-flight and so tests can await them.
_background: set[asyncio.Task] = set()


def _serialise(file: FileObject) -> FileOut:
    out = FileOut.model_validate(file)
    out.download_url = f"/files/{file.id}/download"
    out.thumbnail_url = f"/files/{file.id}/thumbnail" if file.thumbnail_key else None
    if file.uploader is not None:
        out.uploader = UserBrief.model_validate(file.uploader)
    return out


async def _post_upload(file_id: str) -> None:
    """Scan, then thumbnail. Runs on its own session after the response."""
    from app.core.db import get_sessionmaker

    async with get_sessionmaker()() as db:
        try:
            status_after = await scanner.scan_file(db, file_id)
            if status_after in ("clean", "skipped", "error"):
                await thumbnails.generate(db, file_id)
        except Exception:  # noqa: BLE001
            log.exception("files.post_upload_failed", file_id=file_id)


def schedule_post_upload(file_id: str) -> asyncio.Task:
    task = asyncio.create_task(_post_upload(file_id), name=f"post-upload:{file_id}")
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def drain_background() -> None:
    """Wait for in-flight post-upload work. For tests and shutdown."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


@router.post(
    "/workspaces/{workspace_id}/files",
    response_model=UploadTicket,
    status_code=status.HTTP_201_CREATED,
)
async def register_upload(
    payload: RegisterUploadRequest, ctx: WorkspaceCtx, db: DbSession, request: Request
) -> UploadTicket:
    if payload.size_bytes > settings.max_upload_bytes:
        raise PayloadTooLarge(
            "This file is larger than the workspace limit.",
            details={
                "max_upload_bytes": settings.max_upload_bytes,
                "size_bytes": payload.size_bytes,
            },
        )

    file_id = new_ulid()
    storage = get_storage()
    filename = display_filename(payload.filename)
    storage_key = build_storage_key(ctx.workspace.id, file_id, filename)

    file = FileObject(
        id=file_id,
        workspace_id=ctx.workspace.id,
        uploader_id=ctx.user.id,
        filename=filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        storage_key=storage_key,
        storage_backend=storage.name,
        is_ready=False,
        scan_status="pending" if scanner.configured() else "skipped",
    )
    db.add(file)
    await db.commit()

    expires_at = datetime.now(UTC) + timedelta(seconds=UPLOAD_TICKET_TTL_SECONDS)
    presigned = await storage.presigned_put_url(
        storage_key, content_type=payload.mime_type, ttl=UPLOAD_TICKET_TTL_SECONDS
    )
    if presigned:
        return UploadTicket(
            file_id=file_id,
            upload_url=presigned,
            method="PUT",
            headers={"Content-Type": payload.mime_type},
            expires_at=expires_at,
        )
    return UploadTicket(
        file_id=file_id,
        upload_url=f"{settings.api_prefix}/files/{file_id}/content",
        method="PUT",
        headers={"Content-Type": payload.mime_type},
        expires_at=expires_at,
    )


@router.put("/files/{file_id}/content", response_model=FileOut)
async def upload_content(
    file_id: str, request: Request, db: DbSession, user: CurrentUser
) -> FileOut:
    """Stream the bytes for a previously registered file (local backend)."""
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    if file.uploader_id != user.id:
        raise Forbidden("Only the uploader can supply this file's contents.",
                        code="not_file_uploader")
    if file.is_ready:
        raise Conflict("This file has already been uploaded.", code="file_already_uploaded")

    storage = get_storage()
    written, digest = await storage.write_stream(file.storage_key, request.stream())

    # If the client declared a checksum, hold it to it.
    if file.checksum_sha256 and file.checksum_sha256.lower() != digest:
        await storage.delete(file.storage_key)
        raise Conflict(
            "The uploaded bytes do not match the declared checksum.",
            code="checksum_mismatch",
        )

    file.size_bytes = written
    file.checksum_sha256 = digest
    file.is_ready = True
    await db.commit()
    await db.refresh(file, ["uploader"])
    schedule_post_upload(file.id)
    return _serialise(file)


@router.post("/files/{file_id}/complete", response_model=FileOut)
async def complete_upload(file_id: str, db: DbSession, user: CurrentUser) -> FileOut:
    """Mark a direct-to-S3 upload finished, after verifying the object exists."""
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    if file.uploader_id != user.id:
        raise Forbidden("Only the uploader can complete this upload.", code="not_file_uploader")

    if not await get_storage().exists(file.storage_key):
        raise Conflict("The upload has not arrived yet.", code="upload_incomplete")

    file.is_ready = True
    await db.commit()
    await db.refresh(file, ["uploader"])
    schedule_post_upload(file.id)
    return _serialise(file)


async def _authorise_read(db: DbSession, *, file: FileObject, user_id: str) -> None:
    """A file is readable by workspace members; uploader always has access."""
    if file.uploader_id == user_id:
        return
    member = await db.scalar(
        select(WorkspaceMember.id)
        .where(
            WorkspaceMember.workspace_id == file.workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active.is_(True),
        )
        .limit(1)
    )
    if member is None:
        raise NotFound("File not found.", code="file_not_found")

    # If the file was shared into channels, require membership of at least one
    # of them — otherwise a workspace member could read a private channel's
    # attachment by id alone.
    channels = list(
        (
            await db.scalars(
                select(MessageAttachment.message_id).where(MessageAttachment.file_id == file.id)
            )
        ).all()
    )
    if not channels:
        return

    visible = await db.scalar(
        select(Message.id)
        .join(ChannelMember, ChannelMember.channel_id == Message.channel_id)
        .where(Message.id.in_(channels), ChannelMember.user_id == user_id)
        .limit(1)
    )
    if visible is None:
        raise NotFound("File not found.", code="file_not_found")


def _refuse_quarantined(file: FileObject | None) -> FileObject:
    """Quarantine is a 410 for everyone; anything else missing is a 404."""
    if file is None:
        raise NotFound("File not found.", code="file_not_found")
    if file.scan_status == "infected":
        raise Gone("This file was quarantined by the virus scanner.", code="file_quarantined")
    if file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    return file


async def _load_readable(
    db: DbSession, *, file_id: str, request: Request, media: str | None
) -> FileObject:
    """Resolve a file for reading via bearer *or* media token.

    The media token is scoped to one file id and signed by the server, and it
    is only ever minted for someone who passed `_authorise_read` — so holding
    one is the authorisation.
    """
    file = _refuse_quarantined(await db.get(FileObject, file_id))

    if media and media_token.verify(media, file_id):
        return file

    authorization = request.headers.get("authorization")
    if not authorization and media:
        raise Unauthorized("This media link has expired.", code="media_token_invalid")
    user = await get_current_user(db, authorization=authorization)
    await _authorise_read(db, file=file, user_id=user.id)
    return file


@router.get("/files/{file_id}", response_model=FileOut)
async def get_file(file_id: str, db: DbSession, user: CurrentUser) -> FileOut:
    file = _refuse_quarantined(await db.get(FileObject, file_id))
    await _authorise_read(db, file=file, user_id=user.id)
    await db.refresh(file, ["uploader"])
    return _serialise(file)


@router.post("/files/{file_id}/media-token", response_model=MediaTokenOut)
async def mint_media_token(file_id: str, db: DbSession, user: CurrentUser) -> MediaTokenOut:
    """A URL a `<video>`/`<img>` element can load without headers, for ten minutes."""
    file = _refuse_quarantined(await db.get(FileObject, file_id))
    await _authorise_read(db, file=file, user_id=user.id)
    token, exp = media_token.mint(file.id)
    return MediaTokenOut(
        url=f"{settings.api_prefix}/files/{file.id}/download?media_token={token}",
        expires_at=datetime.fromtimestamp(exp, tz=UTC),
    )


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """`bytes=start-end` → (start, end) inclusive, or None for no/invalid range."""
    if not header or not header.startswith("bytes=") or size <= 0:
        return None
    spec = header[len("bytes="):].split(",")[0].strip()
    start_text, _, end_text = spec.partition("-")
    try:
        if start_text == "":
            # Suffix range: the last N bytes.
            length = int(end_text)
            if length <= 0:
                return None
            return max(0, size - length), size - 1
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


async def _empty() -> AsyncIterator[bytes]:
    """A body with no bytes, for the 416 response."""
    return
    yield b""  # pragma: no cover — makes this an async generator


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: DbSession,
    request: Request,
    inline: Annotated[bool, Query()] = False,
    media_token_value: Annotated[str | None, Query(alias="media_token", max_length=200)] = None,
    range_header: Annotated[str | None, Header(alias="range")] = None,
):
    """Stream a file (with Range support), or redirect to a presigned URL on S3."""
    file = await _load_readable(db, file_id=file_id, request=request, media=media_token_value)
    if not file.is_ready:
        raise Conflict("This file is still uploading.", code="file_not_ready")

    storage = get_storage()
    presigned = await storage.presigned_get_url(file.storage_key)
    if presigned:
        return RedirectResponse(presigned, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    disposition = "inline" if inline or media_token_value else "attachment"
    headers = {
        # RFC 5987 encoding so non-ASCII filenames survive the header.
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file.filename)}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
    }

    byte_range = _parse_range(range_header, file.size_bytes)
    if range_header and byte_range is None and file.size_bytes > 0:
        return StreamingResponse(
            _empty(),
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file.size_bytes}"},
        )
    if byte_range is not None:
        start, end = byte_range
        headers["Content-Range"] = f"bytes {start}-{end}/{file.size_bytes}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            storage.read_range(file.storage_key, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=file.mime_type,
            headers=headers,
        )

    headers["Content-Length"] = str(file.size_bytes)
    return StreamingResponse(
        storage.read_stream(file.storage_key),
        media_type=file.mime_type,
        headers=headers,
    )


@router.get("/files/{file_id}/thumbnail")
async def download_thumbnail(
    file_id: str,
    db: DbSession,
    request: Request,
    media_token_value: Annotated[str | None, Query(alias="media_token", max_length=200)] = None,
):
    """The 320px rendition, under the same authorisation as the original."""
    file = await _load_readable(db, file_id=file_id, request=request, media=media_token_value)
    if not file.thumbnail_key:
        raise NotFound("This file has no thumbnail.", code="thumbnail_missing")
    storage = get_storage()
    presigned = await storage.presigned_get_url(file.thumbnail_key)
    if presigned:
        return RedirectResponse(presigned, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    media_type = "image/png" if file.thumbnail_key.endswith(".png") else "image/jpeg"
    return StreamingResponse(
        storage.read_stream(file.thumbnail_key),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/workspaces/{workspace_id}/files", response_model=list[WorkspaceFileOut])
async def list_workspace_files(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    uploader_id: Annotated[str | None, Query(max_length=26)] = None,
    kind: Annotated[Literal["image", "document"] | None, Query()] = None,
    mine: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=26)] = None,
) -> list[WorkspaceFileOut]:
    """Workspace file browser — the 'find that spreadsheet' view.

    Each row says *where* the file was shared, because a name alone does not
    answer "which discussion was that from". The lookup is one extra query
    for the whole page, filtered by the viewer's channel memberships, so a
    private channel the viewer is not in never shows up as the location.
    """
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    stmt = (
        select(FileObject)
        .where(
            FileObject.workspace_id == ctx.workspace.id,
            FileObject.deleted_at.is_(None),
            FileObject.is_ready.is_(True),
            file_service.visible_to(ctx.user.id),
        )
        .options(selectinload(FileObject.uploader))
    )
    if q:
        stmt = stmt.where(func.lower(FileObject.filename).like(f"%{q.strip().lower()}%"))
    if uploader_id:
        stmt = stmt.where(FileObject.uploader_id == uploader_id)
    if mine:
        stmt = stmt.where(FileObject.uploader_id == ctx.user.id)
    if kind == "image":
        stmt = stmt.where(FileObject.mime_type.like("image/%"))
    elif kind == "document":
        stmt = stmt.where(FileObject.mime_type.not_like("image/%"))
    if cursor:
        stmt = stmt.where(FileObject.id < cursor)

    files = list((await db.scalars(stmt.order_by(FileObject.id.desc()).limit(limit))).all())
    if not files:
        return []

    placements = await db.execute(
        select(
            MessageAttachment.file_id,
            Message.id,
            Channel.id,
            Channel.name,
            Channel.kind,
        )
        .join(Message, Message.id == MessageAttachment.message_id)
        .join(Channel, Channel.id == Message.channel_id)
        .join(
            ChannelMember,
            and_(
                ChannelMember.channel_id == Channel.id,
                ChannelMember.user_id == ctx.user.id,
            ),
        )
        .where(
            MessageAttachment.file_id.in_([f.id for f in files]),
            Message.deleted_at.is_(None),
        )
        .order_by(Message.id.desc())
    )
    newest: dict[str, SharedIn] = {}
    for file_id, message_id, channel_id, channel_name, channel_kind in placements.all():
        if file_id not in newest:
            newest[file_id] = SharedIn(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_kind=channel_kind,
                message_id=message_id,
            )

    out: list[WorkspaceFileOut] = []
    for file in files:
        row = WorkspaceFileOut.model_validate(file)
        row.download_url = f"/files/{file.id}/download"
        row.thumbnail_url = f"/files/{file.id}/thumbnail" if file.thumbnail_key else None
        if file.uploader is not None:
            row.uploader = UserBrief.model_validate(file.uploader)
        row.shared_in = newest.get(file.id)
        out.append(row)
    return out


@router.delete("/files/{file_id}", response_model=OkResponse)
async def delete_file(file_id: str, db: DbSession, user: CurrentUser) -> OkResponse:
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    if file.uploader_id != user.id:
        # Workspace admins may also delete.
        from app.core.enums import WorkspaceRole
        from app.services.workspaces import require_membership

        await require_membership(
            db,
            workspace_id=file.workspace_id,
            user_id=user.id,
            minimum_role=WorkspaceRole.ADMIN,
        )

    # Soft delete the row; the blob is reclaimed by the cleanup worker so a
    # request in flight does not 404 mid-stream.
    file.deleted_at = datetime.now(UTC)
    await db.commit()
    return OkResponse()
