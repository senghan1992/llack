"""Posting, listing, editing, deleting and threading messages."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API, auth, join_workspace, signup


async def _channel(client: httpx.AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=auth(token),
        json={"name": "general", "topic": "팀 공지"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_post_and_list_messages(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    posted = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "배포 준비 끝났습니다."},
    )
    assert posted.status_code == 200
    message = posted.json()
    assert message["id"].startswith("msg_")
    assert message["channel_id"] == channel_id
    assert message["user_id"] == data["user"]["id"]
    assert message["body"] == "배포 준비 끝났습니다."
    assert message["kind"] == "text"
    assert message["parent_id"] is None
    assert message["reply_count"] == 0
    assert message["last_reply_at"] is None
    assert message["pinned"] is False
    assert message["edited_at"] is None
    assert message["deleted_at"] is None
    assert message["reactions"] == []
    assert message["attachments"] == []
    assert message["author"]["name"] == "김현진"
    assert message["author"]["id"] == data["user"]["id"]

    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["has_more"] is False
    assert [item["id"] for item in body["messages"]] == [message["id"]]


async def test_messages_are_returned_newest_last(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    ids = []
    for index in range(5):
        response = await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": f"메시지 {index}"},
        )
        ids.append(response.json()["id"])

    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert [item["id"] for item in listing.json()["messages"]] == ids


async def test_pagination_with_before_and_limit(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    ids = []
    for index in range(10):
        response = await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": f"메시지 {index}"},
        )
        ids.append(response.json()["id"])

    first_page = await client.get(f"{API}/channels/{channel_id}/messages?limit=4", headers=headers)
    body = first_page.json()
    assert [item["id"] for item in body["messages"]] == ids[6:]
    assert body["has_more"] is True

    # `before` walks backwards through the history
    second_page = await client.get(
        f"{API}/channels/{channel_id}/messages?limit=4&before={ids[6]}", headers=headers
    )
    body = second_page.json()
    assert [item["id"] for item in body["messages"]] == ids[2:6]
    assert body["has_more"] is True

    last_page = await client.get(
        f"{API}/channels/{channel_id}/messages?limit=4&before={ids[2]}", headers=headers
    )
    body = last_page.json()
    assert [item["id"] for item in body["messages"]] == ids[:2]
    assert body["has_more"] is False

    capped = await client.get(f"{API}/channels/{channel_id}/messages?limit=500", headers=headers)
    assert len(capped.json()["messages"]) == 10


async def test_thread_replies_are_listed_separately(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    root = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "이 버그 어떻게 보시나요?"},
    )
    root_id = root.json()["id"]

    replies = []
    for body in ["저도 같은 증상이에요.", "로그 확인해보면 될 것 같아요.", "고정했습니다."]:
        response = await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": body, "parent_id": root_id},
        )
        assert response.status_code == 200
        reply = response.json()
        assert reply["parent_id"] == root_id
        replies.append(reply)

    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert [item["id"] for item in listing.json()["messages"]] == [root_id]

    root_after = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert root_after.json()["messages"][0]["reply_count"] == 3
    assert root_after.json()["messages"][0]["last_reply_at"] is not None

    thread = await client.get(f"{API}/messages/{root_id}/replies", headers=headers)
    assert thread.status_code == 200
    assert [item["id"] for item in thread.json()] == [reply["id"] for reply in replies]
    assert [item["body"] for item in thread.json()] == [
        "저도 같은 증상이에요.",
        "로그 확인해보면 될 것 같아요.",
        "고정했습니다.",
    ]


async def test_replies_route_requires_channel_access(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])

    private = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "release", "is_private": True},
    )
    channel_id = private.json()["id"]

    root = await client.post(
        f"{API}/channels/{channel_id}/messages", headers=headers, json={"body": "비밀"}
    )
    root_id = root.json()["id"]

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    response = await client.get(
        f"{API}/messages/{root_id}/replies", headers=auth(other["access_token"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    owner_view = await client.get(f"{API}/messages/{root_id}/replies", headers=headers)
    assert owner_view.status_code == 200
    assert owner_view.json() == []


async def test_only_the_author_or_an_admin_can_edit_a_message(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    other = await join_workspace(client, session, workspace_id, "sua@hanbit.co.kr", "최수아")
    other_headers = auth(other["access_token"])

    posted = await client.post(
        f"{API}/channels/{channel_id}/messages", headers=headers, json={"body": "원본"}
    )
    message_id = posted.json()["id"]

    denied = await client.patch(
        f"{API}/messages/{message_id}", headers=other_headers, json={"body": "남의 메시지"}
    )
    assert denied.status_code == 403

    edited = await client.patch(
        f"{API}/messages/{message_id}", headers=headers, json={"body": "수정본"}
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "수정본"
    assert edited.json()["edited_at"] is not None

    await client.patch(
        f"{API}/workspaces/{workspace_id}/members/{other['user']['id']}",
        headers=headers,
        json={"role": "admin"},
    )
    admin_edit = await client.patch(
        f"{API}/messages/{message_id}", headers=other_headers, json={"body": "관리자가 고침"}
    )
    assert admin_edit.status_code == 200
    assert admin_edit.json()["body"] == "관리자가 고침"


async def test_delete_is_a_soft_delete(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    posted = await client.post(
        f"{API}/channels/{channel_id}/messages", headers=headers, json={"body": "잘못 보냈어요"}
    )
    message_id = posted.json()["id"]

    deleted = await client.delete(f"{API}/messages/{message_id}", headers=headers)
    assert deleted.status_code == 204

    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    messages = listing.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["id"] == message_id
    assert messages[0]["body"] == ""
    assert messages[0]["deleted_at"] is not None


async def test_pins(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    workspace_id = data["workspace"]["id"]
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], workspace_id)

    posted = await client.post(
        f"{API}/channels/{channel_id}/messages", headers=headers, json={"body": "배포 체크리스트"}
    )
    message_id = posted.json()["id"]

    pinned = await client.post(f"{API}/messages/{message_id}/pin", headers=headers)
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    pins = await client.get(f"{API}/channels/{channel_id}/pins", headers=headers)
    assert [item["id"] for item in pins.json()] == [message_id]

    unpinned = await client.delete(f"{API}/messages/{message_id}/pin", headers=headers)
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned"] is False

    pins = await client.get(f"{API}/channels/{channel_id}/pins", headers=headers)
    assert pins.json() == []


async def test_message_routes_reject_unknown_ids(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    headers = auth(data["access_token"])

    response = await client.patch(
        f"{API}/messages/msg_missing", headers=headers, json={"body": "x"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    response = await client.get(f"{API}/channels/chl_missing/messages", headers=headers)
    assert response.status_code == 404


async def test_an_answer_in_the_room_is_quoted_and_joins_the_thread(
    client: httpx.AsyncClient,
) -> None:
    """An answer written in the room shows there, quoted, and joins the thread."""
    data = await signup(client)
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], data["workspace"]["id"])

    asked = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "라벤더는 어떤 색으로 할까요?"},
    )
    assert asked.status_code == 200
    asked_message = asked.json()

    answered = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={
            "body": "다크로 할게요.",
            "reply_to_id": asked_message["id"],
            "inline": True,
        },
    )
    assert answered.status_code == 200
    answer = answered.json()
    assert answer["inline"] is True
    assert answer["reply_to_id"] == asked_message["id"]
    assert answer["parent_id"] == asked_message["id"]
    assert answer["reply_to"] == {
        "id": asked_message["id"],
        "author_name": "김현진",
        "body": "라벤더는 어떤 색으로 할까요?",
        "deleted": False,
    }

    # it shows in the room, right after the message it answers
    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert [item["id"] for item in listing.json()["messages"]] == [
        asked_message["id"],
        answer["id"],
    ]

    # and it is a reply of that message, so the thread holds it too
    replies = await client.get(f"{API}/messages/{asked_message['id']}/replies", headers=headers)
    assert [item["id"] for item in replies.json()] == [answer["id"]]

    # the answered message counts it
    refreshed = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    root = next(item for item in refreshed.json()["messages"] if item["id"] == asked_message["id"])
    assert root["reply_count"] == 1
    assert root["last_reply_at"] is not None


async def test_an_answer_in_a_thread_stays_in_the_thread(client: httpx.AsyncClient) -> None:
    data = await signup(client)
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], data["workspace"]["id"])

    asked = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "배포 순서 좀 봐주세요."},
    )
    asked_message = asked.json()

    answered = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "배포부터 하겠습니다.", "parent_id": asked_message["id"]},
    )
    assert answered.status_code == 200
    answer = answered.json()
    assert answer["inline"] is False
    assert answer["reply_to_id"] is None
    assert answer["reply_to"] is None

    listing = await client.get(f"{API}/channels/{channel_id}/messages", headers=headers)
    assert [item["id"] for item in listing.json()["messages"]] == [asked_message["id"]]


async def test_answers_are_one_level_deep(client: httpx.AsyncClient) -> None:
    """Answering an answer joins the thread of the message that answer answered."""
    data = await signup(client)
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], data["workspace"]["id"])

    root = (
        await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": "일정 언제예요?"},
        )
    ).json()
    first = (
        await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": "다음 주예요.", "reply_to_id": root["id"], "inline": True},
        )
    ).json()
    second = (
        await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": "그럼 그날로.", "reply_to_id": first["id"], "inline": True},
        )
    ).json()

    # the second answer belongs to the root's thread, not to the first answer
    assert second["parent_id"] == root["id"]
    assert second["reply_to_id"] == first["id"]

    replies = await client.get(f"{API}/messages/{root['id']}/replies", headers=headers)
    assert [item["id"] for item in replies.json()] == [first["id"], second["id"]]


async def test_a_message_cannot_be_answered_after_it_is_deleted(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    headers = auth(data["access_token"])
    channel_id = await _channel(client, data["access_token"], data["workspace"]["id"])

    asked = (
        await client.post(
            f"{API}/channels/{channel_id}/messages",
            headers=headers,
            json={"body": "이건 지울게요."},
        )
    ).json()
    deleted = await client.delete(f"{API}/messages/{asked['id']}", headers=headers)
    assert deleted.status_code in (200, 204)

    answered = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "뭐였죠?", "reply_to_id": asked["id"], "inline": True},
    )
    assert answered.status_code == 422
    assert answered.json()["error"]["field"] == "reply_to_id"


async def test_a_message_of_another_channel_cannot_be_answered(
    client: httpx.AsyncClient,
) -> None:
    data = await signup(client)
    headers = auth(data["access_token"])
    workspace_id = data["workspace"]["id"]
    channel_id = await _channel(client, data["access_token"], workspace_id)

    other = await client.post(
        f"{API}/workspaces/{workspace_id}/channels",
        headers=headers,
        json={"name": "engineering"},
    )
    other_id = other.json()["id"]
    elsewhere = (
        await client.post(
            f"{API}/channels/{other_id}/messages",
            headers=headers,
            json={"body": "다른 방의 말입니다."},
        )
    ).json()

    answered = await client.post(
        f"{API}/channels/{channel_id}/messages",
        headers=headers,
        json={"body": "답할 수 없죠.", "reply_to_id": elsewhere["id"], "inline": True},
    )
    assert answered.status_code == 404
