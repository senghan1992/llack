# Pydantic Schemas

## Overview

The wire contract. Every request body and every response body of the v1 API is
one of these models; the HTTP routers use them directly as `response_model` and
the services layer builds them from ORM rows.

Models deriving from `ORMModel` are read straight off SQLAlchemy instances
(`from_attributes=True`). Models that are pure request bodies derive from
`BaseModel` directly.

## Interface

### Common

- `ORMModel` — `BaseModel` with `model_config = ConfigDict(from_attributes=True)`
  [backend/app/schemas/common.py:ORMModel]

### Auth (`auth.py`)

- `SignupRequest` — `email: EmailStr`, `password: str`, `name: str`,
  `workspace_name: str` [backend/app/schemas/auth.py:SignupRequest]
- `LoginRequest` — `email: EmailStr`, `password: str`
  [backend/app/schemas/auth.py:LoginRequest]
- `RefreshRequest` — `refresh_token: str`
  [backend/app/schemas/auth.py:RefreshRequest]
- `Tokens` — `access_token`, `refresh_token`
  [backend/app/schemas/auth.py:Tokens]
- `Session` — `access_token`, `refresh_token`, `user: UserOut`,
  `workspace: WorkspaceOut` [backend/app/schemas/auth.py:Session]

### Users and workspaces

- `UserOut` — `id`, `email`, `name`, `title`, `avatar_color`, `avatar_url`,
  `presence`, `last_seen_at`, `created_at`
  [backend/app/schemas/user.py:UserOut]
- `MemberOut` — `user: UserOut`, `role: str`, `joined_at: datetime`
  [backend/app/schemas/user.py:MemberOut]
- `UserUpdate` — `name`, `title`, `avatar_color`, `status_text`, `presence`
  [backend/app/schemas/user.py:UserUpdate]
- `PRESENCE_VALUES`, `PRESENCE_SELECTABLE`, `ROLE_VALUES`
  [backend/app/schemas/user.py:PRESENCE_VALUES]
- `WorkspaceOut` — `id`, `name`, `slug`, `created_at`
  [backend/app/schemas/workspace.py:WorkspaceOut]
- `WorkspaceCreate` — `name: str`
  [backend/app/schemas/workspace.py:WorkspaceCreate]
- `BootstrapOut` — `workspace`, `channels`, `dms`, `members`, `me`, `org`
  [backend/app/schemas/workspace.py:BootstrapOut]

### Channels (`channel.py`)

- `ChannelOut` — `id`, `workspace_id`, `name`, `topic`, `purpose`, `kind`,
  `is_private`, `created_by`, `created_at`, `member_count`, `unread_count`,
  `last_message_at`, `dm_user`, `members`, `is_member`
  [backend/app/schemas/channel.py:ChannelOut]
- `ChannelCreate` — `name`, `topic`, `is_private`, `member_ids`
  [backend/app/schemas/channel.py:ChannelCreate]
- `ChannelUpdate` — `name`, `topic`, `purpose`
  [backend/app/schemas/channel.py:ChannelUpdate]
- `ChannelMemberAdd` — `user_id: str`
  [backend/app/schemas/channel.py:ChannelMemberAdd]
- `DmCreate` — `user_id: str` [backend/app/schemas/channel.py:DmCreate]
- `ReadUpdate` — `message_id: str | None`
  [backend/app/schemas/channel.py:ReadUpdate]
- `KIND_CHANNEL = "channel"`, `KIND_DM = "dm"`
  [backend/app/schemas/channel.py:KIND_CHANNEL]

### Messages (`message.py`)

- `MessageOut` — `id`, `channel_id`, `user_id`, `author: UserOut`, `body`,
  `kind`, `parent_id`, `reply_to_id`, `reply_to: ReplyToOut | None`, `inline`,
  `created_at`, `edited_at`, `deleted_at`, `reply_count`, `last_reply_at`,
  `pinned`, `reactions: list[ReactionOut]`, `attachments: list[FileOut]`
  [backend/app/schemas/message.py:MessageOut]
- `MessagePage` — `messages: list[MessageOut]`, `has_more: bool`,
  `has_more_after: bool` [backend/app/schemas/message.py:MessagePage]
