"""첫 스키마 — 이 프로젝트의 모든 테이블.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-14 14:37:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

import app.models.base


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("status_text", sa.String(length=120), nullable=True),
        sa.Column("avatar_color", sa.String(length=16), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("presence", sa.String(length=16), nullable=False),
        sa.Column("last_seen_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_presence"), ["presence"], unique=False)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workspaces_slug"), ["slug"], unique=True)

    op.create_table(
        "channels",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("dm_key", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dm_key"),
    )
    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_channels_kind"), ["kind"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_channels_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "files",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("mime", sa.String(length=150), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_files_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_files_workspace_id"), ["workspace_id"], unique=False)

    op.create_table(
        "invites",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=40), nullable=True),
        sa.Column("revoked_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invites_email"), ["email"], unique=False)
        batch_op.create_index(batch_op.f("ix_invites_token"), ["token"], unique=True)
        batch_op.create_index(batch_op.f("ix_invites_workspace_id"), ["workspace_id"], unique=False)

    op.create_table(
        "org_units",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("parent_id", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["org_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("org_units", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_org_units_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_org_units_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )
    with op.batch_alter_table("workspace_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_memberships_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_workspace_memberships_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "channel_memberships",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("joined_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),
    )
    with op.batch_alter_table("channel_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_channel_memberships_channel_id"), ["channel_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_channel_memberships_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_body", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("parent_id", sa.String(length=40), nullable=True),
        sa.Column("reply_to_id", sa.String(length=40), nullable=True),
        sa.Column("inline", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("edited_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("reply_count", sa.Integer(), nullable=False),
        sa.Column("last_reply_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reply_to_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_messages_channel_id"), ["channel_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_user_id"), ["user_id"], unique=False)

    op.create_table(
        "org_unit_managers",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_unit_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("appointed_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["appointed_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_manager"),
    )
    with op.batch_alter_table("org_unit_managers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_org_unit_managers_org_unit_id"), ["org_unit_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_org_unit_managers_user_id"), ["user_id"], unique=False)

    op.create_table(
        "org_unit_members",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_unit_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("joined_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_member"),
    )
    with op.batch_alter_table("org_unit_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_org_unit_members_org_unit_id"), ["org_unit_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_org_unit_members_user_id"), ["user_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("deliverables", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_projects_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "read_states",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("last_read_message_id", sa.String(length=40), nullable=True),
        sa.Column("last_read_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "user_id", name="uq_read_state"),
    )
    with op.batch_alter_table("read_states", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_read_states_channel_id"), ["channel_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_read_states_user_id"), ["user_id"], unique=False)

    op.create_table(
        "schedule_events",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("starts_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("ends_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("channel_id", sa.String(length=40), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("schedule_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_schedule_events_starts_at"), ["starts_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_events_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "message_attachments",
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("file_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id", "file_id"),
    )
    op.create_table(
        "milestones",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("start_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("end_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("milestones", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_milestones_project_id"), ["project_id"], unique=False)

    op.create_table(
        "project_members",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    with op.batch_alter_table("project_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_members_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_project_members_user_id"), ["user_id"], unique=False)

    op.create_table(
        "reactions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("emoji", sa.String(length=32), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),
    )
    with op.batch_alter_table("reactions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reactions_message_id"), ["message_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reactions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "roadmaps",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("roadmaps", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_roadmaps_project_id"), ["project_id"], unique=False)

    op.create_table(
        "schedule_attendees",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("response", sa.String(length=16), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["schedule_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_attendee"),
    )
    with op.batch_alter_table("schedule_attendees", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_schedule_attendees_event_id"), ["event_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_schedule_attendees_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assignee_id", sa.String(length=40), nullable=True),
        sa.Column("roadmap_id", sa.String(length=40), nullable=True),
        sa.Column("milestone_id", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("start_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("due_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_assignee_id"), ["assignee_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_milestone_id"), ["milestone_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_roadmap_id"), ["roadmap_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_status"), ["status"], unique=False)

    op.create_table(
        "task_comments",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("task_comments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_task_comments_task_id"), ["task_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("task_comments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_task_comments_task_id"))

    op.drop_table("task_comments")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_status"))
        batch_op.drop_index(batch_op.f("ix_tasks_roadmap_id"))
        batch_op.drop_index(batch_op.f("ix_tasks_project_id"))
        batch_op.drop_index(batch_op.f("ix_tasks_milestone_id"))
        batch_op.drop_index(batch_op.f("ix_tasks_assignee_id"))

    op.drop_table("tasks")
    with op.batch_alter_table("schedule_attendees", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_schedule_attendees_user_id"))
        batch_op.drop_index(batch_op.f("ix_schedule_attendees_event_id"))

    op.drop_table("schedule_attendees")
    with op.batch_alter_table("roadmaps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_roadmaps_project_id"))

    op.drop_table("roadmaps")
    with op.batch_alter_table("reactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reactions_user_id"))
        batch_op.drop_index(batch_op.f("ix_reactions_message_id"))

    op.drop_table("reactions")
    with op.batch_alter_table("project_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_project_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_project_members_project_id"))

    op.drop_table("project_members")
    with op.batch_alter_table("milestones", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_milestones_project_id"))

    op.drop_table("milestones")
    op.drop_table("message_attachments")
    with op.batch_alter_table("schedule_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_schedule_events_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_schedule_events_starts_at"))

    op.drop_table("schedule_events")
    with op.batch_alter_table("read_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_read_states_user_id"))
        batch_op.drop_index(batch_op.f("ix_read_states_channel_id"))

    op.drop_table("read_states")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_workspace_id"))

    op.drop_table("projects")
    with op.batch_alter_table("org_unit_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_org_unit_members_user_id"))
        batch_op.drop_index(batch_op.f("ix_org_unit_members_org_unit_id"))

    op.drop_table("org_unit_members")
    with op.batch_alter_table("org_unit_managers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_org_unit_managers_user_id"))
        batch_op.drop_index(batch_op.f("ix_org_unit_managers_org_unit_id"))

    op.drop_table("org_unit_managers")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_user_id"))
        batch_op.drop_index(batch_op.f("ix_messages_parent_id"))
        batch_op.drop_index(batch_op.f("ix_messages_created_at"))
        batch_op.drop_index(batch_op.f("ix_messages_channel_id"))

    op.drop_table("messages")
    with op.batch_alter_table("channel_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channel_memberships_user_id"))
        batch_op.drop_index(batch_op.f("ix_channel_memberships_channel_id"))

    op.drop_table("channel_memberships")
    with op.batch_alter_table("workspace_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspace_memberships_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_workspace_memberships_user_id"))

    op.drop_table("workspace_memberships")
    with op.batch_alter_table("org_units", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_org_units_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_org_units_parent_id"))

    op.drop_table("org_units")
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invites_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_invites_token"))
        batch_op.drop_index(batch_op.f("ix_invites_email"))

    op.drop_table("invites")
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_files_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_files_owner_id"))

    op.drop_table("files")
    with op.batch_alter_table("channels", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_channels_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_channels_kind"))

    op.drop_table("channels")
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workspaces_slug"))

    op.drop_table("workspaces")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_presence"))
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
