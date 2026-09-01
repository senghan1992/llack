"""Message creation, editing, threading, reactions, history and search."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ChannelKind, MessageKind, NotificationLevel
from app.core.errors import Forbidden, NotFound
from app.core.ids import is_ulid, new_ulid
from app.core.logging import get_logger
from app.models.channel import Channel, ChannelMember
from app.models.file import FileObject
from app.models.message import Message, MessageAttachment, Reaction
from app.models.user import User
from app.services.text import (
    extract_handle_mentions,
    extract_mentions,
    make_snippet,
    plain_text_preview,
    rewrite_handles_to_mentions,
)

log = get_logger(__name__)

MAX_HISTORY_LIMIT = 200


# ── Loading ─────────────────────────────────────────────────────────────────


def _with_relations() -> list[Any]:
    return [
        selectinload(Message.author),
        selectinload(Message.reactions),
        selectinload(Message.attachments).selectinload(MessageAttachment.file),
    ]


async def get_message(db: AsyncSession, message_id: str, *, with_relations: bool = True) -> Message:
    stmt = select(Message).where(Message.id == message_id).limit(1)
    if with_relations:
        stmt = stmt.options(*_with_relations())
    message = await db.scalar(stmt)
    if message is None:
        raise NotFound("Message not found.", code="message_not_found")
    return message


async def history(
    db: AsyncSession,
    *,
    channel_id: str,
    limit: int = 50,
    before: str | None = None,
    after: str | None = None,
    include_thread_replies: bool = False,
) -> tuple[list[Message], bool]:
    """Keyset-paginated channel history, newest first.

    `before`/`after` are message ULIDs. Thread replies are excluded by default
    so the channel view shows roots only — the thread pane fetches them
    separately.
    """
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    stmt = select(Message).where(Message.channel_id == channel_id).options(*_with_relations())

    if not include_thread_replies:
        # A reply the author also broadcast still belongs in the channel.
        stmt = stmt.where(
            or_(Message.parent_id.is_(None), Message.also_sent_to_channel.is_(True))
        )
    if before and is_ulid(before):
        stmt = stmt.where(Message.id < before)
    if after and is_ulid(after):
        stmt = stmt.where(Message.id > after)

    # Fetch one extra row to answer has_more without a second COUNT query.
    stmt = stmt.order_by(Message.id.desc()).limit(limit + 1)
    rows = list((await db.scalars(stmt)).all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def thread_replies(
    db: AsyncSession, *, parent_id: str, limit: int = 100, after: str | None = None
) -> tuple[list[Message], bool]:
    """Thread replies, oldest first — a thread reads top to bottom."""
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    stmt = (
        select(Message)
        .where(Message.parent_id == parent_id)
        .options(*_with_relations())
        .order_by(Message.id.asc())
        .limit(limit + 1)
    )
    if after and is_ulid(after):
        stmt = stmt.where(Message.id > after)
    rows = list((await db.scalars(stmt)).all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


# ── Creation ────────────────────────────────────────────────────────────────


async def _resolve_mentions(
    db: AsyncSession, *, body: str, workspace_id: str
) -> tuple[str, list[str], bool]:
    """Normalise `@handle` to `<@id>` and collect mention targets."""
    from app.models.workspace import WorkspaceMember

    handles = extract_handle_mentions(body)
    if handles:
        rows = await db.execute(
            select(User.handle, User.id)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                User.handle.in_(handles),
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_active.is_(True),
            )
        )
        body = rewrite_handles_to_mentions(body, dict(rows.all()))

    mentioned, everyone = extract_mentions(body)
    return body, mentioned, everyone


async def create_message(
    db: AsyncSession,
    *,
    channel: Channel,
    author: User | None,
    body: str,
    blocks: list[dict[str, Any]] | None = None,
    client_msg_id: str | None = None,
    parent_id: str | None = None,
    also_send_to_channel: bool = False,
    file_ids: list[str] | None = None,
    app_id: str | None = None,
    kind: MessageKind = MessageKind.USER,
) -> tuple[Message, bool]:
    """Insert a message. Returns (message, created).

    `created=False` means `client_msg_id` matched an existing row — a retried
    send after a dropped response, which must not double-post.
    """
    if channel.is_archived:
        raise Forbidden("This channel is archived.", code="channel_archived")

    if client_msg_id:
        existing = await db.scalar(
            select(Message)
            .where(Message.channel_id == channel.id, Message.client_msg_id == client_msg_id)
            .options(*_with_relations())
            .limit(1)
        )
        if existing is not None:
            return existing, False

    parent: Message | None = None
    if parent_id:
        parent = await db.scalar(select(Message).where(Message.id == parent_id).limit(1))
        if parent is None or parent.channel_id != channel.id:
            raise NotFound("The thread you replied to does not exist.", code="thread_not_found")
        # Threads are one level deep; replying to a reply joins its root thread.
        if parent.parent_id is not None:
            parent_id = parent.parent_id
            parent = await db.scalar(select(Message).where(Message.id == parent_id).limit(1))

    normalised_body, mentioned, everyone = await _resolve_mentions(
        db, body=body, workspace_id=channel.workspace_id
    )

    message = Message(
        id=new_ulid(),
        channel_id=channel.id,
        user_id=author.id if author else None,
        app_id=app_id,
        kind=kind.value,
        client_msg_id=client_msg_id,
        body=normalised_body,
        blocks=blocks,
        parent_id=parent_id,
        also_sent_to_channel=bool(parent_id) and also_send_to_channel,
        mentioned_user_ids=mentioned,
        mentions_everyone=everyone,
    )
    db.add(message)

    if file_ids:
        await _attach_files(
            db, message=message, file_ids=file_ids, workspace_id=channel.workspace_id
        )

    try:
        # SAVEPOINT, not the outer transaction: a duplicate client_msg_id must
        # roll back only this insert, leaving the caller's transaction usable.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Two concurrent retries of the same client_msg_id raced; the loser
        # reads back the winner's row.
        if not client_msg_id:
            raise
        db.expunge(message)
        existing = await db.scalar(
            select(Message)
            .where(Message.channel_id == channel.id, Message.client_msg_id == client_msg_id)
            .options(*_with_relations())
            .limit(1)
        )
        if existing is None:
            raise
        return existing, False

    now = datetime.now(UTC)
    if parent is not None:
        parent.reply_count += 1
        parent.last_reply_at = now
        if author and author.id not in parent.reply_user_ids:
            # Reassigned rather than mutated so SQLAlchemy sees the JSON change.
            parent.reply_user_ids = [*parent.reply_user_ids, author.id]

    # Only channel-visible messages move the sidebar's "latest activity".
    if parent_id is None or message.also_sent_to_channel:
        channel.last_message_id = message.id
        channel.last_message_at = now
    channel.message_count += 1

    await _bump_unread(db, message=message, channel=channel)
    await db.flush()

    log.info(
        "message.created",
        message_id=message.id,
        channel_id=channel.id,
        user_id=author.id if author else None,
        is_reply=parent_id is not None,
    )
    return message, True


async def _attach_files(
    db: AsyncSession, *, message: Message, file_ids: list[str], workspace_id: str
) -> None:
    files = list(
        (
            await db.scalars(
                select(FileObject).where(
                    FileObject.id.in_(set(file_ids)),
                    FileObject.workspace_id == workspace_id,
                    FileObject.deleted_at.is_(None),
                    FileObject.is_ready.is_(True),
                )
            )
        ).all()
    )
    found = {f.id for f in files}
    missing = set(file_ids) - found
    if missing:
        raise NotFound(
            "Some attachments could not be found or are still uploading.",
            code="attachment_not_ready",
            details={"file_ids": sorted(missing)},
        )
    # Preserve the order the client sent.
    order = {fid: i for i, fid in enumerate(file_ids)}
    for file in sorted(files, key=lambda f: order.get(f.id, 0)):
        db.add(
            MessageAttachment(
                id=new_ulid(),
                message_id=message.id,
                file_id=file.id,
                sort_order=order.get(file.id, 0),
            )
        )


async def _bump_unread(db: AsyncSession, *, message: Message, channel: Channel) -> None:
    """Increment unread/mention counters for everyone except the author.

    One UPDATE for unread and one for mentions, rather than a row per member —
    a #general with 2,000 people otherwise costs 2,000 statements per message.
    """
    author_id = message.user_id
    # An app-authored message has no author to exclude.
    not_author = [ChannelMember.user_id != author_id] if author_id else []

    await db.execute(
        update(ChannelMember)
        .where(ChannelMember.channel_id == channel.id, *not_author)
        .values(unread_count=ChannelMember.unread_count + 1)
    )

    if message.mentions_everyone:
        mention_filter = [
            ChannelMember.notification_level != NotificationLevel.NOTHING.value
        ]
    elif message.mentioned_user_ids:
        mention_filter = [ChannelMember.user_id.in_(set(message.mentioned_user_ids))]
    else:
        return

    await db.execute(
        update(ChannelMember)
        .where(ChannelMember.channel_id == channel.id, *not_author, *mention_filter)
        .values(mention_count=ChannelMember.mention_count + 1)
    )


# ── Editing / deletion ──────────────────────────────────────────────────────


async def update_message(
    db: AsyncSession,
    *,
    message: Message,
    actor: User,
    body: str,
    blocks: list[dict[str, Any]] | None = None,
    workspace_id: str,
) -> Message:
    if message.user_id != actor.id:
        raise Forbidden("Only the author can edit a message.", code="not_message_author")
    if message.deleted_at is not None:
        raise Forbidden("This message was deleted.", code="message_deleted")

    normalised_body, mentioned, everyone = await _resolve_mentions(
        db, body=body, workspace_id=workspace_id
    )
    message.body = normalised_body
    message.blocks = blocks
    message.mentioned_user_ids = mentioned
    message.mentions_everyone = everyone
    message.edited_at = datetime.now(UTC)
    message.edit_count += 1
    await db.flush()
    return message


async def delete_message(
    db: AsyncSession, *, message: Message, actor: User, is_channel_admin: bool = False
) -> Message:
    if message.user_id != actor.id and not is_channel_admin:
        raise Forbidden(
            "Only the author or a channel admin can delete a message.", code="cannot_delete_message"
        )
    if message.deleted_at is not None:
        return message

    # Soft delete: the row stays so thread counts and read cursors hold.
    message.deleted_at = datetime.now(UTC)
    message.body = ""
    message.blocks = None
    message.mentioned_user_ids = []
    message.mentions_everyone = False
    await db.flush()
    return message


# ── Reactions ───────────────────────────────────────────────────────────────


async def add_reaction(
    db: AsyncSession, *, message: Message, user_id: str, emoji: str
) -> tuple[Reaction, bool]:
    existing = await db.scalar(
        select(Reaction)
        .where(
            Reaction.message_id == message.id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        .limit(1)
    )
    if existing is not None:
        return existing, False

    reaction = Reaction(id=new_ulid(), message_id=message.id, user_id=user_id, emoji=emoji)
    db.add(reaction)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Same emoji from the same user twice (double-click); treat as a no-op.
        db.expunge(reaction)
        existing = await db.scalar(
            select(Reaction)
            .where(
                Reaction.message_id == message.id,
                Reaction.user_id == user_id,
                Reaction.emoji == emoji,
            )
            .limit(1)
        )
        if existing is None:
            raise
        return existing, False
    return reaction, True


async def remove_reaction(
    db: AsyncSession, *, message_id: str, user_id: str, emoji: str
) -> bool:
    reaction = await db.scalar(
        select(Reaction)
        .where(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        .limit(1)
    )
    if reaction is None:
        return False
    await db.delete(reaction)
    await db.flush()
    return True


# ── Search ──────────────────────────────────────────────────────────────────


async def search_messages(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    query: str,
    channel_id: str | None = None,
    from_user_id: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
) -> tuple[list[tuple[Message, Channel, str]], bool, int]:
    """Search messages the user can actually see.

    Deliberately a LIKE scan over the channels the user belongs to. It is
    correct and needs no extra infrastructure; swapping in Postgres full-text
    or an external index later only changes this function.
    """
    started = time.perf_counter()
    term = query.strip()
    if not term:
        return [], False, 0

    limit = max(1, min(limit, 100))
    pattern = f"%{term.lower()}%"

    stmt = (
        select(Message, Channel)
        .join(Channel, Channel.id == Message.channel_id)
        .join(
            ChannelMember,
            (ChannelMember.channel_id == Channel.id) & (ChannelMember.user_id == user_id),
        )
        .where(
            Channel.workspace_id == workspace_id,
            Message.deleted_at.is_(None),
            func.lower(Message.body).like(pattern),
        )
        .options(*_with_relations())
    )
    if channel_id:
        stmt = stmt.where(Message.channel_id == channel_id)
    if from_user_id:
        stmt = stmt.where(Message.user_id == from_user_id)
    if cursor and is_ulid(cursor):
        stmt = stmt.where(Message.id < cursor)

    stmt = stmt.order_by(Message.id.desc()).limit(limit + 1)
    rows = (await db.execute(stmt)).all()
    has_more = len(rows) > limit
    trimmed = rows[:limit]

    hits = [
        (message, channel, make_snippet(message.body, term)) for message, channel in trimmed
    ]
    took_ms = int((time.perf_counter() - started) * 1000)
    return hits, has_more, took_ms


# ── Presentation helpers ────────────────────────────────────────────────────


def reactions_summary(message: Message, *, viewer_id: str | None) -> list[dict[str, Any]]:
    """Collapse individual reaction rows into per-emoji groups."""
    grouped: dict[str, list[str]] = {}
    for reaction in message.reactions:
        grouped.setdefault(reaction.emoji, []).append(reaction.user_id)
    return [
        {
            "emoji": emoji,
            "count": len(user_ids),
            "user_ids": user_ids,
            "me": viewer_id in user_ids if viewer_id else False,
        }
        # Most-used first, then alphabetical so the order is stable.
        for emoji, user_ids in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]


async def mention_display_names(
    db: AsyncSession, user_ids: Sequence[str]
) -> dict[str, str]:
    """Display names for the ids a body mentions, for readable previews."""
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.display_name).where(User.id.in_(set(user_ids)))
        )
    ).all()
    return {row.id: row.display_name for row in rows}


def notification_preview(
    message: Message,
    *,
    channel: Channel,
    author_name: str,
    names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Payload for an OS-level desktop notification."""
    if channel.kind_enum.is_conversation:
        title = author_name
    else:
        title = f"#{channel.name or channel.slug or ''} · {author_name}"
    return {
        "title": title,
        "body": plain_text_preview(message.body, names=names) or "새 메시지",
        "channel_id": channel.id,
        "message_id": message.id,
        "thread_id": message.parent_id,
        "is_dm": channel.kind_enum.is_conversation,
    }


