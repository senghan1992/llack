"""App platform surfaces beyond install/panel: commands, interactions, the home
tab, review, and the developer console (secrets, tokens, deliveries).

Kept apart from `apps.py` so that file stays the directory/bridge story and
this one is "what a team does to *ship* an app and what people do *with* it".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import ChannelCtx, CurrentUser, DbSession, WorkspaceCtx
from app.core.config import settings
from app.core.enums import MessageKind
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.models.app import App, WebhookDelivery
from app.models.channel import Channel
from app.models.user import User
from app.realtime.events import emit_to_channel, emit_to_users
from app.schemas.app import (
    ActionResultOut,
    AppTokenOut,
    BlockActionRequest,
    CommandOut,
    CommandResultOut,
    CreateAppTokenRequest,
    DeveloperAppOut,
    PanelSessionOut,
    RespondRequest,
    ReviewRequest,
    RunCommandRequest,
    SecretOut,
    WebhookDeliveryOut,
)
from app.schemas.common import OkResponse
from app.schemas.realtime import ServerEvent
from app.schemas.user import UserBrief
from app.services import apps as app_service
from app.services import audit, commands, interactions, outbound, webhooks
from app.services import messages as message_service
from app.services.blocks import validate_blocks

router = APIRouter(tags=["app-platform"])


def _response_base(request: Request) -> str:
    """Where an app should POST back to: the public address, else this request's."""
    if settings.public_web_url:
        return settings.public_web_url.rstrip("/")
    return str(request.base_url).rstrip("/")


async def _load_app(db: DbSession, app_id: str) -> App:
    app_row = await db.get(App, app_id)
    if app_row is None:
        raise NotFound("App not found.", code="app_not_found")
    return app_row


async def _broadcast_new_message(db: DbSession, message_id: str, channel: Channel) -> None:
    """Fan out a message a command created, the way the create route does."""
    from app.api.v1.messages import serialise_message

    message = await message_service.get_message(db, message_id)
    out = serialise_message(message, viewer_id=None)
    await emit_to_channel(
        channel.id,
        ServerEvent.MESSAGE_CREATED,
        {"message": out.model_dump(mode="json")},
        workspace_id=channel.workspace_id,
    )


# ── Slash commands ──────────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/commands", response_model=list[CommandOut])
async def list_commands(ctx: WorkspaceCtx, db: DbSession) -> list[CommandOut]:
    """Built-ins plus every installed app's commands, for the composer's `/` picker."""
    rows = await commands.list_commands(db, workspace_id=ctx.workspace.id)
    return [CommandOut.model_validate(row) for row in rows]


@router.post("/channels/{channel_id}/commands", response_model=CommandResultOut)
async def run_command(
    payload: RunCommandRequest, ctx: ChannelCtx, db: DbSession, request: Request
) -> CommandResultOut:
    """Execute a slash command in this channel.

    Nothing is posted unless the command posts (`/shrug`, a non-ephemeral app
    reply); the answer for the caller comes back in `response`. A failed or
    unknown command is `handled: false` with a Korean explanation — never a
    500 from an app's server.
    """
    membership = ctx.require_member()
    result = await commands.run(
        db,
        channel=ctx.channel,
        membership=membership,
        user=ctx.user,
        text=payload.text,
        response_base=_response_base(request),
    )
    await db.commit()
    if result.posted_message_id:
        await _broadcast_new_message(db, result.posted_message_id, ctx.channel)
    if result.text is not None and result.handled and payload.text.split()[0].lower() == "/leave":
        await emit_to_channel(
            ctx.channel.id,
            ServerEvent.CHANNEL_MEMBER_LEFT,
            {"channel_id": ctx.channel.id, "user_id": ctx.user.id},
            workspace_id=ctx.channel.workspace_id,
        )
    return CommandResultOut.model_validate(result.as_dict())


