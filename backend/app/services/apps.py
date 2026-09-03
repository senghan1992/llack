"""The mini-app platform: registration, installation, scopes and bridge tokens.

Security model, in one place so it can be reviewed as a whole:

1. A mini-app runs in a **sandboxed webview** owned by the desktop host. It
   never receives the signed-in user's access token.
2. To talk to the backend, the host mints a short-lived **bridge token** — a
   JWT of type `app` carrying the installation id, the acting user and the
   granted scopes. It expires in minutes and is re-minted by the host.
3. Every app-authenticated request is checked against the *installation's*
   granted scopes, not the manifest's requested scopes. Narrowing scopes at
   install time therefore actually restricts the app.
4. An app posting a message posts as its own **bot user**, so attribution in
   the transcript is never ambiguous.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AppKind, AppScope, AppStatus, WorkspaceRole
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.ids import new_token, new_ulid
from app.core.logging import get_logger
from app.core.security import create_access_token, decode_access_token, hash_token
from app.models.app import App, AppInstallation, AppStorageItem, AppToken
from app.models.user import User
from app.schemas.app import AppManifest
from app.services.auth import allocate_handle
from app.services.workspaces import require_membership

log = get_logger(__name__)

BRIDGE_TOKEN_TTL_SECONDS = 600  # 10 minutes; the host refreshes silently.


# ── Registration ────────────────────────────────────────────────────────────


async def register_app(
    db: AsyncSession,
    *,
    manifest: AppManifest,
    author: User,
    owner_workspace_id: str | None = None,
) -> App:
    """Create an app from a manifest.

    `owner_workspace_id` set = a private app only that workspace can install
    (the common case for a team's own internal tool). None = available to every
    workspace on this deployment.
    """
    if owner_workspace_id:
        await require_membership(
            db,
            workspace_id=owner_workspace_id,
            user_id=author.id,
            minimum_role=WorkspaceRole.ADMIN,
        )

    taken = await db.scalar(select(App.id).where(App.slug == manifest.slug).limit(1))
    if taken is not None:
        raise Conflict("An app with this identifier already exists.", code="app_slug_taken")

    _validate_manifest_surfaces(manifest)

    app_row = App(
        id=new_ulid(),
        slug=manifest.slug,
        name=manifest.name,
        version=manifest.version,
        tagline=manifest.tagline,
        description=manifest.description,
        icon_url=manifest.icon_url,
        accent_color=manifest.accent_color,
        kind=manifest.kind.value,
        status=AppStatus.DRAFT.value,
        owner_workspace_id=owner_workspace_id,
        author_id=author.id,
        panel_url=str(manifest.panel_url) if manifest.panel_url else None,
        sidebar_url=str(manifest.sidebar_url) if manifest.sidebar_url else None,
        event_webhook_url=str(manifest.event_webhook_url) if manifest.event_webhook_url else None,
        command_url=str(manifest.command_url) if manifest.command_url else None,
        interaction_url=str(manifest.interaction_url) if manifest.interaction_url else None,
        home_url=str(manifest.home_url) if manifest.home_url else None,
        # Minted once; the register response is the only time it is shown.
        app_secret=new_app_secret(),
        default_width=manifest.default_width,
        requested_scopes=[s.value for s in manifest.scopes],
        slash_commands=[c.model_dump(exclude_none=True) for c in manifest.slash_commands],
        event_subscriptions=manifest.events,
        manifest=manifest.model_dump(mode="json"),
    )
    db.add(app_row)
    await db.flush()
    log.info("app.registered", app_id=app_row.id, slug=app_row.slug, author_id=author.id)
    return app_row


def new_app_secret() -> str:
    return f"llack_as_{new_token(32)}"


async def rotate_secret(db: AsyncSession, *, app_row: App, actor: User) -> str:
    """A new signing secret; the old one stops verifying immediately."""
    await _require_app_maintainer(db, app_row=app_row, actor=actor)
    app_row.app_secret = new_app_secret()
    await db.flush()
    return app_row.app_secret


def _validate_manifest_surfaces(manifest: AppManifest) -> None:
    needs_panel = manifest.kind in (AppKind.PANEL, AppKind.BOTH)
    if needs_panel and manifest.panel_url is None:
        raise Conflict(
            "A panel app must declare panel_url.",
            code="manifest_missing_panel_url",
        )
    if manifest.kind is AppKind.LINK:
        if manifest.panel_url is None:
            raise Conflict(
                "A link app must declare panel_url.",
                code="manifest_missing_panel_url",
            )
        if manifest.scopes:
            # A link app is an arbitrary external site: it gets a frame from
            # the host and nothing else, so scopes are meaningless here and
            # accepting them would only mislead the installer.
            raise Conflict(
                "A link app cannot request scopes.",
                code="manifest_link_with_scopes",
            )
    if manifest.kind is AppKind.BOT and manifest.panel_url is not None:
        raise Conflict(
            "A bot-only app must not declare panel_url.",
            code="manifest_unexpected_panel_url",
        )
    if AppScope.PANEL_UI in manifest.scopes and not needs_panel:
        raise Conflict(
            "The panel:ui scope requires a panel surface.",
            code="manifest_scope_without_surface",
        )


async def update_app_manifest(
    db: AsyncSession, *, app_row: App, manifest: AppManifest, actor: User
) -> App:
    await _require_app_maintainer(db, app_row=app_row, actor=actor)
    if manifest.slug != app_row.slug:
        raise Conflict("An app's identifier cannot be changed.", code="app_slug_immutable")

    _validate_manifest_surfaces(manifest)

    app_row.name = manifest.name
    app_row.version = manifest.version
    app_row.tagline = manifest.tagline
    app_row.description = manifest.description
    app_row.icon_url = manifest.icon_url
    app_row.accent_color = manifest.accent_color
    app_row.kind = manifest.kind.value
    app_row.panel_url = str(manifest.panel_url) if manifest.panel_url else None
    app_row.sidebar_url = str(manifest.sidebar_url) if manifest.sidebar_url else None
    app_row.event_webhook_url = (
        str(manifest.event_webhook_url) if manifest.event_webhook_url else None
    )
    app_row.command_url = str(manifest.command_url) if manifest.command_url else None
    app_row.interaction_url = str(manifest.interaction_url) if manifest.interaction_url else None
    app_row.home_url = str(manifest.home_url) if manifest.home_url else None
    app_row.default_width = manifest.default_width
    app_row.requested_scopes = [s.value for s in manifest.scopes]
    app_row.slash_commands = [c.model_dump(exclude_none=True) for c in manifest.slash_commands]
    app_row.event_subscriptions = manifest.events
    app_row.manifest = manifest.model_dump(mode="json")
    await db.flush()
    return app_row


async def _require_app_maintainer(db: AsyncSession, *, app_row: App, actor: User) -> None:
    if app_row.author_id == actor.id or actor.is_service_admin:
        return
    if app_row.owner_workspace_id:
        await require_membership(
            db,
            workspace_id=app_row.owner_workspace_id,
            user_id=actor.id,
            minimum_role=WorkspaceRole.ADMIN,
        )
        return
    raise Forbidden("You cannot modify this app.", code="not_app_maintainer")


async def set_app_status(
    db: AsyncSession, *, app_row: App, status: AppStatus, actor: User
) -> App:
    """Direct status changes: pausing (`disabled`) and un-pausing (`draft`).

    Publication is not a status an author sets — it is the outcome of review
    (`submit_for_review` / `decide_review`). Only a service admin may write
    `published` directly, which is how first-party apps are seeded.
    """
    await _require_app_maintainer(db, app_row=app_row, actor=actor)
    review_states = (AppStatus.PUBLISHED, AppStatus.PENDING_REVIEW, AppStatus.REJECTED)
    if status in review_states and not actor.is_service_admin:
        raise Forbidden(
            "Publication goes through review: submit the app instead.",
            code="review_required",
        )
    app_row.status = status.value
    await db.flush()
    return app_row


async def require_app_maintainer(db: AsyncSession, *, app_row: App, actor: User) -> None:
    await _require_app_maintainer(db, app_row=app_row, actor=actor)


async def submit_for_review(db: AsyncSession, *, app_row: App, actor: User) -> App:
    await _require_app_maintainer(db, app_row=app_row, actor=actor)
    if app_row.status not in (AppStatus.DRAFT.value, AppStatus.REJECTED.value):
        raise Conflict(
            "Only a draft or rejected app can be submitted for review.",
            code="not_submittable",
            details={"status": app_row.status},
        )
    if app_row.kind == AppKind.LINK.value:
        raise Conflict(
            "A link app is workspace furniture and is not published.", code="not_submittable"
        )
    app_row.status = AppStatus.PENDING_REVIEW.value
    app_row.review_note = None
    await db.flush()
    return app_row


async def decide_review(
    db: AsyncSession, *, app_row: App, actor: User, approve: bool, note: str | None
) -> App:
    if not actor.is_service_admin:
        raise Forbidden("Only a service admin reviews apps.", code="service_admin_required")
    if app_row.status != AppStatus.PENDING_REVIEW.value:
        raise Conflict("This app is not waiting for review.", code="not_pending_review")
    app_row.status = AppStatus.PUBLISHED.value if approve else AppStatus.REJECTED.value
    app_row.review_note = (note or None) and note.strip()[:500]
    await db.flush()
    return app_row


async def list_pending(db: AsyncSession) -> list[App]:
    rows = await db.scalars(
        select(App).where(App.status == AppStatus.PENDING_REVIEW.value).order_by(App.updated_at)
    )
    return list(rows.all())


async def list_authored(db: AsyncSession, *, workspace_id: str, user_id: str) -> list[App]:
    """The developer console's list: apps this workspace made."""
    await require_membership(
        db, workspace_id=workspace_id, user_id=user_id, minimum_role=WorkspaceRole.ADMIN
    )
    rows = await db.scalars(
        select(App)
        .where(App.owner_workspace_id == workspace_id, App.kind != AppKind.LINK.value)
        .order_by(App.created_at.desc())
    )
    return list(rows.all())


async def home_installation(
    db: AsyncSession, *, app_row: App, actor: User
) -> AppInstallation:
    """The installation the console operates on: the app in its owner workspace.

    App tokens belong to an installation (they act as its bot), so the console
    ensures the app is installed at home first — unpinned, with its manifest
    scopes — and issues tokens against that.
    """
    await _require_app_maintainer(db, app_row=app_row, actor=actor)
    if not app_row.owner_workspace_id:
        raise Conflict(
            "A shared app has no home workspace; issue tokens per installation.",
            code="no_home_workspace",
        )
    existing = await db.scalar(
        select(AppInstallation)
        .where(
            AppInstallation.workspace_id == app_row.owner_workspace_id,
            AppInstallation.app_id == app_row.id,
        )
        .limit(1)
    )
    if existing is not None:
        return existing
    installation = await install_app(
        db,
        workspace_id=app_row.owner_workspace_id,
        app_row=app_row,
        actor=actor,
        pin_to_dock=False,
    )
    if installation.bot_user_id is None:
        # A panel-only app still needs an identity to post as when a token is
        # used server-to-server; give it one on demand.
        installation.bot_user_id = (
            await _ensure_bot_user(
                db, app_row=app_row, workspace_id=app_row.owner_workspace_id
            )
        ).id
        await db.flush()
    return installation


async def list_app_tokens(db: AsyncSession, *, app_row: App) -> list[AppToken]:
    rows = await db.execute(
        select(AppToken)
        .join(AppInstallation, AppInstallation.id == AppToken.installation_id)
        .where(AppInstallation.app_id == app_row.id, AppToken.revoked_at.is_(None))
        .order_by(AppToken.created_at.desc())
    )
    return list(rows.scalars().all())


async def revoke_app_token(db: AsyncSession, *, app_row: App, token_id: str) -> AppToken:
    token = await db.scalar(
        select(AppToken)
        .join(AppInstallation, AppInstallation.id == AppToken.installation_id)
        .where(AppToken.id == token_id, AppInstallation.app_id == app_row.id)
        .limit(1)
    )
    if token is None or token.revoked_at is not None:
        raise NotFound("Token not found.", code="app_token_not_found")
    token.revoked_at = datetime.now(UTC)
    await db.flush()
    return token


# ── Directory ───────────────────────────────────────────────────────────────


async def list_available_apps(
    db: AsyncSession, *, workspace_id: str, user_id: str, include_drafts: bool = False
) -> list[App]:
    """Apps installable in this workspace: shared apps plus its own private ones."""
    await require_membership(db, workspace_id=workspace_id, user_id=user_id)
    # Published apps from anywhere, plus everything this workspace authored —
    # a team installs and tries its own app long before review. Link apps are
    # dock tiles, not directory entries. `include_drafts` is kept for older
    # clients; own drafts are always listed now.
    del include_drafts
    rows = await db.scalars(
        select(App)
        .where(
            App.kind != AppKind.LINK.value,
            App.status != AppStatus.DISABLED.value,
            or_(
                App.status == AppStatus.PUBLISHED.value,
                App.owner_workspace_id == workspace_id,
            ),
        )
        .order_by(App.is_first_party.desc(), App.name)
    )
    return list(rows.all())


async def list_installations(
    db: AsyncSession, *, workspace_id: str, user_id: str, only_enabled: bool = True
) -> list[AppInstallation]:
    await require_membership(db, workspace_id=workspace_id, user_id=user_id)
    stmt = select(AppInstallation).where(AppInstallation.workspace_id == workspace_id)
    if only_enabled:
        stmt = stmt.where(AppInstallation.is_enabled.is_(True))
    stmt = stmt.order_by(
        AppInstallation.is_pinned.desc(), AppInstallation.sort_order, AppInstallation.created_at
    )
    return list((await db.scalars(stmt)).all())


async def get_installation(
    db: AsyncSession, *, installation_id: str, user_id: str
) -> AppInstallation:
    installation = await db.get(AppInstallation, installation_id)
    if installation is None:
        raise NotFound("This app is not installed.", code="installation_not_found")
    await require_membership(
        db, workspace_id=installation.workspace_id, user_id=user_id
    )
    return installation


# ── Installation ────────────────────────────────────────────────────────────


async def install_app(
    db: AsyncSession,
    *,
    workspace_id: str,
    app_row: App,
    actor: User,
    granted_scopes: list[AppScope] | None = None,
    config: dict[str, Any] | None = None,
    pin_to_dock: bool = True,
    minimum_role: WorkspaceRole = WorkspaceRole.ADMIN,
) -> AppInstallation:
    # Installing an app grants it access to workspace data, so it is an
    # admin-level action — except for link apps, which are granted nothing
    # (no scopes, no bridge) and may be added by any member; the caller
    # lowers `minimum_role` for those.
    await require_membership(
        db, workspace_id=workspace_id, user_id=actor.id, minimum_role=minimum_role
    )

    if app_row.status == AppStatus.DISABLED.value:
        raise Forbidden("This app has been disabled.", code="app_disabled")
    # `owner_workspace_id` says who wrote it. Until review publishes the app it
    # is installable only there; once published, everywhere.
    if (
        app_row.status != AppStatus.PUBLISHED.value
        and app_row.owner_workspace_id != workspace_id
    ):
        raise Forbidden(
            "This app has not been published yet.", code="app_not_published"
        )

    requested = set(app_row.requested_scopes)
    if granted_scopes is None:
        final_scopes = sorted(requested)
    else:
        asked = {s.value for s in granted_scopes}
        # Cannot grant a scope the manifest never asked for.
        extra = asked - requested
        if extra:
            raise Conflict(
                "These scopes are not requested by the app's manifest.",
                code="scope_not_requested",
                details={"scopes": sorted(extra)},
            )
        final_scopes = sorted(asked)

    existing = await db.scalar(
        select(AppInstallation)
        .where(
            AppInstallation.workspace_id == workspace_id,
            AppInstallation.app_id == app_row.id,
        )
        .limit(1)
    )
    if existing is not None:
        # Re-installing is an upgrade: refresh scopes, config and version.
        existing.granted_scopes = final_scopes
        existing.installed_version = app_row.version
        existing.is_enabled = True
        if config is not None:
            existing.config = config
        await db.flush()
        return existing

    installation = AppInstallation(
        id=new_ulid(),
        workspace_id=workspace_id,
        app_id=app_row.id,
        installed_by=actor.id,
        granted_scopes=final_scopes,
        config=config or {},
        is_pinned=pin_to_dock,
        installed_version=app_row.version,
    )
    db.add(installation)

    # Every installation gets a bot identity so its messages are attributable.
    if app_row.kind in (AppKind.BOT.value, AppKind.BOTH.value):
        installation.bot_user_id = (
            await _ensure_bot_user(db, app_row=app_row, workspace_id=workspace_id)
        ).id

    await db.flush()
    log.info(
        "app.installed",
        app_id=app_row.id,
        workspace_id=workspace_id,
        installation_id=installation.id,
        scopes=final_scopes,
    )
    return installation


async def _ensure_bot_user(db: AsyncSession, *, app_row: App, workspace_id: str) -> User:
    from app.services.workspaces import add_member

    email = f"bot+{app_row.slug}.{workspace_id.lower()}@apps.llack.internal"
    existing = await db.scalar(select(User).where(User.email == email).limit(1))
    if existing is not None:
        return existing

    handle = await allocate_handle(db, f"{app_row.slug}-bot"[:56])
    bot = User(
        id=new_ulid(),
        email=email,
        password_hash=None,  # Bots never sign in with a password.
        display_name=app_row.name,
        handle=handle,
        avatar_url=app_row.icon_url,
        is_bot=True,
    )
    db.add(bot)
    await db.flush()
    await add_member(db, workspace_id=workspace_id, user_id=bot.id, role=WorkspaceRole.GUEST)
    return bot


async def require_installation_control(
    db: AsyncSession, *, installation: AppInstallation, actor: User
) -> None:
    """Who may change or remove an installation.

    Admins always. For a link app — which holds no permissions — the person
    who added it may also rename or remove it, so a designer can manage the
    Figma tile they put in the dock without filing a request.
    """
    membership = await require_membership(
        db, workspace_id=installation.workspace_id, user_id=actor.id
    )
    if membership.role_enum.at_least(WorkspaceRole.ADMIN):
        return
    is_link = installation.app.kind == AppKind.LINK.value
    if is_link and installation.installed_by == actor.id:
        return
    raise Forbidden(
        "Only a workspace admin (or, for a link app, the person who added it) can do this.",
        code="insufficient_role",
        details={"required_role": WorkspaceRole.ADMIN.value, "your_role": membership.role},
    )


async def uninstall_app(db: AsyncSession, *, installation: AppInstallation, actor: User) -> None:
    await require_installation_control(db, installation=installation, actor=actor)
    # Cascades to tokens and storage; the bot user is kept so its past messages
    # still render with a name and avatar.
    await db.delete(installation)
    await db.flush()
    log.info("app.uninstalled", installation_id=installation.id, actor_id=actor.id)


async def update_installation(
    db: AsyncSession,
    *,
    installation: AppInstallation,
    actor: User,
    config: dict[str, Any] | None = None,
    granted_scopes: list[AppScope] | None = None,
    is_enabled: bool | None = None,
    is_pinned: bool | None = None,
    sort_order: int | None = None,
    name: str | None = None,
    icon_url: str | None = None,
) -> AppInstallation:
    await require_installation_control(db, installation=installation, actor=actor)
    if name is not None or icon_url is not None:
        if installation.app.kind != AppKind.LINK.value:
            raise ValidationFailed(
                "Only a link app can be renamed here; other apps take their name from"
                " the manifest.",
                code="not_a_link_app",
            )
        if name is not None:
            installation.app.name = name.strip()
        if icon_url is not None:
            installation.app.icon_url = icon_url or None
    if config is not None:
        installation.config = config
    if granted_scopes is not None:
        requested = set(installation.app.requested_scopes)
        asked = {s.value for s in granted_scopes}
        extra = asked - requested
        if extra:
            raise Conflict(
                "These scopes are not requested by the app's manifest.",
                code="scope_not_requested",
                details={"scopes": sorted(extra)},
            )
        installation.granted_scopes = sorted(asked)
    if is_enabled is not None:
        installation.is_enabled = is_enabled
    if is_pinned is not None:
        installation.is_pinned = is_pinned
    if sort_order is not None:
        installation.sort_order = sort_order
    await db.flush()
    return installation


# ── Bridge tokens (panel → backend) ─────────────────────────────────────────


def mint_bridge_token(
    *, installation: AppInstallation, acting_user_id: str, channel_id: str | None = None
) -> tuple[str, datetime]:
    """Short-lived token for a panel webview's SDK calls."""
    return create_access_token(
        subject=acting_user_id,
        token_type="app",
        ttl_seconds=BRIDGE_TOKEN_TTL_SECONDS,
        extra={
            "iid": installation.id,
            "aid": installation.app_id,
            "wid": installation.workspace_id,
            "scp": installation.granted_scopes,
            "cid": channel_id,
        },
    )


def decode_bridge_token(token: str) -> dict[str, Any]:
    payload = decode_access_token(token, expected_type="app")
    for claim in ("iid", "aid", "wid"):
        if not payload.get(claim):
            from app.core.errors import Unauthorized

            raise Unauthorized("Bridge token is malformed.", code="token_invalid")
    return payload


def require_scope(granted: list[str], scope: AppScope) -> None:
    if scope.value not in granted:
        raise Forbidden(
            f"This app was not granted the {scope.value} scope.",
            code="missing_scope",
            details={"required_scope": scope.value},
        )


# ── Long-lived server-to-server tokens ──────────────────────────────────────


async def create_app_token(
    db: AsyncSession,
    *,
    installation: AppInstallation,
    actor: User,
    name: str = "default",
    ttl_days: int | None = None,
) -> tuple[AppToken, str]:
    await require_membership(
        db,
        workspace_id=installation.workspace_id,
        user_id=actor.id,
        minimum_role=WorkspaceRole.ADMIN,
    )
    raw = f"llack_at_{new_token(32)}"
    token = AppToken(
        id=new_ulid(),
        installation_id=installation.id,
        name=name,
        token_hash=hash_token(raw),
        token_prefix=raw[:14],
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None,
    )
    db.add(token)
    await db.flush()
    return token, raw


async def resolve_app_token(db: AsyncSession, raw_token: str) -> AppInstallation:
    row = await db.scalar(
        select(AppToken).where(AppToken.token_hash == hash_token(raw_token)).limit(1)
    )
    if row is None or row.revoked_at is not None:
        from app.core.errors import Unauthorized

        raise Unauthorized("App token is invalid.", code="app_token_invalid")
    if row.expires_at is not None and row.expires_at < datetime.now(UTC):
        from app.core.errors import Unauthorized

        raise Unauthorized("App token has expired.", code="app_token_expired")

    installation = await db.get(AppInstallation, row.installation_id)
    if installation is None or not installation.is_enabled:
        raise NotFound("This app is not installed.", code="installation_not_found")

    row.last_used_at = datetime.now(UTC)
    return installation


# ── Per-installation key/value storage ──────────────────────────────────────


async def storage_get(
    db: AsyncSession, *, installation_id: str, scope_key: str, key: str
) -> AppStorageItem | None:
    return await db.scalar(
        select(AppStorageItem)
        .where(
            AppStorageItem.installation_id == installation_id,
            AppStorageItem.scope_key == scope_key,
            AppStorageItem.key == key,
        )
        .limit(1)
    )


async def storage_set(
    db: AsyncSession, *, installation_id: str, scope_key: str, key: str, value: Any
) -> AppStorageItem:
    item = await storage_get(
        db, installation_id=installation_id, scope_key=scope_key, key=key
    )
    if item is None:
        item = AppStorageItem(
            id=new_ulid(),
            installation_id=installation_id,
            scope_key=scope_key,
            key=key,
            value=value,
        )
        db.add(item)
    else:
        item.value = value
    await db.flush()
    return item


async def storage_list(
    db: AsyncSession, *, installation_id: str, scope_key: str, prefix: str | None = None
) -> list[AppStorageItem]:
    stmt = select(AppStorageItem).where(
        AppStorageItem.installation_id == installation_id,
        AppStorageItem.scope_key == scope_key,
    )
    if prefix:
        stmt = stmt.where(AppStorageItem.key.startswith(prefix))
    return list((await db.scalars(stmt.order_by(AppStorageItem.key))).all())


async def storage_delete(
    db: AsyncSession, *, installation_id: str, scope_key: str, key: str
) -> bool:
    item = await storage_get(
        db, installation_id=installation_id, scope_key=scope_key, key=key
    )
    if item is None:
        return False
    await db.delete(item)
    await db.flush()
    return True
