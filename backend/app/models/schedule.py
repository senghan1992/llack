"""Schedule events and their attendees.

A schedule belongs to a workspace. Most events are open to the whole team;
a private one is visible only to its creator and the people it invites.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

RESPONSE_PENDING = "pending"
RESPONSE_ACCEPTED = "accepted"
RESPONSE_DECLINED = "declined"
RESPONSE_TENTATIVE = "tentative"
RESPONSES = (RESPONSE_PENDING, RESPONSE_ACCEPTED, RESPONSE_DECLINED, RESPONSE_TENTATIVE)


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    channel_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    attendees: Mapped[list[ScheduleAttendee]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class ScheduleAttendee(Base):
    __tablename__ = "schedule_attendees"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_attendee"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("schedule_events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    response: Mapped[str] = mapped_column(String(16), default=RESPONSE_PENDING)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    event: Mapped[ScheduleEvent] = relationship(back_populates="attendees")
