"""Declarative base plus the mixins every table shares."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, String, TypeDecorator, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_ulid

# Explicit naming convention so Alembic generates stable, human-readable
# constraint names instead of database-assigned ones.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ULID = String(26)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    Postgres `timestamptz` round-trips an aware datetime; SQLite has no
    timezone storage at all and hands back a naive one. Without normalising
    here, every `expires_at > utcnow()` comparison in the codebase raises
    "can't compare offset-naive and offset-aware datetimes" on SQLite and
    works on Postgres — the worst possible split.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # A naive value from application code is taken to mean UTC.
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self) -> str:
        ident = getattr(self, "id", None)
        return f"<{type(self).__name__} id={ident!r}>"


class ULIDPrimaryKey:
    """ULID primary key — lexicographically sortable by creation time."""

    id: Mapped[str] = mapped_column(ULID, primary_key=True, default=new_ulid)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class SoftDelete:
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
