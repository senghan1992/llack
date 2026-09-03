"""File payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import Payload, Schema
from app.schemas.user import UserBrief


class FileOut(Schema):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    # Relative API path; the client resolves it against its base URL and adds
    # the bearer token. Never a raw storage URL.
    download_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    uploader: UserBrief | None = None
    is_ready: bool = False
    created_at: datetime


class SharedIn(Schema):
    """Where the viewer last saw this file: the newest live message carrying
    it in a channel the viewer belongs to. Never a channel they are not in."""

    channel_id: str
    channel_name: str | None = None
    channel_kind: str
    message_id: str


class WorkspaceFileOut(FileOut):
    """A file-browser row: the file plus the conversation it lives in, so
    "그 파일 어디 있지" ends with a jump rather than a download."""

    shared_in: SharedIn | None = None


class RegisterUploadRequest(Payload):
    """Step 1 of an upload: reserve a file row and get an upload target."""

    filename: str = Field(min_length=1, max_length=400)
    mime_type: str = Field(default="application/octet-stream", max_length=160)
    size_bytes: int = Field(ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class UploadTicket(Schema):
    file_id: str
    # Where to PUT/POST the bytes. For the local backend this is an API path;
    # for S3 it is a presigned URL.
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime | None = None
