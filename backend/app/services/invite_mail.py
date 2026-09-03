"""Invitation e-mails.

The invite link used to be copied out of the admin screen and pasted into a
chat or a mail by hand. When a relay is configured (환경설정 → 메일, or the
LLACK_SMTP_* fallback) the server mails it itself. The web address comes from
`LLACK_PUBLIC_WEB_URL`; failing that, from the request's Origin — the very
browser the admin is using — and failing that, the invite is created but not
mailed, and the UI says so (`emailed: false`).
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mailer
from app.core.config import settings
from app.core.logging import get_logger
from app.services.server_settings import resolve_smtp

log = get_logger(__name__)


def public_web_url(request: Request | None) -> str | None:
    if settings.public_web_url:
        return settings.public_web_url.rstrip("/")
    origin = request.headers.get("origin") if request is not None else None
    if origin and origin.startswith(("http://", "https://")):
        return origin.rstrip("/")
    return None


def invite_link(base: str, token: str) -> str:
    return f"{base}/?invite={token}"


async def send_invite(
    db: AsyncSession,
    *,
    request: Request | None,
    to: str,
    token: str,
    workspace_name: str,
    inviter_name: str,
    expires_days: int,
) -> bool:
    """Mail the link. True when it was actually handed to a relay."""
    base = public_web_url(request)
    if base is None:
        log.info("invite.mail_skipped", reason="no_public_web_url", to=to)
        return False
    config = await resolve_smtp(db)
    if not config.configured:
        log.info("invite.mail_skipped", reason="smtp_not_configured", to=to)
        return False
    link = invite_link(base, token)
    subject = f"[Llack] {inviter_name} 님이 {workspace_name} 워크스페이스에 초대했습니다"
    body = (
        f"{inviter_name} 님이 Llack 의 {workspace_name} 워크스페이스에 초대했습니다.\n\n"
        f"아래 링크를 열어 가입하면 바로 팀에 합류합니다. "
        f"이미 계정이 있으면 같은 링크로 로그인하세요.\n\n"
        f"{link}\n\n"
        f"이 링크는 {expires_days}일 뒤 만료되며, 이 주소({to})로만 쓸 수 있습니다. "
        f"모르는 초대라면 무시해도 됩니다.\n"
    )
    try:
        await mailer.send_email(to, subject, body, config)
    except Exception:  # noqa: BLE001
        log.exception("invite.mail_failed", to=to)
        return False
    return True
