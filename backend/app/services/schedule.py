"""Schedule events: creation, visibility, attendees and serialisation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden, not_found, validation_error
from app.core.ids import ATTENDEE_PREFIX, EVENT_PREFIX, new_id
from app.models.channel import Channel
from app.models.schedule import (
    RESPONSE_ACCEPTED,
    RESPONSE_PENDING,
    ScheduleAttendee,
    ScheduleEvent,
)
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.schemas.schedule import AttendeeOut, EventOut
from app.services.members import workspace_member_ids

# A window that covers a working month either side of today. The client asks
# for the exact range it draws; this is only the fallback.
DEFAULT_LOOKBACK = timedelta(days=30)
DEFAULT_LOOKAHEAD = timedelta(days=180)


async def get_event_or_404(session: AsyncSession, event_id: str) -> ScheduleEvent:
    event = await session.get(ScheduleEvent, event_id)
    if event is None:
        raise not_found("event not found")
    return event


async def attendee_event_ids(session: AsyncSession, user_id: str) -> set[str]:
    rows = await session.scalars(
        select(ScheduleAttendee.event_id).where(ScheduleAttendee.user_id == user_id)
    )
    return set(rows.all())


async def can_view_event(session: AsyncSession, event: ScheduleEvent, user_id: str) -> bool:
    """True when the user may see this event at all.

    An open event belongs to the whole workspace; a private one to its
    creator and the people it invites.
    """
    if event.created_by == user_id:
        return True
    if not event.is_private:
        return True
    return event.id in await attendee_event_ids(session, user_id)


async def require_event_access(
    session: AsyncSession, event: ScheduleEvent, user_id: str
) -> WorkspaceMembership:
    """Load the caller's workspace membership and enforce event visibility."""
    membership = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == event.workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise forbidden("you are not a member of this workspace")
    if not await can_view_event(session, event, user_id):
        raise forbidden("you cannot see this event")
    return membership


def _validate_window(starts_at: datetime, ends_at: datetime) -> None:
    if ends_at < starts_at:
        raise validation_error("the event ends before it starts", "ends_at")


async def resolve_channel(
    session: AsyncSession, workspace_id: str, channel_id: str | None, user_id: str
) -> str | None:
    """Check that a linked channel exists and that the user may see it."""
    if not channel_id:
        return None
    channel = await session.get(Channel, channel_id)
    if channel is None or channel.workspace_id != workspace_id:
        raise validation_error("that channel does not belong to this workspace", "channel_id")
    if channel.is_private:
        member = await session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        if member is None:
            raise forbidden("you cannot see this channel")
    return channel_id


async def _sync_attendees(
    session: AsyncSession,
    event: ScheduleEvent,
    user_ids: list[str],
    workspace_id: str,
) -> None:
    """Replace the attendee list, keeping the responses that survive."""
    wanted = list(dict.fromkeys(user_ids))
    for user_id in wanted:
        member = await session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        if member is None:
            raise validation_error("an attendee is not a member of this workspace", "attendee_ids")

    existing = list(
        await session.scalars(select(ScheduleAttendee).where(ScheduleAttendee.event_id == event.id))
    )
    by_user = {row.user_id: row for row in existing}

    for user_id, row in by_user.items():
        if user_id not in wanted:
            await session.delete(row)

    for user_id in wanted:
        if user_id in by_user:
            continue
        session.add(
            ScheduleAttendee(
                id=new_id(ATTENDEE_PREFIX),
                event_id=event.id,
                user_id=user_id,
                response=RESPONSE_PENDING,
            )
        )
    await session.flush()


async def create_event(
    session: AsyncSession,
    workspace_id: str,
    creator: User,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    description: str = "",
    location: str = "",
    all_day: bool = False,
    is_private: bool = False,
    channel_id: str | None = None,
    attendee_ids: list[str] | None = None,
) -> ScheduleEvent:
    clean_title = title.strip()
    if not clean_title:
        raise validation_error("event title is required", "title")
    _validate_window(starts_at, ends_at)

    resolved_channel = await resolve_channel(session, workspace_id, channel_id, creator.id)

    event = ScheduleEvent(
        id=new_id(EVENT_PREFIX),
        workspace_id=workspace_id,
        title=clean_title,
        description=(description or "").strip(),
        location=(location or "").strip(),
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        is_private=is_private,
        created_by=creator.id,
        channel_id=resolved_channel,
    )
    session.add(event)
    await session.flush()

    # The creator is an attendee from the start — they made the plan.
    await _sync_attendees(
        session,
        event,
        [creator.id, *(attendee_ids or [])],
        workspace_id,
    )
    creator_row = await session.scalar(
        select(ScheduleAttendee).where(
            ScheduleAttendee.event_id == event.id,
            ScheduleAttendee.user_id == creator.id,
        )
    )
    if creator_row is not None:
        creator_row.response = RESPONSE_ACCEPTED
    await session.flush()
    return event


