"""File upload and download."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError, forbidden, validation_error
from app.core.security import current_user_or_token
from app.models.channel import Channel
from app.models.message import Message, message_attachments
from app.models.user import User
from app.schemas.file import FileOut
from app.services.files import (
    disk_path,
    disposition_for,
    get_file_or_404,
    purge_orphan_files,
    save_upload,
)
from app.services.members import require_channel_access, require_membership

router = APIRouter(prefix="/files", tags=["files"])


def _file_out(record) -> FileOut:
    return FileOut(
        id=record.id,
        name=record.name,
        url=f"{get_settings().api_prefix}/files/{record.id}",
        mime=record.mime,
        size=record.size,
    )


@router.post("", response_model=FileOut)
async def upload_file(
    user: CurrentUser,
    session: DbSession,
    file: UploadFile = File(...),
    workspace_id: str | None = None,
) -> FileOut:
    """Upload a file into a workspace.

    The workspace decides where the file is kept and how much room it may
    take — the client does not get a say in either. Uploading into a
    workspace you are not a member of is refused.
    """
    if not workspace_id:
        raise validation_error("a workspace is needed to upload a file", "workspace_id")
    await require_membership(session, workspace_id, user.id)
    record = await save_upload(session, user, file, workspace_id)
    await session.commit()
    await purge_orphan_files(session, get_settings().orphan_file_hours)
    return _file_out(record)


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    user: Annotated[User, Depends(current_user_or_token)],
    session: DbSession,
) -> FileResponse:
    record = await get_file_or_404(session, file_id)
    if record.owner_id != user.id and not await _can_read(session, record.id, user.id):
        raise forbidden("you cannot download this file")
    path = disk_path(record)
    if not path.exists():
        raise forbidden("file is no longer available")

    disposition = disposition_for(record.mime)
    headers = {"X-Content-Type-Options": "nosniff"}
    if disposition == "inline" and record.mime.startswith("image/"):
        # A rendered image must not be able to reach the app's origin.
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; sandbox"
    return FileResponse(
        path,
        media_type=record.mime,
        filename=record.name,
        content_disposition_type=disposition,
        headers=headers,
    )


async def _can_read(session: DbSession, file_id: str, user_id: str) -> bool:
    """True when the file is attached to a message in a readable channel."""
    rows = await session.execute(
        select(Message.channel_id)
        .join(message_attachments, message_attachments.c.message_id == Message.id)
        .where(message_attachments.c.file_id == file_id)
    )
    for (channel_id,) in rows.all():
        channel = await session.get(Channel, channel_id)
        if channel is None:
            continue
        try:
            await require_channel_access(session, channel, user_id)
        except AppError:
            continue
        return True
    return False
