"""Activity: my threads and my mentions."""

from __future__ import annotations

import httpx

from tests.conftest import Actor, register
from tests.test_channels import _join_workspace


async def _channel(alice: Actor, bob: Actor, workspace: dict, *extra: Actor) -> dict:
    await _join_workspace(alice, bob, workspace)
    for actor in extra:
        await _join_workspace(alice, actor, workspace)
    return (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "활동", "member_ids": [bob.id, *(a.id for a in extra)]},
        )
    ).json()


async def test_threads_i_take_part_in(
    alice: Actor, bob: Actor, workspace: dict, client: httpx.AsyncClient
) -> None:
    carol = await register(client, "carol@example.com", "박캐롤")
    channel = await _channel(alice, bob, workspace, carol)
    ws = workspace["id"]

    root = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "QA 기간 맞나요?"})
    ).json()
    for body in ("2일입니다", "결제 QA 는 3일"):
        await bob.post(
            f"/channels/{channel['id']}/messages", json={"body": body, "parent_id": root["id"]}
        )

    # The root author: both replies are news.
    mine = (await alice.get(f"/workspaces/{ws}/activity/threads")).json()
    assert len(mine["items"]) == 1
    item = mine["items"][0]
    assert item["root"]["id"] == root["id"]
    assert item["channel"] == {"id": channel["id"], "name": "활동", "kind": "public", "peers": []}
    assert item["last_reply"]["body"] == "결제 QA 는 3일"
    assert [p["id"] for p in item["participants"]] == [alice.id, bob.id]
    assert item["unread_replies"] == 2
    assert mine["has_more"] is False and mine["next_before"] is None

    # The replier: nothing after his own last word.
    theirs = (await bob.get(f"/workspaces/{ws}/activity/threads")).json()
    assert theirs["items"][0]["unread_replies"] == 0

    # A member who never took part sees nothing.
    assert (await carol.get(f"/workspaces/{ws}/activity/threads")).json()["items"] == []

    # Alice answers; bob now has one unread reply.
    await alice.post(
        f"/channels/{channel['id']}/messages", json={"body": "감사합니다", "parent_id": root["id"]}
    )
    theirs = (await bob.get(f"/workspaces/{ws}/activity/threads")).json()
    assert theirs["items"][0]["unread_replies"] == 1
    assert theirs["items"][0]["last_reply"]["body"] == "감사합니다"

    # Paging by activity time.
    second = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "두 번째 스레드"})
    ).json()
    await bob.post(
        f"/channels/{channel['id']}/messages", json={"body": "답", "parent_id": second["id"]}
    )
    page = (await alice.get(f"/workspaces/{ws}/activity/threads?limit=1")).json()
    assert [i["root"]["id"] for i in page["items"]] == [second["id"]]
    assert page["has_more"] is True and page["next_before"] == second["id"]
    rest = (
        await alice.get(f"/workspaces/{ws}/activity/threads?limit=1&before={page['next_before']}")
    ).json()
    assert [i["root"]["id"] for i in rest["items"]] == [root["id"]]
    assert rest["has_more"] is False


async def test_threads_stay_inside_my_channels(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    private = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "경영", "kind": "private"}
        )
    ).json()
    root = (
        await alice.post(
            f"/channels/{private['id']}/messages", json={"body": "<@" + bob.id + "> 비밀"}
        )
    ).json()
    await alice.post(
        f"/channels/{private['id']}/messages", json={"body": "혼자 답", "parent_id": root["id"]}
    )
    # Bob is mentioned in a channel he is not in: not his to see, in either list.
    ws = workspace["id"]
    assert (await bob.get(f"/workspaces/{ws}/activity/threads")).json()["items"] == []
    assert (await bob.get(f"/workspaces/{ws}/activity/mentions")).json()["items"] == []


async def test_mentions_of_me(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _channel(alice, bob, workspace)
    ws = workspace["id"]

    direct = (
        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 확인 부탁"}
        )
    ).json()
    everyone = (
        await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": "@channel 데모 15:00"}
        )
    ).json()
    await alice.post(f"/channels/{channel['id']}/messages", json={"body": "멘션 아님"})
    # My own @channel does not call me.
    await bob.post(f"/channels/{channel['id']}/messages", json={"body": "@channel 제가 쏩니다"})

    mentions = (await bob.get(f"/workspaces/{ws}/activity/mentions")).json()
    assert [m["message"]["id"] for m in mentions["items"]] == [everyone["id"], direct["id"]]
    assert mentions["items"][0]["channel"]["name"] == "활동"
    assert mentions["has_more"] is False

    page = (await bob.get(f"/workspaces/{ws}/activity/mentions?limit=1")).json()
    assert page["has_more"] is True and page["next_before"] == everyone["id"]
    rest = (
        await bob.get(f"/workspaces/{ws}/activity/mentions?limit=1&before={page['next_before']}")
    ).json()
    assert [m["message"]["id"] for m in rest["items"]] == [direct["id"]]

    # A DM mention names the person, not a hash.
    dm = (await alice.post(f"/workspaces/{ws}/channels/dm", json={"user_ids": [bob.id]})).json()
    await alice.post(f"/channels/{dm['id']}/messages", json={"body": f"<@{bob.id}> 디엠"})
    latest = (await bob.get(f"/workspaces/{ws}/activity/mentions?limit=1")).json()["items"][0]
    assert latest["channel"]["kind"] == "dm"
    assert [p["id"] for p in latest["channel"]["peers"]] == [alice.id]
