"""Channel endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import ChannelCtx, DbSession, WorkspaceCtx
from app.api.v1.messages import serialise_message
from app.core.enums import ChannelKind, ChannelRole, MessageKind
from app.core.errors import Forbidden, NotFound
from app.models.channel import Channel, ChannelMember
from app.models.user import User
from app.realtime.events import emit_to_channel, emit_to_workspace
from app.schemas.channel import (
    AddMembersRequest,
    ChannelMemberOut,
    ChannelMembershipOut,
    ChannelOut,
    CreateChannelRequest,
    MarkReadRequest,
    OpenDmRequest,
    UpdateChannelRequest,
    UpdateMemberRoleRequest,
    UpdateMembershipRequest,
)
from app.schemas.common import OkResponse
from app.schemas.realtime import ServerEvent
from app.schemas.user import UserBrief
from app.services import audit, webhooks
from app.services import channels as channel_service
from app.services import messages as message_service

router = APIRouter(tags=["channels"])


async def _serialise(
    db: DbSession,
    channel,  # noqa: ANN001
    membership: ChannelMember | None,
    *,
    viewer_id: str,
) -> ChannelOut:
    out = ChannelOut.model_validate(channel)
    if membership is not None:
        out.membership = ChannelMembershipOut.model_validate(membership)
    if channel.kind_enum.is_conversation:
        peers = await channel_service.dm_peers(db, channel_id=channel.id, exclude_user_id=viewer_id)
        out.peers = [UserBrief.model_validate(p) for p in peers]
        # DMs have no stored name; derive one so the client has something to show.
        out.name = ", ".join(p.display_name for p in peers) or "나와의 대화"
    return out


# ── Listing ─────────────────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/channels", response_model=list[ChannelOut])
async def list_my_channels(
    ctx: WorkspaceCtx,
    db: DbSession,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ChannelOut]:
    """Everything in the caller's sidebar: channels they joined plus open DMs."""
    rows = await channel_service.list_my_channels(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        include_archived=include_archived,
    )
    return [
        await _serialise(db, channel, membership, viewer_id=ctx.user.id)
        for channel, membership in rows
    ]


@router.get("/workspaces/{workspace_id}/channels/browse", response_model=list[ChannelOut])
async def browse_channels(
    ctx: WorkspaceCtx,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ChannelOut]:
    """Public channels in the workspace, joined or not."""
    rows = await channel_service.browse_channels(
        db, workspace_id=ctx.workspace.id, user_id=ctx.user.id, query=q, limit=limit
    )
    joined = (
        set(
            (
                await db.scalars(
                    select(ChannelMember.channel_id).where(
                        ChannelMember.user_id == ctx.user.id,
                        ChannelMember.channel_id.in_([c.id for c in rows]),
                    )
                )
            ).all()
        )
        if rows
        else set()
    )

    out: list[ChannelOut] = []
    for channel in rows:
        item = ChannelOut.model_validate(channel)
        if channel.id in joined:
            item.membership = ChannelMembershipOut()
        out.append(item)
    return out


# ── Create ──────────────────────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/channels",
    response_model=ChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: CreateChannelRequest, ctx: WorkspaceCtx, db: DbSession
) -> ChannelOut:
    channel = await channel_service.create_channel(
        db,
        workspace_id=ctx.workspace.id,
        creator=ctx.user,
        name=payload.name,
        slug=payload.slug,
        kind=payload.kind,
        topic=payload.topic,
        purpose=payload.purpose,
        member_ids=payload.member_ids,
    )
    await db.commit()

    out = ChannelOut.model_validate(channel)
    # Only public channels are announced workspace-wide; a private channel is
    # announced to its members only.
    if channel.kind == ChannelKind.PUBLIC.value:
        await emit_to_workspace(
            ctx.workspace.id, ServerEvent.CHANNEL_CREATED, {"channel": out.model_dump(mode="json")}
        )
    else:
        await emit_to_channel(
            channel.id,
            ServerEvent.CHANNEL_CREATED,
            {"channel": out.model_dump(mode="json")},
            workspace_id=ctx.workspace.id,
        )
    return out


