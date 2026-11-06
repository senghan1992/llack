"""File schemas."""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import ORMModel


class FileOut(ORMModel):
    id: str
    name: str
    url: str
    mime: str
    size: int


class FileRecord(FileOut):
    created_at: datetime
