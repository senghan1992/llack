"""Uploads and downloads."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.file import File
from app.services.files import purge_orphan_files
from tests.conftest import API, auth, join_workspace, signup

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def test_upload_and_download(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("fil_")
    assert body["name"] == "design.png"
    assert body["mime"] == "image/png"
    assert body["size"] == len(PNG)
    assert body["url"] == f"{API}/files/{body['id']}"

    download = await client.get(body["url"], headers=headers)
    assert download.status_code == 200
    assert download.content == PNG


async def test_a_plain_document_can_be_shared(client: httpx.AsyncClient) -> None:
    """A team shares .txt and .csv files; refusing them is not company work."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["mime"] == "text/plain"


async def test_a_spoofed_type_does_not_survive(client: httpx.AsyncClient) -> None:
    """The browser says what it likes; the bytes decide what is stored."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("payload.png", PNG, "application/x-msdownload")},
    )
    assert response.status_code == 200
    assert response.json()["mime"] == "image/png"


async def test_an_executable_is_rejected(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("tool.bin", b"\x7fELF\x02\x01\x01" + b"\x00" * 64, "application/zip")},
    )
    assert response.status_code == 422


async def test_an_office_document_is_accepted(client: httpx.AsyncClient) -> None:
    """A .docx is a zip that carries word/document.xml — and that is checked."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", "<document/>")
    payload = buffer.getvalue()

    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={
            "file": (
                "report.docx",
                payload,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mime"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


async def test_a_zip_that_claims_to_be_a_docx_is_rejected(client: httpx.AsyncClient) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "just a zip")
    payload = buffer.getvalue()

    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={
            "file": (
                "report.docx",
                payload,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 422


async def test_a_document_downloads_and_an_image_opens(client: httpx.AsyncClient) -> None:
    """Images open in place; documents are handed over as a download."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    image = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    image_headers = (await client.get(image.json()["url"], headers=headers)).headers
    assert image_headers["content-disposition"].startswith("inline")
    assert image_headers["x-content-type-options"] == "nosniff"

    document = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    document_headers = (await client.get(document.json()["url"], headers=headers)).headers
    assert document_headers["content-disposition"].startswith("attachment")


async def test_other_users_cannot_download_a_file(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    url = uploaded.json()["url"]

    other = await join_workspace(
        client, session, data["workspace"]["id"], "sua@hanbit.co.kr", "최수아"
    )
    response = await client.get(url, headers=auth(other["access_token"]))
    assert response.status_code == 403


async def test_a_file_can_be_downloaded_with_the_token_in_the_query(
    client: httpx.AsyncClient,
) -> None:
    """An <img> cannot send an Authorization header, so the token rides in the URL."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    url = uploaded.json()["url"]

    response = await client.get(url, params={"token": data["access_token"]})
    assert response.status_code == 200
    assert response.content == PNG


async def test_a_file_download_without_any_token_is_refused(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    url = uploaded.json()["url"]

    response = await client.get(url)
    assert response.status_code == 401


async def test_attached_files_are_listed_on_the_message(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels", headers=headers, json={"name": "general"}
    )
    channel_id = created.json()["id"]

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    file_id = uploaded.json()["id"]

    posted = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "시안 공유합니다", "attachment_ids": [file_id]},
    )
    assert posted.status_code == 200
    attachments = posted.json()["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["id"] == file_id
    assert attachments[0]["name"] == "design.png"


async def test_a_file_needs_a_workspace(client: httpx.AsyncClient) -> None:
    """The workspace decides where a file lives — so the client must name it."""
    data = await signup(client)
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    assert response.status_code == 422


async def test_a_file_cannot_be_uploaded_into_a_stranger_s_workspace(
    client: httpx.AsyncClient,
) -> None:
    """A workspace keeps its own files; a stranger may not fill it."""
    data = await signup(client)
    stranger = await signup(client, email="sua@hanbit.co.kr", name="최수아")

    response = await client.post(
        f"{API}/files?workspace_id={data['workspace']['id']}",
        headers=auth(stranger["access_token"]),
        files={"file": ("design.png", PNG, "image/png")},
    )
    assert response.status_code == 403


async def test_the_name_follows_the_bytes_not_the_name(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """A file called report.exe whose bytes are a PNG is a PNG — and is named so."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("report.exe", PNG, "application/x-msdownload")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mime"] == "image/png"
    assert body["name"] == "report.png"


async def test_the_file_is_kept_under_its_workspace(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The disk layout is the backend's business: workspace, bucket, id."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    file_id = uploaded.json()["id"]

    record = await session.get(File, file_id)
    assert record is not None
    assert record.workspace_id == workspace_id
    path = Path(record.storage_path)
    assert path.parent.parent.name == workspace_id
    assert path.parent.name == file_id[:2]
    assert path.name == f"{file_id}.png"
    assert await asyncio.to_thread(path.exists)


async def test_a_name_cannot_carry_a_path(client: httpx.AsyncClient) -> None:
    """A name is text a person typed; it never becomes a path."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    response = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("../../etc/passwd.png", PNG, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "passwd.png"


async def test_a_workspace_has_a_room(client: httpx.AsyncClient) -> None:
    """The quota is the workspace's, and it is the backend's to set."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    settings = get_settings()
    original = settings.workspace_quota_bytes
    settings.workspace_quota_bytes = len(PNG)
    try:
        first = await client.post(
            f"{API}/files?workspace_id={workspace_id}",
            headers=headers,
            files={"file": ("one.png", PNG, "image/png")},
        )
        assert first.status_code == 200

        second = await client.post(
            f"{API}/files?workspace_id={workspace_id}",
            headers=headers,
            files={"file": ("two.png", PNG, "image/png")},
        )
        assert second.status_code == 422
    finally:
        settings.workspace_quota_bytes = original


async def test_an_upload_that_was_never_shared_is_taken_away(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """A file that sat unattached for a day was never going to be shared."""
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    file_id = uploaded.json()["id"]
    record = await session.get(File, file_id)
    assert record is not None
    path = Path(record.storage_path)

    old = utcnow() - timedelta(days=2)
    record.created_at = old
    await session.commit()

    removed = await purge_orphan_files(session, 24)
    assert removed == 1
    assert not await asyncio.to_thread(path.exists)
    assert await session.get(File, file_id) is None


async def test_a_file_that_reached_a_message_is_kept(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    created = await client.post(
        f"{API}/workspaces/{workspace_id}/channels", headers=headers, json={"name": "general"}
    )
    channel_id = created.json()["id"]

    uploaded = await client.post(
        f"{API}/files?workspace_id={workspace_id}",
        headers=headers,
        files={"file": ("design.png", PNG, "image/png")},
    )
    file_id = uploaded.json()["id"]
    await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "시안", "attachment_ids": [file_id]},
    )

    record = await session.get(File, file_id)
    assert record is not None
    record.created_at = utcnow() - timedelta(days=2)
    await session.commit()

    removed = await purge_orphan_files(session, 24)
    assert removed == 0
    assert await session.get(File, file_id) is not None
