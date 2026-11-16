"""Shared FastAPI dependencies."""

from __future__ import annotations

import ipaddress
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import POLICY_PERIODS, limiter
from app.core.security import current_user
from app.models.channel import Channel
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.services.channels import get_channel_or_404
from app.services.members import require_channel_access, require_membership
from app.services.workspaces import get_workspace_or_404

WorkspaceId = Annotated[str, Path(description="Workspace id")]
ChannelId = Annotated[str, Path(description="Channel id")]
MessageId = Annotated[str, Path(description="Message id")]

CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]


async def workspace_membership(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
) -> WorkspaceMembership:
    """The caller's membership of the workspace, or 404/403."""
    await get_workspace_or_404(session, workspace_id)
    return await require_membership(session, workspace_id, user.id)


async def channel_with_access(
    channel_id: ChannelId,
    user: CurrentUser,
    session: DbSession,
) -> tuple[Channel, WorkspaceMembership]:
    """The channel plus the caller's membership, enforcing visibility rules."""
    channel = await get_channel_or_404(session, channel_id)
    membership = await require_channel_access(session, channel, user.id)
    return channel, membership


WorkspaceMember = Annotated[WorkspaceMembership, Depends(workspace_membership)]
ChannelAccess = Annotated[tuple[Channel, WorkspaceMembership], Depends(channel_with_access)]


def _is_trusted_proxy(host: str, networks: list[str]) -> bool:
    """이 주소가 신뢰하는 프록시인가?"""
    if not networks:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    for raw in networks:
        try:
            if "/" in raw:
                if address in ipaddress.ip_network(raw, strict=False):
                    return True
            elif address == ipaddress.ip_address(raw):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    """요청한 쪽의 주소.

    프록시(nginx) 뒤에 있으면 그 프록시가 앞장섭니다. 그래도 **믿을 수 있는
    프록시**에서 왔을 때만 `X-Forwarded-For` 를 봅니다 — 아무나 그 헤더를
    조작하면 한도를 피할 수 있으니까요.

    헤더에는 주소가 여러 개 실릴 수 있습니다(프록시마다 하나씩 덧붙입니다).
    그중 **오른쪽에서 처음으로 신뢰하지 않는 주소**가 진짜 손님입니다 —
    오른쪽일수록 나중에 만난 프록시이니까요. 왼쪽(맨 앞)은 손님이 직접
    써 넣은 것일 수 있습니다.

    `TRUSTED_PROXY_NETWORKS` 에 적힌 주소만 믿습니다
    (docs/DEPLOY.md 의 리버스 프록시 설정을 보세요).
    """
    peer = request.client.host if request.client else "-"
    settings = get_settings()
    networks = settings.trusted_proxy_networks_list
    if not _is_trusted_proxy(peer, networks):
        return peer

    chain = [
        item.strip()
        for item in (request.headers.get("x-forwarded-for") or "").split(",")
        if item.strip()
    ]
    for candidate in reversed(chain):
        if not _is_trusted_proxy(candidate, networks):
            return candidate
    # 전부 신뢰하는 주소라면 — 손님도 프록시였다는 뜻입니다. 가장 오른쪽을 씁니다.
    return chain[-1] if chain else peer


def check_limit(scope: str, key: str) -> None:
    """한도를 확인합니다. 넘으면 :func:`rate_limited` 가 429 를 던집니다."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    capacity = settings.rate_limit_capacity(scope)
    if capacity <= 0:
        return
    limiter.check(
        scope,
        key,
        capacity=capacity,
        per_seconds=POLICY_PERIODS.get(scope, 60.0),
    )


def limit_by_ip(scope: str):
    """주소별로 한도를 거는 의존성.

    ```python
    @router.post("/login")
    async def login(_: None = Depends(limit_by_ip("login"))):
    ```

    몇 번까지인지와 몇 초 창인지, 켜고 끄는지는 `RATE_LIMIT_*` 설정이
    정합니다 — 여기에는 동작 이름만 씁니다.
    """

    async def dependency(request: Request) -> None:
        check_limit(scope, client_ip(request))

    return dependency


def limit_by_user(scope: str):
    """사람별로 한도를 거는 의존성 — 로그인한 사람 기준입니다."""

    async def dependency(user: CurrentUser) -> None:
        check_limit(scope, user.id)

    return dependency
