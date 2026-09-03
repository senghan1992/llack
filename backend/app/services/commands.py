"""Slash commands: `/remind`, `/dnd`, `/topic` … and whatever installed apps add.

A command is an instruction, not a message: nothing is posted unless the
command itself posts. Built-ins run here; an app's command is forwarded to its
`command_url` as a signed POST (services/outbound.py) and its answer either
comes back to the caller alone (`ephemeral`) or is posted as the app's bot.

Every reply is Korean and says what happened — `/remind` confirms the time it
resolved to, `/dnd` how long, an unknown command what the usage is — because
a command that silently does the wrong thing is worse than no command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MessageKind
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.models.app import App, AppInstallation, WebhookDelivery
from app.models.channel import Channel, ChannelMember
from app.models.user import User
from app.schemas.user import UserBrief
from app.services import outbound
from app.services import saved as saved_service
from app.services.blocks import validate_blocks

log = get_logger(__name__)

RESPONSE_URL_TTL = timedelta(minutes=30)


@dataclass(slots=True)
class CommandResult:
    handled: bool
    text: str | None = None
    ephemeral: bool = True
    blocks: list[dict[str, Any]] | None = None
    # Set when the command created a message the caller should fan out.
    posted_message_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        response = (
            None
            if self.text is None
            else {"text": self.text, "ephemeral": self.ephemeral, "blocks": self.blocks}
        )
        return {"handled": self.handled, "response": response}


BUILTINS: list[dict[str, Any]] = [
    {
        "command": "/remind",
        "description": "저장하고 정한 시각에 알려드립니다",
        "usage": "/remind me in 30m 내용 · /remind me at 15:00 내용",
    },
    {"command": "/dnd", "description": "알림을 잠시 멈춥니다", "usage": "/dnd 30m · 2h · off"},
    {"command": "/topic", "description": "채널 주제를 바꿉니다", "usage": "/topic 새 주제"},
    {"command": "/leave", "description": "이 채널에서 나갑니다", "usage": "/leave"},
    {"command": "/mute", "description": "이 채널 알림을 끄거나 켭니다", "usage": "/mute"},
    {"command": "/shrug", "description": "¯\\_(ツ)_/¯ 를 붙여 보냅니다", "usage": "/shrug 내용"},
]

DURATION_RE = re.compile(r"^(\d{1,3})\s*(m|min|분|h|시간|d|일|w|주)$", re.IGNORECASE)
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_duration(token: str) -> timedelta | None:
    match = DURATION_RE.match(token.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("m", "min", "분"):
        return timedelta(minutes=amount)
    if unit in ("h", "시간"):
        return timedelta(hours=amount)
    if unit in ("d", "일"):
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def resolve_at(hhmm: str, *, timezone: str, now: datetime | None = None) -> datetime | None:
    """`at 15:00` in the user's zone — today if still ahead, else tomorrow."""
    match = TIME_RE.match(hhmm.strip())
    if not match:
        return None
    now = now or datetime.now(UTC)
    try:
        zone = ZoneInfo(timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    local_now = now.astimezone(zone)
    target = datetime.combine(
        local_now.date(), time(int(match.group(1)), int(match.group(2))), tzinfo=zone
    )
    if target <= local_now:
        target += timedelta(days=1)
    return target.astimezone(UTC)


def _fmt_local(when: datetime, timezone: str) -> str:
    try:
        local = when.astimezone(ZoneInfo(timezone or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        local = when
    return local.strftime("%m/%d %H:%M")


# ── Listing ─────────────────────────────────────────────────────────────────


async def list_commands(db: AsyncSession, *, workspace_id: str) -> list[dict[str, Any]]:
    out = [{**spec, "app": None, "builtin": True} for spec in BUILTINS]
    rows = await db.execute(
        select(App, AppInstallation)
        .join(AppInstallation, AppInstallation.app_id == App.id)
        .where(
            AppInstallation.workspace_id == workspace_id,
            AppInstallation.is_enabled.is_(True),
        )
        .order_by(App.name)
    )
    taken = {spec["command"] for spec in BUILTINS}
    for app_row, _installation in rows.all():
        for spec in app_row.slash_commands or []:
            command = spec.get("command")
            if not command or command in taken:
                continue
            taken.add(command)
            out.append(
                {
                    "command": command,
                    "description": spec.get("description"),
                    "usage": spec.get("usage") or spec.get("usage_hint"),
                    "app": {"id": app_row.id, "name": app_row.name, "icon_url": app_row.icon_url},
                    "builtin": False,
                }
            )
    return out


# ── Running ─────────────────────────────────────────────────────────────────


async def run(
    db: AsyncSession,
    *,
    channel: Channel,
    membership: ChannelMember,
    user: User,
    text: str,
    response_base: str,
) -> CommandResult:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return CommandResult(False, "명령은 / 로 시작해야 합니다.")
    head, _, rest = stripped.partition(" ")
    command = head.lower()
    args = rest.strip()

    if command == "/remind":
        return await _remind(db, channel=channel, user=user, args=args)
    if command == "/dnd":
        return await _dnd(db, user=user, args=args)
    if command == "/topic":
        return await _topic(db, channel=channel, args=args)
    if command == "/leave":
        return await _leave(db, channel=channel, user=user)
    if command == "/mute":
        return await _mute(db, membership=membership)
    if command == "/shrug":
        return await _shrug(db, channel=channel, user=user, args=args)

    return await _app_command(
        db,
        channel=channel,
        user=user,
        command=command,
        text=args,
        response_base=response_base,
    )


async def _remind(db: AsyncSession, *, channel: Channel, user: User, args: str) -> CommandResult:
    usage = "사용법: /remind me in 30m 내용 · /remind me at 15:00 내용"
    tokens = args.split()
    if len(tokens) >= 1 and tokens[0].lower() in ("me", "나", "나에게"):
        tokens = tokens[1:]
    when: datetime | None = None
    body_tokens: list[str] = []
    if len(tokens) >= 2 and tokens[0].lower() == "in":
        delta = parse_duration(tokens[1])
        if delta is None:
            return CommandResult(False, f"기간을 이해하지 못했습니다: {tokens[1]}. {usage}")
        when = datetime.now(UTC) + delta
        body_tokens = tokens[2:]
    elif len(tokens) >= 2 and tokens[0].lower() == "at":
        when = resolve_at(tokens[1], timezone=user.timezone)
        if when is None:
            return CommandResult(False, f"시각은 HH:MM 으로 적어주세요: {tokens[1]}. {usage}")
        body_tokens = tokens[2:]
    else:
        return CommandResult(False, usage)
    note = " ".join(body_tokens).strip()
    if not note:
        return CommandResult(False, f"무엇을 알려드릴지 적어주세요. {usage}")

    # The note lives in the note-to-self DM, never in the channel it was typed in.
    from app.services import messages as message_service
    from app.services.channels import open_self_dm

    self_dm = await open_self_dm(db, workspace_id=channel.workspace_id, user=user)
    message, _ = await message_service.create_message(
        db, channel=self_dm, author=user, body=note, kind=MessageKind.USER
    )
    await saved_service.save(db, user_id=user.id, message_id=message.id, note=None, remind_at=when)
    return CommandResult(
        True, f"⏰ {_fmt_local(when, user.timezone)} 에 알려드릴게요: {note}", ephemeral=True
    )


async def _dnd(db: AsyncSession, *, user: User, args: str) -> CommandResult:
    token = args.split()[0].lower() if args else ""
    if token in ("off", "해제", "끝"):
        user.notify_paused_until = None
        await db.flush()
        return CommandResult(True, "알림을 다시 켰습니다.")
    delta = parse_duration(token) if token else None
    if delta is None:
        return CommandResult(False, "사용법: /dnd 30m · /dnd 2h · /dnd off")
    until = datetime.now(UTC) + delta
    user.notify_paused_until = until
    await db.flush()
    return CommandResult(
        True, f"🌙 {_fmt_local(until, user.timezone)} 까지 알림을 멈춥니다. 배지는 그대로 셉니다."
    )


async def _topic(db: AsyncSession, *, channel: Channel, args: str) -> CommandResult:
    if channel.kind in ("dm", "group_dm"):
        return CommandResult(False, "다이렉트 메시지에는 주제가 없습니다.")
    if not args:
        return CommandResult(False, "사용법: /topic 새 주제")
    channel.topic = args[:400]
    await db.flush()
    return CommandResult(True, f"주제를 바꿨습니다: {channel.topic}")


async def _leave(db: AsyncSession, *, channel: Channel, user: User) -> CommandResult:
    from app.services.channels import leave_channel

    if channel.kind in ("dm", "group_dm"):
        return CommandResult(
            False, "다이렉트 메시지는 나갈 수 없습니다. 사이드바에서 숨길 수 있습니다."
        )
    await leave_channel(db, channel=channel, user_id=user.id)
    return CommandResult(True, f"#{channel.name} 에서 나갔습니다.")


async def _mute(db: AsyncSession, *, membership: ChannelMember) -> CommandResult:
    membership.is_muted = not membership.is_muted
    await db.flush()
    return CommandResult(
        True,
        "이 채널 알림을 껐습니다. 다시 /mute 하면 켜집니다."
        if membership.is_muted
        else "이 채널 알림을 켰습니다.",
    )


async def _shrug(db: AsyncSession, *, channel: Channel, user: User, args: str) -> CommandResult:
    from app.services import messages as message_service

    body = f"{args} ¯\\_(ツ)_/¯".strip()
    message, _ = await message_service.create_message(
        db, channel=channel, author=user, body=body, kind=MessageKind.USER
    )
    return CommandResult(True, None, posted_message_id=message.id)


async def _app_command(
    db: AsyncSession,
    *,
    channel: Channel,
    user: User,
    command: str,
    text: str,
    response_base: str,
) -> CommandResult:
    rows = await db.execute(
        select(App, AppInstallation)
        .join(AppInstallation, AppInstallation.app_id == App.id)
        .where(
            AppInstallation.workspace_id == channel.workspace_id,
            AppInstallation.is_enabled.is_(True),
        )
    )
    match: tuple[App, AppInstallation] | None = None
    for app_row, installation in rows.all():
        if any(spec.get("command") == command for spec in app_row.slash_commands or []):
            match = (app_row, installation)
            break
    if match is None:
        return CommandResult(
            False, f"{command} 는 모르는 명령입니다. / 를 치면 쓸 수 있는 명령이 보입니다."
        )
    app_row, installation = match
    if not app_row.command_url or not app_row.app_secret:
        return CommandResult(False, f"{app_row.name} 앱이 명령을 받을 주소를 등록하지 않았습니다.")

    delivery = WebhookDelivery(
        id=new_ulid(),
        app_id=app_row.id,
        installation_id=installation.id,
        kind="command",
        event=command,
        payload={"text": text, "user_id": user.id, "channel_id": channel.id},
        status="pending",
        channel_id=channel.id,
        response_nonce=new_ulid(),
        expires_at=datetime.now(UTC) + RESPONSE_URL_TTL,
    )
    db.add(delivery)
    await db.flush()

    outcome = await outbound.post_signed(
        app_row.command_url,
        secret=app_row.app_secret,
        payload={
            "command": command,
            "text": text,
            "user": UserBrief.model_validate(user).model_dump(),
            "channel": {"id": channel.id, "name": channel.name},
            "workspace_id": channel.workspace_id,
            "response_url": (
                f"{response_base}/api/v1/apps/{app_row.id}/respond/{delivery.response_nonce}"
            ),
        },
    )
    delivery.attempts = 1
    delivery.last_status_code = outcome.status_code
    delivery.status = "ok" if outcome.ok else "failed"
    delivery.last_error = None if outcome.ok else (outcome.error or "unknown")[:500]
    await db.flush()
    if not outcome.ok:
        return CommandResult(
            False, f"{app_row.name} 앱이 응답하지 않았습니다. 잠시 후 다시 시도해주세요."
        )

    body = outcome.body or {}
    reply_text = body.get("text") if isinstance(body.get("text"), str) else None
    blocks = validate_blocks(body.get("blocks")) if isinstance(body.get("blocks"), list) else None
    ephemeral = bool(body.get("ephemeral", True))
    if reply_text is None and blocks is None:
        return CommandResult(True, None)
    if ephemeral:
        return CommandResult(True, reply_text or "", ephemeral=True, blocks=blocks)

    from app.services import messages as message_service

    bot = await db.get(User, installation.bot_user_id) if installation.bot_user_id else None
    message, _ = await message_service.create_message(
        db,
        channel=channel,
        author=bot or user,
        body=reply_text or "",
        blocks=blocks,
        app_id=app_row.id,
        kind=MessageKind.APP,
    )
    return CommandResult(True, None, posted_message_id=message.id)
