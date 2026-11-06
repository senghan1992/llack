"""The organization of a workspace: the units people are arranged in.

A workspace is one company, but a company is not one shape. So a workspace
holds a tree of **org units** — 부서, 팀, whatever the team calls them — and
people sit in them. A unit knows its parent, so the tree is drawn from
``parent_id``.

Who looks after a unit is a second thing: the people appointed to manage it.
An org unit manager may look after their own unit and everything below it.
The workspace owner and the workspace admins look after everything, and they
appoint the unit managers.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow


class OrgUnit(Base):
    """One unit of the organization's tree."""

    __tablename__ = "org_units"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # The unit above this one. None means the unit sits at the top.
    parent_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("org_units.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # A free label the workspace picks for itself: "부서", "팀", anything.
    kind: Mapped[str] = mapped_column(String(24), default="team")
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    members: Mapped[list[OrgUnitMember]] = relationship(
        back_populates="unit", cascade="all, delete-orphan"
    )
    managers: Mapped[list[OrgUnitManager]] = relationship(
        back_populates="unit", cascade="all, delete-orphan"
    )


class OrgUnitMember(Base):
    """The people who belong to a unit."""

    __tablename__ = "org_unit_members"
    __table_args__ = (UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_member"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_unit_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("org_units.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    unit: Mapped[OrgUnit] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="org_memberships")  # noqa: F821


class OrgUnitManager(Base):
    """The people appointed to look after a unit.

    The appointment carries its own authority: a manager may look after the
    unit and every unit below it.
    """

    __tablename__ = "org_unit_managers"
    __table_args__ = (UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_manager"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_unit_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("org_units.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    appointed_by: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    unit: Mapped[OrgUnit] = relationship(back_populates="managers")
    user: Mapped[User] = relationship(  # noqa: F821
        back_populates="org_appointments", foreign_keys=[user_id]
    )
