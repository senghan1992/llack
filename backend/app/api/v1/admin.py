"""Server administration — runtime settings an operator edits from the UI.

Today: the SMTP relay. Guarded by `ServerAdmin` (a workspace owner or a
service admin) — these settings affect every workspace on the server, so a
workspace *admin* is deliberately not enough.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Request
from pydantic import EmailStr, Field

from app.api.deps import DbSession, ServerAdmin
from app.core.mailer import send_via_smtp
from app.schemas.common import Payload
from app.services import audit, partitions
from app.services import server_settings as server_settings_service
from app.services.server_settings import SmtpConfig

router = APIRouter(prefix="/admin", tags=["admin"])


class SmtpSettingsRequest(Payload):
    host: str = Field(max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    # None = keep the stored secret; the form can be edited without retyping.
    password: str | None = Field(default=None, max_length=512)
    starttls: bool = True
    mail_from: EmailStr


@router.get("/smtp", response_model=dict)
async def get_smtp(db: DbSession, _admin: ServerAdmin) -> dict:
    """The current relay, password redacted to a boolean."""
    stored = await server_settings_service.get_stored_smtp(db)
    return server_settings_service.public_view(stored)


@router.put("/smtp", response_model=dict)
async def put_smtp(
    payload: SmtpSettingsRequest, db: DbSession, admin: ServerAdmin, request: Request
) -> dict:
    """Save the relay. An empty host clears the override (env/console win)."""
    stored = await server_settings_service.set_smtp(
        db,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        starttls=payload.starttls,
        mail_from=str(payload.mail_from),
    )
    # Server-wide, so no workspace: owners see it in every workspace's log.
    await audit.record(
        db,
        workspace_id=None,
        actor=admin,
        action="smtp.updated",
        target_type="server",
        target_label=payload.host.strip() or "(cleared)",
        details={
            "host": payload.host.strip(),
            "port": payload.port,
            "username": payload.username.strip(),
            "starttls": payload.starttls,
            "mail_from": str(payload.mail_from),
            "password_changed": payload.password is not None,
        },
        request=request,
    )
    await db.commit()
    return server_settings_service.public_view(stored or None)


class SmtpTestRequest(Payload):
    """Test with the *typed* values, before saving — password may be omitted
    to reuse the stored one."""

    host: str = Field(max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=512)
    starttls: bool = True
    mail_from: EmailStr


@router.post("/smtp/test", response_model=dict)
async def test_smtp(
    payload: SmtpTestRequest, db: DbSession, admin: ServerAdmin
) -> dict:
    """Send a test mail to the caller and report the relay's verdict.

    Failures come back as `{"ok": false, "error": …}` rather than a 500: a
    wrong port or password is the *expected* case on this endpoint, and the
    admin needs the SMTP error text to fix it.
    """
    password = payload.password
    if password is None:
        stored = await server_settings_service.get_stored_smtp(db)
        password = (stored or {}).get("password", "")

    config = SmtpConfig(
        host=payload.host.strip(),
        port=payload.port,
        username=payload.username.strip(),
        password=password,
        starttls=payload.starttls,
        mail_from=str(payload.mail_from),
    )
    if not config.configured:
        return {"ok": False, "error": "SMTP 호스트가 비어 있습니다."}

    try:
        await anyio.to_thread.run_sync(
            send_via_smtp,
            config,
            admin.email,
            "[Llack] SMTP 연결 테스트",
            "이 메일이 보인다면 SMTP 설정이 올바릅니다. 저장을 눌러 적용하세요.",
        )
    except Exception as exc:  # noqa: BLE001 — the error text is the product here
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "sent_to": admin.email}


@router.get("/partitions", response_model=dict)
async def get_partitions(db: DbSession, _admin: ServerAdmin) -> dict:
    """How `messages` is laid out on disk — Postgres monthly partitions.

    Operators use this to see which months exist, how big each is, and whether
    the default partition is empty (it should be; rows there mean the
    maintenance worker missed a month).
    """
    conn = await db.connection()
    dialect = conn.dialect.name
    partitioned = await partitions.is_partitioned(conn)
    rows = await partitions.list_partitions(conn) if partitioned else []
    return {
        "dialect": dialect,
        "partitioned": partitioned,
        "partitions": [
            {
                "name": row.name,
                "from_id": row.from_id,
                "to_id": row.to_id,
                "rows": row.rows,
                "bytes": row.bytes,
            }
            for row in rows
        ],
    }