- `MessageCreate` — `body`, `parent_id`, `reply_to_id`, `inline`,
  `attachment_ids` [backend/app/schemas/message.py:MessageCreate]
- `MessageUpdate` — `body: str` [backend/app/schemas/message.py:MessageUpdate]
- `ReactionCreate` — `emoji: str` [backend/app/schemas/message.py:ReactionCreate]
- `ReactionOut` — `emoji`, `count: int`, `user_ids: list[str]`, `me: bool`
  [backend/app/schemas/message.py:ReactionOut]
- `ReplyToOut` — `id`, `author_name`, `body`, `deleted`
  [backend/app/schemas/message.py:ReplyToOut]
- `KIND_TEXT = "text"`, `KIND_SYSTEM = "system"`
  [backend/app/schemas/message.py:KIND_TEXT]

### Files and invites

- `FileOut` — `id`, `name`, `url`, `mime`, `size: int`
  [backend/app/schemas/file.py:FileOut]
- `FileRecord` — `FileOut` plus `created_at: datetime`
  [backend/app/schemas/file.py:FileRecord]
- `InviteOut` — `id`, `workspace_id`, `email`, `role`, `token`, `created_by`,
  `created_at`, `expires_at` [backend/app/schemas/invite.py:InviteOut]
- `InviteCreate` — `email: EmailStr`, `role: Literal["admin", "member"]`
  [backend/app/schemas/invite.py:InviteCreate]
- `InviteAccept` — `token: str` [backend/app/schemas/invite.py:InviteAccept]

### Organization (`org.py`)

- `OrgRole = Literal["owner", "admin", "member"]`
  [backend/app/schemas/org.py:OrgRole]
- `OrgUnit` — `id`, `workspace_id`, `parent_id`, `name`, `kind`, `description`,
  `position`, `created_at`, `updated_at`, `member_count`, `child_count`,
  `depth`, `members`, `managers`, `is_manager`, `can_manage`,
  `can_appoint_managers` [backend/app/schemas/org.py:OrgUnit]
- `OrgOverview` — `units: list[OrgUnit]`, `admins: list[MemberOut]`,
  `my_role: OrgRole`, `can_manage_admins: bool`, `managed_unit_ids: list[str]`
  [backend/app/schemas/org.py:OrgOverview]
- `OrgSummary` — `unit_count: int`, `managed_unit_ids: list[str]`
  [backend/app/schemas/org.py:OrgSummary]
- `OrgUnitCreate` — `name`, `parent_id`, `kind`, `description`
  [backend/app/schemas/org.py:OrgUnitCreate]
- `OrgUnitUpdate` — `name`, `kind`, `description`, `parent_id`
  [backend/app/schemas/org.py:OrgUnitUpdate]
- `OrgMemberAdd` — `user_id: str` [backend/app/schemas/org.py:OrgMemberAdd]
- `OrgManagerAdd` — `user_id: str` [backend/app/schemas/org.py:OrgManagerAdd]

### Projects (`project.py`)

- `TaskStatus = Literal["request", "todo", "in-progress", "done"]`
  [backend/app/schemas/project.py:TaskStatus]
- `ProjectOut` — `id`, `workspace_id`, `name`, `description`, `purpose`,
  `deliverables`, `channel_id`, `created_by`, `is_archived`, `created_at`,
  `updated_at`, `members: list[UserOut]`, `is_member`, `open_tasks`,
  `my_open_tasks`, `total_tasks`, `done_tasks`, `start_at`, `end_at`
  [backend/app/schemas/project.py:ProjectOut]
- `ProjectCreate` — `name`, `description`, `purpose`, `deliverables`,
  `channel_id`, `member_ids` [backend/app/schemas/project.py:ProjectCreate]
- `ProjectUpdate` — `name`, `description`, `purpose`, `deliverables`,
  `channel_id`, `member_ids`, `is_archived`
  [backend/app/schemas/project.py:ProjectUpdate]
- `ProjectMemberAdd` — `user_id: str`
  [backend/app/schemas/project.py:ProjectMemberAdd]
- `RoadmapOut` — `id`, `project_id`, `name`, `position`, `created_by`,
  `created_at`, `task_count` [backend/app/schemas/project.py:RoadmapOut]
