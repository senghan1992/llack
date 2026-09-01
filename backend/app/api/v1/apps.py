"""Mini-app platform endpoints: directory, install, panel sessions, bridge API.

The bridge API (`/app-bridge/*`) is what a mini-app's SDK calls. It is a
deliberately small surface — identity, channel/message read+write, storage,
notify — and every route enforces the installation's granted scopes.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field

from app.api.deps import (
    AdminWorkspaceCtx,
    CurrentPrincipal,
    CurrentUser,
    DbSession,
    WorkspaceCtx,
)
from app.core.enums import AppScope, AppStatus, MessageKind
from app.core.errors import Forbidden, NotFound
from app.models.app import App
from app.realtime.events import emit_to_channel, emit_to_users, emit_to_workspace
from app.schemas.app import (
    AppInstallationOut,
    AppManifest,
    AppOut,
    AppStorageItemOut,
    AppStorageSetRequest,
    AppTokenOut,
    CreateAppTokenRequest,
    InstallAppRequest,
    PanelSessionOut,
    UpdateInstallationRequest,
)
from app.schemas.common import OkResponse, Payload
from app.schemas.realtime import ServerEvent
from app.schemas.user import UserBrief
from app.services import apps as app_service
from app.services import messages as message_service

router = APIRouter(tags=["apps"])


# ── Directory & authoring ───────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/apps/available", response_model=list[AppOut])
async def list_available_apps(
    ctx: WorkspaceCtx,
    db: DbSession,
    include_drafts: Annotated[bool, Query()] = False,
) -> list[AppOut]:
    """The app directory for this workspace: shared apps plus its private ones."""
    rows = await app_service.list_available_apps(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        include_drafts=include_drafts,
    )
    return [AppOut.model_validate(row) for row in rows]


@router.post("/apps", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def register_app(
    manifest: AppManifest,
    db: DbSession,
    user: CurrentUser,
    owner_workspace_id: Annotated[str | None, Query(max_length=26)] = None,
) -> AppOut:
    """Register an app from a manifest.

    Pass `owner_workspace_id` to make it private to that workspace — the normal
    case for a team publishing its own internal tool.
    """
    app_row = await app_service.register_app(
        db, manifest=manifest, author=user, owner_workspace_id=owner_workspace_id
    )
    await db.commit()
    return AppOut.model_validate(app_row)


@router.get("/apps/{app_id}", response_model=AppOut)
async def get_app(app_id: str, db: DbSession, user: CurrentUser) -> AppOut:
    app_row = await db.get(App, app_id)
    if app_row is None:
        raise NotFound("App not found.", code="app_not_found")
    return AppOut.model_validate(app_row)


@router.put("/apps/{app_id}/manifest", response_model=AppOut)
async def update_manifest(
    app_id: str, manifest: AppManifest, db: DbSession, user: CurrentUser
) -> AppOut:
    app_row = await db.get(App, app_id)
    if app_row is None:
        raise NotFound("App not found.", code="app_not_found")
    await app_service.update_app_manifest(db, app_row=app_row, manifest=manifest, actor=user)
    await db.commit()
    return AppOut.model_validate(app_row)


class SetStatusRequest(Payload):
    status: AppStatus


@router.put("/apps/{app_id}/status", response_model=AppOut)
async def set_status(
    app_id: str, payload: SetStatusRequest, db: DbSession, user: CurrentUser
) -> AppOut:
    app_row = await db.get(App, app_id)
    if app_row is None:
        raise NotFound("App not found.", code="app_not_found")
    await app_service.set_app_status(db, app_row=app_row, status=payload.status, actor=user)
    await db.commit()
    return AppOut.model_validate(app_row)


# ── Installation ────────────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/apps", response_model=list[AppInstallationOut])
async def list_installed(
    ctx: WorkspaceCtx,
    db: DbSession,
    only_enabled: Annotated[bool, Query()] = True,
) -> list[AppInstallationOut]:
    """The workspace's app dock."""
    rows = await app_service.list_installations(
        db, workspace_id=ctx.workspace.id, user_id=ctx.user.id, only_enabled=only_enabled
    )
    return [AppInstallationOut.model_validate(row) for row in rows]


