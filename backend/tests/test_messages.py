"""Messages: posting, idempotency, mentions, threads, reactions, unread, search."""

from __future__ import annotations

from app.core.ids import new_ulid
from tests.conftest import Actor
from tests.test_channels import _join_workspace


async def _setup(alice: Actor, bob: Actor, workspace: dict) -> dict:
    """Both users in the workspace, both in a fresh #팀-채널."""
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "팀 채널", "member_ids": [bob.id]},
        )
    ).json()
    return channel


async def test_posting_and_reading_history(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)

    for i in range(3):
        response = await alice.post(
            f"/channels/{channel['id']}/messages", json={"body": f"메시지 {i}"}
        )
        assert response.status_code == 201

    page = (await bob.get(f"/channels/{channel['id']}/messages")).json()
    assert [m["body"] for m in page["items"]] == ["메시지 2", "메시지 1", "메시지 0"]
    assert page["items"][0]["author"]["id"] == alice.id
    assert page["has_more"] is False


async def test_history_is_keyset_paginated(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    for i in range(10):
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": f"m{i}"})

    first = (await alice.get(f"/channels/{channel['id']}/messages?limit=4")).json()
    assert len(first["items"]) == 4
    assert first["has_more"] is True

    second = (
        await alice.get(
            f"/channels/{channel['id']}/messages?limit=4&before={first['next_cursor']}"
        )
    ).json()
    assert len(second["items"]) == 4
    # Pages must not overlap.
    assert not ({m["id"] for m in first["items"]} & {m["id"] for m in second["items"]})


async def test_client_msg_id_makes_a_retry_idempotent(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    client_msg_id = new_ulid()

    first = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "한 번만 보내야 함", "client_msg_id": client_msg_id},
    )
    retry = await alice.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "한 번만 보내야 함", "client_msg_id": client_msg_id},
    )
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]

    page = (await alice.get(f"/channels/{channel['id']}/messages")).json()
    assert len(page["items"]) == 1


async def test_empty_message_is_rejected(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    response = await alice.post(f"/channels/{channel['id']}/messages", json={"body": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_handle_mentions_are_normalised_and_recorded(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    posted = (
        await alice.post(
            f"/channels/{channel['id']}/messages",
            json={"body": f"@{bob.user['handle']} 확인 부탁드립니다"},
        )
    ).json()

    assert posted["mentioned_user_ids"] == [bob.id]
    assert f"<@{bob.id}>" in posted["body"]


async def test_mentions_inside_code_do_not_notify(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    posted = (
        await alice.post(
            f"/channels/{channel['id']}/messages",
            json={"body": f"보기: `@{bob.user['handle']}` 그리고 @channel 은 코드 밖"},
        )
    ).json()
    # The backticked handle is not a mention; the bare @channel is.
    assert posted["mentioned_user_ids"] == []
    assert posted["mentions_everyone"] is True

    only_code = (
        await alice.post(
            f"/channels/{channel['id']}/messages",
            json={"body": "```\n@channel @everyone\n```"},
        )
    ).json()
    assert only_code["mentions_everyone"] is False


async def test_unread_and_mention_counters(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)

    await alice.post(f"/channels/{channel['id']}/messages", json={"body": "첫 번째"})
    await alice.post(
        f"/channels/{channel['id']}/messages", json={"body": f"<@{bob.id}> 봐주세요"}
    )

    membership = (await bob.get(f"/channels/{channel['id']}")).json()["membership"]
    assert membership["unread_count"] == 2
    assert membership["mention_count"] == 1

    # The author accrues nothing.
    assert (await alice.get(f"/channels/{channel['id']}")).json()["membership"]["unread_count"] == 0

    read = await bob.post(f"/channels/{channel['id']}/read", json={})
    assert read.json()["unread_count"] == 0
    assert read.json()["mention_count"] == 0


async def test_read_cursor_never_moves_backwards(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    first = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "1"})
    ).json()
    second = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "2"})
    ).json()

    await bob.post(f"/channels/{channel['id']}/read", json={"message_id": second["id"]})
    rewound = await bob.post(
        f"/channels/{channel['id']}/read", json={"message_id": first["id"]}
    )
    assert rewound.json()["last_read_message_id"] == second["id"]


