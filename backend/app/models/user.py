"""Users and per-device sessions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PresenceState
from app.models.base import ULID, Base, SoftDelete, Timestamps, ULIDPrimaryKey, UTCDateTime

if TYPE_CHECKING:
    from app.models.workspace import WorkspaceMember


class User(Base, ULIDPrimaryKey, Timestamps, SoftDelete):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, default=None)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    handle: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(160), default=None)
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="ko-KR")

    # Custom status ("🌴 휴가 중")
    status_emoji: Mapped[str | None] = mapped_column(String(64), default=None)
    status_text: Mapped[str | None] = mapped_column(String(200), default=None)
    status_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    # Last known presence. Live presence lives in Redis; this is the durable
    # fallback so a cold client still renders something sensible.
    presence: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PresenceState.OFFLINE.value
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_service_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── 방해 금지 ────────────────────────────────────────────────────────
    # A daily quiet window in the user's own timezone ("22:00"–"08:00" may
    # cross midnight) on `dnd_days` (Python weekday, Monday = 0), plus a
    # one-off pause. Counters keep counting; only notifications go quiet.
    dnd_start: Mapped[str | None] = mapped_column(String(5), default=None)
    dnd_end: Mapped[str | None] = mapped_column(String(5), default=None)
    dnd_days: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=lambda: [0, 1, 2, 3, 4]
    )
    notify_paused_until: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise_on_sql"
    )
    memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise_on_sql"
    )


class Session(Base, ULIDPrimaryKey, Timestamps):
    """One row per signed-in device, so devices can be revoked individually."""

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        Index("ix_sessions_refresh_token_hash", "refresh_token_hash", unique=True),
    )

    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    device_name: Mapped[str | None] = mapped_column(String(160), default=None)
    platform: Mapped[str | None] = mapped_column(String(32), default=None)
    app_version: Mapped[str | None] = mapped_column(String(32), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise_on_sql")

    @property
    def is_valid(self) -> bool:
        from app.models.base import utcnow

        return self.revoked_at is None and self.expires_at > utcnow()


class PasswordResetCode(Base, ULIDPrimaryKey, Timestamps):
    """A short-lived code mailed to the account's address.

    Stored hashed (like refresh tokens and invites): the mail is the only
    place the code exists in the clear. `attempts` bounds brute force per
    code, `used_at` makes it single-use, and issuing a new code invalidates
    the previous ones for the same user.
    """

    __tablename__ = "password_reset_codes"
    __table_args__ = (
        Index("ix_password_reset_codes_user_id", "user_id"),
    )

    user_id: Mapped[str] = mapped_column(
        ULID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