@router.post("/apps/{app_id}/respond/{nonce}", response_model=OkResponse)
async def respond_to_command(
    app_id: str, nonce: str, payload: RespondRequest, db: DbSession, request: Request
) -> OkResponse:
    """A command handler answering later through its `response_url`.

    Signed by the app with the same scheme Llack uses outbound; the nonce is
    single-use and expires 30 minutes after the command. The text is posted to
    the originating channel as the app's bot.
    """
    app_row = await _load_app(db, app_id)
    body = await request.body()
    timestamp = request.headers.get("x-llack-timestamp", "")
    signature = request.headers.get("x-llack-signature", "")
    if not app_row.app_secret or not outbound.verify(
        app_row.app_secret, timestamp, body, signature
    ):
        raise Unauthorized("Signature does not verify.", code="bad_signature")

    from sqlalchemy import select

    delivery = await db.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.app_id == app_row.id,
            WebhookDelivery.response_nonce == nonce,
        )
        .limit(1)
    )
    if delivery is None or delivery.channel_id is None:
        raise NotFound("This response URL is not valid.", code="response_url_invalid")
    if delivery.expires_at is None or delivery.expires_at < datetime.now(UTC):
        raise NotFound("This response URL has expired.", code="response_url_expired")

    channel = await db.get(Channel, delivery.channel_id)
    if channel is None:
        raise NotFound("Channel not found.", code="channel_not_found")
    from app.models.app import AppInstallation

    installation = (
        await db.get(AppInstallation, delivery.installation_id)
        if delivery.installation_id
        else None
    )
    bot = (
        await db.get(User, installation.bot_user_id)
        if installation is not None and installation.bot_user_id
        else None
    )
    message, _ = await message_service.create_message(
        db,
        channel=channel,
        author=bot,
        body=payload.text,
        blocks=validate_blocks(payload.blocks),
        app_id=app_row.id,
        kind=MessageKind.APP,
    )
    # One shot: burn the nonce.
    delivery.response_nonce = None
    await db.commit()
    await _broadcast_new_message(db, message.id, channel)
    return OkResponse()


# ── Interactive blocks ──────────────────────────────────────────────────────


