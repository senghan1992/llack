"""Message creation, editing, threading, reactions and read state."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import not_found, validation_error
from app.core.ids import MESSAGE_PREFIX, REACTION_PREFIX, READ_STATE_PREFIX, new_id
from app.models.base import utcnow
from app.models.channel import Channel
from app.models.file import File
from app.models.message import KIND_TEXT, Message, Reaction, ReadState, message_attachments
from app.models.user import User
from app.schemas.message import MessageOut, ReactionOut, ReplyToOut

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


async def get_message_or_404(session: AsyncSession, message_id: str) -> Message:
    message = await session.get(Message, message_id)
    if message is None:
        raise not_found("message not found")
    return message


async def create_message(
    session: AsyncSession,
    channel: Channel,
    author: User,
    body: str,
    parent_id: str | None = None,
    reply_to_id: str | None = None,
    inline: bool = False,
    attachment_ids: list[str] | None = None,
) -> Message:
    target: Message | None = None
    if reply_to_id:
        target = await session.get(Message, reply_to_id)
        if target is None or target.channel_id != channel.id:
            raise not_found("the message to reply to was not found")
        if target.deleted_at is not None:
            raise validation_error("a deleted message cannot be answered", "reply_to_id")
        # Replies are one level deep: answering a reply joins the thread of
        # the message that reply answered.
        parent_id = target.parent_id or target.id

    parent: Message | None = None
    if parent_id:
        parent = await session.get(Message, parent_id)
        if parent is None or parent.channel_id != channel.id:
            raise not_found("parent message not found")
        if parent.parent_id is not None:
            raise validation_error("threads cannot be nested", "parent_id")

    clean_body = body.strip()
    wanted = list(dict.fromkeys(attachment_ids or []))
    if not clean_body and not wanted:
        raise validation_error("message body is required", "body")

    message = Message(
        id=new_id(MESSAGE_PREFIX),
        channel_id=channel.id,
        user_id=author.id,
        body=clean_body,
        kind=KIND_TEXT,
        parent_id=parent_id,
        reply_to_id=target.id if target is not None else None,
        inline=bool(inline and target is not None),
    )
    session.add(message)
    await session.flush()

    if wanted:
        files = list(await session.scalars(select(File).where(File.id.in_(wanted))))
        found = {item.id for item in files}
        missing = [item for item in wanted if item not in found]
        if missing:
            raise not_found(f"attachment not found: {missing[0]}")
        not_owned = [item for item in files if item.owner_id != author.id]
        if not_owned:
            raise validation_error("attachment belongs to another user", "attachment_ids")
        await session.execute(
            message_attachments.insert(),
            [{"message_id": message.id, "file_id": item.id} for item in files],
        )
        await session.flush()

    if parent is not None:
        await recompute_thread_stats(session, parent.id)
    return message


async def recompute_thread_stats(session: AsyncSession, root_id: str) -> None:
    root = await session.get(Message, root_id)
    if root is None:
        return
    count, last_reply_at = (
        await session.execute(
            select(func.count(Message.id), func.max(Message.created_at)).where(
                Message.parent_id == root_id,
                Message.deleted_at.is_(None),
            )
        )
    ).one()
    root.reply_count = int(count or 0)
    root.last_reply_at = last_reply_at


async def list_messages(
    session: AsyncSession,
    channel: Channel,
    limit: int = DEFAULT_PAGE_SIZE,
    before: str | None = None,
) -> tuple[list[Message], bool]:
    """Return the top-level messages of a channel, newest last.

    Without a cursor the newest page is returned; ``before`` walks backwards
    through the history. A reply written in the channel is a top-level
    message too: it is quoted in place of the message it answers.
    """
    page_size = max(1, min(limit, MAX_PAGE_SIZE))
    query = select(Message).where(
        Message.channel_id == channel.id,
        or_(Message.parent_id.is_(None), Message.inline.is_(True)),
    )

    if before:
        anchor = await session.get(Message, before)
        if anchor is None or anchor.channel_id != channel.id:
            raise not_found("message not found")
        query = query.where(
            or_(
                Message.created_at < anchor.created_at,
                and_(Message.created_at == anchor.created_at, Message.id < anchor.id),
            )
        )

    rows = list(
        await session.scalars(
            query.order_by(Message.created_at.desc(), Message.id.desc()).limit(page_size + 1)
        )
    )
    has_more = len(rows) > page_size
    messages = rows[:page_size]
    messages.reverse()
    return messages, has_more


async def list_thread_replies(
    session: AsyncSession, root: Message, limit: int = MAX_PAGE_SIZE
) -> list[Message]:
    """The replies of a thread root, oldest first."""
    rows = await session.scalars(
        select(Message)
        .where(Message.parent_id == root.id)
        .order_by(Message.created_at, Message.id)
        .limit(max(1, min(limit, MAX_PAGE_SIZE)))
    )
    return list(rows)


async def edit_message(session: AsyncSession, message: Message, body: str) -> Message:
    if message.deleted_at is not None:
        raise validation_error("message has been deleted", "body")
    clean = body.strip()
    if not clean:
        raise validation_error("message body is required", "body")
    message.body = clean
    message.edited_at = utcnow()
    await session.flush()
    return message


async def delete_message(session: AsyncSession, message: Message) -> Message:
    message.deleted_at = utcnow()
    message.body = ""
    await session.flush()
    if message.parent_id:
        await recompute_thread_stats(session, message.parent_id)
    return message


async def toggle_reaction(
    session: AsyncSession, message: Message, user_id: str, emoji: str
) -> bool:
    """Add the reaction, or remove it when the user already reacted with it."""
    existing = await session.scalar(
        select(Reaction).where(
            Reaction.message_id == message.id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
    )
    if existing is not None:
        await session.delete(existing)
        await session.flush()
        return False
    session.add(
        Reaction(
            id=new_id(REACTION_PREFIX),
            message_id=message.id,
            user_id=user_id,
            emoji=emoji,
        )
    )
    await session.flush()
    return True


async def remove_reaction(
    session: AsyncSession, message: Message, user_id: str, emoji: str
) -> None:
    existing = await session.scalar(
        select(Reaction).where(
            Reaction.message_id == message.id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
    )
    if existing is not None:
        await session.delete(existing)
        await session.flush()


async def set_pinned(session: AsyncSession, message: Message, pinned: bool) -> Message:
    message.pinned = pinned
    await session.flush()
    return message


async def list_pinned(session: AsyncSession, channel: Channel) -> list[Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.channel_id == channel.id, Message.pinned.is_(True))
        .order_by(Message.created_at.desc(), Message.id.desc())
    )
    return list(rows)


async def mark_read(
    session: AsyncSession, channel: Channel, user_id: str, message_id: str | None = None
) -> None:
    anchor: Message | None = None
    if message_id:
        anchor = await session.get(Message, message_id)
        if anchor is None or anchor.channel_id != channel.id:
            raise not_found("message not found")
    else:
        anchor = await session.scalar(
            select(Message)
            .where(Message.channel_id == channel.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )

    state = await session.scalar(
        select(ReadState).where(
            ReadState.channel_id == channel.id,
            ReadState.user_id == user_id,
        )
    )
    if state is None:
        # Two requests for the same (channel, user) can arrive together — the
        # client marks a channel read over the socket and over REST. The
        # second insert would break the unique constraint, so it is attempted
        # inside a savepoint and falls back to an update when the row is
        # already there.
        try:
            async with session.begin_nested():
                session.add(
                    ReadState(
                        id=new_id(READ_STATE_PREFIX),
                        channel_id=channel.id,
                        user_id=user_id,
                        last_read_message_id=anchor.id if anchor else None,
                        last_read_at=utcnow(),
                    )
                )
                await session.flush()
        except IntegrityError:
            state = await session.scalar(
                select(ReadState).where(
                    ReadState.channel_id == channel.id,
                    ReadState.user_id == user_id,
                )
            )
            if state is None:
                raise
            state.last_read_message_id = anchor.id if anchor else None
            state.last_read_at = utcnow()
    else:
        state.last_read_message_id = anchor.id if anchor else None
        state.last_read_at = utcnow()
    await session.flush()


async def unread_count(session: AsyncSession, channel_id: str, user_id: str) -> int:
    counts = await unread_counts(session, [channel_id], user_id)
    return counts.get(channel_id, 0)


async def unread_counts(
    session: AsyncSession, channel_ids: list[str], user_id: str
) -> dict[str, int]:
    """Unread counts per channel for one user.

    A message counts as unread when it is newer than the caller's last read
    message and was not written by the caller.
    """
    if not channel_ids:
        return {}

    states = list(
        await session.scalars(
            select(ReadState).where(
                ReadState.user_id == user_id,
                ReadState.channel_id.in_(channel_ids),
            )
        )
    )
    last_read = {state.channel_id: state.last_read_message_id for state in states}

    anchors: dict[str, Message] = {}
    anchor_ids = [value for value in last_read.values() if value]
    if anchor_ids:
        for anchor in await session.scalars(select(Message).where(Message.id.in_(anchor_ids))):
            anchors[anchor.id] = anchor

    with_anchor = {
        channel_id for channel_id, message_id in last_read.items() if message_id in anchors
    }
    without_state = {channel_id for channel_id in channel_ids if channel_id not in last_read}

    counts: dict[str, int] = {}

    if with_anchor:
        anchor_table = Message.__table__.alias("anchor")
        rows = await session.execute(
            select(Message.channel_id, func.count(Message.id))
            .join(
                ReadState,
                and_(
                    ReadState.channel_id == Message.channel_id,
                    ReadState.user_id == user_id,
                ),
            )
            .join(anchor_table, anchor_table.c.id == ReadState.last_read_message_id)
            .where(
                Message.channel_id.in_(with_anchor),
                Message.user_id != user_id,
                Message.deleted_at.is_(None),
                or_(
                    Message.created_at > anchor_table.c.created_at,
                    and_(
                        Message.created_at == anchor_table.c.created_at,
                        Message.id > anchor_table.c.id,
                    ),
                ),
            )
            .group_by(Message.channel_id)
        )
        for channel_id, count in rows.all():
            counts[channel_id] = int(count)

    if without_state:
        rows = await session.execute(
            select(Message.channel_id, func.count(Message.id))
            .where(
                Message.channel_id.in_(without_state),
                Message.user_id != user_id,
                Message.deleted_at.is_(None),
            )
            .group_by(Message.channel_id)
        )
        for channel_id, count in rows.all():
            counts[channel_id] = int(count)

    return counts


def _file_out(item: File, api_prefix: str) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "url": f"{api_prefix}/files/{item.id}",
        "mime": item.mime,
        "size": item.size,
    }


@dataclass
class MessageBundle:
    """Everything needed to render messages, loaded once for many viewers."""

    authors: dict[str, User]
    reactions: dict[str, list[tuple[str, list[str]]]]
    attachments: dict[str, list[File]]
    reply_targets: dict[str, Message]


async def load_message_bundle(session: AsyncSession, messages: list[Message]) -> MessageBundle:
    """Load authors, reactions and attachments for a batch of messages."""
    if not messages:
        return MessageBundle(authors={}, reactions={}, attachments={}, reply_targets={})

    message_ids = [message.id for message in messages]

    # The messages these ones answer, so a quote can be drawn without a
    # second round trip.
    reply_ids = {message.reply_to_id for message in messages if message.reply_to_id}
    targets: dict[str, Message] = {}
    if reply_ids:
        targets = {
            target.id: target
            for target in await session.scalars(select(Message).where(Message.id.in_(reply_ids)))
        }

    author_ids = {message.user_id for message in messages} | {
        target.user_id for target in targets.values()
    }
    authors = {
        user.id: user for user in await session.scalars(select(User).where(User.id.in_(author_ids)))
    }

    reaction_rows = list(
        await session.scalars(
            select(Reaction)
            .where(Reaction.message_id.in_(message_ids))
            .order_by(Reaction.created_at, Reaction.id)
        )
    )
    reactions: dict[str, list[tuple[str, list[str]]]] = {}
    for row in reaction_rows:
        groups = reactions.setdefault(row.message_id, [])
        for emoji, user_ids in groups:
            if emoji == row.emoji:
                user_ids.append(row.user_id)
                break
        else:
            groups.append((row.emoji, [row.user_id]))

    attachments: dict[str, list[File]] = {}
    rows = await session.execute(
        select(message_attachments.c.message_id, File)
        .join(File, File.id == message_attachments.c.file_id)
        .where(message_attachments.c.message_id.in_(message_ids))
        .order_by(File.created_at, File.id)
    )
    for message_id, item in rows.all():
        attachments.setdefault(message_id, []).append(item)

    return MessageBundle(
        authors=authors,
        reactions=reactions,
        attachments=attachments,
        reply_targets=targets,
    )


def build_message_out(
    message: Message, bundle: MessageBundle, viewer_id: str, api_prefix: str
) -> MessageOut | None:
    """Render one message for one viewer."""
    author = bundle.authors.get(message.user_id)
    if author is None:
        return None
    reactions = [
        ReactionOut(emoji=emoji, count=len(user_ids), user_ids=user_ids, me=viewer_id in user_ids)
        for emoji, user_ids in bundle.reactions.get(message.id, [])
    ]
    reply_to: ReplyToOut | None = None
    if message.reply_to_id:
        target = bundle.reply_targets.get(message.reply_to_id)
        if target is not None:
            target_author = bundle.authors.get(target.user_id)
            gone = target.deleted_at is not None
            reply_to = ReplyToOut(
                id=target.id,
                author_name=target_author.name if target_author else "",
                body="" if gone else target.body,
                deleted=gone,
            )
    return MessageOut(
        id=message.id,
        channel_id=message.channel_id,
        user_id=message.user_id,
        author=author,
        body=message.body,
        kind=message.kind,
        parent_id=message.parent_id,
        reply_to_id=message.reply_to_id,
        reply_to=reply_to,
        inline=bool(message.inline),
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
        reply_count=message.reply_count,
        last_reply_at=message.last_reply_at,
        pinned=message.pinned,
        reactions=reactions,
        attachments=[
            _file_out(item, api_prefix) for item in bundle.attachments.get(message.id, [])
        ],
    )


async def serialize_messages(
    session: AsyncSession, messages: list[Message], viewer_id: str
) -> list[MessageOut]:
    """Build the API representation of a batch of messages for one viewer."""
    if not messages:
        return []
    api_prefix = get_settings().api_prefix
    bundle = await load_message_bundle(session, messages)
    out: list[MessageOut] = []
    for message in messages:
        rendered = build_message_out(message, bundle, viewer_id, api_prefix)
        if rendered is not None:
            out.append(rendered)
    return out


async def serialize_message(session: AsyncSession, message: Message, viewer_id: str) -> MessageOut:
    result = await serialize_messages(session, [message], viewer_id)
    return result[0]