- `RoadmapUpdate` — `name: str | None`
  [backend/app/schemas/project.py:RoadmapUpdate]
- `MilestoneOut` — `id`, `project_id`, `title`, `start_at`, `end_at`, `color`,
  `progress`, `manual_progress`, `description`, `task_count`, `done_count`,
  `auto_progress`, `task_ids`, `created_by`, `created_at`, `updated_at`
  [backend/app/schemas/project.py:MilestoneOut]
- `MilestoneCreate` — `title`, `start_at`, `end_at`, `color`, `progress`,
  `description`, `task_ids` [backend/app/schemas/project.py:MilestoneCreate]
- `MilestoneUpdate` — `title`, `start_at`, `end_at`, `color`, `progress`,
  `description`, `task_ids` [backend/app/schemas/project.py:MilestoneUpdate]
- `TaskOut` — `id`, `project_id`, `title`, `description`, `status`,
  `assignee_id`, `assignee`, `roadmap_id`, `roadmap_name`, `milestone_id`,
  `milestone_name`, `milestone_color`, `created_by`, `start_at`, `due_at`,
  `position`, `created_at`, `updated_at`, `comments`, `comment_count`
  [backend/app/schemas/project.py:TaskOut]
- `TaskCreate` — `title`, `description`, `status: TaskStatus`, `assignee_id`,
  `roadmap_id`, `milestone_id`, `start_at`, `due_at`
  [backend/app/schemas/project.py:TaskCreate]
- `TaskUpdate` — `title`, `description`, `status: TaskStatus | None`,
  `assignee_id`, `roadmap_id`, `milestone_id`, `start_at`, `due_at`,
  `position` [backend/app/schemas/project.py:TaskUpdate]
- `TaskCommentOut` — `id`, `task_id`, `user_id`, `author: UserOut`, `body`,
  `created_at` [backend/app/schemas/project.py:TaskCommentOut]
- `TaskCommentCreate` — `body: str`
  [backend/app/schemas/project.py:TaskCommentCreate]

### Schedule (`schedule.py`)

- `RsvpResponse = Literal["accepted", "declined", "tentative"]`
  [backend/app/schemas/schedule.py:RsvpResponse]
- `EventOut` — `id`, `workspace_id`, `title`, `description`, `location`,
  `starts_at`, `ends_at`, `all_day`, `is_private`, `created_by`, `channel_id`,
  `created_at`, `updated_at`, `attendees: list[AttendeeOut]`, `my_response`
  [backend/app/schemas/schedule.py:EventOut]
- `EventCreate` — `title`, `description`, `location`, `starts_at`, `ends_at`,
  `all_day`, `is_private`, `channel_id`, `attendee_ids`
  [backend/app/schemas/schedule.py:EventCreate]
- `EventUpdate` — same fields as `EventCreate`, all optional
  [backend/app/schemas/schedule.py:EventUpdate]
- `AttendeeAdd` — `user_id: str` [backend/app/schemas/schedule.py:AttendeeAdd]
- `RsvpUpdate` — `response: RsvpResponse`
  [backend/app/schemas/schedule.py:RsvpUpdate]
- `AttendeeOut` — `user: UserOut`, `response: str`
  [backend/app/schemas/schedule.py:AttendeeOut]

### Search (`search.py`)

- `SearchResult` — `message: MessageOut`, `channel: ChannelOut`
  [backend/app/schemas/search.py:SearchResult]

## Invariants

- ORM mode is enabled via `ConfigDict(from_attributes=True)` on every
  `ORMModel` subclass [backend/app/schemas/common.py:ORMModel]
- `SignupRequest.password` is bounded to `min_length=8, max_length=128`, and
  `SignupRequest.email` is validated as an email address
  [backend/app/schemas/auth.py:SignupRequest.password]
- `SignupRequest.name` is bounded to `min_length=1, max_length=80` and
  `SignupRequest.workspace_name` to `min_length=1, max_length=120`
  [backend/app/schemas/auth.py:SignupRequest.name]
- `LoginRequest.password` is bounded to `min_length=1, max_length=128`
  [backend/app/schemas/auth.py:LoginRequest.password]
- `RefreshRequest.refresh_token` is bounded to `min_length=1`
  [backend/app/schemas/auth.py:RefreshRequest.refresh_token]
