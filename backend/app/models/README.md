# SQLAlchemy ORM Models

## Overview

The persistence layer: 22 tables described with SQLAlchemy 2.0 declarative
mappings on a single `Base`. All primary keys are application-generated
`String(40)` strings (ULID-with-prefix, see `app.core.ids`), never database
sequences. Every timestamp column uses the `UTCDateTime` type decorator, so all
stored datetimes round-trip as timezone-aware UTC.

`app.core.db` drives DDL straight from this metadata (`create_all`,
`ensure_columns`, `ensure_schema`) — there is no separate migration tool in this
project.

## Interface

### Base (`base.py`)

- `Base` — declarative base class for every Llack table
  [backend/app/models/base.py:Base]
- `utcnow()` — helper returning `datetime.now(UTC)`
  [backend/app/models/base.py:utcnow]
- `UTCDateTime` — `TypeDecorator[datetime]` with `impl = DateTime(timezone=True)`
  and `cache_ok = True`; normalises naive datetimes to UTC on bind and re-tags
  naive results as UTC on read [backend/app/models/base.py:UTCDateTime]
- `Base.metadata` — the DDL for all 22 tables
  [backend/app/models/base.py:Base.metadata]
- Package re-exports every model plus `message_attachments`
  [backend/app/models/__init__.py:__all__]

### Identity and workspace

- `User` — `__tablename__ = "users"`; columns `id`, `email`, `password_hash`,
  `name`, `title`, `status_text`, `avatar_color`, `avatar_url`, `presence`,
  `last_seen_at`, `created_at`; relationships `memberships`,
  `channel_memberships`, `org_memberships`, `org_appointments`
  [backend/app/models/user.py:User]
- `PRESENCE_ONLINE/BUSY/AWAY/DND/BRB/OFFLINE` and `PRESENCE_CLAIMED = (busy,
  dnd, away, brb)` — the subset a user may set for themselves
  [backend/app/models/user.py:PRESENCE_CLAIMED]
- `Workspace` — `__tablename__ = "workspaces"`; columns `id`, `name`, `slug`,
  `created_at`; relationship `memberships`
  [backend/app/models/workspace.py:Workspace]
- `WorkspaceMembership` — `__tablename__ = "workspace_memberships"`; columns
  `id`, `workspace_id`, `user_id`, `role`, `joined_at`
  [backend/app/models/workspace.py:WorkspaceMembership]
- `ROLE_OWNER = "owner"`, `ROLE_ADMIN = "admin"`, `ROLE_MEMBER = "member"`,
  `ROLES = (owner, admin, member)` [backend/app/models/workspace.py:ROLES]

### Channels, messages and files

- `Channel` — `__tablename__ = "channels"`; columns `id`, `workspace_id`,
  `name`, `topic`, `purpose`, `kind`, `is_private`, `created_by`, `created_at`,
  `dm_key`; relationship `members` [backend/app/models/channel.py:Channel]
- `KIND_CHANNEL = "channel"`, `KIND_DM = "dm"`
  [backend/app/models/channel.py:KIND_CHANNEL]
- `ChannelMember` — `__tablename__ = "channel_memberships"`; columns `id`,
  `channel_id`, `user_id`, `joined_at` [backend/app/models/channel.py:ChannelMember]
- `Message` — `__tablename__ = "messages"`; columns `id`, `channel_id`,
  `user_id`, `body`, `deleted_body`, `kind`, `parent_id`, `reply_to_id`,
  `inline`, `created_at`, `edited_at`, `deleted_at`, `pinned`, `reply_count`,
  `last_reply_at`; relationships `author` (viewonly), `attachments` (viewonly)
  [backend/app/models/message.py:Message]
- `KIND_TEXT = "text"`, `KIND_SYSTEM = "system"`
  [backend/app/models/message.py:KIND_TEXT]
- `message_attachments` — association table with composite PK
  (`message_id`, `file_id`) [backend/app/models/message.py:message_attachments]