async def test_threads_keep_a_reply_count_and_stay_out_of_the_channel(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    root = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "스레드 시작"})
    ).json()

    for i in range(2):
        reply = await bob.post(
            f"/channels/{channel['id']}/messages",
            json={"body": f"답글 {i}", "parent_id": root["id"]},
        )
        assert reply.status_code == 201
        assert reply.json()["parent_id"] == root["id"]

    # The channel view still shows only the root.
    page = (await alice.get(f"/channels/{channel['id']}/messages")).json()
    assert [m["id"] for m in page["items"]] == [root["id"]]
    assert page["items"][0]["reply_count"] == 2

    # The thread view shows the replies oldest-first.
    replies = (await alice.get(f"/messages/{root['id']}/replies")).json()
    assert [m["body"] for m in replies["items"]] == ["답글 0", "답글 1"]


async def test_replying_to_a_reply_joins_the_same_thread(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    """Threads are one level deep, as in Slack — no nested sub-threads."""
    channel = await _setup(alice, bob, workspace)
    root = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "루트"})
    ).json()
    reply = (
        await bob.post(
            f"/channels/{channel['id']}/messages",
            json={"body": "답글", "parent_id": root["id"]},
        )
    ).json()
    nested = (
        await alice.post(
            f"/channels/{channel['id']}/messages",
            json={"body": "답글의 답글", "parent_id": reply["id"]},
        )
    ).json()

    assert nested["parent_id"] == root["id"]
    assert len((await alice.get(f"/messages/{root['id']}/replies")).json()["items"]) == 2


async def test_also_send_to_channel_surfaces_a_reply(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    root = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "루트"})
    ).json()
    await bob.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "모두에게도", "parent_id": root["id"], "also_send_to_channel": True},
    )
    page = (await alice.get(f"/channels/{channel['id']}/messages")).json()
    assert [m["body"] for m in page["items"]] == ["모두에게도", "루트"]


async def test_only_the_author_may_edit(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "원본"})
    ).json()

    denied = await bob.patch(f"/messages/{message['id']}", json={"body": "남의 글"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_message_author"

    edited = await alice.patch(f"/messages/{message['id']}", json={"body": "수정됨"})
    assert edited.status_code == 200
    assert edited.json()["body"] == "수정됨"
    assert edited.json()["edited_at"] is not None


async def test_delete_is_soft_and_preserves_thread_counts(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    root = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "루트"})
    ).json()
    await bob.post(
        f"/channels/{channel['id']}/messages",
        json={"body": "답글", "parent_id": root["id"]},
    )

    assert (await alice.delete(f"/messages/{root['id']}")).status_code == 200
    fetched = (await alice.get(f"/messages/{root['id']}")).json()
    assert fetched["deleted_at"] is not None
    assert fetched["body"] == ""
    # The thread survives its root being deleted.
    assert fetched["reply_count"] == 1


async def test_reactions_group_and_toggle(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "좋아요?"})
    ).json()

    assert (
        await alice.put(f"/messages/{message['id']}/reactions", json={"emoji": "👍"})
    ).status_code == 200
    # Reacting twice with the same emoji is a no-op, not a duplicate.
    await alice.put(f"/messages/{message['id']}/reactions", json={"emoji": "👍"})
    await bob.put(f"/messages/{message['id']}/reactions", json={"emoji": "👍"})
    await bob.put(f"/messages/{message['id']}/reactions", json={"emoji": "🎉"})

    as_alice = (await alice.get(f"/messages/{message['id']}")).json()["reactions"]
    thumbs = next(r for r in as_alice if r["emoji"] == "👍")
    assert thumbs["count"] == 2
    assert thumbs["me"] is True
    party = next(r for r in as_alice if r["emoji"] == "🎉")
    assert party["count"] == 1 and party["me"] is False

    await alice.delete(f"/messages/{message['id']}/reactions?emoji=👍")
    thumbs = next(
        r for r in (await alice.get(f"/messages/{message['id']}")).json()["reactions"]
        if r["emoji"] == "👍"
    )
    assert thumbs["count"] == 1 and thumbs["me"] is False


