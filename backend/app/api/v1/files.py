"""File upload and download.

Two-step upload:

1. `POST /workspaces/{id}/files` reserves a row and returns an upload ticket.
2. The client sends the bytes — to `PUT /files/{id}/content` for the local
   backend, or straight to a presigned S3 URL.

The two steps let the client show a progress bar against a known file id, and
let a resumed or retried upload target the same row instead of creating a
duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, WorkspaceCtx
from app.core.config import settings
from app.core.errors import Conflict, Forbidden, NotFound, PayloadTooLarge
from app.core.ids import new_ulid
from app.models.channel import ChannelMember
from app.models.file import FileObject
from app.models.message import MessageAttachment
from app.models.workspace import WorkspaceMember
from app.schemas.common import OkResponse
from app.schemas.file import FileOut, RegisterUploadRequest, UploadTicket
from app.schemas.user import UserBrief
from app.services import files as file_service
from app.services.storage import build_storage_key, display_filename, get_storage

router = APIRouter(tags=["files"])

UPLOAD_TICKET_TTL_SECONDS = 900


def _serialise(file: FileObject) -> FileOut:
    out = FileOut.model_validate(file)
    out.download_url = f"/files/{file.id}/download"
    out.thumbnail_url = f"/files/{file.id}/thumbnail" if file.thumbnail_key else None
    if file.uploader is not None:
        out.uploader = UserBrief.model_validate(file.uploader)
    return out


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

    from app.models.message import Message

    visible = await db.scalar(
        select(Message.id)
        .join(ChannelMember, ChannelMember.channel_id == Message.channel_id)
        .where(Message.id.in_(channels), ChannelMember.user_id == user_id)
        .limit(1)
    )
    if visible is None:
        raise NotFound("File not found.", code="file_not_found")


@router.get("/files/{file_id}", response_model=FileOut)
async def get_file(file_id: str, db: DbSession, user: CurrentUser) -> FileOut:
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    await _authorise_read(db, file=file, user_id=user.id)
    await db.refresh(file, ["uploader"])
    return _serialise(file)


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: DbSession,
    user: CurrentUser,
    inline: Annotated[bool, Query()] = False,
):
    """Stream a file, or redirect to a presigned URL when using S3."""
    file = await db.get(FileObject, file_id)
    if file is None or file.deleted_at is not None:
        raise NotFound("File not found.", code="file_not_found")
    if not file.is_ready:
        raise Conflict("This file is still uploading.", code="file_not_ready")
    await _authorise_read(db, file=file, user_id=user.id)

    storage = get_storage()
    presigned = await storage.presigned_get_url(file.storage_key)
    if presigned:
        return RedirectResponse(presigned, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    disposition = "inline" if inline else "attachment"
    # RFC 5987 encoding so non-ASCII filenames survive the header.
    from urllib.parse import quote

    return StreamingResponse(
        storage.read_stream(file.storage_key),
        media_type=file.mime_type,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(file.filename)}"
            ),
            "Content-Length": str(file.size_bytes),
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/workspaces/{workspace_id}/files", response_model=list[FileOut])
async def list_workspace_files(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    uploader_id: Annotated[str | None, Query(max_length=26)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=26)] = None,
) -> list[FileOut]:
    """Workspace file browser — the 'find that spreadsheet' view."""
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
    if cursor:
        stmt = stmt.where(FileObject.id < cursor)

    rows = await db.scalars(stmt.order_by(FileObject.id.desc()).limit(limit))
    return [_serialise(f) for f in rows.all()]


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