- `ChannelOut.kind` is a plain `str`, not a `Literal` — `KIND_CHANNEL`/`KIND_DM`
  are conventions only [backend/app/schemas/channel.py:ChannelOut.kind]
- `ChannelCreate.name` is bounded to `min_length=1, max_length=120` and
  `ChannelCreate.member_ids` to `max_length=100`
  [backend/app/schemas/channel.py:ChannelCreate.name]
- `ChannelUpdate.name` / `topic` / `purpose` are all optional (`None` = unchanged)
  [backend/app/schemas/channel.py:ChannelUpdate.name]
- `InviteCreate.email` is validated as an email address, and `InviteCreate.role`
  is restricted to `Literal["admin", "member"]` (no `"owner"`), defaulting to
  `"member"` [backend/app/schemas/invite.py:InviteCreate.role]
- `InviteOut.email` and `InviteOut.role` are plain `str`, not
  `EmailStr`/`Literal` [backend/app/schemas/invite.py:InviteOut.email]
- `MessageOut.kind` is a plain `str`; `KIND_TEXT`/`KIND_SYSTEM` are conventions
  only [backend/app/schemas/message.py:MessageOut.kind]
- `MessageCreate.body` is bounded to `max_length=4000` with default `""` — an
  empty body is allowed because a message may carry only attachments
  [backend/app/schemas/message.py:MessageCreate.body]
- `MessageUpdate.body` is bounded to `min_length=1, max_length=4000`
  [backend/app/schemas/message.py:MessageUpdate.body]
- `ReactionCreate.emoji` is bounded to `min_length=1, max_length=32`
  [backend/app/schemas/message.py:ReactionCreate.emoji]
- `OrgOverview.my_role` is restricted to the `OrgRole` Literal and defaults to
  `"member"` [backend/app/schemas/org.py:OrgOverview.my_role]
- `OrgOverview.units` is a flat `list[OrgUnit]` — the tree is drawn from
  `parent_id` [backend/app/schemas/org.py:OrgOverview.units]
- `OrgUnitUpdate.parent_id` is optional; a null `parent_id` moves the unit to
  the top of the tree [backend/app/schemas/org.py:OrgUnitUpdate.parent_id]
- `TaskStatus` is restricted to `Literal["request", "todo", "in-progress",
  "done"]` [backend/app/schemas/project.py:TaskStatus]
- `TaskOut.status` is a plain `str` (default `"todo"`), not the `TaskStatus`
  Literal [backend/app/schemas/project.py:TaskOut.status]
- `MilestoneCreate.progress` is bounded to `ge=0, le=100` with default `0`, and
  `MilestoneUpdate.progress` is optional but still bounded
  [backend/app/schemas/project.py:MilestoneCreate.progress]
- `MilestoneCreate.color` is bounded to `max_length=16` with default
  `"#4f6cff"` [backend/app/schemas/project.py:MilestoneCreate.color]
- `TaskUpdate.position` is an optional int bounded to `ge=0`
  [backend/app/schemas/project.py:TaskUpdate.position]
- `RsvpResponse` is restricted to `Literal["accepted", "declined", "tentative"]`
  [backend/app/schemas/schedule.py:RsvpResponse]
- `AttendeeOut.response` is a plain `str` (default `"pending"`), not the
  `RsvpResponse` Literal [backend/app/schemas/schedule.py:AttendeeOut.response]
- `EventCreate.starts_at` and `EventCreate.ends_at` are required datetimes
  [backend/app/schemas/schedule.py:EventCreate.starts_at]
- `PRESENCE_VALUES` includes `"offline"` while `PRESENCE_SELECTABLE` excludes
  it — offline is server-owned state
  [backend/app/schemas/user.py:PRESENCE_SELECTABLE]
- `ROLE_VALUES = ("owner", "admin", "member")` matches the `OrgRole` value set
  [backend/app/schemas/user.py:ROLE_VALUES]
- `UserOut.presence` is a plain `str` (default `"offline"`), not a `Literal`
  [backend/app/schemas/user.py:UserOut.presence]
- `UserUpdate.presence` is restricted to
  `Literal["online", "busy", "dnd", "away", "brb"] | None`
  [backend/app/schemas/user.py:UserUpdate.presence]
