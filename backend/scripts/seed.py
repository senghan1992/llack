"""Seed a development workspace with people, channels, messages and an app.

    python -m scripts.seed

Idempotent: re-running tops up whatever is missing rather than duplicating.
Never point this at a production database — it creates accounts with a known
password.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.db import dispose_engine, get_sessionmaker
from app.core.enums import AppKind, AppStatus, ChannelKind, MessageKind, WorkspaceRole
from app.models.app import App
from app.models.channel import Channel
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.app import AppManifest
from app.services import apps as app_service
from app.services import auth as auth_service
from app.services import channels as channel_service
from app.services import messages as message_service
from app.services import workspaces as workspace_service

PASSWORD = "llack-dev-password"


def stable_key(*parts: str) -> str:
    """A deterministic client_msg_id.

    Python's built-in hash() is salted per process (PYTHONHASHSEED), so using
    it here would give every re-run new ids and re-post every seed message.
    """
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return f"seed-{digest[:24]}"

PEOPLE = [
    ("alice@example.com", "김앨리스", "백엔드 엔지니어"),
    ("bob@example.com", "이밥", "프론트엔드 엔지니어"),
    ("carol@example.com", "박캐롤", "프로덕트 디자이너"),
    ("dave@example.com", "최데이브", "데이터 엔지니어"),
]

CHANNELS = [
    ("공지", "회사 전체 공지", ChannelKind.PUBLIC),
    ("개발", "개발팀 논의", ChannelKind.PUBLIC),
    ("디자인", "디자인 리뷰", ChannelKind.PUBLIC),
    ("배포", "릴리스와 배포 알림", ChannelKind.PUBLIC),
    ("경영", "경영진 전용", ChannelKind.PRIVATE),
]

CONVERSATION = [
    ("개발", "alice@example.com", "새 인증 흐름 PR 올렸습니다. 리뷰 부탁드려요 🙏"),
    ("개발", "bob@example.com", "확인했습니다. 리프레시 토큰 회전 부분이 특히 깔끔하네요."),
    ("개발", "alice@example.com", "고맙습니다. `client_msg_id` 로 재전송 중복도 막아뒀어요."),
    ("개발", "dave@example.com", "쿼리 계획도 봤는데 `(channel_id, id)` 인덱스가 잘 먹습니다."),
    (
        "디자인",
        "carol@example.com",
        "스레드 패널을 오버레이가 아니라 사이드 도크로 바꿨습니다.\n"
        "채널을 가리지 않아서 훨씬 편해요.",
    ),
    ("디자인", "bob@example.com", "이거 진짜 필요했던 겁니다 👍"),
    ("공지", "alice@example.com", "이번 주 금요일 오후 4시에 전사 데모가 있습니다. @channel"),
    (
        "배포",
        "dave@example.com",
        "```\nv0.1.0 → staging\n  migrations: 1 applied\n  health: ok\n```",
    ),
]


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        # ── People ──────────────────────────────────────────────────────
        users: dict[str, User] = {}
        for email, name, title in PEOPLE:
            existing = await db.scalar(select(User).where(User.email == email).limit(1))
            if existing is None:
                user = await auth_service.register_user(
                    db, email=email, password=PASSWORD, display_name=name
                )
                user.title = title
                users[email] = user
                print(f"  + 사용자 {name} <{email}>")
            else:
                users[email] = existing
        await db.commit()

        owner = users["alice@example.com"]

        # ── Workspace ───────────────────────────────────────────────────
        workspace = await db.scalar(
            select(Workspace).where(Workspace.slug == "acme").limit(1)
        )
        if workspace is None:
            workspace = await workspace_service.create_workspace(
                db,
                owner=owner,
                name="아크메 주식회사",
                slug="acme",
                description="Llack 개발용 시드 워크스페이스",
            )
            await db.commit()
            print(f"  + 워크스페이스 {workspace.name} (/{workspace.slug})")

        for email, user in users.items():
            role = WorkspaceRole.OWNER if user.id == owner.id else WorkspaceRole.MEMBER
            if email == "bob@example.com":
                role = WorkspaceRole.ADMIN
            await workspace_service.add_member(
                db, workspace_id=workspace.id, user_id=user.id, role=role
            )
        await db.commit()

        # ── Channels ────────────────────────────────────────────────────
        channels: dict[str, Channel] = {}
        for name, topic, kind in CHANNELS:
            existing = await db.scalar(
                select(Channel)
                .where(Channel.workspace_id == workspace.id, Channel.name == name)
                .limit(1)
            )
            if existing is not None:
                channels[name] = existing
                continue
            member_ids = [u.id for u in users.values()]
            if kind is ChannelKind.PRIVATE:
                member_ids = [owner.id, users["bob@example.com"].id]
            channel = await channel_service.create_channel(
                db,
                workspace_id=workspace.id,
                creator=owner,
                name=name,
                slug=None,
                kind=kind,
                topic=topic,
                member_ids=member_ids,
            )
            channels[name] = channel
            print(f"  + 채널 #{name} ({kind.value})")
        await db.commit()

        # ── Messages ────────────────────────────────────────────────────
        for channel_name, email, body in CONVERSATION:
            channel = channels.get(channel_name)
            author = users.get(email)
            if channel is None or author is None:
                continue
            # A stable client_msg_id makes reseeding idempotent: the server
            # treats it as an idempotency key.
            client_msg_id = stable_key("msg", channel_name, body)
            _, created = await message_service.create_message(
                db,
                channel=channel,
                author=author,
                body=body,
                client_msg_id=client_msg_id,
            )
            if created:
                print(f"  + 메시지 #{channel_name}: {body.splitlines()[0][:36]}…")
        await db.commit()

        # ── A thread, so the thread pane has something to show ───────────
        dev_channel = channels.get("개발")
        if dev_channel is not None:
            root = await db.scalar(
                select(message_service.Message)
                .where(
                    message_service.Message.channel_id == dev_channel.id,
                    message_service.Message.parent_id.is_(None),
                )
                .order_by(message_service.Message.id.asc())
                .limit(1)
            )
            if root is not None:
                for email, reply in [
                    ("carol@example.com", "디자인 쪽에서도 확인했습니다."),
                    ("bob@example.com", "머지했습니다 ✅"),
                ]:
                    await message_service.create_message(
                        db,
                        channel=dev_channel,
                        author=users[email],
                        body=reply,
                        parent_id=root.id,
                        client_msg_id=stable_key("thread", reply),
                    )
                await db.commit()

        # ── A DM ────────────────────────────────────────────────────────
        dm, created = await channel_service.open_dm(
            db,
            workspace_id=workspace.id,
            opener=owner,
            user_ids=[users["carol@example.com"].id],
        )
        await db.commit()
        if created:
            await message_service.create_message(
                db,
                channel=dm,
                author=users["carol@example.com"],
                body="스탠드업 앱 패널 시안 보냈어요. 확인 부탁드립니다!",
                client_msg_id="seed-dm-1",
            )
            await db.commit()
            print("  + 다이렉트 메시지")

        # ── A mini-app, registered and installed ────────────────────────
        existing_app = await db.scalar(select(App).where(App.slug == "standup").limit(1))
        if existing_app is None:
            manifest = AppManifest(
                slug="standup",
                name="데일리 스탠드업",
                version="0.1.0",
                tagline="매일 아침 팀의 진행 상황을 모아 채널에 올립니다",
                kind=AppKind.BOTH,
                panel_url="http://localhost:5180/index.html",
                accent_color="#7c6aff",
                scopes=[
                    "identity:read",
                    "channels:read",
                    "messages:write",
                    "storage",
                    "panel:ui",
                ],
                slash_commands=[{"command": "/standup", "description": "스탠드업 작성"}],
                events=["message.created"],
            )
            app_row = await app_service.register_app(
                db, manifest=manifest, author=owner, owner_workspace_id=workspace.id
            )
            await app_service.set_app_status(
                db, app_row=app_row, status=AppStatus.PUBLISHED, actor=owner
            )
            await db.commit()

            installation = await app_service.install_app(
                db, workspace_id=workspace.id, app_row=app_row, actor=owner
            )
            await db.commit()
            print(f"  + 앱 '{app_row.name}' 등록 및 설치 (installation {installation.id})")

            # A message from the app, so the transcript shows an app-authored one.
            if installation.bot_user_id and (deploy := channels.get("배포")):
                bot = await db.get(User, installation.bot_user_id)
                if bot is not None:
                    await message_service.create_message(
                        db,
                        channel=deploy,
                        author=bot,
                        body="오늘의 스탠드업이 3명에게서 수집되었습니다.",
                        app_id=app_row.id,
                        kind=MessageKind.APP,
                        client_msg_id="seed-app-1",
                    )
                    await db.commit()

        print()
        print("시드 완료")
        print(f"  워크스페이스 : {workspace.name} ({workspace.id})")
        print(f"  로그인       : alice@example.com / {PASSWORD}")
        print(f"  구성원       : {', '.join(name for _, name, _ in PEOPLE)}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