- `Reaction` — `__tablename__ = "reactions"`; columns `id`, `message_id`,
  `user_id`, `emoji`, `created_at` [backend/app/models/message.py:Reaction]
- `ReadState` — `__tablename__ = "read_states"`; columns `id`, `channel_id`,
  `user_id`, `last_read_message_id`, `last_read_at`
  [backend/app/models/message.py:ReadState]
- `File` — `__tablename__ = "files"`; columns `id`, `name`, `mime`, `size`,
  `owner_id`, `workspace_id`, `storage_path`, `created_at`
  [backend/app/models/file.py:File]

### Invites

- `Invite` — `__tablename__ = "invites"`; columns `id`, `workspace_id`,
  `email`, `role`, `token`, `created_by`, `created_at`, `expires_at`,
  `accepted_at`, `accepted_by`, `revoked_at`
  [backend/app/models/invite.py:Invite]
- `INVITE_TTL_DAYS = 7` and `default_expiry()` = `utcnow() + 7 days`
  [backend/app/models/invite.py:INVITE_TTL_DAYS]

### Organization

- `OrgUnit` — `__tablename__ = "org_units"`; columns `id`, `workspace_id`,
  `parent_id`, `name`, `kind`, `description`, `position`, `created_by`,
  `created_at`, `updated_at`; relationships `members`, `managers`
  [backend/app/models/org.py:OrgUnit]
- `OrgUnitMember` — `__tablename__ = "org_unit_members"`; columns `id`,
  `org_unit_id`, `user_id`, `joined_at` [backend/app/models/org.py:OrgUnitMember]
- `OrgUnitManager` — `__tablename__ = "org_unit_managers"`; columns `id`,
  `org_unit_id`, `user_id`, `appointed_by`, `created_at`
  [backend/app/models/org.py:OrgUnitManager]

### Projects, tasks and milestones

- `Project` — `__tablename__ = "projects"`; columns `id`, `workspace_id`,
  `name`, `description`, `purpose`, `deliverables`, `channel_id`, `created_by`,
  `is_archived`, `created_at`, `updated_at`; relationships `members`, `tasks`,
  `milestones`, `roadmaps` [backend/app/models/project.py:Project]
- `ProjectMember` — `__tablename__ = "project_members"`; columns `id`,
  `project_id`, `user_id`, `created_at`
  [backend/app/models/project.py:ProjectMember]
- `Milestone` — `__tablename__ = "milestones"`; columns `id`, `project_id`,
  `title`, `start_at`, `end_at`, `color`, `progress`, `description`,
  `created_by`, `created_at`, `updated_at`
  [backend/app/models/project.py:Milestone]
- `Roadmap` — `__tablename__ = "roadmaps"`; columns `id`, `project_id`, `name`,
  `position`, `created_by`, `created_at`
  [backend/app/models/project.py:Roadmap]
- `Task` — `__tablename__ = "tasks"`; columns `id`, `project_id`, `title`,
  `description`, `status`, `assignee_id`, `roadmap_id`, `milestone_id`,
  `created_by`, `start_at`, `due_at`, `position`, `created_at`, `updated_at`;
  relationships `project`, `comments` [backend/app/models/project.py:Task]
- `TaskComment` — `__tablename__ = "task_comments"`; columns `id`, `task_id`,
  `user_id`, `body`, `created_at` [backend/app/models/project.py:TaskComment]
- `STATUS_REQUEST = "request"`, `STATUS_TODO = "todo"`,
  `STATUS_IN_PROGRESS = "in-progress"`, `STATUS_DONE = "done"`,
  `TASK_STATUSES = (request, todo, in-progress, done)`
  [backend/app/models/project.py:TASK_STATUSES]

### Schedule

