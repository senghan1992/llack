"""Server → client WebSocket events.

Every helper here works on the *audience* of a channel: the users that are
allowed to see the event.  Payloads that contain per-viewer data (the ``me``
flag of a reaction, the ``unread_count`` of a channel) are rendered once per
recipient so every client sees its own truth.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.channel import Channel
from app.models.message import Message
from app.models.project import Milestone, Project, Task
from app.models.schedule import ScheduleEvent
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.realtime.hub import hub
from app.schemas.user import UserOut
from app.services.channels import list_channel_members, serialize_channel
from app.services.members import channel_audience, workspace_member_ids
from app.services.messages import build_message_out, load_message_bundle, unread_counts
from app.services.projects import serialize_milestones, serialize_projects, serialize_tasks
from app.services.schedule import event_audience, serialize_event


async def emit_message_created(session: AsyncSession, channel: Channel, message: Message) -> None:
    api_prefix = get_settings().api_prefix
    bundle = await load_message_bundle(session, [message])
    audience = await channel_audience(session, channel)
    for viewer_id in audience:
        rendered = build_message_out(message, bundle, viewer_id, api_prefix)
        if rendered is None:
            continue
        await hub.send_to_user(
            viewer_id, {"type": "message.created", "message": rendered.model_dump(mode="json")}
        )
    await emit_unread_counts(session, channel)


async def emit_message_updated(session: AsyncSession, channel: Channel, message: Message) -> None:
    api_prefix = get_settings().api_prefix
    bundle = await load_message_bundle(session, [message])
    audience = await channel_audience(session, channel)
    for viewer_id in audience:
        rendered = build_message_out(message, bundle, viewer_id, api_prefix)
        if rendered is None:
            continue
        await hub.send_to_user(
            viewer_id, {"type": "message.updated", "message": rendered.model_dump(mode="json")}
        )


async def emit_message_deleted(session: AsyncSession, channel: Channel, message: Message) -> None:
    audience = await channel_audience(session, channel)
    await hub.send_to_users(
        audience,
        {
            "type": "message.deleted",
            "message_id": message.id,
            "channel_id": channel.id,
        },
    )


async def emit_reaction_updated(session: AsyncSession, channel: Channel, message: Message) -> None:
    api_prefix = get_settings().api_prefix
    bundle = await load_message_bundle(session, [message])
    audience = await channel_audience(session, channel)
    for viewer_id in audience:
        rendered = build_message_out(message, bundle, viewer_id, api_prefix)
        if rendered is None:
            continue
        await hub.send_to_user(
            viewer_id, {"type": "reaction.updated", "message": rendered.model_dump(mode="json")}
        )


async def emit_typing(session: AsyncSession, channel: Channel, user: User, on: bool) -> None:
    recipients = await channel_audience(session, channel)
    recipients.discard(user.id)
    await hub.send_to_users(
        recipients,
        {
            "type": "typing",
            "channel_id": channel.id,
            "user_id": user.id,
            "name": user.name,
            "on": on,
        },
    )


async def emit_presence(session: AsyncSession, user: User, presence: str) -> None:
    recipients: set[str] = set()
    for workspace_id in await user_workspace_ids(session, user.id):
        recipients |= await workspace_member_ids(session, workspace_id)
    recipients.discard(user.id)
    payload = {
        "type": "presence",
        "user_id": user.id,
        "presence": presence,
        "last_seen_at": user.last_seen_at.isoformat().replace("+00:00", "Z"),
    }
    await hub.send_to_users(recipients, payload)


async def emit_user_updated(session: AsyncSession, user: User) -> None:
    """Tell the team that somebody changed their profile."""
    recipients: set[str] = set()
    for workspace_id in await user_workspace_ids(session, user.id):
        recipients |= await workspace_member_ids(session, workspace_id)
    recipients.discard(user.id)
    payload = {
        "type": "user.updated",
        "user": UserOut.model_validate(user).model_dump(mode="json"),
    }
    await hub.send_to_users(recipients, payload)


async def emit_channel_created(session: AsyncSession, channel: Channel) -> None:
    recipients = await workspace_member_ids(session, channel.workspace_id)
    for viewer_id in recipients:
        payload = await serialize_channel(session, channel, viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "channel.created", "channel": payload.model_dump(mode="json")}
        )


async def emit_channel_updated(session: AsyncSession, channel: Channel) -> None:
    audience = await channel_audience(session, channel)
    for viewer_id in audience:
        payload = await serialize_channel(session, channel, viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "channel.updated", "channel": payload.model_dump(mode="json")}
        )


async def emit_members_changed(session: AsyncSession, channel: Channel) -> None:
    audience = await channel_audience(session, channel)
    members = await list_channel_members(session, channel)
    payload_members = [member.user.model_dump(mode="json") for member in members]
    await hub.send_to_users(
        audience,
        {"type": "members.changed", "channel_id": channel.id, "members": payload_members},
    )


async def emit_event_created(session: AsyncSession, event: ScheduleEvent) -> None:
    for viewer_id in await event_audience(session, event):
        rendered = await serialize_event(session, event, viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "event.created", "event": rendered.model_dump(mode="json")}
        )


async def emit_event_updated(session: AsyncSession, event: ScheduleEvent) -> None:
    for viewer_id in await event_audience(session, event):
        rendered = await serialize_event(session, event, viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "event.updated", "event": rendered.model_dump(mode="json")}
        )


async def emit_event_deleted(recipients: set[str], event_id: str) -> None:
    await hub.send_to_users(recipients, {"type": "event.deleted", "event_id": event_id})


async def emit_project_created(session: AsyncSession, project: Project) -> None:
    """A project is open to the whole workspace, so the whole team hears."""
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_projects(session, [project], viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "project.created", "project": rendered[0].model_dump(mode="json")}
        )


async def emit_project_updated(session: AsyncSession, project: Project) -> None:
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_projects(session, [project], viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "project.updated", "project": rendered[0].model_dump(mode="json")}
        )


async def emit_project_deleted(session: AsyncSession, project: Project) -> None:
    recipients = await workspace_member_ids(session, project.workspace_id)
    await hub.send_to_users(recipients, {"type": "project.deleted", "project_id": project.id})


async def emit_task_created(session: AsyncSession, project: Project, task: Task) -> None:
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_tasks(session, [task], viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "task.created", "task": rendered[0].model_dump(mode="json")}
        )


async def emit_task_updated(session: AsyncSession, project: Project, task: Task) -> None:
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_tasks(session, [task], viewer_id)
        await hub.send_to_user(
            viewer_id, {"type": "task.updated", "task": rendered[0].model_dump(mode="json")}
        )


async def emit_task_deleted(session: AsyncSession, project: Project, task: Task) -> None:
    recipients = await workspace_member_ids(session, project.workspace_id)
    await hub.send_to_users(
        recipients,
        {"type": "task.deleted", "project_id": project.id, "task_id": task.id},
    )


async def emit_milestone_created(
    session: AsyncSession, project: Project, milestone: Milestone
) -> None:
    """A milestone sits on a project, so the whole workspace hears about it."""
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_milestones(session, [milestone])
        await hub.send_to_user(
            viewer_id,
            {"type": "milestone.created", "milestone": rendered[0].model_dump(mode="json")},
        )


async def emit_milestone_updated(
    session: AsyncSession, project: Project, milestone: Milestone
) -> None:
    for viewer_id in await workspace_member_ids(session, project.workspace_id):
        rendered = await serialize_milestones(session, [milestone])
        await hub.send_to_user(
            viewer_id,
            {"type": "milestone.updated", "milestone": rendered[0].model_dump(mode="json")},
        )


async def emit_milestone_deleted(
    session: AsyncSession, project: Project, milestone: Milestone
) -> None:
    recipients = await workspace_member_ids(session, project.workspace_id)
    await hub.send_to_users(
        recipients,
        {"type": "milestone.deleted", "milestone_id": milestone.id},
    )


async def emit_org_changed(session: AsyncSession, workspace_id: str) -> None:
    """The organization tree changed — everyone in the workspace may need to know."""
    recipients = await workspace_member_ids(session, workspace_id)
    await hub.send_to_users(
        recipients,
        {"type": "org.changed", "workspace_id": workspace_id},
    )


async def emit_unread_counts(session: AsyncSession, channel: Channel) -> None:
    audience = await channel_audience(session, channel)
    for viewer_id in audience:
        counts = await unread_counts(session, [channel.id], viewer_id)
        await hub.send_to_user(
            viewer_id,
            {"type": "unread", "channel_id": channel.id, "count": counts.get(channel.id, 0)},
        )


async def user_workspace_ids(session: AsyncSession, user_id: str) -> list[str]:
    rows = await session.scalars(
        select(WorkspaceMembership.workspace_id).where(WorkspaceMembership.user_id == user_id)
    )
    return list(rows.all())
