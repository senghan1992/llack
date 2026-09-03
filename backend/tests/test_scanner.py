"""Attachment scanning against a fake clamd."""

from __future__ import annotations

import asyncio
import hashlib
import struct
from collections.abc import AsyncIterator

import pytest

from app.api.v1 import files as files_api
from app.core.config import settings
from app.services import scanner
from tests.conftest import Actor
from tests.test_channels import _join_workspace


async def _fake_clamd() -> tuple[asyncio.AbstractServer, int]:
    """Speaks just enough INSTREAM: FOUND when the payload contains EICAR."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        command = await reader.readuntil(b"\0")
        assert command == b"zINSTREAM\0"
        payload = bytearray()
        while True:
            (length,) = struct.unpack("!I", await reader.readexactly(4))
            if length == 0:
                break
            payload += await reader.readexactly(length)
        infected = b"EICAR" in payload
        verdict = b"stream: Eicar-Test-Signature FOUND\0" if infected else b"stream: OK\0"
        writer.write(verdict)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


@pytest.fixture
async def clamd(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    server, port = await _fake_clamd()
    monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings, "clamav_port", port)
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


async def _upload_bytes(actor: Actor, workspace: dict, name: str, data: bytes) -> dict:
    ticket = await actor.post(
        f"/workspaces/{workspace['id']}/files",
        json={
            "filename": name,
            "mime_type": "application/octet-stream",
            "size_bytes": len(data),
            "checksum_sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert ticket.status_code == 201, ticket.text
    path = ticket.json()["upload_url"].removeprefix("/api/v1")
    uploaded = await actor.put(path, content=data)
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()


async def test_without_a_scanner_files_are_skipped(alice: Actor, workspace: dict) -> None:
    file = await _upload_bytes(alice, workspace, "plain.bin", b"hello")
    assert file["scan_status"] == "skipped"
    await files_api.drain_background()
    assert (await alice.get(f"/files/{file['id']}")).json()["scan_status"] == "skipped"


async def test_clean_files_pass_and_infected_files_are_quarantined(
    alice: Actor, bob: Actor, workspace: dict, clamd: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _join_workspace(alice, bob, workspace)
    notified: list[tuple[list[str], str, dict]] = []

    async def capture(user_ids, event, data, **_kwargs):  # noqa: ANN001, ANN003
        notified.append((user_ids, event, data))

    monkeypatch.setattr(scanner, "emit_to_users", capture)

    clean = await _upload_bytes(alice, workspace, "report.bin", b"quarterly numbers")
    assert clean["scan_status"] == "pending"
    await files_api.drain_background()
    assert (await alice.get(f"/files/{clean['id']}")).json()["scan_status"] == "clean"

    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"
    bad = await _upload_bytes(alice, workspace, "invoice.exe", eicar)
    await files_api.drain_background()

    # Gone for everyone, with the reason, not a bare 404.
    gone = await alice.get(f"/files/{bad['id']}/download")
    assert gone.status_code == 410
    assert gone.json()["error"]["code"] == "file_quarantined"
    assert (await bob.get(f"/files/{bad['id']}")).status_code == 410

    # Cannot be attached to a message any more.
    general = next(
        c
        for c in (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()
        if c["name"] == "general"
    )
    attach = await alice.post(
        f"/channels/{general['id']}/messages", json={"body": "첨부", "file_ids": [bad["id"]]}
    )
    assert attach.status_code == 410
    assert attach.json()["error"]["code"] == "file_quarantined"

    # The uploader was told, and the act was audited as the system's.
    assert notified and notified[-1][0] == [alice.id]
    assert notified[-1][2]["kind"] == "quarantine"
    assert notified[-1][2]["title"] == "첨부 파일이 차단되었습니다"
    audit = (
        await alice.get(f"/workspaces/{workspace['id']}/audit?action=file.quarantined")
    ).json()
    assert len(audit["items"]) == 1
    assert audit["items"][0]["actor"] is None
    assert audit["items"][0]["details"]["signature"] == "Eicar-Test-Signature"
    assert audit["items"][0]["target_label"] == "invoice.exe"


async def test_an_unreachable_scanner_marks_error_not_clean(
    alice: Actor, workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings, "clamav_port", 1)  # nothing listens here
    monkeypatch.setattr(settings, "clamav_timeout_seconds", 1.0)
    file = await _upload_bytes(alice, workspace, "x.bin", b"data")
    await files_api.drain_background()
    assert (await alice.get(f"/files/{file['id']}")).json()["scan_status"] == "error"
    # Still downloadable: an outage of the scanner is not evidence of malware.
    assert (await alice.get(f"/files/{file['id']}/download")).status_code == 200