- `SearchResult` requires both `message: MessageOut` and `channel: ChannelOut`
  [backend/app/schemas/search.py:SearchResult]
- `BootstrapOut` requires `workspace`, `channels`, `dms`, `members`, `me` and
  `org` [backend/app/schemas/workspace.py:BootstrapOut]

## Side Effects

These models are inert data holders; the only observable behaviour is their
defaults and validation.

- `ChannelOut` defaults: `topic=""`, `purpose=""`, `kind="channel"`,
  `is_private=False`, `member_count=0`, `unread_count=0`, `last_message_at=None`,
  `dm_user=None`, `members=None`, `is_member=False`
  [backend/app/schemas/channel.py:ChannelOut.topic]
- `ChannelCreate.member_ids` and `MessageCreate.attachment_ids` use
  `default_factory=list`, giving each instance its own list
  [backend/app/schemas/channel.py:ChannelCreate.member_ids]
- `MessageOut` defaults: `body=""`, `kind="text"`, `parent_id=None`,
  `reply_to_id=None`, `reply_to=None`, `inline=False`, `edited_at=None`,
  `deleted_at=None`, `reply_count=0`, `last_reply_at=None`, `pinned=False`,
  `reactions=[]`, `attachments=[]`
  [backend/app/schemas/message.py:MessageOut.body]
- `MessagePage.has_more_after` defaults to `False`
  [backend/app/schemas/message.py:MessagePage.has_more_after]
- `ReplyToOut.body` defaults to `""` and `deleted` to `False`
  [backend/app/schemas/message.py:ReplyToOut]
- `OrgUnit` defaults: `parent_id=None`, `kind="team"`, `description=""`,
  `position=0`, `member_count=0`, `child_count=0`, `depth=0` (top-level unit has
  depth 0), `members=[]`, `managers=[]`, `is_manager=False` (direct appointment
  only), `can_manage=False` (includes inherited reach),
  `can_appoint_managers=False` [backend/app/schemas/org.py:OrgUnit.depth]
- `OrgOverview` defaults: `units=[]`, `admins=[]`, `my_role="member"`,
  `can_manage_admins=False`, `managed_unit_ids=[]`
  [backend/app/schemas/org.py:OrgOverview.my_role]
- `OrgSummary` defaults: `unit_count=0`, `managed_unit_ids=[]`
  [backend/app/schemas/org.py:OrgSummary]
- `ProjectOut` defaults: `description=""`, `purpose=""`, `deliverables=""`,
  `channel_id=None`, `is_archived=False`, `members=[]`, `is_member=False`,
  `open_tasks=0`, `my_open_tasks=0`, `total_tasks=0`, `done_tasks=0`,
  `start_at=None`, `end_at=None`
  [backend/app/schemas/project.py:ProjectOut]
- `MilestoneOut` defaults: `color="#4f6cff"`, `progress=0`,
  `manual_progress=0`, `description=""`, `task_count=0`, `done_count=0`,
  `auto_progress=False`, `task_ids=[]`
  [backend/app/schemas/project.py:MilestoneOut.progress]
- `TaskOut` defaults: `description=""`, `status="todo"`, `assignee_id=None`,
  `assignee=None`, `roadmap_id=None`, `roadmap_name=None`, `milestone_id=None`,
  `milestone_name=None`, `milestone_color=None`, `position=0`, `comments=[]`,
  `comment_count=0` [backend/app/schemas/project.py:TaskOut.status]
- `EventOut` defaults: `description=""`, `location=""`, `all_day=False`,
  `is_private=False`, `channel_id=None`, `attendees=[]`, `my_response=None`
  [backend/app/schemas/schedule.py:EventOut]
- `UserOut` defaults: `title=None`, `avatar_url=None`, `avatar_color="#3f6f52"`,
  `presence="offline"` [backend/app/schemas/user.py:UserOut.avatar_color]
- `UserUpdate` fields all default to `None` (unset means unchanged)
  [backend/app/schemas/user.py:UserUpdate]
- `FileRecord` inherits `FileOut` and adds a required `created_at: datetime`
  [backend/app/schemas/file.py:FileRecord]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