@router.post(
    "/workspaces/{workspace_id}/channels/dm",
    response_model=ChannelOut,
    status_code=status.HTTP_200_OK,
)
async def open_dm(payload: OpenDmRequest, ctx: WorkspaceCtx, db: DbSession) -> ChannelOut:
    """Get-or-create a direct message. Idempotent for the same set of people."""
    channel, created = await channel_service.open_dm(
        db, workspace_id=ctx.workspace.id, opener=ctx.user, user_ids=payload.user_ids
    )
    await db.commit()

    membership = await channel_service.get_channel_member(
        db, channel_id=channel.id, user_id=ctx.user.id
    )
    out = await _serialise(db, channel, membership, viewer_id=ctx.user.id)
    if created:
        await emit_to_channel(
            channel.id,
            ServerEvent.CHANNEL_CREATED,
            {"channel": out.model_dump(mode="json")},
            workspace_id=ctx.workspace.id,
        )
    return out


# ── Single channel ──────────────────────────────────────────────────────────


@router.get("/channels/{channel_id}", response_model=ChannelOut)
async def get_channel(ctx: ChannelCtx, db: DbSession) -> ChannelOut:
    return await _serialise(db, ctx.channel, ctx.membership, viewer_id=ctx.user.id)


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
async def update_channel(
    payload: UpdateChannelRequest, ctx: ChannelCtx, db: DbSession, request: Request
) -> ChannelOut:
    membership = ctx.require_member()
    if ctx.channel.kind_enum.is_conversation:
        raise Forbidden("Direct messages have no settings to change.", code="cannot_edit_dm")
    # Renaming, archiving and retention are channel-admin actions; topic is
    # open to members.
    changes = payload.model_dump(exclude_unset=True)
    privileged = {"name", "is_archived", "retention_days"} & changes.keys()
    if privileged and membership.role != ChannelRole.ADMIN.value:
        raise Forbidden(
            "Only a channel admin can rename, archive or set retention on this channel.",
            code="not_channel_admin",
            details={"fields": sorted(privileged)},
        )

    was_archived = ctx.channel.is_archived
    previous_name = ctx.channel.name
    previous_retention = ctx.channel.retention_days
    for field, value in changes.items():
        setattr(ctx.channel, field, value)

    if "name" in changes and changes["name"] != previous_name:
        await audit.record(
            db,
            workspace_id=ctx.channel.workspace_id,
            actor=ctx.user,
            action="channel.renamed",
            target_type="channel",
            target_id=ctx.channel.id,
            target_label=ctx.channel.name,
            details={"from": previous_name, "to": ctx.channel.name},
            request=request,
        )
    if ctx.channel.is_archived and not was_archived:
        await audit.record(
            db,
            workspace_id=ctx.channel.workspace_id,
            actor=ctx.user,
            action="channel.archived",
            target_type="channel",
            target_id=ctx.channel.id,
            target_label=ctx.channel.name,
            request=request,
        )
    if "retention_days" in changes and changes["retention_days"] != previous_retention:
        await audit.record(
            db,
            workspace_id=ctx.channel.workspace_id,
            actor=ctx.user,
            action="retention.updated",
            target_type="channel",
            target_id=ctx.channel.id,
            target_label=ctx.channel.name,
            details={"from": previous_retention, "to": ctx.channel.retention_days},
            request=request,
        )
    await db.commit()

    out = await _serialise(db, ctx.channel, membership, viewer_id=ctx.user.id)
    event = (
        ServerEvent.CHANNEL_ARCHIVED
        if ctx.channel.is_archived and not was_archived
        else ServerEvent.CHANNEL_UPDATED
    )
    await emit_to_channel(
        ctx.channel.id,
        event,
        {"channel": out.model_dump(mode="json")},
        workspace_id=ctx.channel.workspace_id,
    )
    return out


# ── Membership ──────────────────────────────────────────────────────────────


@router.post("/channels/{channel_id}/join", response_model=ChannelOut)
async def join_channel(ctx: ChannelCtx, db: DbSession) -> ChannelOut:
    was_member = ctx.membership is not None
    membership = await channel_service.join_channel(db, channel=ctx.channel, user_id=ctx.user.id)
    if not was_member:
        await _announce(db, ctx.channel, f"{ctx.user.display_name} 님이 참여했습니다.")
    await db.commit()
    await emit_to_channel(
        ctx.channel.id,
        ServerEvent.CHANNEL_MEMBER_JOINED,
        {
            "channel_id": ctx.channel.id,
            "user": UserBrief.model_validate(ctx.user).model_dump(),
        },
        workspace_id=ctx.channel.workspace_id,
    )
    if not was_member:
        webhooks.schedule(
            "channel.member_joined",
            workspace_id=ctx.channel.workspace_id,
            payload={
                "channel": {"id": ctx.channel.id, "name": ctx.channel.name},
                "user": UserBrief.model_validate(ctx.user).model_dump(),
            },
        )
    return await _serialise(db, ctx.channel, membership, viewer_id=ctx.user.id)


