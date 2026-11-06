"""Workspace and membership management."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, not_found
from app.core.ids import MEMBER_PREFIX, WORKSPACE_PREFIX, new_id
from app.models.user import User
from app.models.workspace import ROLES, Workspace, WorkspaceMembership
from app.schemas.user import MemberOut

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Revised Romanization tables for Hangul syllables, so that a Korean name
# such as "한빛" becomes the slug "hanbit".
_INITIALS = (
    "g",
    "gg",
    "n",
    "d",
    "dd",
    "r",
    "m",
    "b",
    "bb",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
)
_VOWELS = (
    "a",
    "ae",
    "ya",
    "yae",
    "eo",
    "e",
    "yeo",
    "ye",
    "o",
    "wa",
    "wae",
    "oe",
    "yo",
    "u",
    "wo",
    "we",
    "wi",
    "yu",
    "eu",
    "ui",
    "i",
)
_FINALS = (
    "",
    "k",
    "k",
    "gs",
    "n",
    "nj",
    "nh",
    "l",
    "l",
    "lg",
    "lm",
    "lb",
    "ls",
    "lt",
    "lp",
    "lh",
    "m",
    "p",
    "ps",
    "s",
    "ss",
    "ng",
    "j",
    "t",
    "k",
    "t",
    "p",
    "h",
)


def _romanize(text: str) -> str:
    out: list[str] = []
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            syllable = code - 0xAC00
            out.append(
                _INITIALS[syllable // 588]
                + _VOWELS[(syllable % 588) // 28]
                + _FINALS[syllable % 28]
            )
        else:
            out.append(char)
    return "".join(out)


def slugify(name: str) -> str:
    romanized = _romanize(name)
    normalized = unicodedata.normalize("NFKD", romanized).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", normalized.lower()).strip("-")
    return slug[:60]


async def unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name) or "workspace"
    candidate = base
    suffix = 1
    while await session.scalar(select(Workspace.id).where(Workspace.slug == candidate)):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def create_workspace(session: AsyncSession, owner: User, name: str) -> Workspace:
    clean = name.strip()
    if not clean:
        raise conflict("workspace name is required")
    workspace = Workspace(
        id=new_id(WORKSPACE_PREFIX),
        name=clean,
        slug=await unique_slug(session, clean),
    )
    session.add(workspace)
    session.add(
        WorkspaceMembership(
            id=new_id(MEMBER_PREFIX),
            workspace_id=workspace.id,
            user_id=owner.id,
            role="owner",
        )
    )
    await session.flush()
    return workspace


async def get_workspace_or_404(session: AsyncSession, workspace_id: str) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise not_found("workspace not found")
    return workspace


async def list_workspaces(session: AsyncSession, user_id: str) -> list[Workspace]:
    rows = await session.scalars(
        select(Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(Workspace.created_at, Workspace.id)
    )
    return list(rows)


async def primary_workspace(session: AsyncSession, user_id: str) -> Workspace | None:
    rows = await session.scalars(
        select(Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(Workspace.created_at, Workspace.id)
    )
    return rows.first()


async def list_members(session: AsyncSession, workspace_id: str) -> list[MemberOut]:
    rows = await session.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.joined_at, WorkspaceMembership.id)
    )
    return [
        MemberOut(user=user, role=membership.role, joined_at=membership.joined_at)
        for membership, user in rows.all()
    ]


async def set_role(
    session: AsyncSession, membership: WorkspaceMembership, role: str
) -> WorkspaceMembership:
    if role not in ROLES:
        raise conflict(f"role must be one of {', '.join(ROLES)}")
    membership.role = role
    await session.flush()
    return membership


async def remove_member(session: AsyncSession, membership: WorkspaceMembership) -> None:
    await session.delete(membership)
    await session.flush()
