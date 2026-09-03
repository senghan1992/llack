"""Event webhooks: telling an app what happened in the workspaces it lives in.

An app declares `event_webhook_url` and `events` in its manifest. When one of
those events happens in a workspace where the app is installed, a signed POST
goes out (see services/outbound.py for the signature). The first attempt is
immediate and off the request path — the person who sent the message never
waits for an app's server. Failures are retried by the `webhook_retry` worker
on a 30 s / 2 min / 10 min ladder, then marked failed. Every attempt is a row
the app author can read in the developer console, because "did Llack call me
at all?" is the first question they ask.

Events: message.created (not the app's own bot posts), reaction.added,
channel.member_joined, app.mention (a message that mentions the app's bot).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import workers
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.models.app import App, AppInstallation, WebhookDelivery
from app.services import outbound

log = get_logger(__name__)

RETRY_DELAYS_SECONDS = (30, 120, 600)
MAX_ATTEMPTS = len(RETRY_DELAYS_SECONDS)
SUPPORTED_EVENTS = frozenset(
    {"message.created", "reaction.added", "channel.member_joined", "app.mention", "ping"}
)

_background: set[asyncio.Task] = set()


async def subscribed(
    db: AsyncSession, *, workspace_id: str, event: str
) -> list[tuple[AppInstallation, App]]:
    rows = await db.execute(
        select(AppInstallation, App)
        .join(App, App.id == AppInstallation.app_id)
        .where(
            AppInstallation.workspace_id == workspace_id,
            AppInstallation.is_enabled.is_(True),
            App.event_webhook_url.isnot(None),
        )
    )
    return [
        (installation, app_row)
        for installation, app_row in rows.all()
        if event in (app_row.event_subscriptions or [])
    ]


def _envelope(delivery: WebhookDelivery, *, workspace_id: str | None) -> dict[str, Any]:
    return {
        "type": delivery.event,
        "delivery_id": delivery.id,
        "app_id": delivery.app_id,
        "installation_id": delivery.installation_id,
        "workspace_id": workspace_id,
        "sent_at": datetime.now(UTC).isoformat(),
        "data": delivery.payload,
    }


async def attempt(
    db: AsyncSession, *, delivery: WebhookDelivery, app_row: App, workspace_id: str | None
) -> WebhookDelivery:
    """One try. Updates status/attempts/next_attempt_at; the caller commits."""
    if not app_row.event_webhook_url or not app_row.app_secret:
        delivery.status = "failed"
        delivery.last_error = "앱에 웹훅 주소나 서명 비밀이 없습니다."
        delivery.next_attempt_at = None
        await db.flush()
        return delivery

    outcome = await outbound.post_signed(
        app_row.event_webhook_url,
        secret=app_row.app_secret,
        payload=_envelope(delivery, workspace_id=workspace_id),
    )
    delivery.attempts += 1
    delivery.last_status_code = outcome.status_code
    if outcome.ok:
        delivery.status = "ok"
        delivery.last_error = None
        delivery.next_attempt_at = None
    else:
        delivery.last_error = (outcome.error or "unknown")[:500]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
            delivery.next_attempt_at = None
        else:
            delivery.status = "pending"
            delay = RETRY_DELAYS_SECONDS[min(delivery.attempts, MAX_ATTEMPTS) - 1]
            delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
    await db.flush()
    return delivery


async def fan_out(
    event: str,
    *,
    workspace_id: str,
    payload: dict[str, Any],
    exclude_bot_user_ids: set[str] | None = None,
    mentioned_user_ids: list[str] | None = None,
) -> int:
    """Create and first-attempt deliveries for every subscribed installation.

    Runs on its own session (background). `exclude_bot_user_ids` keeps an app
    from being told about its own bot's message; `mentioned_user_ids` lets
    `message.created` also raise `app.mention` for the app whose bot was named.
    """
    from app.core.db import get_sessionmaker

    delivered = 0
    async with get_sessionmaker()() as db:
        try:
            targets = await subscribed(db, workspace_id=workspace_id, event=event)
            mention_targets: list[tuple[AppInstallation, App]] = []
            if event == "message.created" and mentioned_user_ids:
                mention_targets = [
                    pair
                    for pair in await subscribed(db, workspace_id=workspace_id, event="app.mention")
                    if pair[0].bot_user_id and pair[0].bot_user_id in mentioned_user_ids
                ]
            for kind_event, pairs in ((event, targets), ("app.mention", mention_targets)):
                for installation, app_row in pairs:
                    if exclude_bot_user_ids and installation.bot_user_id in exclude_bot_user_ids:
                        continue
                    delivery = WebhookDelivery(
                        id=new_ulid(),
                        app_id=app_row.id,
                        installation_id=installation.id,
                        kind="event",
                        event=kind_event,
                        payload=payload,
                        status="pending",
                    )
                    db.add(delivery)
                    await db.flush()
                    await attempt(db, delivery=delivery, app_row=app_row, workspace_id=workspace_id)
                    delivered += 1
            await db.commit()
        except Exception:  # noqa: BLE001
            log.exception("webhooks.fan_out_failed", event=event, workspace_id=workspace_id)
    return delivered


def schedule(
    event: str,
    *,
    workspace_id: str,
    payload: dict[str, Any],
    exclude_bot_user_ids: set[str] | None = None,
    mentioned_user_ids: list[str] | None = None,
) -> asyncio.Task | None:
    """Fire-and-forget fan-out; the request that caused the event returns now."""
    task = asyncio.create_task(
        fan_out(
            event,
            workspace_id=workspace_id,
            payload=payload,
            exclude_bot_user_ids=exclude_bot_user_ids,
            mentioned_user_ids=mentioned_user_ids,
        ),
        name=f"webhook:{event}",
    )
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def drain_background() -> None:
    """Wait for in-flight fan-outs. For tests and shutdown."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


