"""Activity: threads I take part in, and mentions of me.

Both lists are scoped by the viewer's channel memberships, so nothing here
can surface a message from a channel the viewer cannot open.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.api.deps import DbSession, WorkspaceCtx
from app.api.v1.messages import serialise_message
from app.core.enums import ChannelKind
from app.models.channel import Channel, ChannelMember
from app.models.message import Message, MessageAttachment
from app.models.user import User
from app.schemas.activity import (
    ChannelRef,
    MentionActivityOut,
    MentionActivityPage,
    ThreadActivityOut,
    ThreadActivityPage,
)
from app.schemas.user import UserBrief
from app.services import messages as message_service

router = APIRouter(tags=["activity"])

MAX_PARTICIPANTS = 6


def _relations() -> list:  # noqa: ANN202
    return [
        selectinload(Message.author),
        selectinload(Message.reactions),
        selectinload(Message.attachments).selectinload(MessageAttachment.file),
    ]


async def _channel_refs(
    db: DbSession, *, channel_ids: set[str], viewer_id: str
) -> dict[str, ChannelRef]:
    """One query for the channels, one for DM peers — for the whole page."""
    if not channel_ids:
        return {}
    channels = list((await db.scalars(select(Channel).where(Channel.id.in_(channel_ids)))).all())
    dm_ids = [c.id for c in channels if ChannelKind(c.kind).is_conversation]
    peers: dict[str, list[UserBrief]] = {}
    if dm_ids:
        rows = await db.execute(
            select(ChannelMember.channel_id, User)
            .join(User, User.id == ChannelMember.user_id)
            .where(ChannelMember.channel_id.in_(dm_ids), ChannelMember.user_id != viewer_id)
            .order_by(ChannelMember.created_at)
        )
        for channel_id, user in rows.all():
            peers.setdefault(channel_id, []).append(UserBrief.model_validate(user))
    return {
        c.id: ChannelRef(id=c.id, name=c.name, kind=c.kind, peers=peers.get(c.id, []))
        for c in channels
    }


def _viewer_channels(viewer_id: str):  # noqa: ANN202
    return and_(
        ChannelMember.channel_id == Message.channel_id,
        ChannelMember.user_id == viewer_id,
    )


@router.get("/workspaces/{workspace_id}/activity/threads", response_model=ThreadActivityPage)
async def list_my_threads(
    ctx: WorkspaceCtx,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[str | None, Query(max_length=26)] = None,
) -> ThreadActivityPage:
    """Threads the viewer started or replied in, most recently active first.

    `before` is the root message id of the last row of the previous page. The
    list is ordered by `(last_reply_at, id)`, and the cursor row's own
    timestamp is read back from the database so the comparison happens in the
    column's type — a timestamp passed as text pages differently on SQLite
    than on Postgres.
    """
    viewer = ctx.user.id
    Reply = aliased(Message)  # noqa: N806

    viewer_replied = exists().where(
        Reply.parent_id == Message.id,
        Reply.user_id == viewer,
        Reply.deleted_at.is_(None),
    )
    stmt = (
        select(Message)
        .join(ChannelMember, _viewer_channels(viewer))
        .join(Channel, Channel.id == Message.channel_id)
        .where(
            Channel.workspace_id == ctx.workspace.id,
            Message.parent_id.is_(None),
            Message.deleted_at.is_(None),
            Message.reply_count > 0,
            Message.last_reply_at.isnot(None),
            or_(Message.user_id == viewer, viewer_replied),
        )
        .options(*_relations())
        .order_by(Message.last_reply_at.desc(), Message.id.desc())
        .limit(limit + 1)
    )
    if before:
        cursor_at = await db.scalar(select(Message.last_reply_at).where(Message.id == before))
        if cursor_at is not None:
            stmt = stmt.where(
                or_(
                    Message.last_reply_at < cursor_at,
                    and_(Message.last_reply_at == cursor_at, Message.id < before),
                )
            )

    roots = list((await db.scalars(stmt)).all())
    has_more = len(roots) > limit
    roots = roots[:limit]
    if not roots:
        return ThreadActivityPage(items=[], has_more=False)

    root_ids = [r.id for r in roots]

    # Newest live reply per thread, in one query.
    newest_ids = (
        select(func.max(Reply.id))
        .where(Reply.parent_id.in_(root_ids), Reply.deleted_at.is_(None))
        .group_by(Reply.parent_id)
    )
    newest_stmt = select(Message).where(Message.id.in_(newest_ids)).options(*_relations())
    last_replies = {m.parent_id: m for m in (await db.scalars(newest_stmt)).all()}

    # The viewer's own last word per thread — everything after it is "unread".
    my_last = dict(
        (
            await db.execute(
                select(Reply.parent_id, func.max(Reply.id))
                .where(Reply.parent_id.in_(root_ids), Reply.user_id == viewer)
                .group_by(Reply.parent_id)
            )
        ).all()
    )
    cursors = {rid: my_last.get(rid, rid) for rid in root_ids}
    unread_rows = await db.execute(
        select(Reply.parent_id, func.count())
        .where(
            Reply.deleted_at.is_(None),
            or_(Reply.user_id.is_(None), Reply.user_id != viewer),
            or_(*[and_(Reply.parent_id == rid, Reply.id > cur) for rid, cur in cursors.items()]),
        )
        .group_by(Reply.parent_id)
    )
    unread = dict(unread_rows.all())

    # Participants: root author + reply authors, resolved in one query.
    wanted: dict[str, list[str]] = {}
    all_ids: set[str] = set()
    for root in roots:
        ids: list[str] = []
        if root.user_id:
            ids.append(root.user_id)
        for uid in root.reply_user_ids:
            if uid not in ids:
                ids.append(uid)
        wanted[root.id] = ids[:MAX_PARTICIPANTS]
        all_ids.update(wanted[root.id])
    users = {
        u.id: UserBrief.model_validate(u)
        for u in (await db.scalars(select(User).where(User.id.in_(all_ids)))).all()
    } if all_ids else {}

    refs = await _channel_refs(db, channel_ids={r.channel_id for r in roots}, viewer_id=viewer)
    saved = await message_service.saved_ids_for(
        db,
        viewer_id=viewer,
        message_ids=[r.id for r in roots] + [m.id for m in last_replies.values()],
    )

    items = [
        ThreadActivityOut(
            root=serialise_message(root, viewer_id=viewer, saved=saved),
            channel=refs[root.channel_id],
            last_reply=(
                serialise_message(last_replies[root.id], viewer_id=viewer, saved=saved)
                if root.id in last_replies
                else None
            ),
            participants=[users[uid] for uid in wanted[root.id] if uid in users],
            unread_replies=int(unread.get(root.id, 0)),
        )
        for root in roots
    ]
    return ThreadActivityPage(
        items=items, has_more=has_more, next_before=roots[-1].id if has_more else None
    )


@router.get("/workspaces/{workspace_id}/activity/mentions", response_model=MentionActivityPage)
async def list_my_mentions(
    ctx: WorkspaceCtx,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[str | None, Query(max_length=26)] = None,
) -> MentionActivityPage:
    """Messages that mention the viewer (directly or via @channel), newest first."""
    viewer = ctx.user.id
    # `mentioned_user_ids` is JSON; the ids are ULIDs (no quotes inside), so a
    # substring match on the quoted id is exact and portable across SQLite and
    # Postgres.
    mentions_me = cast(Message.mentioned_user_ids, String).like(f'%"{viewer}"%')
    stmt = (
        select(Message)
        .join(ChannelMember, _viewer_channels(viewer))
        .join(Channel, Channel.id == Message.channel_id)
        .where(
            Channel.workspace_id == ctx.workspace.id,
            Message.deleted_at.is_(None),
            or_(Message.user_id.is_(None), Message.user_id != viewer),
            or_(Message.mentions_everyone.is_(True), mentions_me),
        )
        .options(*_relations())
        .order_by(Message.id.desc())
        .limit(limit + 1)
    )
    if before:
        stmt = stmt.where(Message.id < before)

    rows = list((await db.scalars(stmt)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    refs = await _channel_refs(db, channel_ids={m.channel_id for m in rows}, viewer_id=viewer)
    saved = await message_service.saved_ids_for(
        db, viewer_id=viewer, message_ids=[m.id for m in rows]
    )
    return MentionActivityPage(
        items=[
            MentionActivityOut(
                message=serialise_message(m, viewer_id=viewer, saved=saved),
                channel=refs[m.channel_id],
            )
            for m in rows
        ],
        has_more=has_more,
        next_before=rows[-1].id if has_more and rows else None,
    )