@router.post("/channels/{channel_id}/leave", response_model=OkResponse)
async def leave_channel(ctx: ChannelCtx, db: DbSession) -> OkResponse:
    was_member = ctx.membership is not None
    await channel_service.leave_channel(db, channel=ctx.channel, user_id=ctx.user.id)
    if was_member and not ctx.channel.kind_enum.is_conversation:
        await _announce(db, ctx.channel, f"{ctx.user.display_name} 님이 나갔습니다.")
    await db.commit()
    await emit_to_channel(
        ctx.channel.id,
        ServerEvent.CHANNEL_MEMBER_LEFT,
        {"channel_id": ctx.channel.id, "user_id": ctx.user.id},
        workspace_id=ctx.channel.workspace_id,
    )
    return OkResponse()


@router.get("/channels/{channel_id}/members", response_model=list[ChannelMemberOut])
async def list_channel_members(
    ctx: ChannelCtx,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ChannelMemberOut]:
    rows = await db.scalars(
        select(ChannelMember)
        .where(ChannelMember.channel_id == ctx.channel.id)
        .options(selectinload(ChannelMember.user))
        .order_by(ChannelMember.role, ChannelMember.created_at)
        .limit(limit)
    )
    return [ChannelMemberOut.model_validate(row) for row in rows.all()]


@router.post("/channels/{channel_id}/members", response_model=list[str])
async def add_channel_members(
    payload: AddMembersRequest, ctx: ChannelCtx, db: DbSession
) -> list[str]:
    ctx.require_member()
    added = await channel_service.add_members(
        db, channel=ctx.channel, user_ids=payload.user_ids, actor_id=ctx.user.id
    )
    if added:
        names = list((await db.scalars(select(User.display_name).where(User.id.in_(added)))).all())
        await _announce(
            db,
            ctx.channel,
            f"{ctx.user.display_name} 님이 {', '.join(names)} 님을 추가했습니다.",
        )
    await db.commit()
    for user_id in added:
        await emit_to_channel(
            ctx.channel.id,
            ServerEvent.CHANNEL_MEMBER_JOINED,
            {"channel_id": ctx.channel.id, "user_id": user_id},
            workspace_id=ctx.channel.workspace_id,
        )
        webhooks.schedule(
            "channel.member_joined",
            workspace_id=ctx.channel.workspace_id,
            payload={
                "channel": {"id": ctx.channel.id, "name": ctx.channel.name},
                "user": {"id": user_id},
                "added_by": UserBrief.model_validate(ctx.user).model_dump(),
            },
        )
    return added


@router.delete("/channels/{channel_id}/members/{user_id}", response_model=OkResponse)
async def remove_channel_member(
    user_id: str, ctx: ChannelCtx, db: DbSession, request: Request
) -> OkResponse:
    """Remove someone from a channel. Channel-admin only.

    Removing yourself is `leave` — routing it there keeps "I left" and "I was
    removed" distinguishable in the emitted events and in any future audit.
    """
    membership = ctx.require_member()
    if ctx.channel.kind_enum.is_conversation:
        raise Forbidden("People cannot be removed from a direct message.", code="cannot_edit_dm")
    if membership.role != ChannelRole.ADMIN.value:
        raise Forbidden("Only a channel admin can remove members.", code="not_channel_admin")
    if user_id == ctx.user.id:
        raise Forbidden("Use leave to remove yourself.", code="cannot_remove_self")

    removed = await db.get(User, user_id)
    await channel_service.leave_channel(db, channel=ctx.channel, user_id=user_id)
    if removed is not None:
        await _announce(
            db,
            ctx.channel,
            f"{ctx.user.display_name} 님이 {removed.display_name} 님을 내보냈습니다.",
        )
    await audit.record(
        db,
        workspace_id=ctx.channel.workspace_id,
        actor=ctx.user,
        action="channel.member_removed",
        target_type="user",
        target_id=user_id,
        target_label=removed.display_name if removed else None,
        details={"channel_id": ctx.channel.id, "channel": ctx.channel.name},
        request=request,
    )
    await db.commit()
    await emit_to_channel(
        ctx.channel.id,
        ServerEvent.CHANNEL_MEMBER_LEFT,
        {"channel_id": ctx.channel.id, "user_id": user_id},
        workspace_id=ctx.channel.workspace_id,
    )
    return OkResponse()