async def notifiable_user_ids(
    db: AsyncSession, *, message: Message, channel: Channel
) -> list[str]:
    """Who should get a desktop notification for this message.

    Honours each member's notification level: `all` gets everything, `mentions`
    only gets mentions (DMs always count as a mention), `nothing` gets none.
    """
    rows = await db.execute(
        select(ChannelMember.user_id, ChannelMember.notification_level, ChannelMember.is_muted)
        .where(ChannelMember.channel_id == channel.id)
    )
    is_dm = channel.kind_enum.is_conversation
    mentioned = set(message.mentioned_user_ids)
    targets: list[str] = []

    for user_id, level, is_muted in rows.all():
        if user_id == message.user_id or is_muted:
            continue
        if level == NotificationLevel.NOTHING.value:
            continue
        if level == NotificationLevel.MENTIONS.value:
            if is_dm or user_id in mentioned or message.mentions_everyone:
                targets.append(user_id)
            continue
        targets.append(user_id)
    return targets


async def channel_member_ids(db: AsyncSession, channel_id: str) -> list[str]:
    rows = await db.scalars(
        select(ChannelMember.user_id).where(ChannelMember.channel_id == channel_id)
    )
    return list(rows.all())


def is_public(channel: Channel) -> bool:
    return channel.kind == ChannelKind.PUBLIC.value