@router.post(
    "/workspaces/{workspace_id}/apps/{app_id}/install",
    response_model=AppInstallationOut,
    status_code=status.HTTP_201_CREATED,
)
async def install_app(
    app_id: str, payload: InstallAppRequest, ctx: AdminWorkspaceCtx, db: DbSession
) -> AppInstallationOut:
    app_row = await db.get(App, app_id)
    if app_row is None:
        raise NotFound("App not found.", code="app_not_found")

    installation = await app_service.install_app(
        db,
        workspace_id=ctx.workspace.id,
        app_row=app_row,
        actor=ctx.user,
        granted_scopes=payload.granted_scopes,
        config=payload.config,
        pin_to_dock=payload.pin_to_dock,
    )
    await db.commit()
    await db.refresh(installation, ["app"])

    out = AppInstallationOut.model_validate(installation)
    await emit_to_workspace(
        ctx.workspace.id,
        ServerEvent.APP_INSTALLED,
        {"installation": out.model_dump(mode="json")},
    )
    return out


@router.patch("/app-installations/{installation_id}", response_model=AppInstallationOut)
async def update_installation(
    installation_id: str,
    payload: UpdateInstallationRequest,
    db: DbSession,
    user: CurrentUser,
) -> AppInstallationOut:
    installation = await app_service.get_installation(
        db, installation_id=installation_id, user_id=user.id
    )
    await app_service.update_installation(
        db,
        installation=installation,
        actor=user,
        config=payload.config,
        granted_scopes=payload.granted_scopes,
        is_enabled=payload.is_enabled,
        is_pinned=payload.is_pinned,
        sort_order=payload.sort_order,
    )
    await db.commit()
    await db.refresh(installation, ["app"])
    return AppInstallationOut.model_validate(installation)


@router.delete("/app-installations/{installation_id}", response_model=OkResponse)
async def uninstall(installation_id: str, db: DbSession, user: CurrentUser) -> OkResponse:
    installation = await app_service.get_installation(
        db, installation_id=installation_id, user_id=user.id
    )
    workspace_id = installation.workspace_id
    app_id = installation.app_id
    await app_service.uninstall_app(db, installation=installation, actor=user)
    await db.commit()

    await emit_to_workspace(
        workspace_id,
        ServerEvent.APP_UNINSTALLED,
        {"installation_id": installation_id, "app_id": app_id},
    )
    return OkResponse()


# ── Panel sessions ──────────────────────────────────────────────────────────


@router.post("/app-installations/{installation_id}/panel-session", response_model=PanelSessionOut)
async def create_panel_session(
    installation_id: str,
    db: DbSession,
    user: CurrentUser,
    channel_id: Annotated[str | None, Query(max_length=26)] = None,
) -> PanelSessionOut:
    """Mint everything the desktop host needs to open a mini-app's webview.

    The returned `bridge_token` is short-lived and scoped to this installation;
    the panel never sees the user's own access token.
    """
    from datetime import UTC, datetime

    installation = await app_service.get_installation(
        db, installation_id=installation_id, user_id=user.id
    )
    if not installation.is_enabled:
        raise Forbidden("This app is disabled.", code="app_disabled")
    if not installation.app.has_panel:
        raise Forbidden("This app has no panel surface.", code="app_without_panel")

    token, expires_at = app_service.mint_bridge_token(
        installation=installation, acting_user_id=user.id, channel_id=channel_id
    )
    installation.last_used_at = datetime.now(UTC)
    await db.commit()

    return PanelSessionOut(
        installation_id=installation.id,
        app_id=installation.app_id,
        panel_url=installation.app.panel_url or "",
        bridge_token=token,
        expires_at=expires_at,
        granted_scopes=installation.granted_scopes,
        config=installation.config,
        context={
            "workspace_id": installation.workspace_id,
            "channel_id": channel_id,
            "user": UserBrief.model_validate(user).model_dump(),
            "locale": user.locale,
            "timezone": user.timezone,
            "default_width": installation.app.default_width,
            "accent_color": installation.app.accent_color,
        },
    )


