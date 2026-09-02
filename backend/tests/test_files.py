"""File upload, download and access control."""

from __future__ import annotations

import hashlib

from tests.conftest import Actor
from tests.test_channels import _join_workspace

CONTENT = "매출,월\n100,1월\n200,2월\n".encode()


async def _upload(actor: Actor, workspace: dict, name: str = "매출.csv") -> dict:
    ticket = await actor.post(
        f"/workspaces/{workspace['id']}/files",
        json={
            "filename": name,
            "mime_type": "text/csv",
            "size_bytes": len(CONTENT),
            "checksum_sha256": hashlib.sha256(CONTENT).hexdigest(),
        },
    )
    assert ticket.status_code == 201, ticket.text
    body = ticket.json()
    # The ticket's URL is absolute from the API root; the test client is
    # already based at /api/v1.
    path = body["upload_url"].removeprefix("/api/v1")
    uploaded = await actor.put(path, content=CONTENT, headers={"Content-Type": "text/csv"})
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()


async def test_two_step_upload_then_download(alice: Actor, workspace: dict) -> None:
    file = await _upload(alice, workspace)
    assert file["is_ready"] is True
    assert file["size_bytes"] == len(CONTENT)
    assert file["uploader"]["id"] == alice.id

    downloaded = await alice.get(f"/files/{file['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == CONTENT
    # A non-ASCII filename survives the header round-trip.
    assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]


async def test_checksum_mismatch_is_rejected(alice: Actor, workspace: dict) -> None:
    ticket = (
        await alice.post(
            f"/workspaces/{workspace['id']}/files",
            json={
                "filename": "corrupt.bin",
                "size_bytes": 4,
                "checksum_sha256": "0" * 64,
            },
        )
    ).json()
    path = ticket["upload_url"].removeprefix("/api/v1")
    response = await alice.put(path, content=b"junk")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "checksum_mismatch"


async def test_uploading_twice_is_rejected(alice: Actor, workspace: dict) -> None:
    file = await _upload(alice, workspace)
    response = await alice.put(f"/files/{file['id']}/content", content=CONTENT)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "file_already_uploaded"


async def test_only_the_uploader_may_supply_the_bytes(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    ticket = (
        await alice.post(
            f"/workspaces/{workspace['id']}/files",
            json={"filename": "x.txt", "size_bytes": 1},
        )
    ).json()
    response = await bob.put(
        ticket["upload_url"].removeprefix("/api/v1"), content=b"x"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_file_uploader"


async def test_a_file_shared_into_a_private_channel_is_not_readable_by_outsiders(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    file = await _upload(alice, workspace)

    # Before it is attached anywhere, any workspace member may read it.
    assert (await bob.get(f"/files/{file['id']}")).status_code == 200

    private = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "재무", "kind": "private"},
        )
    ).json()
    attached = await alice.post(
        f"/channels/{private['id']}/messages",
        json={"body": "이번 달 매출입니다", "file_ids": [file["id"]]},
    )
    assert attached.status_code == 201
    assert attached.json()["attachments"][0]["filename"] == "매출.csv"

    # Now that it lives only in a channel Bob cannot see, he cannot read it.
    assert (await bob.get(f"/files/{file['id']}")).status_code == 404
    assert (await bob.get(f"/files/{file['id']}/download")).status_code == 404
    # Alice still can.
    assert (await alice.get(f"/files/{file['id']}/download")).status_code == 200


async def test_attaching_an_unfinished_upload_is_rejected(
    alice: Actor, workspace: dict
) -> None:
    ticket = (
        await alice.post(
            f"/workspaces/{workspace['id']}/files",
            json={"filename": "pending.txt", "size_bytes": 10},
        )
    ).json()
    channel = (await alice.get(f"/workspaces/{workspace['id']}/channels")).json()[0]
    response = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "첨부", "file_ids": [ticket["file_id"]]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "attachment_not_ready"


async def test_oversized_registration_is_rejected(alice: Actor, workspace: dict) -> None:
    response = await alice.post(
        f"/workspaces/{workspace['id']}/files",
        json={"filename": "huge.bin", "size_bytes": 10**12},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_workspace_file_browser_filters_by_name(alice: Actor, workspace: dict) -> None:
    await _upload(alice, workspace, "매출.csv")
    await _upload(alice, workspace, "기획서.pdf")

    listed = (await alice.get(f"/workspaces/{workspace['id']}/files")).json()
    assert {f["filename"] for f in listed} == {"매출.csv", "기획서.pdf"}

    filtered = (await alice.get(f"/workspaces/{workspace['id']}/files?q=기획")).json()
    assert [f["filename"] for f in filtered] == ["기획서.pdf"]


async def test_path_traversal_in_a_filename_is_neutralised(
    alice: Actor, workspace: dict
) -> None:
    ticket = (
        await alice.post(
            f"/workspaces/{workspace['id']}/files",
            json={"filename": "../../../../etc/passwd", "size_bytes": len(CONTENT)},
        )
    ).json()
    uploaded = await alice.put(
        ticket["upload_url"].removeprefix("/api/v1"), content=CONTENT
    )
    assert uploaded.status_code == 200
    # The display name keeps no directory component...
    assert uploaded.json()["filename"] == "passwd"
    # ...and the file is readable, i.e. it landed inside the storage root.
    assert (await alice.get(f"/files/{uploaded.json()['id']}/download")).content == CONTENT


async def test_unified_search_finds_files_by_name_but_not_unfinished_uploads(
    alice: Actor, workspace: dict
) -> None:
    await _upload(alice, workspace, "분기 매출.csv")
    # A reserved ticket whose bytes never arrived must stay invisible.
    ticket = await alice.post(
        f"/workspaces/{workspace['id']}/files",
        json={"filename": "매출 초안.csv", "size_bytes": len(CONTENT)},
    )
    assert ticket.status_code == 201

    result = (await alice.get(f"/workspaces/{workspace['id']}/search?q=매출")).json()
    names = [f["filename"] for f in result["files"]]
    assert names == ["분기 매출.csv"]
    hit = result["files"][0]
    assert hit["size_bytes"] == len(CONTENT)
    assert hit["uploader_name"] == "김앨리스"
