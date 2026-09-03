"""Shared schema building blocks."""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")


class Schema(BaseModel):
    """Base for response models read out of ORM objects."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Payload(BaseModel):
    """Base for request bodies — rejects unknown keys so typos surface early."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CursorPage(Schema, Generic[T]):
    """Keyset pagination.

    Cursors are ULIDs, so paging is `WHERE id < :cursor ORDER BY id DESC` — no
    OFFSET, and results stay stable while new messages arrive.
    """

    items: list[T]
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_more: bool = False


Slug = Annotated[
    str,
    Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
]
Handle = Annotated[
    str,
    Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
]


def _must_look_like_emoji(value: str) -> str:
    # `:+1:` and `thumbsup` are shortcodes, not emoji; rendering them as a
    # reaction chip produced a literal `:+1: 1` under the message.
    if value.isascii() or any(ch.isspace() for ch in value):
        raise ValueError("Reactions must be an emoji character, not text.")
    return value


Emoji = Annotated[
    str, Field(min_length=1, max_length=80), AfterValidator(_must_look_like_emoji)
]


class OkResponse(Schema):
    ok: bool = True


class ErrorBody(Schema):
    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorResponse(Schema):
    error: ErrorBody