async def retry_due(now: datetime | None = None) -> int:
    """Re-attempt every pending delivery whose time has come."""
    from app.core.db import get_sessionmaker

    now = now or datetime.now(UTC)
    retried = 0
    async with get_sessionmaker()() as db:
        rows = await db.execute(
            select(WebhookDelivery, App, AppInstallation)
            .join(App, App.id == WebhookDelivery.app_id)
            .outerjoin(AppInstallation, AppInstallation.id == WebhookDelivery.installation_id)
            .where(
                WebhookDelivery.status == "pending",
                WebhookDelivery.kind == "event",
                WebhookDelivery.next_attempt_at.isnot(None),
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(200)
        )
        for delivery, app_row, installation in rows.all():
            await attempt(
                db,
                delivery=delivery,
                app_row=app_row,
                workspace_id=installation.workspace_id if installation else None,
            )
            retried += 1
        await db.commit()
    if retried:
        log.info("webhooks.retried", count=retried)
    return retried


async def _webhook_retry() -> None:
    await retry_due()


workers.register("webhook_retry", 30, _webhook_retry)


async def test_delivery(
    db: AsyncSession, *, app_row: App, installation: AppInstallation | None
) -> WebhookDelivery:
    """One synchronous `ping` so the console can say "your endpoint answered"."""
    delivery = WebhookDelivery(
        id=new_ulid(),
        app_id=app_row.id,
        installation_id=installation.id if installation else None,
        kind="test",
        event="ping",
        payload={"message": "Llack 에서 보낸 테스트 이벤트입니다."},
        status="pending",
    )
    db.add(delivery)
    await db.flush()
    await attempt(
        db,
        delivery=delivery,
        app_row=app_row,
        workspace_id=installation.workspace_id if installation else None,
    )
    # A test is one shot: no retry ladder for a button the author just pressed.
    if delivery.status == "pending":
        delivery.status = "failed"
        delivery.next_attempt_at = None
        await db.flush()
    return delivery
