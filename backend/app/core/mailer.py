"""Outbound mail — the smallest thing that can send a reset code.

Two backends behind one function:

- **SMTP** when `LLACK_SMTP_HOST` is set: stdlib `smtplib` run in a worker
  thread (no new dependency for one email a day). STARTTLS by default.
- **Console** otherwise: the message is logged. That makes dev and tests work
  without a mail server, and makes "메일이 안 와요" debuggable — the code is
  in the server log, so an operator can read it out while SMTP is being set
  up. This is a fallback, not the plan.

Deliberately not a queue: a reset code is the only mail this product sends,
and a synchronous failure should surface to the caller, not rot in a retry
table nobody watches.
"""

from __future__ import annotations

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import anyio

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _send_smtp(to: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr((str(Header("Llack", "utf-8")), settings.mail_from))
    message["To"] = to

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.sendmail(settings.mail_from, [to], message.as_string())


async def send_email(to: str, subject: str, body: str) -> None:
    if settings.smtp_host:
        await anyio.to_thread.run_sync(_send_smtp, to, subject, body)
        log.info("mail.sent", to=to, subject=subject)
    else:
        # Console backend: dev, tests, and the operator's escape hatch.
        log.info("mail.console", to=to, subject=subject, body=body)