- `ScheduleEvent` — `__tablename__ = "schedule_events"`; columns `id`,
  `workspace_id`, `title`, `description`, `location`, `starts_at`, `ends_at`,
  `all_day`, `is_private`, `created_by`, `channel_id`, `created_at`,
  `updated_at`; relationship `attendees`
  [backend/app/models/schedule.py:ScheduleEvent]
- `ScheduleAttendee` — `__tablename__ = "schedule_attendees"`; columns `id`,
  `event_id`, `user_id`, `response`, `created_at`
  [backend/app/models/schedule.py:ScheduleAttendee]
- `RESPONSE_PENDING = "pending"`, `RESPONSE_ACCEPTED = "accepted"`,
  `RESPONSE_DECLINED = "declined"`, `RESPONSE_TENTATIVE = "tentative"`,
  `RESPONSES = (pending, accepted, declined, tentative)`
  [backend/app/models/schedule.py:RESPONSES]

## Invariants

- Every model id column is a `String(40)` primary key — ids are
  application-generated strings, not database sequences
  [backend/app/models/base.py:Base]
- Every timestamp column uses the `UTCDateTime` decorator, so all stored
  datetimes round-trip as timezone-aware UTC [backend/app/models/base.py:UTCDateTime]
- `ChannelMember` rows are unique per `(channel_id, user_id)` via
  `UniqueConstraint("channel_id", "user_id", name="uq_channel_member")`
  [backend/app/models/channel.py:ChannelMember.__table_args__]
- `Channel.dm_key` is globally unique and nullable, so at most one DM channel
  may hold a given key while ordinary channels keep `NULL`
  [backend/app/models/channel.py:Channel.dm_key]
- `Channel.kind` defaults to `KIND_CHANNEL` and is limited by convention to
  `"channel"` or `"dm"` [backend/app/models/channel.py:Channel.kind]
- `File.workspace_id` is a plain indexed nullable column with **no** foreign key
  to `workspaces.id` — deleting a workspace does not cascade to files
  [backend/app/models/file.py:File.workspace_id]
- `Invite.token` is unique and indexed; `Invite.role` defaults to `ROLE_MEMBER`
  and must stay within `ROLES` [backend/app/models/invite.py:Invite.token]
- `Invite.expires_at` defaults to `default_expiry()` = `utcnow() + 7 days`
  [backend/app/models/invite.py:Invite.expires_at]
- `Invite.accepted_by` uses `ondelete="SET NULL"` so the user row survives
  invite deletion [backend/app/models/invite.py:Invite.accepted_by]
- `Message.parent_id` is a self-referencing FK with `ondelete="CASCADE"`, so
  deleting a parent removes its thread replies
  [backend/app/models/message.py:Message.parent_id]
- `Message.reply_to_id` uses `ondelete="SET NULL"`, so the answered message
  survives deletion while the reply loses its link
  [backend/app/models/message.py:Message.reply_to_id]
- `Message.deleted_body` is nullable and holds the body kept for restoring an
  undone delete [backend/app/models/message.py:Message.deleted_body]
- Reactions are unique per `(message_id, user_id, emoji)` via
  `UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction")`
  [backend/app/models/message.py:Reaction.__table_args__]
- `ReadState` rows are unique per `(channel_id, user_id)` via
  `UniqueConstraint("channel_id", "user_id", name="uq_read_state")`
  [backend/app/models/message.py:ReadState.__table_args__]
- `ReadState.last_read_message_id` is a nullable `String(40)` with **no**
  foreign key to `messages.id` [backend/app/models/message.py:ReadState.last_read_message_id]
- The `message_attachments` primary key is the pair `(message_id, file_id)`, so a
  file can be attached to a message only once
  [backend/app/models/message.py:message_attachments]
- `OrgUnit.parent_id` is a self-referencing FK with `ondelete="CASCADE"` and is
  nullable (`NULL` = top of the tree) [backend/app/models/org.py:OrgUnit.parent_id]