@router.patch("/channels/{channel_id}/members/{user_id}", response_model=ChannelMemberOut)
async def update_channel_member_role(
    user_id: str,
    payload: UpdateMemberRoleRequest,
    ctx: ChannelCtx,
    db: DbSession,
    request: Request,
) -> ChannelMemberOut:
    """Promote or demote a channel member. Channel-admin only.

    Until this existed the creator was the channel's only admin for life —
    one holiday and nobody could rename, archive or remove. An admin cannot
    change their own role: the last admin demoting themself would orphan the
    channel, and promoting yourself is meaningless.
    """
    membership = ctx.require_member()
    if ctx.channel.kind_enum.is_conversation:
        raise Forbidden("Direct messages have no roles.", code="cannot_edit_dm")
    if membership.role != ChannelRole.ADMIN.value:
        raise Forbidden("Only a channel admin can change roles.", code="not_channel_admin")
    if user_id == ctx.user.id:
        raise Forbidden("Ask another admin to change your role.", code="cannot_change_own_role")

    target = await db.scalar(
        select(ChannelMember)
        .where(ChannelMember.channel_id == ctx.channel.id, ChannelMember.user_id == user_id)
        .options(selectinload(ChannelMember.user))
        .limit(1)
    )
    if target is None:
        raise NotFound("That person is not in this channel.", code="not_channel_member")

    if target.role != payload.role.value:
        previous_role = target.role
        target.role = payload.role.value
        await audit.record(
            db,
            workspace_id=ctx.channel.workspace_id,
            actor=ctx.user,
            action="channel.member_role_changed",
            target_type="user",
            target_id=user_id,
            target_label=target.user.display_name,
            details={
                "channel_id": ctx.channel.id,
                "channel": ctx.channel.name,
                "from": previous_role,
                "to": target.role,
            },
            request=request,
        )
        promoted = payload.role == ChannelRole.ADMIN
        verb = "관리자로 지정했습니다" if promoted else "관리자에서 해제했습니다"
        await _announce(
            db,
            ctx.channel,
            f"{ctx.user.display_name} 님이 {target.user.display_name} 님을 {verb}.",
        )
        await db.commit()
        await emit_to_channel(
            ctx.channel.id,
            ServerEvent.CHANNEL_UPDATED,
            {"channel_id": ctx.channel.id, "member_role_changed": user_id},
            workspace_id=ctx.channel.workspace_id,
        )
    return ChannelMemberOut.model_validate(target)


async def _announce(db: DbSession, channel: Channel, body: str) -> None:
    """Leave a system line in the transcript and fan it out.

    Joins, leaves, adds and removals used to happen silently: a person could be
    pulled out of a channel and neither they nor anyone else saw a trace. The
    row is a real message (kind=system, no author) so it pages, searches and
    syncs like everything else; it never bumps unread counters.
    """
    message, created = await message_service.create_message(
        db, channel=channel, author=None, body=body, kind=MessageKind.SYSTEM
    )
    if not created:
        return
    await db.flush()
    await db.refresh(message, ["author", "reactions", "attachments"])
    out = serialise_message(message, viewer_id=None)
    await emit_to_channel(
        channel.id,
        ServerEvent.MESSAGE_CREATED,
        {"message": out.model_dump(mode="json")},
        workspace_id=channel.workspace_id,
    )


@router.patch("/channels/{channel_id}/membership", response_model=ChannelMembershipOut)
async def update_my_membership(
    payload: UpdateMembershipRequest, ctx: ChannelCtx, db: DbSession
) -> ChannelMembershipOut:
    """Per-user channel preferences: mute, star, sidebar section, notifications."""
    membership = ctx.require_member()
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(membership, field, value)
    await db.commit()
    return ChannelMembershipOut.model_validate(membership)


@router.post("/channels/{channel_id}/read", response_model=ChannelMembershipOut)
async def mark_read(
    payload: MarkReadRequest, ctx: ChannelCtx, db: DbSession
) -> ChannelMembershipOut:
    """Move the read cursor. Also syncs the caller's other devices."""
    membership = ctx.require_member()
    updated = await channel_service.mark_read(
        db, membership=membership, message_id=payload.message_id, channel=ctx.channel
    )
    await db.commit()

    from app.realtime.events import emit_to_users

    await emit_to_users(
        [ctx.user.id],
        ServerEvent.CHANNEL_READ,
        {
            "channel_id": ctx.channel.id,
            "last_read_message_id": updated.last_read_message_id,
            "unread_count": updated.unread_count,
            "mention_count": updated.mention_count,
        },
        workspace_id=ctx.channel.workspace_id,
    )
    return ChannelMembershipOut.model_validate(updated)
