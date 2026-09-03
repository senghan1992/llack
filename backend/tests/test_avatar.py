"""Profile pictures: upload, public serving, replacement, removal."""

from __future__ import annotations

import httpx

from tests.conftest import Actor

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def test_avatar_round_trip(alice: Actor, client: httpx.AsyncClient) -> None:
    uploaded = await alice.put("/me/avatar", content=PNG, headers={"Content-Type": "image/png"})
    assert uploaded.status_code == 200, uploaded.text
    url = uploaded.json()["avatar_url"]
    assert url.startswith(f"/api/v1/users/{alice.id}/avatar/") and url.endswith(".png")

    # Served without a token — an <img> cannot carry one — and cached forever.
    public = await client.get(url.removeprefix("/api/v1"))
    assert public.status_code == 200
    assert public.headers["content-type"] == "image/png"
    assert "immutable" in public.headers["cache-control"]
    assert public.content == PNG

    # Replacing it retires the old address.
    replaced = await alice.put(
        "/me/avatar", content=b"RIFF" + b"\x00" * 32, headers={"Content-Type": "image/webp"}
    )
    new_url = replaced.json()["avatar_url"]
    assert new_url != url and new_url.endswith(".webp")
    assert (await client.get(url.removeprefix("/api/v1"))).status_code == 404
    assert (await client.get(new_url.removeprefix("/api/v1"))).status_code == 200

    # Everyone reading the profile sees the new picture.
    me = (await alice.get("/me")).json()
    assert me["avatar_url"] == new_url

    removed = await alice.delete("/me/avatar")
    assert removed.status_code == 200
    assert removed.json()["avatar_url"] is None
    assert (await client.get(new_url.removeprefix("/api/v1"))).status_code == 404


async def test_avatar_rejects_wrong_type_size_and_forged_names(
    alice: Actor, client: httpx.AsyncClient
) -> None:
    gif = await alice.put("/me/avatar", content=b"GIF89a", headers={"Content-Type": "image/gif"})
    assert gif.status_code == 415
    assert gif.json()["error"]["code"] == "unsupported_media_type"

    huge = await alice.put(
        "/me/avatar", content=b"\x00" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "image/png"}
    )
    assert huge.status_code == 413

    empty = await alice.put("/me/avatar", content=b"", headers={"Content-Type": "image/png"})
    assert empty.status_code == 400

    # Names outside the pattern never touch storage.
    assert (await client.get(f"/users/{alice.id}/avatar/..%2F..%2Fetc%2Fpasswd")).status_code == 404
    assert (await client.get(f"/users/{alice.id}/avatar/nothing.png")).status_code == 404
