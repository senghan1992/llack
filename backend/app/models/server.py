"""Server-wide settings, editable at runtime.

One row per key, value as JSON. Environment variables stay the *defaults*;
what an operator types into the admin UI lands here and wins. Today the only
tenant is the SMTP configuration — the table is generic so the next runtime
setting does not need another migration.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps


class ServerSetting(Base, Timestamps):
    __tablename__ = "server_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