- `OrgUnitMember` rows are unique per `(org_unit_id, user_id)` via
  `UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_member")`
  [backend/app/models/org.py:OrgUnitMember.__table_args__]
- `OrgUnitManager` rows are unique per `(org_unit_id, user_id)` via
  `UniqueConstraint("org_unit_id", "user_id", name="uq_org_unit_manager")`
  [backend/app/models/org.py:OrgUnitManager.__table_args__]
- `Task.status` defaults to `STATUS_TODO` and must stay within `TASK_STATUSES`
  [backend/app/models/project.py:Task.status]
- `Task.assignee_id`, `Task.roadmap_id` and `Task.milestone_id` use
  `ondelete="SET NULL"`, so deleting the assignee, roadmap or milestone keeps
  the task on the board [backend/app/models/project.py:Task.milestone_id]
- `ProjectMember` rows are unique per `(project_id, user_id)` via
  `UniqueConstraint("project_id", "user_id", name="uq_project_member")`
  [backend/app/models/project.py:ProjectMember.__table_args__]
- `Project.channel_id` uses `ondelete="SET NULL"` — deleting the channel keeps
  the project [backend/app/models/project.py:Project.channel_id]
- `Milestone.start_at` and `Milestone.end_at` are NOT NULL; `color` defaults to
  `"#4f6cff"`, `progress` defaults to `0`
  [backend/app/models/project.py:Milestone.start_at]
- `ScheduleAttendee` rows are unique per `(event_id, user_id)` via
  `UniqueConstraint("event_id", "user_id", name="uq_event_attendee")`
  [backend/app/models/schedule.py:ScheduleAttendee.__table_args__]
- `ScheduleAttendee.response` defaults to `RESPONSE_PENDING` and must stay
  within `RESPONSES` [backend/app/models/schedule.py:ScheduleAttendee.response]
- `ScheduleEvent.starts_at` is indexed; `ends_at` is NOT NULL
  [backend/app/models/schedule.py:ScheduleEvent.starts_at]
- `User.email` is NOT NULL, unique and indexed — one user row per email address
  [backend/app/models/user.py:User.email]
- `User.presence` defaults to `PRESENCE_OFFLINE`; only `PRESENCE_CLAIMED` may be
  set by the person themselves [backend/app/models/user.py:User.presence]
- `Workspace.slug` is NOT NULL, unique and indexed — one workspace per slug
  [backend/app/models/workspace.py:Workspace.slug]
- `WorkspaceMembership` rows are unique per `(workspace_id, user_id)` via
  `UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member")`
  [backend/app/models/workspace.py:WorkspaceMembership.__table_args__]
- `WorkspaceMembership.role` defaults to `ROLE_MEMBER` and must stay within
  `ROLES` [backend/app/models/workspace.py:WorkspaceMembership.role]

## Side Effects

- `Base.metadata` holds the DDL for 22 tables: workspaces, workspace_memberships,
  users, channels, channel_memberships, files, invites, messages,
  message_attachments, reactions, read_states, org_units, org_unit_members,
  org_unit_managers, projects, project_members, milestones, roadmaps, tasks,
  task_comments, schedule_events, schedule_attendees — `create_all` and
  `ensure_schema` in `app.core.db` emit these from this metadata
  [backend/app/models/base.py:Base.metadata]
- Insert-time column defaults write values: `utcnow` for `created_at` /
  `joined_at` / `last_seen_at` / `last_read_at`, empty string for
  `topic`/`purpose`/`body`/`description`/`location`, `False` for
  `is_private`/`is_archived`/`all_day`/`inline`/`pinned`, `0` for
  `size`/`position`/`progress`/`reply_count`, and the enum defaults
  `KIND_CHANNEL`, `KIND_TEXT`, `ROLE_MEMBER`, `STATUS_TODO`,
  `RESPONSE_PENDING`, `PRESENCE_OFFLINE`, `"team"`, `"#4f6cff"`, `"#3f6f52"`
  [backend/app/models/base.py:utcnow]