@router.post("/messages/{message_id}/actions", response_model=ActionResultOut)
async def message_action(
    message_id: str,
    payload: BlockActionRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> ActionResultOut:
    """A button/select in an app's message was used; forward it to the app."""
    from app.api.v1.messages import serialise_message
    from app.services.channels import resolve_access

    message = await message_service.get_message(db, message_id)
    channel, _ = await resolve_access(
        db, channel_id=message.channel_id, user_id=user.id, require_member=True
    )
    handled, ephemeral, changed = await interactions.dispatch(
        db,
        message=message,
        channel=channel,
        user=user,
        action_id=payload.action_id,
        value=payload.value,
        response_base=_response_base(request),
    )
    await db.commit()
    if changed:
        await db.refresh(message, ["author", "reactions", "attachments"])
        out = serialise_message(message, viewer_id=None)
        await emit_to_channel(
            channel.id,
            ServerEvent.MESSAGE_UPDATED,
            {"message": out.model_dump(mode="json")},
            workspace_id=channel.workspace_id,
        )
    return ActionResultOut(handled=handled, ephemeral={"text": ephemeral} if ephemeral else None)


# ── App home ────────────────────────────────────────────────────────────────


@router.post("/app-installations/{installation_id}/home-session", response_model=PanelSessionOut)
async def create_home_session(
    installation_id: str, db: DbSession, user: CurrentUser
) -> PanelSessionOut:
    """Like a panel session, for the app's channel-independent home screen."""
    installation = await app_service.get_installation(
        db, installation_id=installation_id, user_id=user.id
    )
    if not installation.is_enabled:
        raise Forbidden("This app is disabled.", code="app_disabled")
    if not installation.app.home_url:
        raise NotFound("This app has no home screen.", code="no_home")

    token, expires_at = app_service.mint_bridge_token(
        installation=installation, acting_user_id=user.id, channel_id=None
    )
    installation.last_used_at = datetime.now(UTC)
    await db.commit()
    return PanelSessionOut(
        installation_id=installation.id,
        app_id=installation.app_id,
        panel_url=installation.app.home_url,
        bridge_token=token,
        expires_at=expires_at,
        granted_scopes=installation.granted_scopes,
        config=installation.config,
        context={
            "workspace_id": installation.workspace_id,
            "channel_id": None,
            "surface": "home",
            "user": UserBrief.model_validate(user).model_dump(),
            "locale": user.locale,
            "timezone": user.timezone,
            "accent_color": installation.app.accent_color,
        },
    )


# ── Review ──────────────────────────────────────────────────────────────────


@router.post("/apps/{app_id}/submit", response_model=DeveloperAppOut)
async def submit_app(
    app_id: str, db: DbSession, user: CurrentUser, request: Request
) -> DeveloperAppOut:
    app_row = await _load_app(db, app_id)
    await app_service.submit_for_review(db, app_row=app_row, actor=user)
    await audit.record(
        db,
        workspace_id=app_row.owner_workspace_id,
        actor=user,
        action="app.submitted",
        target_type="app",
        target_id=app_row.id,
        target_label=app_row.name,
        request=request,
    )
    await db.commit()
    return DeveloperAppOut.model_validate(app_row)


@router.post("/apps/{app_id}/review", response_model=DeveloperAppOut)
async def review_app(
    app_id: str, payload: ReviewRequest, db: DbSession, user: CurrentUser, request: Request
) -> DeveloperAppOut:
    """Service admin: publish company-wide, or send back with a note."""
    app_row = await _load_app(db, app_id)
    approve = payload.decision == "approve"
    await app_service.decide_review(
        db, app_row=app_row, actor=user, approve=approve, note=payload.note
    )
    await audit.record(
        db,
        workspace_id=app_row.owner_workspace_id,
        actor=user,
        action="app.review_decided",
        target_type="app",
        target_id=app_row.id,
        target_label=app_row.name,
        details={"decision": payload.decision, "note": payload.note},
        request=request,
    )
    await db.commit()
    if app_row.author_id:
        body = (
            f"{app_row.name} 이(가) 게시되었습니다. 모든 워크스페이스에서 설치할 수 있습니다."
            if approve
            else f"{app_row.name} 이(가) 반려되었습니다."
        )
        if payload.note:
            body += f" 메모: {payload.note}"
        await emit_to_users(
            [app_row.author_id],
            "notification",
            {"kind": "review", "title": "앱 심사 결과", "body": body, "app_id": app_row.id},
            workspace_id=app_row.owner_workspace_id,
        )
    return DeveloperAppOut.model_validate(app_row)


@router.get("/apps/pending", response_model=list[DeveloperAppOut])
async def list_pending_apps(db: DbSession, user: CurrentUser) -> list[DeveloperAppOut]:
    if not user.is_service_admin:
        raise Forbidden("Only a service admin reviews apps.", code="service_admin_required")
    return [DeveloperAppOut.model_validate(row) for row in await app_service.list_pending(db)]


# ── Developer console ───────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/apps/mine", response_model=list[DeveloperAppOut])
async def list_my_apps(ctx: WorkspaceCtx, db: DbSession) -> list[DeveloperAppOut]:
    rows = await app_service.list_authored(db, workspace_id=ctx.workspace.id, user_id=ctx.user.id)
    return [DeveloperAppOut.model_validate(row) for row in rows]


@router.post("/apps/{app_id}/rotate-secret", response_model=SecretOut)
async def rotate_secret(
    app_id: str, db: DbSession, user: CurrentUser, request: Request
) -> SecretOut:
    app_row = await _load_app(db, app_id)
    secret = await app_service.rotate_secret(db, app_row=app_row, actor=user)
    await audit.record(
        db,
        workspace_id=app_row.owner_workspace_id,
        actor=user,
        action="app.secret_rotated",
        target_type="app",
        target_id=app_row.id,
        target_label=app_row.name,
        request=request,
    )
    await db.commit()
    return SecretOut(secret=secret)


@router.post("/apps/{app_id}/test-webhook", response_model=WebhookDeliveryOut)
async def test_webhook(app_id: str, db: DbSession, user: CurrentUser) -> WebhookDeliveryOut:
    """One synchronous `ping` to the app's webhook URL; the row says how it went."""
    app_row = await _load_app(db, app_id)
    await app_service.require_app_maintainer(db, app_row=app_row, actor=user)
    if not app_row.event_webhook_url:
        raise NotFound("This app has no event_webhook_url.", code="no_webhook_url")
    installation = None
    if app_row.owner_workspace_id:
        from sqlalchemy import select

        from app.models.app import AppInstallation

        installation = await db.scalar(
            select(AppInstallation)
            .where(
                AppInstallation.app_id == app_row.id,
                AppInstallation.workspace_id == app_row.owner_workspace_id,
            )
            .limit(1)
        )
    delivery = await webhooks.test_delivery(db, app_row=app_row, installation=installation)
    await db.commit()
    return WebhookDeliveryOut.model_validate(delivery)


@router.get("/apps/{app_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    app_id: str,
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[WebhookDeliveryOut]:
    from sqlalchemy import select

    app_row = await _load_app(db, app_id)
    await app_service.require_app_maintainer(db, app_row=app_row, actor=user)
    rows = await db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.app_id == app_row.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(limit)
    )
    return [WebhookDeliveryOut.model_validate(row) for row in rows.all()]


@router.get("/apps/{app_id}/tokens", response_model=list[AppTokenOut])
async def list_app_tokens(app_id: str, db: DbSession, user: CurrentUser) -> list[AppTokenOut]:
    app_row = await _load_app(db, app_id)
    await app_service.require_app_maintainer(db, app_row=app_row, actor=user)
    return [
        AppTokenOut.model_validate(row)
        for row in await app_service.list_app_tokens(db, app_row=app_row)
    ]


@router.post(
    "/apps/{app_id}/tokens", response_model=AppTokenOut, status_code=status.HTTP_201_CREATED
)
async def create_app_token(
    app_id: str,
    payload: CreateAppTokenRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> AppTokenOut:
    """A server-to-server token for the app in its home workspace.

    Tokens act as an installation's bot, so the app is installed at home (if
    it was not yet) and the token is issued against that installation. The
    plaintext is in this response and nowhere else.
    """
    app_row = await _load_app(db, app_id)
    installation = await app_service.home_installation(db, app_row=app_row, actor=user)
    token, raw = await app_service.create_app_token(
        db, installation=installation, actor=user, name=payload.name, ttl_days=payload.ttl_days
    )
    await audit.record(
        db,
        workspace_id=app_row.owner_workspace_id,
        actor=user,
        action="app.token_created",
        target_type="app",
        target_id=app_row.id,
        target_label=app_row.name,
        details={"token_id": token.id, "name": token.name},
        request=request,
    )
    await db.commit()
    return AppTokenOut(**AppTokenOut.model_validate(token).model_dump(exclude={"token"}), token=raw)


@router.delete("/apps/{app_id}/tokens/{token_id}", response_model=OkResponse)
async def revoke_app_token(
    app_id: str, token_id: str, db: DbSession, user: CurrentUser, request: Request
) -> OkResponse:
    app_row = await _load_app(db, app_id)
    await app_service.require_app_maintainer(db, app_row=app_row, actor=user)
    token = await app_service.revoke_app_token(db, app_row=app_row, token_id=token_id)
    await audit.record(
        db,
        workspace_id=app_row.owner_workspace_id,
        actor=user,
        action="app.token_revoked",
        target_type="app",
        target_id=app_row.id,
        target_label=app_row.name,
        details={"token_id": token.id, "name": token.name},
        request=request,
    )
    await db.commit()
    return OkResponse()
