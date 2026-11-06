"""The organization of a workspace: the units, the people in them, the managers.

A workspace is one company, but a company is not one shape — so the team
draws its own: a tree of **org units** and the people who sit in them.

Two tiers of authority live here, and only here:

* the workspace role — the owner and the admins, who may do anything inside
  the workspace;
* the scoped one — a person appointed to look after an org unit looks after
  that unit **and everything below it**.

Every route asks the same question through :func:`managed_unit_ids`, so the
server — never the screen — decides what a person may touch.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict, forbidden, not_found, validation_error
from app.core.ids import ORG_MANAGER_PREFIX, ORG_MEMBER_PREFIX, ORG_UNIT_PREFIX, new_id
from app.models.org import OrgUnit as OrgUnitRow
from app.models.org import OrgUnitManager, OrgUnitMember
from app.models.user import User
from app.models.workspace import ROLE_ADMIN, ROLE_OWNER, WorkspaceMembership
from app.schemas.org import OrgOverview, OrgSummary, OrgUnit
from app.schemas.user import UserOut
from app.services.members import is_manager
from app.services.workspaces import list_members

# How deep the tree may be walked. A cycle in the data must not hang the
# server, so every walk stops here.
MAX_TREE_DEPTH = 50


async def is_workspace_manager(membership: WorkspaceMembership) -> bool:
    """Whether the caller may act for the whole workspace."""
    return is_manager(membership)


async def list_units(session: AsyncSession, workspace_id: str) -> list[OrgUnitRow]:
    """Every unit of the workspace, in the order they are shown."""
    rows = await session.scalars(
        select(OrgUnitRow)
        .where(OrgUnitRow.workspace_id == workspace_id)
        .order_by(OrgUnitRow.position, OrgUnitRow.created_at, OrgUnitRow.id)
    )
    return list(rows)


async def get_unit_or_404(session: AsyncSession, unit_id: str) -> OrgUnitRow:
    unit = await session.get(OrgUnitRow, unit_id)
    if unit is None:
        raise not_found("조직을 찾을 수 없습니다")
    return unit


async def managed_unit_ids(
    session: AsyncSession,
    workspace_id: str,
    user_id: str,
    membership: WorkspaceMembership,
) -> set[str]:
    """Every unit the user may look after: the units they manage plus all
    their descendants. A workspace owner or admin manages everything."""
    if is_manager(membership):
        rows = await session.scalars(
            select(OrgUnitRow.id).where(OrgUnitRow.workspace_id == workspace_id)
        )
        return set(rows.all())

    managed = await session.scalars(
        select(OrgUnitRow.id)
        .join(OrgUnitManager, OrgUnitManager.org_unit_id == OrgUnitRow.id)
        .where(
            OrgUnitRow.workspace_id == workspace_id,
            OrgUnitManager.user_id == user_id,
        )
    )
    roots = set(managed.all())
    if not roots:
        return set()

    units = await list_units(session, workspace_id)
    by_id = {unit.id: unit for unit in units}
    scope = set(roots)
    for unit in units:
        if unit.id in roots:
            continue
        # Walk the parents up: a unit belongs to the scope when one of the
        # units above it is managed.
        current = unit.parent_id
        seen: set[str] = set()
        depth = 0
        while current and current not in seen and depth < MAX_TREE_DEPTH:
            if current in roots:
                scope.add(unit.id)
                break
            seen.add(current)
            depth += 1
            parent = by_id.get(current)
            current = parent.parent_id if parent else None
    return scope


def require_scope(unit: OrgUnitRow, scope: set[str]) -> None:
    """The one rule every changing route asks before it touches a unit."""
    if unit.id not in scope:
        raise forbidden("이 조직을 관리할 권한이 없습니다")


async def create_unit(
    session: AsyncSession,
    workspace_id: str,
    creator: User,
    membership: WorkspaceMembership,
    scope: set[str],
    name: str,
    parent_id: str | None = None,
    kind: str = "team",
    description: str = "",
) -> OrgUnitRow:
    """Open a new unit — at the top, or under a unit the caller looks after."""
    clean_name = name.strip()
    if not clean_name:
        raise validation_error("조직 이름이 필요합니다", "name")

    if parent_id is None:
        # The top of the tree belongs to the workspace admins alone.
        if not is_manager(membership):
            raise forbidden("최상위 조직은 워크스페이스 관리자만 만들 수 있습니다")
    else:
        parent = await get_unit_or_404(session, parent_id)
        if parent.workspace_id != workspace_id:
            raise not_found("상위 조직을 찾을 수 없습니다")
        require_scope(parent, scope)

    unit = OrgUnitRow(
        id=new_id(ORG_UNIT_PREFIX),
        workspace_id=workspace_id,
        parent_id=parent_id,
        name=clean_name,
        kind=(kind or "team").strip() or "team",
        description=(description or "").strip(),
        position=0,
        created_by=creator.id,
    )
    session.add(unit)
    await session.flush()
    return unit


async def update_unit(
    session: AsyncSession,
    unit: OrgUnitRow,
    membership: WorkspaceMembership,
    scope: set[str],
    payload: dict,
) -> OrgUnitRow:
    """Rename a unit, write about it, or hang it under another one."""
    require_scope(unit, scope)

    if "name" in payload and payload["name"] is not None:
        clean = payload["name"].strip()
        if not clean:
            raise validation_error("조직 이름이 필요합니다", "name")
        unit.name = clean
    if "kind" in payload and payload["kind"] is not None:
        unit.kind = payload["kind"].strip() or "team"
    if "description" in payload and payload["description"] is not None:
        unit.description = payload["description"].strip()
    if "parent_id" in payload and payload["parent_id"] != unit.parent_id:
        await _move_unit(session, unit, membership, scope, payload["parent_id"])

    await session.flush()
    return unit


async def _move_unit(
    session: AsyncSession,
    unit: OrgUnitRow,
    membership: WorkspaceMembership,
    scope: set[str],
    new_parent_id: str | None,
) -> None:
    """Hang a unit under another one — without folding the tree onto itself."""
    if new_parent_id is None:
        # The top of the tree belongs to the workspace admins alone.
        if not is_manager(membership):
            raise forbidden("최상위 조직으로 옮기는 것은 워크스페이스 관리자만 할 수 있습니다")
        unit.parent_id = None
        return

    if new_parent_id == unit.id:
        raise conflict("조직은 자기 아래로 옮길 수 없습니다")

    parent = await get_unit_or_404(session, new_parent_id)
    if parent.workspace_id != unit.workspace_id:
        raise not_found("상위 조직을 찾을 수 없습니다")
    if await _is_descendant(session, unit.id, new_parent_id):
        raise conflict("조직을 자기 하위 조직 아래로 옮길 수 없습니다")
    require_scope(parent, scope)
    unit.parent_id = new_parent_id


async def _is_descendant(session: AsyncSession, ancestor_id: str, candidate_id: str) -> bool:
    """Whether a unit sits below another one."""
    current = candidate_id
    seen: set[str] = set()
    depth = 0
    while current and current not in seen and depth < MAX_TREE_DEPTH:
        if current == ancestor_id:
            return True
        seen.add(current)
        unit = await session.get(OrgUnitRow, current)
        current = unit.parent_id if unit else None
        depth += 1
    return False


async def delete_unit(session: AsyncSession, unit: OrgUnitRow, scope: set[str]) -> None:
    """Take a unit away — but only when it is empty.

    People and child units are moved somewhere else first: an organization
    that loses its people by accident is worse than one that keeps a unit
    too long.
    """
    require_scope(unit, scope)
    children = await session.scalar(
        select(func.count(OrgUnitRow.id)).where(OrgUnitRow.parent_id == unit.id)
    )
    if children:
        raise conflict("하위 조직이 있는 조직은 삭제할 수 없습니다")
    people = await session.scalar(
        select(func.count(OrgUnitMember.id)).where(OrgUnitMember.org_unit_id == unit.id)
    )
    if people:
        raise conflict("멤버가 있는 조직은 삭제할 수 없습니다")

    # The unit's own manager rows go with it.
    await session.delete(unit)
    await session.flush()


async def add_unit_member(
    session: AsyncSession,
    unit: OrgUnitRow,
    user_id: str,
    workspace_id: str,
    scope: set[str],
) -> None:
    """Put a person into a unit. Doing it twice changes nothing."""
    require_scope(unit, scope)
    membership = await session.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise not_found("이 사람은 이 워크스페이스의 멤버가 아닙니다")

    existing = await session.scalar(
        select(OrgUnitMember.id).where(
            OrgUnitMember.org_unit_id == unit.id,
            OrgUnitMember.user_id == user_id,
        )
    )
    if existing is not None:
        return

    session.add(
        OrgUnitMember(
            id=new_id(ORG_MEMBER_PREFIX),
            org_unit_id=unit.id,
            user_id=user_id,
        )
    )
    await session.flush()


async def remove_unit_member(
    session: AsyncSession, unit: OrgUnitRow, user_id: str, scope: set[str]
) -> None:
    """Take a person out of a unit."""
    require_scope(unit, scope)
    row = await session.scalar(
        select(OrgUnitMember).where(
            OrgUnitMember.org_unit_id == unit.id,
            OrgUnitMember.user_id == user_id,
        )
    )
    if row is None:
        return
    await session.delete(row)
    await session.flush()


async def appoint_manager(
    session: AsyncSession,
    unit: OrgUnitRow,
    user_id: str,
    appointed_by: User,
    workspace_id: str,
    scope: set[str],
    membership: WorkspaceMembership,
) -> None:
    """Appoint a person to look after a unit."""
    require_scope(unit, scope)
    if user_id == appointed_by.id and not is_manager(membership):
        # A unit manager gains nothing by appointing themselves: they already
        # look after everything below their own unit. A workspace admin may
        # put their own name on a unit — they often run one.
        raise forbidden("이미 관리 중인 조직이므로 다시 지정할 수 없습니다")

    membership = await session.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise not_found("이 사람은 이 워크스페이스의 멤버가 아닙니다")

    existing = await session.scalar(
        select(OrgUnitManager.id).where(
            OrgUnitManager.org_unit_id == unit.id,
            OrgUnitManager.user_id == user_id,
        )
    )
    if existing is not None:
        return

    session.add(
        OrgUnitManager(
            id=new_id(ORG_MANAGER_PREFIX),
            org_unit_id=unit.id,
            user_id=user_id,
            appointed_by=appointed_by.id,
        )
    )
    await session.flush()


async def dismiss_manager(
    session: AsyncSession, unit: OrgUnitRow, user_id: str, scope: set[str]
) -> None:
    """Take the appointment away. A manager may do this to themselves."""
    require_scope(unit, scope)
    row = await session.scalar(
        select(OrgUnitManager).where(
            OrgUnitManager.org_unit_id == unit.id,
            OrgUnitManager.user_id == user_id,
        )
    )
    if row is None:
        return
    await session.delete(row)
    await session.flush()


# ── serialisation ────────────────────────────────────────────────────────


def _tree_shape(units: list[OrgUnitRow]) -> tuple[dict[str, int], dict[str, int]]:
    """How many children and how deep every unit of a tree is."""
    by_id = {unit.id: unit for unit in units}
    child_counts: dict[str, int] = {}
    for unit in units:
        if unit.parent_id:
            child_counts[unit.parent_id] = child_counts.get(unit.parent_id, 0) + 1

    depths: dict[str, int] = {}
    for unit in units:
        depth = 0
        current = unit.parent_id
        seen: set[str] = set()
        while current and current not in seen and depth < MAX_TREE_DEPTH:
            seen.add(current)
            depth += 1
            parent = by_id.get(current)
            current = parent.parent_id if parent else None
        depths[unit.id] = depth
    return child_counts, depths


async def serialize_units(
    session: AsyncSession, units: list[OrgUnitRow], scope: set[str], viewer_id: str
) -> list[OrgUnit]:
    """The API shape of a batch of units, for one reader."""
    if not units:
        return []

    workspace_id = units[0].workspace_id
    all_units = await list_units(session, workspace_id)
    child_counts, depths = _tree_shape(all_units)
    unit_ids = [unit.id for unit in units]

    rosters = await session.execute(
        select(OrgUnitMember, User)
        .join(User, User.id == OrgUnitMember.user_id)
        .where(OrgUnitMember.org_unit_id.in_(unit_ids))
        .order_by(OrgUnitMember.joined_at, OrgUnitMember.id)
    )
    members: dict[str, list[User]] = {}
    for member, user in rosters.all():
        members.setdefault(member.org_unit_id, []).append(user)

    managers = await session.execute(
        select(OrgUnitManager, User)
        .join(User, User.id == OrgUnitManager.user_id)
        .where(OrgUnitManager.org_unit_id.in_(unit_ids))
        .order_by(OrgUnitManager.created_at, OrgUnitManager.id)
    )
    appointed: dict[str, list[User]] = {}
    for manager, user in managers.all():
        appointed.setdefault(manager.org_unit_id, []).append(user)

    return [
        OrgUnit(
            id=unit.id,
            workspace_id=unit.workspace_id,
            parent_id=unit.parent_id,
            name=unit.name,
            kind=unit.kind,
            description=unit.description,
            position=unit.position,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
            member_count=len(members.get(unit.id, [])),
            child_count=child_counts.get(unit.id, 0),
            depth=depths.get(unit.id, 0),
            members=[UserOut.model_validate(user) for user in members.get(unit.id, [])],
            managers=[UserOut.model_validate(user) for user in appointed.get(unit.id, [])],
            is_manager=any(manager.id == viewer_id for manager in appointed.get(unit.id, [])),
            can_manage=unit.id in scope,
            can_appoint_managers=unit.id in scope,
        )
        for unit in units
    ]


async def serialize_overview(
    session: AsyncSession,
    workspace_id: str,
    user_id: str,
    membership: WorkspaceMembership,
) -> OrgOverview:
    """The whole organization of a workspace, for one reader."""
    units = await list_units(session, workspace_id)
    scope = await managed_unit_ids(session, workspace_id, user_id, membership)
    people = await list_members(session, workspace_id)
    return OrgOverview(
        units=await serialize_units(session, units, scope, user_id),
        admins=[person for person in people if person.role in (ROLE_OWNER, ROLE_ADMIN)],
        my_role=membership.role,
        can_manage_admins=is_manager(membership),
        managed_unit_ids=sorted(scope),
    )


async def org_summary(
    session: AsyncSession,
    workspace_id: str,
    user_id: str,
    membership: WorkspaceMembership,
) -> OrgSummary:
    """The little of the organization that comes with the bootstrap."""
    units = await list_units(session, workspace_id)
    scope = await managed_unit_ids(session, workspace_id, user_id, membership)
    return OrgSummary(unit_count=len(units), managed_unit_ids=sorted(scope))