# ── Server-to-server tokens ─────────────────────────────────────────────────


@router.post(
    "/app-installations/{installation_id}/tokens",
    response_model=AppTokenOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    installation_id: str,
    payload: CreateAppTokenRequest,
    db: DbSession,
    user: CurrentUser,
) -> AppTokenOut:
    """Issue a long-lived token. The secret is returned exactly once."""
    installation = await app_service.get_installation(
        db, installation_id=installation_id, user_id=user.id
    )
    token, raw = await app_service.create_app_token(
        db,
        installation=installation,
        actor=user,
        name=payload.name,
        ttl_days=payload.ttl_days,
    )
    await db.commit()
    return AppTokenOut(
        **AppTokenOut.model_validate(token).model_dump(exclude={"token"}), token=raw
    )


# ══════════════════════════════════════════════════════════════════════════
#  Bridge API — called by a mini-app's SDK, authenticated as the app
# ══════════════════════════════════════════════════════════════════════════

bridge = APIRouter(prefix="/app-bridge", tags=["app-bridge"])


@bridge.get("/context", response_model=dict)
async def bridge_context(principal: CurrentPrincipal, db: DbSession) -> dict[str, Any]:
    """Who am I, where am I, and what am I allowed to do."""
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.IDENTITY_READ)
    installation = principal.installation
    return {
        "installation_id": installation.id,
        "app_id": installation.app_id,
        "workspace_id": installation.workspace_id,
        "granted_scopes": list(principal.scopes),
        "config": installation.config,
        "acting_user": UserBrief.model_validate(principal.user).model_dump(),
    }


class BridgePostMessageRequest(Payload):
    channel_id: str = Field(min_length=26, max_length=26)
    body: str = Field(default="", max_length=40_000)
    blocks: list[dict[str, Any]] | None = None
    parent_id: str | None = Field(default=None, max_length=26)
    client_msg_id: str | None = Field(default=None, max_length=64)


@bridge.post("/messages", response_model=dict, status_code=status.HTTP_201_CREATED)
async def bridge_post_message(
    payload: BridgePostMessageRequest, principal: CurrentPrincipal, db: DbSession
) -> dict[str, Any]:
    """Post a message as the app's bot user."""
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.MESSAGES_WRITE)

    from app.services.channels import get_channel

    channel = await get_channel(db, payload.channel_id)
    if channel.workspace_id != principal.installation.workspace_id:
        raise NotFound("Channel not found.", code="channel_not_found")

    allowed = principal.installation.channel_ids
    if allowed and channel.id not in allowed:
        raise Forbidden("This app was not added to this channel.", code="app_not_in_channel")

    bot_user_id = principal.installation.bot_user_id
    author = principal.user
    if bot_user_id and bot_user_id != author.id:
        from app.models.user import User

        bot = await db.get(User, bot_user_id)
        if bot is not None:
            author = bot

    message, created = await message_service.create_message(
        db,
        channel=channel,
        author=author,
        body=payload.body,
        blocks=payload.blocks,
        client_msg_id=payload.client_msg_id,
        parent_id=payload.parent_id,
        app_id=principal.installation.app_id,
        kind=MessageKind.APP,
    )
    await db.commit()

    from app.api.v1.messages import serialise_message

    await db.refresh(message, ["author", "reactions", "attachments"])
    out = serialise_message(message, viewer_id=None)
    if created:
        await emit_to_channel(
            channel.id,
            ServerEvent.MESSAGE_CREATED,
            {"message": out.model_dump(mode="json")},
            workspace_id=channel.workspace_id,
        )
    return {"message": out.model_dump(mode="json"), "created": created}


