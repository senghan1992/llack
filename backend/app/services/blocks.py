"""Message blocks: the rich content an app may attach beside Markdown.

Validated on the way in so the client renders a known shape and an app cannot
smuggle arbitrary JSON into every reader's transcript. `unfurl` is the one
block only the server writes (services/unfurl.py); a client or app sending it
is refused rather than trusted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.core.errors import ValidationFailed

MAX_BLOCKS = 20


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SectionBlock(_Strict):
    type: Literal["section"]
    text: str = Field(min_length=1, max_length=4000)


class ContextBlock(_Strict):
    type: Literal["context"]
    text: str = Field(min_length=1, max_length=1000)


class ButtonElement(_Strict):
    type: Literal["button"]
    text: str = Field(min_length=1, max_length=80)
    action_id: str = Field(min_length=1, max_length=120)
    value: str | None = Field(default=None, max_length=2000)
    style: Literal["primary", "danger"] | None = None


class SelectOption(_Strict):
    text: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)


class SelectElement(_Strict):
    type: Literal["select"]
    action_id: str = Field(min_length=1, max_length=120)
    placeholder: str | None = Field(default=None, max_length=80)
    options: list[SelectOption] = Field(min_length=1, max_length=50)


class ActionsBlock(_Strict):
    type: Literal["actions"]
    elements: list[ButtonElement | SelectElement] = Field(min_length=1, max_length=10)


class UnfurlBlock(_Strict):
    type: Literal["unfurl"]
    url: str
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    site_name: str | None = None


Block = SectionBlock | ContextBlock | ActionsBlock
_blocks_adapter: TypeAdapter[list[Block]] = TypeAdapter(list[Block])
_with_unfurl_adapter: TypeAdapter[list[Block | UnfurlBlock]] = TypeAdapter(
    list[Block | UnfurlBlock]
)


def validate_blocks(
    blocks: list[dict[str, Any]] | None, *, allow_unfurl: bool = False
) -> list[dict[str, Any]] | None:
    """Return the blocks normalised, or raise 422 `invalid_blocks`.

    `allow_unfurl` is for the server's own edits (an app replacing a message
    that already carries a link card); client input never gets it.
    """
    if blocks is None:
        return None
    if len(blocks) > MAX_BLOCKS:
        raise ValidationFailed(
            f"A message may carry at most {MAX_BLOCKS} blocks.", code="invalid_blocks"
        )
    adapter = _with_unfurl_adapter if allow_unfurl else _blocks_adapter
    try:
        parsed = adapter.validate_python(blocks)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        raise ValidationFailed(
            "Message blocks are not valid.",
            code="invalid_blocks",
            details={"error": first.get("msg"), "loc": list(first.get("loc", []))},
        ) from exc
    return [block.model_dump(exclude_none=True) for block in parsed]