async def test_pins(alice: Actor, bob: Actor, workspace: dict) -> None:
    channel = await _setup(alice, bob, workspace)
    message = (
        await alice.post(f"/channels/{channel['id']}/messages", json={"body": "중요 공지"})
    ).json()

    await alice.post(f"/messages/{message['id']}/pin?pinned=true")
    pins = (await bob.get(f"/channels/{channel['id']}/pins")).json()
    assert [m["id"] for m in pins] == [message["id"]]

    await alice.post(f"/messages/{message['id']}/pin?pinned=false")
    assert (await bob.get(f"/channels/{channel['id']}/pins")).json() == []


async def test_search_only_returns_channels_the_user_is_in(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    await _join_workspace(alice, bob, workspace)
    shared = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "공유 채널", "member_ids": [bob.id]},
        )
    ).json()
    private = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels",
            json={"name": "비공개", "kind": "private"},
        )
    ).json()

    await alice.post(f"/channels/{shared['id']}/messages", json={"body": "김치찌개 레시피"})
    await alice.post(f"/channels/{private['id']}/messages", json={"body": "김치찌개 비밀"})

    as_alice = (await alice.get(f"/workspaces/{workspace['id']}/search/messages?q=김치찌개")).json()
    assert as_alice["total"] == 2

    as_bob = (await bob.get(f"/workspaces/{workspace['id']}/search/messages?q=김치찌개")).json()
    assert as_bob["total"] == 1
    assert as_bob["hits"][0]["channel_id"] == shared["id"]
    assert "<mark>김치찌개</mark>" in as_bob["hits"][0]["highlight"]


async def test_unified_search_covers_channels_people_and_messages(
    alice: Actor, bob: Actor, workspace: dict
) -> None:
    channel = await _setup(alice, bob, workspace)
    await alice.post(f"/channels/{channel['id']}/messages", json={"body": "팀 회의록"})

    result = (await alice.get(f"/workspaces/{workspace['id']}/search?q=팀")).json()
    assert any(c["name"] == "팀 채널" for c in result["channels"])
    assert any("팀" in m["message"]["body"] for m in result["messages"])
    assert "people" in result and "apps" in result


async def test_a_non_member_cannot_post(alice: Actor, bob: Actor, workspace: dict) -> None:
    await _join_workspace(alice, bob, workspace)
    channel = (
        await alice.post(
            f"/workspaces/{workspace['id']}/channels", json={"name": "혼자만"}
        )
    ).json()
    response = await bob.post(f"/channels/{channel['id']}/messages", json={"body": "끼어들기"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_channel_member"


def test_a_notification_preview_resolves_mentions_to_names() -> None:
    """The canonical mention form must not survive into a notification body.

    `<@ID>` used to reach the OS notification verbatim, minus its closing `>`,
    because the Markdown strip removes `>`. Reads as `<@01J…` to the user.
    """
    from app.services.text import plain_text_preview

    user_id = new_ulid()
    body = f"<@{user_id}> 배포 확인 부탁드립니다"

    resolved = plain_text_preview(body, names={user_id: "김앨리스"})
    assert resolved == "@김앨리스 배포 확인 부탁드립니다"

    # Without a name we still must not leak the id or a broken token.
    anonymous = plain_text_preview(body)
    assert anonymous == "@사용자 배포 확인 부탁드립니다"
    assert user_id not in anonymous
    assert "<@" not in anonymous


def test_a_notification_preview_still_strips_markdown() -> None:
    from app.services.text import plain_text_preview

    # Inline code collapses to a placeholder like a fenced block does; that is
    # the existing behaviour and a preview is not a place for code anyway.
    assert plain_text_preview("**굵게** _기울임_ `코드`") == "굵게 기울임 [코드]"
    assert plain_text_preview("> 인용문입니다") == "인용문입니다"
    assert plain_text_preview("```\nprint(1)\n```") == "[코드]"