- ORM-level cascade `"all, delete-orphan"` on `Channel.members` deletes
  membership rows when the channel is deleted
  [backend/app/models/channel.py:Channel.members]
- ORM-level cascade `"all, delete-orphan"` on `OrgUnit.members` and
  `OrgUnit.managers` deletes member/manager rows with the unit
  [backend/app/models/org.py:OrgUnit.members]
- ORM-level cascade `"all, delete-orphan"` on `Project.members`,
  `Project.tasks`, `Project.milestones` and `Project.roadmaps` deletes those
  child rows with the project [backend/app/models/project.py:Project.tasks]
- ORM-level cascade `"all, delete-orphan"` on `Task.comments` deletes comment
  rows with the task [backend/app/models/project.py:Task.comments]
- ORM-level cascade `"all, delete-orphan"` on `ScheduleEvent.attendees` deletes
  attendee rows with the event
  [backend/app/models/schedule.py:ScheduleEvent.attendees]
- ORM-level cascade `"all, delete-orphan"` on `User.memberships`,
  `User.channel_memberships`, `User.org_memberships` and
  `User.org_appointments` deletes those rows with the user
  [backend/app/models/user.py:User.memberships]
- ORM-level cascade `"all, delete-orphan"` on `Workspace.memberships` deletes
  membership rows with the workspace
  [backend/app/models/workspace.py:Workspace.memberships]
- Database-level `ON DELETE CASCADE` on `workspace_id` columns (channels,
  invites, org_units, projects, schedule_events) removes those rows with the
  workspace [backend/app/models/channel.py:Channel.workspace_id]
- Database-level `ON DELETE CASCADE` on `user_id` columns
  (channel_memberships, workspace_memberships, org_unit_members,
  org_unit_managers, project_members, reactions, read_states,
  schedule_attendees) removes those rows with the user
  [backend/app/models/workspace.py:WorkspaceMembership.user_id]
- Database-level `ON DELETE CASCADE` on `created_by` / `appointed_by` columns
  removes the referencing row with the creating user
  [backend/app/models/project.py:Project.created_by]
- Database-level `ON DELETE CASCADE` on `message_attachments.file_id` and
  `message_id` removes the attachment link with the message or file
  [backend/app/models/message.py:message_attachments]
- Database-level `ON DELETE SET NULL` clears `Invite.accepted_by`,
  `Message.reply_to_id`, `Project.channel_id`, `Task.assignee_id`,
  `Task.roadmap_id`, `Task.milestone_id` and `ScheduleEvent.channel_id`
  instead of deleting the referencing row
  [backend/app/models/project.py:Task.milestone_id]
- Database-level `ON DELETE CASCADE` on `org_units.parent_id` removes descendant
  org units with the parent unit [backend/app/models/org.py:OrgUnit.parent_id]
- `updated_at` columns are auto-refreshed on every UPDATE via
  `onupdate=utcnow` on `OrgUnit`, `Project`, `Milestone`, `Task` and
  `ScheduleEvent` [backend/app/models/project.py:Project.updated_at]
- `UTCDateTime` rewrites every bound datetime to UTC and re-tags naive
  datetimes read back as UTC
  [backend/app/models/base.py:UTCDateTime.process_bind_param]
- `Message.author` (lazy `"joined"`) and `Message.attachments` (lazy
  `"selectin"`, `secondary=message_attachments`) are `viewonly=True`, so the ORM
  never writes through them — attachment links must be inserted into
  `message_attachments` directly
  [backend/app/models/message.py:Message.attachments]
- `User.org_appointments` disambiguates the two FKs to `users` with
  `foreign_keys="OrgUnitManager.user_id"`, and `OrgUnitManager.user` uses
  `foreign_keys=[user_id]` so only the managed user, not the appointer, is
  targeted [backend/app/models/user.py:User.org_appointments]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