async def update_event(
    session: AsyncSession,
    event: ScheduleEvent,
    payload: dict,
    workspace_id: str,
    user_id: str,
) -> ScheduleEvent:
    data = payload

    if "title" in data and data["title"] is not None:
        clean = data["title"].strip()
        if not clean:
            raise validation_error("event title is required", "title")
        event.title = clean
    if "description" in data and data["description"] is not None:
        event.description = data["description"].strip()
    if "location" in data and data["location"] is not None:
        event.location = data["location"].strip()
    if "starts_at" in data and data["starts_at"] is not None:
        event.starts_at = data["starts_at"]
    if "ends_at" in data and data["ends_at"] is not None:
        event.ends_at = data["ends_at"]
    if "all_day" in data and data["all_day"] is not None:
        event.all_day = data["all_day"]
    if "is_private" in data and data["is_private"] is not None:
        event.is_private = data["is_private"]
    if "channel_id" in data:
        event.channel_id = await resolve_channel(session, workspace_id, data["channel_id"], user_id)

    _validate_window(event.starts_at, event.ends_at)
    await session.flush()

    if data.get("attendee_ids") is not None:
        # The creator is on their own roster — they made the plan.
        guests = list(data["attendee_ids"])
        if event.created_by not in guests:
            guests.append(event.created_by)
        await _sync_attendees(session, event, guests, workspace_id)
    return event


async def delete_event(session: AsyncSession, event: ScheduleEvent) -> None:
    await session.delete(event)
    await session.flush()


async def add_attendee(
    session: AsyncSession, event: ScheduleEvent, user_id: str, workspace_id: str
) -> ScheduleEvent:
    await _sync_attendees(
        session,
        event,
        [*(await _attendee_user_ids(session, event)), user_id],
        workspace_id,
    )
    return event


async def remove_attendee(session: AsyncSession, event: ScheduleEvent, user_id: str) -> None:
    row = await session.scalar(
        select(ScheduleAttendee).where(
            ScheduleAttendee.event_id == event.id,
            ScheduleAttendee.user_id == user_id,
        )
    )
    if row is None:
        return
    await session.delete(row)
    await session.flush()


async def set_response(
    session: AsyncSession, event: ScheduleEvent, user_id: str, response: str
) -> ScheduleEvent:
    """Record the caller's answer to an invitation."""
    row = await session.scalar(
        select(ScheduleAttendee).where(
            ScheduleAttendee.event_id == event.id,
            ScheduleAttendee.user_id == user_id,
        )
    )
    if row is None:
        # Answering an open event is allowed — you are joining it.
        session.add(
            ScheduleAttendee(
                id=new_id(ATTENDEE_PREFIX),
                event_id=event.id,
                user_id=user_id,
                response=response,
            )
        )
        await session.flush()
        return event
    row.response = response
    await session.flush()
    return event


async def _attendee_user_ids(session: AsyncSession, event: ScheduleEvent) -> list[str]:
    rows = await session.scalars(
        select(ScheduleAttendee.user_id).where(ScheduleAttendee.event_id == event.id)
    )
    return list(rows.all())


async def list_events(
    session: AsyncSession,
    workspace_id: str,
    viewer_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ScheduleEvent]:
    """Every event of the workspace the viewer may see, inside the window."""
    now = datetime.now(UTC)
    window_start = start or (now - DEFAULT_LOOKBACK)
    window_end = end or (now + DEFAULT_LOOKAHEAD)

    invited = await attendee_event_ids(session, viewer_id)
    visibility = [
        ScheduleEvent.is_private.is_(False),
        ScheduleEvent.created_by == viewer_id,
    ]
    if invited:
        visibility.append(ScheduleEvent.id.in_(invited))

    rows = await session.scalars(
        select(ScheduleEvent)
        .where(
            ScheduleEvent.workspace_id == workspace_id,
            ScheduleEvent.ends_at >= window_start,
            ScheduleEvent.starts_at <= window_end,
            or_(*visibility),
        )
        .order_by(ScheduleEvent.starts_at, ScheduleEvent.id)
    )
    return list(rows)


async def event_audience(session: AsyncSession, event: ScheduleEvent) -> set[str]:
    """Everyone who should receive live updates about this event."""
    if not event.is_private:
        return await workspace_member_ids(session, event.workspace_id)
    recipients = {event.created_by}
    recipients |= set(await _attendee_user_ids(session, event))
    return recipients


async def serialize_event(session: AsyncSession, event: ScheduleEvent, viewer_id: str) -> EventOut:
    result = await serialize_events(session, [event], viewer_id)
    return result[0]


async def serialize_events(
    session: AsyncSession, events: list[ScheduleEvent], viewer_id: str
) -> list[EventOut]:
    """Build the API representation of a batch of events for one viewer."""
    if not events:
        return []

    event_ids = [event.id for event in events]
    rows = await session.execute(
        select(ScheduleAttendee, User)
        .join(User, User.id == ScheduleAttendee.user_id)
        .where(ScheduleAttendee.event_id.in_(event_ids))
        .order_by(ScheduleAttendee.created_at, ScheduleAttendee.id)
    )
    by_event: dict[str, list[AttendeeOut]] = {}
    responses: dict[str, str] = {}
    for attendee, user in rows.all():
        by_event.setdefault(attendee.event_id, []).append(
            AttendeeOut(user=user, response=attendee.response)
        )
        if attendee.user_id == viewer_id:
            responses[attendee.event_id] = attendee.response

    return [
        EventOut(
            id=event.id,
            workspace_id=event.workspace_id,
            title=event.title,
            description=event.description,
            location=event.location,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            all_day=event.all_day,
            is_private=event.is_private,
            created_by=event.created_by,
            channel_id=event.channel_id,
            created_at=event.created_at,
            updated_at=event.updated_at,
            attendees=by_event.get(event.id, []),
            my_response=responses.get(event.id),
        )
        for event in events
    ]
