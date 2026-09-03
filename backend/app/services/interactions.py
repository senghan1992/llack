"""Block interactions: a button or select inside an app's message was used.

The click is forwarded to the app's `interaction_url` as a signed POST. The
app may answer with `replace_original` (the message body/blocks change for
everyone, announced as MESSAGE_UPDATED) and/or `ephemeral` (a line only the
person who clicked sees). The dispatch is recorded as a delivery row so the
author can see clicks arriving — or not — in the console.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.core.ids import new_ulid
from app.models.app import App, AppInstallation, WebhookDelivery
from app.models.channel import Channel
from app.models.message import Message
from app.models.user import User
from app.schemas.user import UserBrief
from app.services import outbound
from app.services.blocks import validate_blocks


async def dispatch(
    db: AsyncSession,
    *,
    message: Message,
    channel: Channel,
    user: User,
    action_id: str,
    value: str | None,
    response_base: str,
) -> tuple[bool, str | None, bool]:
    """Forward the click. Returns (handled, ephemeral_text, message_changed).

    The caller commits and, when `message_changed`, emits MESSAGE_UPDATED.
    """
    if message.app_id is None:
        raise Conflict("This message has no interactive app behind it.", code="not_interactive")
    app_row = await db.get(App, message.app_id)
    if app_row is None or not app_row.interaction_url or not app_row.app_secret:
        raise Conflict("This app does not handle interactions.", code="not_interactive")

    installation = await db.scalar(
        select(AppInstallation)
        .where(
            AppInstallation.workspace_id == channel.workspace_id,
            AppInstallation.app_id == app_row.id,
        )
        .limit(1)
    )

    delivery = WebhookDelivery(
        id=new_ulid(),
        app_id=app_row.id,
        installation_id=installation.id if installation is not None else None,
        kind="interaction",
        event="block_action",
        payload={"action_id": action_id, "message_id": message.id, "user_id": user.id},
        status="pending",
        channel_id=channel.id,
    )
    db.add(delivery)
    await db.flush()

    outcome = await outbound.post_signed(
        app_row.interaction_url,
        secret=app_row.app_secret,
        payload={
            "type": "block_action",
            "action_id": action_id,
            "value": value,
            "user": UserBrief.model_validate(user).model_dump(),
            "channel": {"id": channel.id, "name": channel.name},
            "workspace_id": channel.workspace_id,
            "message_id": message.id,
            "message": {"body": message.body, "blocks": message.blocks},
            "response_url": f"{response_base}/api/v1/apps/{app_row.id}/respond/{delivery.id}",
        },
    )
    delivery.attempts = 1
    delivery.last_status_code = outcome.status_code
    delivery.status = "ok" if outcome.ok else "failed"
    delivery.last_error = None if outcome.ok else (outcome.error or "unknown")[:500]
    if not outcome.ok:
        await db.flush()
        return False, "앱이 응답하지 않았습니다. 잠시 후 다시 시도해주세요.", False

    body: dict[str, Any] = outcome.body or {}
    changed = False
    replace = body.get("replace_original")
    if isinstance(replace, dict):
        text = replace.get("text")
        blocks = replace.get("blocks")
        if isinstance(text, str):
            message.body = text[:40_000]
        if blocks is not None:
            # An app may keep the server's unfurl card when it rewrites its
            # own blocks, so the card is allowed through here.
            message.blocks = validate_blocks(
                blocks if isinstance(blocks, list) else None, allow_unfurl=True
            )
        changed = True
    ephemeral = body.get("ephemeral")
    ephemeral_text = None
    if isinstance(ephemeral, dict) and isinstance(ephemeral.get("text"), str):
        ephemeral_text = ephemeral["text"][:4000]
    elif isinstance(ephemeral, str):
        ephemeral_text = ephemeral[:4000]
    await db.flush()
    return True, ephemeral_text, changed
