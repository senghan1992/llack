"""Outbound mail — the smallest thing that can send a reset code.

The relay is resolved per send (`services/server_settings.resolve_smtp`):
what an operator saved in the admin UI wins, the `LLACK_SMTP_*` environment
variables are the fallback, and with neither the **console backend** logs the
message. That last one makes dev and tests work without a mail server, and
makes "메일이 안 와요" debuggable — the code is in the server log, so an
operator can read it out while SMTP is being set up.

`smtplib` in a worker thread rather than a new async dependency: this product
sends a handful of mails a day, and a synchronous failure should surface to
the caller, not rot in a retry queue nobody watches.
"""

from __future__ import annotations

from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import TYPE_CHECKING

import anyio

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.server_settings import SmtpConfig

log = get_logger(__name__)


def send_via_smtp(config: SmtpConfig, to: str, subject: str, body: str) -> None:
    """Blocking SMTP send. Public so the admin "test mail" endpoint can call
    it with a not-yet-saved configuration."""
    import smtplib

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr((str(Header("Llack", "utf-8")), config.mail_from))
    message["To"] = to

    with smtplib.SMTP(config.host, config.port, timeout=15) as client:
        if config.starttls:
            client.starttls()
        if config.username:
            client.login(config.username, config.password)
        client.sendmail(config.mail_from, [to], message.as_string())


async def send_email(to: str, subject: str, body: str, config: SmtpConfig) -> None:
    if config.configured:
        await anyio.to_thread.run_sync(send_via_smtp, config, to, subject, body)
        log.info("mail.sent", to=to, subject=subject)
    else:
        # Console backend: dev, tests, and the operator's escape hatch.
        log.info("mail.console", to=to, subject=subject, body=body)
