"""Schedule routes: the team calendar."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession, WorkspaceId, WorkspaceMember
from app.core.errors import forbidden, not_found
from app.models.schedule import RESPONSES
from app.realtime import events
from app.schemas.schedule import (
    AttendeeAdd,
    EventCreate,
    EventOut,
    EventUpdate,
    RsvpUpdate,
)
from app.services.members import is_manager
from app.services.schedule import (
    add_attendee,
    create_event,
    delete_event,
    event_audience,
    get_event_or_404,
    list_events,
    remove_attendee,
    require_event_access,
    serialize_events,
    set_response,
    update_event,
)

router = APIRouter(tags=["schedule"])


@router.get("/workspaces/{workspace_id}/events", response_model=list[EventOut])
async def read_events(
    workspace_id: WorkspaceId,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
) -> list[EventOut]:
    """The events the caller may see, inside the requested window."""
    events_in_window = await list_events(session, workspace_id, user.id, from_at, to_at)
    return await serialize_events(session, events_in_window, user.id)


@router.post("/workspaces/{workspace_id}/events", response_model=EventOut)
async def post_event(
    workspace_id: WorkspaceId,
    payload: EventCreate,
    user: CurrentUser,
    session: DbSession,
    membership: WorkspaceMember,
) -> EventOut:
    event = await create_event(
        session,
        workspace_id,
        user,
        payload.title,
        payload.starts_at,
        payload.ends_at,
        payload.description,
        payload.location,
        payload.all_day,
        payload.is_private,
        payload.channel_id,
        payload.attendee_ids,
    )
    await session.commit()
    await events.emit_event_created(session, event)
    rendered = await serialize_events(session, [event], user.id)
    return rendered[0]


@router.get("/events/{event_id}", response_model=EventOut)
async def read_event(
    event_id: str,
    user: CurrentUser,
    session: DbSession,
) -> EventOut:
    event = await get_event_or_404(session, event_id)
    await require_event_access(session, event, user.id)
    rendered = await serialize_events(session, [event], user.id)
    return rendered[0]


@router.patch("/events/{event_id}", response_model=EventOut)
async def patch_event(
    event_id: str,
    payload: EventUpdate,
    user: CurrentUser,
    session: DbSession,
) -> EventOut:
    event = await get_event_or_404(session, event_id)
    membership = await require_event_access(session, event, user.id)
    if event.created_by != user.id and not is_manager(membership):
        raise forbidden("only the creator or a workspace admin can change this event")

    data = payload.model_dump(exclude_unset=True)
    await update_event(session, event, data, event.workspace_id, user.id)
    await session.commit()
    await events.emit_event_updated(session, event)
    rendered = await serialize_events(session, [event], user.id)
    return rendered[0]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_event(
    event_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    event = await get_event_or_404(session, event_id)
    membership = await require_event_access(session, event, user.id)
    if event.created_by != user.id and not is_manager(membership):
        raise forbidden("only the creator or a workspace admin can delete this event")

    # The audience is read before the row goes away — a private event must
    # not announce its own deletion to the whole workspace.
    audience = await event_audience(session, event)
    await delete_event(session, event)
    await session.commit()
    await events.emit_event_deleted(audience, event.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/events/{event_id}/attendees", response_model=EventOut)
async def post_attendee(
    event_id: str,
    payload: AttendeeAdd,
    user: CurrentUser,
    session: DbSession,
) -> EventOut:
    event = await get_event_or_404(session, event_id)
    membership = await require_event_access(session, event, user.id)
    if event.created_by != user.id and not is_manager(membership):
        raise forbidden("only the creator or a workspace admin can invite people")

    await add_attendee(session, event, payload.user_id, event.workspace_id)
    await session.commit()
    await events.emit_event_updated(session, event)
    rendered = await serialize_events(session, [event], user.id)
    return rendered[0]


@router.delete("/events/{event_id}/attendees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attendee(
    event_id: str,
    user_id: str,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    event = await get_event_or_404(session, event_id)
    membership = await require_event_access(session, event, user.id)
    if event.created_by != user.id and not is_manager(membership):
        raise forbidden("only the creator or a workspace admin can change the guest list")
    if user_id == event.created_by:
        raise forbidden("the creator cannot be removed from their own event")

    await remove_attendee(session, event, user_id)
    await session.commit()
    await events.emit_event_updated(session, event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/events/{event_id}/rsvp", response_model=EventOut)
async def post_rsvp(
    event_id: str,
    payload: RsvpUpdate,
    user: CurrentUser,
    session: DbSession,
) -> EventOut:
    """Answer an invitation: accept, decline or mark it tentative."""
    if payload.response not in RESPONSES:
        raise not_found("unknown response")

    event = await get_event_or_404(session, event_id)
    await require_event_access(session, event, user.id)
    await set_response(session, event, user.id, payload.response)
    await session.commit()
    await events.emit_event_updated(session, event)
    rendered = await serialize_events(session, [event], user.id)
    return rendered[0]
