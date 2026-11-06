"""Search schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.channel import ChannelOut
from app.schemas.message import MessageOut


class SearchResult(BaseModel):
    message: MessageOut
    channel: ChannelOut