@bridge.get("/channels", response_model=list[dict])
async def bridge_list_channels(
    principal: CurrentPrincipal,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, Any]]:
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.CHANNELS_READ)

    from sqlalchemy import select

    from app.core.enums import ChannelKind
    from app.models.channel import Channel

    rows = await db.scalars(
        select(Channel)
        .where(
            Channel.workspace_id == principal.installation.workspace_id,
            # An app never sees DMs — that is a hard boundary, not a scope.
            Channel.kind.in_([ChannelKind.PUBLIC.value, ChannelKind.PRIVATE.value]),
            Channel.is_archived.is_(False),
        )
        .order_by(Channel.name)
        .limit(limit)
    )
    return [
        {"id": c.id, "name": c.name, "slug": c.slug, "kind": c.kind, "topic": c.topic}
        for c in rows.all()
    ]


class BridgeNotifyRequest(Payload):
    user_ids: list[str] = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=500)
    deep_link: str | None = Field(default=None, max_length=500)


@bridge.post("/notify", response_model=OkResponse)
async def bridge_notify(
    payload: BridgeNotifyRequest, principal: CurrentPrincipal, db: DbSession
) -> OkResponse:
    """Send a desktop notification to specific people in the workspace."""
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.NOTIFY)

    from sqlalchemy import select

    from app.models.workspace import WorkspaceMember

    # Only people actually in this workspace may be notified.
    valid = list(
        (
            await db.scalars(
                select(WorkspaceMember.user_id).where(
                    WorkspaceMember.workspace_id == principal.installation.workspace_id,
                    WorkspaceMember.user_id.in_(set(payload.user_ids)),
                    WorkspaceMember.is_active.is_(True),
                )
            )
        ).all()
    )
    await emit_to_users(
        valid,
        "notification",
        {
            "title": payload.title,
            "body": payload.body,
            "app_id": principal.installation.app_id,
            "installation_id": principal.installation.id,
            "deep_link": payload.deep_link,
        },
        workspace_id=principal.installation.workspace_id,
    )
    return OkResponse()


@bridge.get("/storage/{key}", response_model=AppStorageItemOut)
async def bridge_storage_get(
    key: str,
    principal: CurrentPrincipal,
    db: DbSession,
    scope_key: Annotated[str, Query(max_length=80)] = "workspace",
) -> AppStorageItemOut:
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.STORAGE)

    item = await app_service.storage_get(
        db, installation_id=principal.installation.id, scope_key=scope_key, key=key
    )
    if item is None:
        raise NotFound("No value stored under this key.", code="storage_key_not_found")
    return AppStorageItemOut.model_validate(item)


@bridge.put("/storage/{key}", response_model=AppStorageItemOut)
async def bridge_storage_set(
    key: str, payload: AppStorageSetRequest, principal: CurrentPrincipal, db: DbSession
) -> AppStorageItemOut:
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.STORAGE)

    item = await app_service.storage_set(
        db,
        installation_id=principal.installation.id,
        scope_key=payload.scope_key,
        key=key,
        value=payload.value,
    )
    await db.commit()
    return AppStorageItemOut.model_validate(item)


@bridge.get("/storage", response_model=list[AppStorageItemOut])
async def bridge_storage_list(
    principal: CurrentPrincipal,
    db: DbSession,
    scope_key: Annotated[str, Query(max_length=80)] = "workspace",
    prefix: Annotated[str | None, Query(max_length=200)] = None,
) -> list[AppStorageItemOut]:
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.STORAGE)

    items = await app_service.storage_list(
        db, installation_id=principal.installation.id, scope_key=scope_key, prefix=prefix
    )
    return [AppStorageItemOut.model_validate(i) for i in items]


@bridge.delete("/storage/{key}", response_model=OkResponse)
async def bridge_storage_delete(
    key: str,
    principal: CurrentPrincipal,
    db: DbSession,
    scope_key: Annotated[str, Query(max_length=80)] = "workspace",
) -> OkResponse:
    if principal.installation is None:
        raise Forbidden("This endpoint requires an app token.", code="app_token_required")
    principal.require_scope(AppScope.STORAGE)

    await app_service.storage_delete(
        db, installation_id=principal.installation.id, scope_key=scope_key, key=key
    )
    await db.commit()
    return OkResponse()
