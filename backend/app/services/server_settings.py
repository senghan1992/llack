"""Runtime server settings — today, the SMTP relay.

Resolution order for outbound mail:

1. what an operator saved in the admin UI (`server_settings` row),
2. the `LLACK_SMTP_*` environment variables,
3. nothing → the console backend (the mail body goes to the server log).

The stored password never leaves the server: reads return `password_set`
instead, and an update with `password=None` keeps the existing one, so the
form can be edited without retyping the secret. It is stored as the DB row's
plain value — the database also holds every message on this server, so a
reader of the DB has already won; what this protects against is the API and
the UI ever echoing it back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.server import ServerSetting

SMTP_KEY = "smtp"


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    starttls: bool
    mail_from: str

    @property
    def configured(self) -> bool:
        return bool(self.host)


def _env_config() -> SmtpConfig:
    return SmtpConfig(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        starttls=settings.smtp_starttls,
        mail_from=settings.mail_from,
    )


def _from_stored(stored: dict[str, Any]) -> SmtpConfig:
    return SmtpConfig(
        host=str(stored.get("host", "")),
        port=int(stored.get("port", 587)),
        username=str(stored.get("username", "")),
        password=str(stored.get("password", "")),
        starttls=bool(stored.get("starttls", True)),
        mail_from=str(stored.get("mail_from", "")) or settings.mail_from,
    )


async def get_stored_smtp(db: AsyncSession) -> dict[str, Any] | None:
    row = await db.get(ServerSetting, SMTP_KEY)
    return dict(row.value) if row is not None else None


async def set_smtp(
    db: AsyncSession,
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    starttls: bool,
    mail_from: str,
) -> dict[str, Any]:
    """Save the relay. `password=None` keeps the already-stored secret;
    an empty `host` clears the whole override (env/console take over)."""
    row = await db.get(ServerSetting, SMTP_KEY)

    if not host.strip():
        if row is not None:
            await db.delete(row)
            await db.flush()
        return {}

    previous = dict(row.value) if row is not None else {}
    value = {
        "host": host.strip(),
        "port": port,
        "username": username.strip(),
        "password": previous.get("password", "") if password is None else password,
        "starttls": starttls,
        "mail_from": mail_from.strip(),
    }
    if row is None:
        db.add(ServerSetting(key=SMTP_KEY, value=value))
    else:
        row.value = value
    await db.flush()
    return value


async def resolve_smtp(db: AsyncSession) -> SmtpConfig:
    stored = await get_stored_smtp(db)
    if stored and stored.get("host"):
        return _from_stored(stored)
    return _env_config()


def public_view(stored: dict[str, Any] | None) -> dict[str, Any]:
    """What the admin UI may see. The password is a boolean here, forever."""
    if stored and stored.get("host"):
        return {
            "source": "database",
            "host": stored.get("host", ""),
            "port": int(stored.get("port", 587)),
            "username": stored.get("username", ""),
            "starttls": bool(stored.get("starttls", True)),
            "mail_from": stored.get("mail_from", ""),
            "password_set": bool(stored.get("password")),
        }
    env = _env_config()
    return {
        "source": "env" if env.configured else "none",
        "host": env.host,
        "port": env.port,
        "username": env.username,
        "starttls": env.starttls,
        "mail_from": env.mail_from,
        "password_set": bool(env.password),
    }
