"""Range requests, media tokens and thumbnails."""

from __future__ import annotations

import hashlib
import io

import httpx
from PIL import Image

from app.api.v1 import files as files_api
from app.services import media_token
from tests.conftest import Actor
from tests.test_channels import _join_workspace
from tests.test_files import CONTENT, _upload


async def test_downloads_honour_byte_ranges(alice: Actor, workspace: dict) -> None:
    file = await _upload(alice, workspace)
    full = await alice.get(f"/files/{file['id']}/download")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"

    part = await alice.get(f"/files/{file['id']}/download", headers={"Range": "bytes=0-3"})
    assert part.status_code == 206
    assert part.content == CONTENT[:4]
    assert part.headers["content-range"] == f"bytes 0-3/{len(CONTENT)}"
    assert part.headers["content-length"] == "4"

    tail = await alice.get(f"/files/{file['id']}/download", headers={"Range": "bytes=-5"})
    assert tail.status_code == 206
    assert tail.content == CONTENT[-5:]

    open_ended = await alice.get(f"/files/{file['id']}/download", headers={"Range": "bytes=10-"})
    assert open_ended.status_code == 206
    assert open_ended.content == CONTENT[10:]

    bad = await alice.get(
        f"/files/{file['id']}/download", headers={"Range": f"bytes={len(CONTENT) + 5}-"}
    )
    assert bad.status_code == 416
    assert bad.headers["content-range"] == f"bytes */{len(CONTENT)}"


async def test_media_token_lets_a_headerless_client_fetch_one_file(
    alice: Actor, bob: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    await _join_workspace(alice, bob, workspace)
    mine = await _upload(alice, workspace, name="영상.mp4")
    other = await _upload(alice, workspace, name="다른.mp4")

    minted = await alice.post(f"/files/{mine['id']}/media-token")
    assert minted.status_code == 200
    url = minted.json()["url"]
    assert url.startswith(f"/api/v1/files/{mine['id']}/download?media_token=")

    # No Authorization header at all — like a <video> element.
    plain = await client.get(url.removeprefix("/api/v1"), headers={"Range": "bytes=0-1"})
    assert plain.status_code == 206
    assert plain.content == CONTENT[:2]
    assert plain.headers["content-disposition"].startswith("inline")

    token = url.split("media_token=")[1]
    # The token names one file: it does not open the other.
    stolen = await client.get(f"/files/{other['id']}/download?media_token={token}")
    assert stolen.status_code == 401
    # A tampered token is refused.
    tampered = await client.get(f"/files/{mine['id']}/download?media_token={token[:-2]}xx")
    assert tampered.status_code == 401
    # An expired token is refused.
    expired, _ = media_token.mint(mine["id"], ttl_seconds=-1)
    assert (
        await client.get(f"/files/{mine['id']}/download?media_token={expired}")
    ).status_code == 401

    # Minting requires read access: bob cannot mint for a file he cannot see.
    private = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "비밀", "kind": "private"}
        )
    ).json()
    secret = await _upload(alice, workspace, name="비밀.csv")
    assert (
        await alice.post(
            f"/channels/{private['id']}/messages", json={"body": "x", "file_ids": [secret["id"]]}
        )
    ).status_code == 201
    assert (await bob.post(f"/files/{secret['id']}/media-token")).status_code == 404


async def _upload_png(actor: Actor, workspace: dict, size: tuple[int, int]) -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", size, (165, 0, 52)).save(buffer, format="PNG")
    data = buffer.getvalue()
    ticket = await actor.post(
        f"/workspaces/{workspace['id']}/files",
        json={
            "filename": "시안.png",
            "mime_type": "image/png",
            "size_bytes": len(data),
            "checksum_sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    path = ticket.json()["upload_url"].removeprefix("/api/v1")
    uploaded = await actor.put(path, content=data, headers={"Content-Type": "image/png"})
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()


async def test_images_get_a_320px_thumbnail(alice: Actor, workspace: dict) -> None:
    file = await _upload_png(alice, workspace, (1600, 900))
    assert file["thumbnail_url"] is None  # rendered after the response
    await files_api.drain_background()

    detail = (await alice.get(f"/files/{file['id']}")).json()
    assert detail["thumbnail_url"] == f"/files/{file['id']}/thumbnail"
    assert detail["metadata"]["thumbnail"] == {"w": 320, "h": 180}

    thumb = await alice.get(f"/files/{file['id']}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(thumb.content)) as image:
        assert image.size == (320, 180)

    # Same authorisation as the original: a media token works here too.
    url = (await alice.post(f"/files/{file['id']}/media-token")).json()["url"]
    token = url.split("media_token=")[1]
    via_token = await alice.get(f"/files/{file['id']}/thumbnail?media_token={token}")
    assert via_token.status_code == 200


async def test_non_images_have_no_thumbnail(alice: Actor, workspace: dict) -> None:
    file = await _upload(alice, workspace)
    await files_api.drain_background()
    assert (await alice.get(f"/files/{file['id']}")).json()["thumbnail_url"] is None
    missing = await alice.get(f"/files/{file['id']}/thumbnail")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "thumbnail_missing"
