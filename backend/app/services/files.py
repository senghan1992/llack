"""File visibility.

A file's *bytes* were always guarded (download checks membership of a channel
the file was shared into). Its *name* was not: the workspace file list and ⌘K
returned every filename in the workspace, so a member could learn that
`리뷰전용-비공개시안.png` exists in a private channel they are not in. Names are
often the secret — `layoffs-q4.xlsx` — so listing follows the same rule as
downloading.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.channel import ChannelMember
from app.models.file import FileObject
from app.models.message import Message, MessageAttachment


def visible_to(user_id: str) -> ColumnElement[bool]:
    """Files a person may know exist: their own uploads, or an attachment to a
    live message in a channel they belong to."""
    shared_with_me = (
        select(MessageAttachment.file_id)
        .join(Message, Message.id == MessageAttachment.message_id)
        .join(
            ChannelMember,
            and_(
                ChannelMember.channel_id == Message.channel_id,
                ChannelMember.user_id == user_id,
            ),
        )
        .where(Message.deleted_at.is_(None))
    )
    return or_(FileObject.uploader_id == user_id, FileObject.id.in_(shared_with_me))
