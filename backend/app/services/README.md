# Domain Services

## Overview

The business logic shared by the HTTP and WebSocket layers. Routers stay thin:
they resolve a dependency, check a permission, call one service function, and
broadcast an event. Everything that touches more than one table, or that
encodes a rule ("only a manager may…", "the DM key is symmetric"), lives here.

| Module | Domain |
| --- | --- |
| `channels.py` | channels, DM channels, channel membership, channel serialization |
| `files.py` | upload validation, quota, on-disk storage, orphan sweeping |
| `invites.py` | invite tokens, creation, revocation, acceptance |
| `members.py` | membership lookups, manager rights, audience computation |
| `messages.py` | message creation, pagination, threads, reactions, read state |
| `org.py` | the organization tree, unit managers, scope enforcement |
| `projects.py` | projects, rosters, tasks, board ordering, roadmaps, milestones |
| `schedule.py` | calendar events, attendees, RSVP, event visibility |
| `search.py` | message search scoped to readable channels |
| `workspaces.py` | workspace creation, slug derivation, roles, member listing |

## Interface

### Channels (`channels.py`)

- `get_channel_or_404(session, channel_id) -> Channel`
  [backend/app/services/channels.py:get_channel_or_404]
- `list_channels(session, workspace_id, viewer_id) -> list[Channel]`
  [backend/app/services/channels.py:list_channels]
- `list_dms(session, workspace_id, viewer_id) -> list[Channel]`
  [backend/app/services/channels.py:list_dms]
- `create_channel(session, workspace_id, creator, name, topic, is_private, member_ids)`
  [backend/app/services/channels.py:create_channel]
- `dm_key(workspace_id, first_user_id, second_user_id) -> str`
  [backend/app/services/channels.py:dm_key]
- `create_dm(session, workspace_id, first_user_id, second_user_id)`
  [backend/app/services/channels.py:create_dm]
- `add_channel_member(session, channel, user_id)`
  [backend/app/services/channels.py:add_channel_member]
- `remove_channel_member(session, channel, user_id)`
  [backend/app/services/channels.py:remove_channel_member]
- `delete_channel(session, channel)`
  [backend/app/services/channels.py:delete_channel]
- `list_public_channels(session, workspace_id) -> list[Channel]`
  [backend/app/services/channels.py:list_public_channels]
- `join_public_channels(session, workspace_id, user_id)`
  [backend/app/services/channels.py:join_public_channels]
- `list_channel_members(session, channel) -> list[MemberOut]`
  [backend/app/services/channels.py:list_channel_members]
- `serialize_channels(session, channels, viewer_id) -> list[ChannelOut]`
  [backend/app/services/channels.py:serialize_channels]
- `serialize_channel(session, channel, viewer_id) -> ChannelOut`
  [backend/app/services/channels.py:serialize_channel]

### Files (`files.py`)

- `CHUNK_BYTES = 1024 * 1024` — 1 MiB read size for uploads
  [backend/app/services/files.py:CHUNK_BYTES]
- `HEAD_BYTES = 8192` — bytes kept as the file head for type sniffing
  [backend/app/services/files.py:HEAD_BYTES]
- `NAME_LIMIT = 120` — character limit for the kept file stem
  [backend/app/services/files.py:NAME_LIMIT]
- `IMAGE_TYPES`, `INLINE_TYPES`, `TEXT_TYPES`, `ZIP_TYPES`, `OLE_TYPES`,
  `ALLOWED_MIME_TYPES`, `MIME_SUFFIX` — the MIME policy tables
  [backend/app/services/files.py:ALLOWED_MIME_TYPES]
- `is_allowed_mime(mime) -> bool`
  [backend/app/services/files.py:is_allowed_mime]
- `storage_path_for(workspace_id, file_id, mime) -> Path`
  [backend/app/services/files.py:storage_path_for]
- `_looks_like_text(path) -> bool`
  [backend/app/services/files.py:_looks_like_text]
- `_verify_zip(path, declared) -> str | None`
  [backend/app/services/files.py:_verify_zip]
- `verify_mime(path, head, declared) -> str | None`
  [backend/app/services/files.py:verify_mime]
- `_same_family(declared, verified) -> bool`
  [backend/app/services/files.py:_same_family]
- `clean_name(raw, mime, declared) -> str`
  [backend/app/services/files.py:clean_name]
- `disposition_for(mime) -> str`
  [backend/app/services/files.py:disposition_for]
- `workspace_usage(session, workspace_id) -> int`
  [backend/app/services/files.py:workspace_usage]
- `save_upload(session, upload, workspace_id, owner)`
  [backend/app/services/files.py:save_upload]
- `purge_orphan_files(session, older_than_hours) -> int`
  [backend/app/services/files.py:purge_orphan_files]
- `get_file_or_404(session, file_id) -> File`
  [backend/app/services/files.py:get_file_or_404]
- `disk_path(record) -> Path` [backend/app/services/files.py:disk_path]

### Invites (`invites.py`)

- `TOKEN_BYTES = 12`, `TOKEN_ATTEMPTS = 5`
  [backend/app/services/invites.py:TOKEN_BYTES]
- `new_token(session) -> str` [backend/app/services/invites.py:new_token]
- `find_pending(session, workspace_id, email) -> Invite | None`
  [backend/app/services/invites.py:find_pending]
- `list_pending_invites(session, workspace_id) -> list[Invite]`
  [backend/app/services/invites.py:list_pending_invites]
- `create_invite(session, workspace_id, email, role, created_by)`
  [backend/app/services/invites.py:create_invite]
- `revoke_invite(session, invite) -> Invite`
  [backend/app/services/invites.py:revoke_invite]
- `accept_invite(session, token, user) -> Workspace`
  [backend/app/services/invites.py:accept_invite]
- `_join_workspace(session, invite, user)`
  [backend/app/services/invites.py:_join_workspace]

### Members (`members.py`)

- `get_membership(session, workspace_id, user_id) -> WorkspaceMembership | None`
  [backend/app/services/members.py:get_membership]
- `require_membership(session, workspace_id, user_id) -> WorkspaceMembership`
  [backend/app/services/members.py:require_membership]
- `is_manager(membership) -> bool`
  [backend/app/services/members.py:is_manager]
- `is_channel_member(session, channel_id, user_id) -> bool`
  [backend/app/services/members.py:is_channel_member]
- `channel_member_ids(session, channel_id) -> set[str]`
  [backend/app/services/members.py:channel_member_ids]
- `workspace_member_ids(session, workspace_id) -> set[str]`
  [backend/app/services/members.py:workspace_member_ids]
- `channel_audience(session, channel) -> set[str]`
  [backend/app/services/members.py:channel_audience]
- `require_channel_access(session, channel, user_id) -> WorkspaceMembership`
  [backend/app/services/members.py:require_channel_access]

### Messages (`messages.py`)

- `MAX_PAGE_SIZE = 100`, `DEFAULT_PAGE_SIZE = 50`
  [backend/app/services/messages.py:MAX_PAGE_SIZE]
- `get_message_or_404(session, message_id) -> Message`
  [backend/app/services/messages.py:get_message_or_404]
- `create_message(session, channel, author, body, parent_id=None, reply_to_id=None, inline=False, attachment_ids=None)`
  [backend/app/services/messages.py:create_message]
- `recompute_thread_stats(session, root_id)`
  [backend/app/services/messages.py:recompute_thread_stats]
- `list_messages(session, channel, limit=DEFAULT_PAGE_SIZE, before=None)`
  [backend/app/services/messages.py:list_messages]
- `list_messages_around(session, channel, limit=DEFAULT_PAGE_SIZE, around=None)`
  [backend/app/services/messages.py:list_messages_around]
- `list_messages_after(session, channel, limit=DEFAULT_PAGE_SIZE, after=None)`
  [backend/app/services/messages.py:list_messages_after]
- `list_messages_with_flags(session, channel, limit=DEFAULT_PAGE_SIZE, before=None)`
  [backend/app/services/messages.py:list_messages_with_flags]
- `list_thread_replies(session, root, limit=MAX_PAGE_SIZE)`
  [backend/app/services/messages.py:list_thread_replies]
- `edit_message(session, message, body) -> Message`
  [backend/app/services/messages.py:edit_message]
- `delete_message(session, message) -> Message`
  [backend/app/services/messages.py:delete_message]
- `restore_message(session, message) -> Message`
  [backend/app/services/messages.py:restore_message]
- `toggle_reaction(session, message, user_id, emoji) -> bool`
  [backend/app/services/messages.py:toggle_reaction]
- `remove_reaction(session, message, user_id, emoji)`
  [backend/app/services/messages.py:remove_reaction]
- `set_pinned(session, message, pinned) -> Message`
  [backend/app/services/messages.py:set_pinned]
- `list_pinned(session, channel) -> list[Message]`
  [backend/app/services/messages.py:list_pinned]
- `mark_read(session, channel, user_id, message_id=None)`
  [backend/app/services/messages.py:mark_read]
- `unread_count(session, channel_id, user_id) -> int`
  [backend/app/services/messages.py:unread_count]
- `unread_counts(session, channel_ids, user_id) -> dict[str, int]`
  [backend/app/services/messages.py:unread_counts]
- `MessageBundle` — dataclass holding authors, reactions, attachments and reply
  targets loaded for a batch of messages
  [backend/app/services/messages.py:MessageBundle]
- `load_message_bundle(session, messages) -> MessageBundle`
  [backend/app/services/messages.py:load_message_bundle]
- `build_message_out(message, bundle, viewer_id, api_prefix) -> MessageOut | None`
  [backend/app/services/messages.py:build_message_out]
- `serialize_messages(session, messages, viewer_id) -> list[MessageOut]`
  [backend/app/services/messages.py:serialize_messages]
- `serialize_message(session, message, viewer_id) -> MessageOut`
  [backend/app/services/messages.py:serialize_message]

### Organization (`org.py`)

- `MAX_TREE_DEPTH = 50` [backend/app/services/org.py:MAX_TREE_DEPTH]
- `is_workspace_manager(membership) -> bool`
  [backend/app/services/org.py:is_workspace_manager]
- `list_units(session, workspace_id) -> list[OrgUnitRow]`
  [backend/app/services/org.py:list_units]
- `get_unit_or_404(session, unit_id) -> OrgUnitRow`
  [backend/app/services/org.py:get_unit_or_404]
- `managed_unit_ids(session, workspace_id, user_id, membership) -> set[str]`
  [backend/app/services/org.py:managed_unit_ids]
- `require_scope(unit, scope)` [backend/app/services/org.py:require_scope]
- `create_unit(session, workspace_id, creator, membership, scope, name, parent_id=None, kind="team", description="")`
  [backend/app/services/org.py:create_unit]
- `update_unit(session, unit, membership, scope, payload) -> OrgUnitRow`
  [backend/app/services/org.py:update_unit]
- `_move_unit(session, unit, membership, scope, parent_id)`
  [backend/app/services/org.py:_move_unit]
- `_is_descendant(session, ancestor_id, candidate_id) -> bool`
  [backend/app/services/org.py:_is_descendant]
- `delete_unit(session, unit, scope)`
  [backend/app/services/org.py:delete_unit]
- `add_unit_member(session, unit, user_id, workspace_id, scope)`
  [backend/app/services/org.py:add_unit_member]
- `remove_unit_member(session, unit, user_id, scope)`
  [backend/app/services/org.py:remove_unit_member]
- `appoint_manager(session, unit, user_id, appointed_by, workspace_id, scope, membership)`
  [backend/app/services/org.py:appoint_manager]
- `dismiss_manager(session, unit, user_id, scope)`
  [backend/app/services/org.py:dismiss_manager]
- `_tree_shape(units)` [backend/app/services/org.py:_tree_shape]
- `serialize_units(session, units, scope, viewer_id) -> list[OrgUnit]`
  [backend/app/services/org.py:serialize_units]
- `serialize_overview(session, workspace_id, user_id, membership) -> OrgOverview`
  [backend/app/services/org.py:serialize_overview]
- `org_summary(session, workspace_id, user_id, membership) -> OrgSummary`
  [backend/app/services/org.py:org_summary]

### Projects, tasks, roadmaps and milestones (`projects.py`)

- `get_project_or_404(session, project_id) -> Project`
  [backend/app/services/projects.py:get_project_or_404]
- `get_task_or_404(session, task_id) -> Task`
  [backend/app/services/projects.py:get_task_or_404]
- `project_member_ids(session, project_id) -> set[str]`
  [backend/app/services/projects.py:project_member_ids]
- `can_manage_project(project, membership, user_id) -> bool`
  [backend/app/services/projects.py:can_manage_project]
- `can_delete_task(task, project, membership, user_id) -> bool`
  [backend/app/services/projects.py:can_delete_task]
- `resolve_channel(session, workspace_id, channel_id, user_id)`
  [backend/app/services/projects.py:resolve_channel]
- `_sync_members(session, project, member_ids)`
  [backend/app/services/projects.py:_sync_members]
- `create_project(session, workspace_id, creator, name, ...)`
  [backend/app/services/projects.py:create_project]
- `update_project(session, project, payload) -> Project`
  [backend/app/services/projects.py:update_project]
- `delete_project(session, project)` [backend/app/services/projects.py:delete_project]
- `add_project_member(session, project, user_id)`
  [backend/app/services/projects.py:add_project_member]
- `remove_project_member(session, project, user_id) -> Project`
  [backend/app/services/projects.py:remove_project_member]
- `list_projects(session, workspace_id, viewer_id, include_archived)`
  [backend/app/services/projects.py:list_projects]
- `list_tasks(session, project_id) -> list[Task]`
  [backend/app/services/projects.py:list_tasks]
- `my_tasks(session, workspace_id, user_id) -> list[Task]`
  [backend/app/services/projects.py:my_tasks]
- `next_position(session, project_id, status) -> int`
  [backend/app/services/projects.py:next_position]
- `create_task(session, project, payload, creator)`
  [backend/app/services/projects.py:create_task]
- `_require_assignee(session, workspace_id, assignee_id)`
  [backend/app/services/projects.py:_require_assignee]
- `update_task(session, task, payload) -> Task`
  [backend/app/services/projects.py:update_task]
- `move_task(session, task, status)` [backend/app/services/projects.py:move_task]
- `reorder_task(session, task, status, position) -> Task`
  [backend/app/services/projects.py:reorder_task]
- `_compact(session, project_id, status, exclude_id)`
  [backend/app/services/projects.py:_compact]
- `delete_task(session, task)` [backend/app/services/projects.py:delete_task]
- `add_comment(session, task, author, body) -> TaskComment`
  [backend/app/services/projects.py:add_comment]
- `get_comment_or_404(session, comment_id) -> TaskComment`
  [backend/app/services/projects.py:get_comment_or_404]
- `delete_comment(session, comment)` [backend/app/services/projects.py:delete_comment]
- `get_roadmap_or_404(session, roadmap_id) -> Roadmap`
  [backend/app/services/projects.py:get_roadmap_or_404]
- `list_roadmaps(session, project_id) -> list[Roadmap]`
  [backend/app/services/projects.py:list_roadmaps]
- `rename_roadmap(session, roadmap, name) -> Roadmap`
  [backend/app/services/projects.py:rename_roadmap]
- `delete_roadmap(session, roadmap)` [backend/app/services/projects.py:delete_roadmap]
- `require_roadmap(session, project_id, roadmap_id) -> str`
  [backend/app/services/projects.py:require_roadmap]
- `MILESTONE_COLOR = "#4f6cff"`
  [backend/app/services/projects.py:MILESTONE_COLOR]
- `get_milestone_or_404(session, milestone_id) -> Milestone`
  [backend/app/services/projects.py:get_milestone_or_404]
- `list_milestones(session, project_id) -> list[Milestone]`
  [backend/app/services/projects.py:list_milestones]
- `require_milestone(session, project_id, milestone_id) -> str`
  [backend/app/services/projects.py:require_milestone]
- `_as_utc(moment) -> datetime`
  [backend/app/services/projects.py:_as_utc]
- `create_milestone(session, project, payload, creator)`
  [backend/app/services/projects.py:create_milestone]
- `update_milestone(session, milestone, payload) -> Milestone`
  [backend/app/services/projects.py:update_milestone]
- `link_milestone_tasks(session, milestone, task_ids)`
  [backend/app/services/projects.py:link_milestone_tasks]
- `delete_milestone(session, milestone)`
  [backend/app/services/projects.py:delete_milestone]
- `serialize_projects(session, projects, viewer_id) -> list[ProjectOut]`
  [backend/app/services/projects.py:serialize_projects]
- `serialize_tasks(session, tasks, viewer_id) -> list[TaskOut]`
  [backend/app/services/projects.py:serialize_tasks]
- `serialize_roadmaps(session, roadmaps) -> list[RoadmapOut]`
  [backend/app/services/projects.py:serialize_roadmaps]
- `serialize_milestones(session, milestones) -> list[MilestoneOut]`
  [backend/app/services/projects.py:serialize_milestones]

### Schedule (`schedule.py`)

- `DEFAULT_LOOKBACK = timedelta(days=30)`,
  `DEFAULT_LOOKAHEAD = timedelta(days=180)`
  [backend/app/services/schedule.py:DEFAULT_LOOKBACK]
- `get_event_or_404(session, event_id) -> ScheduleEvent`
  [backend/app/services/schedule.py:get_event_or_404]
- `attendee_event_ids(session, user_id) -> set[str]`
  [backend/app/services/schedule.py:attendee_event_ids]
- `can_view_event(session, event, user_id) -> bool`
  [backend/app/services/schedule.py:can_view_event]
- `require_event_access(session, event, user_id) -> WorkspaceMembership`
  [backend/app/services/schedule.py:require_event_access]
- `_validate_window(starts_at, ends_at)` [backend/app/services/schedule.py:_validate_window]
- `resolve_channel(session, workspace_id, channel_id, user_id)`
  [backend/app/services/schedule.py:resolve_channel]
- `_sync_attendees(session, event, attendee_ids)`
  [backend/app/services/schedule.py:_sync_attendees]
- `create_event(session, workspace_id, creator, payload)`
  [backend/app/services/schedule.py:create_event]
- `update_event(session, event, payload) -> ScheduleEvent`
  [backend/app/services/schedule.py:update_event]
- `delete_event(session, event)` [backend/app/services/schedule.py:delete_event]
- `add_attendee(session, event, user_id)`
  [backend/app/services/schedule.py:add_attendee]
- `remove_attendee(session, event, user_id)`
  [backend/app/services/schedule.py:remove_attendee]
- `set_response(session, event, user_id, response)`
  [backend/app/services/schedule.py:set_response]
- `_attendee_user_ids(session, event) -> list[str]`
  [backend/app/services/schedule.py:_attendee_user_ids]
- `list_events(session, workspace_id, viewer_id, window_start, window_end)`
  [backend/app/services/schedule.py:list_events]
- `event_audience(session, event) -> set[str]`
  [backend/app/services/schedule.py:event_audience]
- `serialize_event(session, event, viewer_id) -> EventOut`
  [backend/app/services/schedule.py:serialize_event]
- `serialize_events(session, events, viewer_id) -> list[EventOut]`
  [backend/app/services/schedule.py:serialize_events]

### Search and workspaces

- `_escape_like(term) -> str` [backend/app/services/search.py:_escape_like]
- `search_messages(session, workspace_id, viewer_id, query, limit)`
  [backend/app/services/search.py:search_messages]
- `slugify(name) -> str` [backend/app/services/workspaces.py:slugify]
- `unique_slug(session, name) -> str`
  [backend/app/services/workspaces.py:unique_slug]
- `create_workspace(session, owner, name) -> Workspace`
  [backend/app/services/workspaces.py:create_workspace]
- `get_workspace_or_404(session, workspace_id) -> Workspace`
  [backend/app/services/workspaces.py:get_workspace_or_404]
- `list_workspaces(session, user_id) -> list[Workspace]`
  [backend/app/services/workspaces.py:list_workspaces]
- `primary_workspace(session, user_id) -> Workspace | None`
  [backend/app/services/workspaces.py:primary_workspace]
- `list_members(session, workspace_id) -> list[MemberOut]`
  [backend/app/services/workspaces.py:list_members]
- `set_role(session, membership, role) -> WorkspaceMembership`
  [backend/app/services/workspaces.py:set_role]
- `remove_member(session, membership)`
  [backend/app/services/workspaces.py:remove_member]

## Invariants

### Channels and files

- Channel names are unique per workspace among `KIND_CHANNEL` rows; a duplicate
  raises `conflict` [backend/app/services/channels.py:create_channel]
- A channel name is required: the stripped name must be non-empty
  [backend/app/services/channels.py:create_channel]
- The creator is always a `ChannelMember` of a newly created channel and is
  never added twice [backend/app/services/channels.py:create_channel]
- `member_ids` are de-duplicated via `dict.fromkeys`, so one `ChannelMember` row
  per user is created [backend/app/services/channels.py:create_channel]
- DM key derivation is symmetric: `dm_key` sorts the two user ids and formats
  `workspace_id:low:high` [backend/app/services/channels.py:dm_key]
- A user cannot open a DM with themselves
  [backend/app/services/channels.py:create_dm]
- A DM is always `kind=KIND_DM` and `is_private=True`, and both participants
  become `ChannelMember` [backend/app/services/channels.py:create_dm]
- `add_channel_member` and `remove_channel_member` are idempotent
  [backend/app/services/channels.py:add_channel_member]
- `list_channels` shows public channels plus private ones the viewer is a member
  of [backend/app/services/channels.py:list_channels]
- `list_dms` returns only DM channels where the viewer holds a `ChannelMember` row
  [backend/app/services/channels.py:list_dms]
- Channel deletion removes children by hand because SQLite does not enforce
  foreign keys here: `message_attachments`, `Reaction`, `Message`, `ReadState`,
  `ChannelMember` and the `Channel` row
  [backend/app/services/channels.py:delete_channel]
- Deleting a channel does not delete a project or schedule event; their
  `channel_id` is set to `None` so the work survives
  [backend/app/services/channels.py:delete_channel]
- A channel member without a `WorkspaceMembership` row is reported with the
  fallback role `"member"` [backend/app/services/channels.py:list_channel_members]
- In serialization a DM is shown under the partner's name, not the stored
  channel name [backend/app/services/channels.py:serialize_channels]
- `last_message_at` ignores soft-deleted messages
  [backend/app/services/channels.py:serialize_channels]
- Only MIME types in `ALLOWED_MIME_TYPES` may be shared
  [backend/app/services/files.py:is_allowed_mime]
- The browser's `content_type` is a hint only; the first bytes decide the type
  [backend/app/services/files.py:verify_mime]
- The declared type may only choose between siblings of one family
  [backend/app/services/files.py:_same_family]
- OLE magic bytes are accepted only when the declared type is one of
  `OLE_TYPES` [backend/app/services/files.py:verify_mime]
- A zip claiming an office format must contain its marker member
  (`word/document.xml`, `xl/workbook.xml`, `ppt/presentation.xml`,
  `Contents/header.xml`) [backend/app/services/files.py:_verify_zip]
- An OpenDocument zip must carry a `mimetype` member whose value is itself in
  `ALLOWED_MIME_TYPES` [backend/app/services/files.py:_verify_zip]
- A zip that names nothing known is stored as `application/zip`
  [backend/app/services/files.py:_verify_zip]
- Text types are only accepted when the file reads as UTF-8 text with no NUL
  byte [backend/app/services/files.py:_looks_like_text]
- SVG is uploadable but never inline-rendered: `image/svg+xml` is absent from
  `INLINE_TYPES` [backend/app/services/files.py:INLINE_TYPES]
- `disposition_for` returns `inline` only for `INLINE_TYPES` and
  `application/pdf`; everything else is an attachment
  [backend/app/services/files.py:disposition_for]
- Storage layout is
  `<UPLOAD_DIR>/<workspace_id>/<first two chars of file id>/<file_id><suffix>`
  [backend/app/services/files.py:storage_path_for]
- The on-disk suffix comes from the verified MIME type, never from the user's
  filename [backend/app/services/files.py:storage_path_for]
- The disk filename is the file id, never the client-supplied name
  [backend/app/services/files.py:save_upload]
- `clean_name` strips directory components, drops non-printable characters and
  `\ / : * ? " < > |`, and caps the stem at `NAME_LIMIT`
  [backend/app/services/files.py:clean_name]
- The user's extension survives only when declared and verified are the same
  family and the extension is one of the known `MIME_SUFFIX` extensions
  [backend/app/services/files.py:clean_name]
- Per-file size is capped by `settings.max_upload_bytes` and enforced while
  streaming [backend/app/services/files.py:save_upload]
- Workspace quota is checked before the upload (`used >=
  workspace_quota_bytes`) and again during the write (`used + total >
  workspace_quota_bytes`) [backend/app/services/files.py:save_upload]
- A zero-byte upload is rejected with `validation_error('file is empty')`
  [backend/app/services/files.py:save_upload]
- A file whose bytes do not verify is rejected and its partial file removed
  [backend/app/services/files.py:save_upload]
- `purge_orphan_files` only runs for `older_than_hours > 0` and only removes
  files created before the cutoff that are absent from `message_attachments`
  [backend/app/services/files.py:purge_orphan_files]

### Invites and members

- Invite tokens are `secrets.token_urlsafe(12)` and must not collide with an
  existing `Invite.token`; after 5 attempts a conflict is raised
  [backend/app/services/invites.py:new_token]
- A pending invite is one that is not accepted, not revoked and not expired
  (`expires_at > utcnow()`) [backend/app/services/invites.py:find_pending]
- `create_invite` returns the existing pending invite for the same email
  instead of creating a duplicate
  [backend/app/services/invites.py:create_invite]
- Invite emails are normalised to stripped lowercase
  [backend/app/services/invites.py:create_invite]
- An invite expires `INVITE_TTL_DAYS` after creation
  [backend/app/services/invites.py:create_invite]
- `revoke_invite` only stamps `revoked_at` when the invite is neither accepted
  nor already revoked [backend/app/services/invites.py:revoke_invite]
- `accept_invite` rejects an unknown token with `not_found`, and a revoked,
  accepted or expired invite with `conflict`
  [backend/app/services/invites.py:accept_invite]
- On acceptance the invite is stamped with `accepted_at` and `accepted_by`
  [backend/app/services/invites.py:accept_invite]
- The invited role can only be `ROLE_ADMIN` or `ROLE_MEMBER`; anything else
  becomes `ROLE_MEMBER` [backend/app/services/invites.py:_join_workspace]
- An existing membership is only upgraded, never downgraded: member becomes
  admin, admin is never demoted [backend/app/services/invites.py:_join_workspace]
- Joining a workspace also seats the user in every public channel of that
  workspace [backend/app/services/invites.py:_join_workspace]
- Access requires workspace membership; otherwise `forbidden` is raised
  [backend/app/services/members.py:require_membership]
- Manager rights are exactly `ROLE_OWNER` and `ROLE_ADMIN`
  [backend/app/services/members.py:is_manager]
- `require_channel_access` enforces workspace membership first, then requires
  `ChannelMember` membership for DM and private channels
  [backend/app/services/members.py:require_channel_access]
- Live-event audience for a public `KIND_CHANNEL` is every workspace member;
  for private channels and DMs only the channel roster
  [backend/app/services/members.py:channel_audience]

### Messages

- Page size is always clamped to `max(1, min(limit, MAX_PAGE_SIZE))` before
  any query limit is applied [backend/app/services/messages.py:list_messages]
- The channel message set is top-level messages only:
  `parent_id IS NULL OR inline IS TRUE`
  [backend/app/services/messages.py:_channel_message_query]
- Cursor comparisons are stable on the `(created_at, id)` pair so equal
  timestamps do not skip or repeat messages
  [backend/app/services/messages.py:_older_than]
  [backend/app/services/messages.py:_newer_than]
- A reply target must exist, belong to the same channel, and not be deleted
  [backend/app/services/messages.py:create_message]
- Replies are one level deep: a reply to a reply is re-parented to the reply's
  own parent (`target.parent_id or target.id`)
  [backend/app/services/messages.py:create_message]
- Threads cannot be nested: a parent that itself has a parent raises "threads
  cannot be nested" [backend/app/services/messages.py:create_message]
- `inline` is only true when a reply_to target exists
  [backend/app/services/messages.py:create_message]
- A message needs a non-empty body or at least one attachment
  [backend/app/services/messages.py:create_message]
- Every attachment must exist and belong to the message author; another user's
  file is rejected [backend/app/services/messages.py:create_message]
- Thread statistics count only non-deleted children: `reply_count` is the count
  of children with `deleted_at IS NULL`, `last_reply_at` the max `created_at` of
  those children [backend/app/services/messages.py:recompute_thread_stats]
- `list_messages` returns the newest page when no cursor is given and walks
  backwards with `before`; the page is reversed so oldest comes first
  [backend/app/services/messages.py:list_messages]
- `list_messages_around` splits the window into `limit // 2` older messages
  plus the remainder as newer, with the anchor in the middle
  [backend/app/services/messages.py:list_messages_around]
- Deleting is a soft delete: the body is copied to `deleted_body`, `body` is
  emptied and `deleted_at` is stamped, so the original text survives for undo
  on every device [backend/app/services/messages.py:delete_message]
- `restore_message` refuses when `deleted_at` is `None` or `deleted_body` is
  `None` [backend/app/services/messages.py:restore_message]
- A deleted message cannot be edited, and an empty body is rejected
  [backend/app/services/messages.py:edit_message]
- Reactions are unique per `(message_id, user_id, emoji)`: `toggle_reaction`
  removes the existing row instead of adding a duplicate
  [backend/app/services/messages.py:toggle_reaction]
- Read state is unique per `(channel_id, user_id)`: the insert runs inside a
  savepoint and falls back to an update on `IntegrityError`
  [backend/app/services/messages.py:mark_read]
- `mark_read` without a `message_id` anchors on the newest message of the
  channel [backend/app/services/messages.py:mark_read]
- Unread counts exclude the caller's own messages and deleted messages
  [backend/app/services/messages.py:unread_counts]
- A channel with no read state counts every non-deleted message not written by
  the caller as unread [backend/app/services/messages.py:unread_counts]
- `build_message_out` returns `None` when the message's author is missing from
  the bundle [backend/app/services/messages.py:build_message_out]
- A quoted reply target that is deleted is rendered with an empty body and
  `deleted=True` [backend/app/services/messages.py:build_message_out]
- Reactions are grouped by emoji in `(created_at, id)` order, and `me` is set
  when the viewer is among the reactors
  [backend/app/services/messages.py:load_message_bundle]

### Organization

- Every tree walk in the org service stops at `MAX_TREE_DEPTH` so a cyclic
  parent chain cannot hang the server [backend/app/services/org.py:MAX_TREE_DEPTH]
- A workspace owner/admin manages every unit of the workspace
  [backend/app/services/org.py:managed_unit_ids]
- A unit manager's scope is the units they manage plus every descendant
  [backend/app/services/org.py:managed_unit_ids]
- `require_scope` raises `forbidden` when the unit is not in the caller's scope;
  every changing route calls it first
  [backend/app/services/org.py:require_scope]
- Only a workspace manager may create a top-level unit
  [backend/app/services/org.py:create_unit]
- A new unit's parent must exist, belong to the same workspace, and be inside
  the caller's scope [backend/app/services/org.py:create_unit]
- A unit cannot be moved under itself or under one of its own descendants
  [backend/app/services/org.py:_move_unit]
- Only a workspace manager may move a unit to the top of the tree
  [backend/app/services/org.py:_move_unit]
- A unit with child units or with members cannot be deleted
  [backend/app/services/org.py:delete_unit]
- `add_unit_member` and `remove_unit_member` are idempotent
  [backend/app/services/org.py:add_unit_member]
- A unit manager cannot appoint themselves; only a workspace admin may put
  their own name on a unit [backend/app/services/org.py:appoint_manager]
- `appoint_manager` and `dismiss_manager` are idempotent
  [backend/app/services/org.py:appoint_manager]
- Units are listed by `(position, created_at, id)`
  [backend/app/services/org.py:list_units]
- `serialize_units` computes `member_count`, `child_count` and `depth` from the
  whole workspace tree, not only the requested units
  [backend/app/services/org.py:serialize_units]
- `can_manage` and `can_appoint_managers` are true exactly when the unit id is
  in the viewer's scope [backend/app/services/org.py:serialize_units]
- `is_manager` on a unit is true only when the viewer is among that unit's
  appointed managers [backend/app/services/org.py:serialize_units]

### Projects and schedule

- A task status must belong to `TASK_STATUSES`; unknown values raise
  `validation_error("unknown task status", "status")`
  [backend/app/services/projects.py:create_task]
- `move_task` refuses a status outside `TASK_STATUSES`
  [backend/app/services/projects.py:move_task]
- Position is scoped to a `(project, status)` column: `next_position` returns
  `max(Task.position) + 1` for that column, and `0` for the first task
  [backend/app/services/projects.py:next_position]
- A negative position is rejected with
  `validation_error("the position must not be negative", "position")`
  [backend/app/services/projects.py:reorder_task]
- A position beyond the end of a column is clamped to the end via
  `index = min(position, len(others))`
  [backend/app/services/projects.py:reorder_task]
- Column ordering is total and deterministic: tasks sort by
  `(position, created_at, id)` [backend/app/services/projects.py:list_tasks]
- A task belongs to exactly one column; moving it renumbers the old column and
  re-appends it to the new column
  [backend/app/services/projects.py:move_task]
- Column positions stay dense and zero-based after a task leaves a column
  [backend/app/services/projects.py:_compact]
- Only the task author, the project creator, or a workspace membership with
  role `owner`/`admin` may delete a task
  [backend/app/services/projects.py:can_delete_task]
- Only the project creator or a workspace membership with role `owner`/`admin`
  may manage a project
  [backend/app/services/projects.py:can_manage_project]
- A linked channel must exist and belong to the same workspace, else
  `validation_error` on `channel_id`
  [backend/app/services/projects.py:resolve_channel]
- A private linked channel requires a `ChannelMember` row for the calling user
  [backend/app/services/projects.py:resolve_channel]
- Every project member must be a `WorkspaceMembership` of the project's
  workspace [backend/app/services/projects.py:_sync_members]
- The project creator is always kept on the roster even if `member_ids` omits
  them [backend/app/services/projects.py:update_project]
- A task assignee must be a `WorkspaceMembership` of the project workspace
  [backend/app/services/projects.py:_require_assignee]
- A task's roadmap and milestone must belong to the task's project
  [backend/app/services/projects.py:create_task]
- Clearing `roadmap_id` or `milestone_id` on a task sets the column to `None`
  rather than failing validation
  [backend/app/services/projects.py:update_task]
- A milestone must not end before it starts
  [backend/app/services/projects.py:create_milestone]
- Naive datetimes are read as UTC and aware datetimes converted to UTC via
  `_as_utc` [backend/app/services/projects.py:_as_utc]
- Milestone progress is clamped to the 0..100 range
  [backend/app/services/projects.py:create_milestone]
- A milestone colour falls back to `MILESTONE_COLOR` when blank
  [backend/app/services/projects.py:update_milestone]
- A card belongs to at most one milestone: linking detaches it from any
  previous milestone [backend/app/services/projects.py:link_milestone_tasks]
- Only cards of the milestone's own project may be linked
  [backend/app/services/projects.py:link_milestone_tasks]
- `my_tasks` lists only unfinished tasks assigned to the caller
  [backend/app/services/projects.py:my_tasks]
- Archived projects are hidden unless `include_archived` is true
  [backend/app/services/projects.py:list_projects]
- A milestone holding cards reports computed progress with `auto_progress=True`;
  a milestone with no cards reports the hand-written progress with
  `auto_progress=False` [backend/app/services/projects.py:serialize_milestones]
- A project's span runs from the earliest of (milestone start, earliest task
  due) to the latest of (milestone end, latest task due)
  [backend/app/services/projects.py:serialize_projects]
- An event must not end before it starts
  [backend/app/services/schedule.py:_validate_window]
- Viewing any event requires `WorkspaceMembership` of the event's workspace
  [backend/app/services/schedule.py:require_event_access]
- A private event is visible only to its creator and its attendees; a
  non-private event is visible to every member of the workspace
  [backend/app/services/schedule.py:can_view_event]
- Every attendee must be a `WorkspaceMembership` of the event's workspace
  [backend/app/services/schedule.py:_sync_attendees]
- The event creator is always an attendee from creation
  [backend/app/services/schedule.py:create_event]
- The creator's own attendance is auto-accepted while every other new attendee
  starts pending [backend/app/services/schedule.py:create_event]
- The event window defaults to `now - DEFAULT_LOOKBACK` and
  `now + DEFAULT_LOOKAHEAD` when start/end are not supplied
  [backend/app/services/schedule.py:list_events]
- `list_events` selects events overlapping the window and orders them by
  `(starts_at, id)` [backend/app/services/schedule.py:list_events]
- The live-update audience of a private event is the creator plus its
  attendees; of an open event it is every workspace member
  [backend/app/services/schedule.py:event_audience]
- Removing an attendee that is not on the roster is a no-op
  [backend/app/services/schedule.py:remove_attendee]

### Search and workspaces

- Search only reads channels that are public or that the viewer is a member of
  [backend/app/services/search.py:search_messages]
- Search excludes soft-deleted messages
  [backend/app/services/search.py:search_messages]
- LIKE wildcards in the query are escaped (backslash, `%`, `_`) and the pattern
  uses `escape='\\'` [backend/app/services/search.py:_escape_like]
- The result limit is clamped to `max(1, min(limit, 100))` and an empty query
  returns no results [backend/app/services/search.py:search_messages]
- Search results are ordered by `created_at desc` then `id desc`
  [backend/app/services/search.py:search_messages]
- Slugs are NFKD-normalized, ASCII-filtered, lowercased, non-alphanumeric runs
  collapsed to a single `-`, trimmed, and truncated to 60 characters
  [backend/app/services/workspaces.py:slugify]
- Hangul syllables are romanized with the initial/vowel/final tables, so
  "한빛" becomes "hanbit" [backend/app/services/workspaces.py:_romanize]
- `unique_slug` falls back to "workspace" when the slug is empty and appends
  `-2`, `-3`, ... until the slug is unused
  [backend/app/services/workspaces.py:unique_slug]
- The creator of a workspace is added as a membership with role `owner`
  [backend/app/services/workspaces.py:create_workspace]
- Workspace listings are ordered by `(created_at, id)`, and `primary_workspace`
  is the first such row [backend/app/services/workspaces.py:list_workspaces]
- `set_role` rejects any role not in `ROLES` with a conflict
  [backend/app/services/workspaces.py:set_role]
- Members are listed by `(joined_at, id)`
  [backend/app/services/workspaces.py:list_members]

## Side Effects

- Inserts a `Channel` row and one `ChannelMember` row per participant, then
  flushes [backend/app/services/channels.py:create_channel]
- Inserts a `Channel` row and two `ChannelMember` rows for a new DM, then
  flushes [backend/app/services/channels.py:create_dm]
- Inserts and deletes `ChannelMember` rows on demand
  [backend/app/services/channels.py:add_channel_member]
- `delete_channel` deletes `message_attachments` and `Reaction` rows for the
  channel's messages, deletes `Message` and `ReadState` rows, nulls
  `Project.channel_id` and `ScheduleEvent.channel_id`, deletes the
  `ChannelMember` roster and the channel, then flushes
  [backend/app/services/channels.py:delete_channel]
- Inserts `ChannelMember` rows for every public channel of the workspace
  [backend/app/services/channels.py:join_public_channels]
- Creates the on-disk directory for the upload and writes the uploaded bytes in
  1 MiB chunks [backend/app/services/files.py:save_upload]
- Deletes the partial file from disk when the upload fails or is rejected, and
  renames the stored file so its path matches the verified MIME type's extension
  [backend/app/services/files.py:save_upload]
- Inserts the `File` row (name, verified mime, size, owner, workspace,
  `storage_path`) and flushes [backend/app/services/files.py:save_upload]
- `purge_orphan_files` deletes orphan files from disk and their `File` rows,
  then commits the transaction [backend/app/services/files.py:purge_orphan_files]
- Reads the file head from disk to sniff its type, and opens the archive on
  disk to read its member names and `mimetype` entry
  [backend/app/services/files.py:_looks_like_text]
- Generates an invite token with `secrets.token_urlsafe(TOKEN_BYTES)`
  [backend/app/services/invites.py:new_token]
- Inserts an `Invite` row with the generated token and expiry and flushes
  [backend/app/services/invites.py:create_invite]
- Sets `invite.revoked_at` and flushes
  [backend/app/services/invites.py:revoke_invite]
- Sets `invite.accepted_at` and `invite.accepted_by` and flushes
  [backend/app/services/invites.py:accept_invite]
- Inserts a `WorkspaceMembership` row for the accepting user, promotes an
  existing membership's role to admin, and adds `ChannelMember` rows for the
  new member's public channels
  [backend/app/services/invites.py:_join_workspace]
- `create_message` inserts a `Message` row (`new_id(MESSAGE_PREFIX)`,
  `kind=KIND_TEXT`) and flushes, and inserts rows into the `message_attachments`
  association table for the resolved files
  [backend/app/services/messages.py:create_message]
- `create_message` triggers `recompute_thread_stats` on the parent when the
  message is a reply
  [backend/app/services/messages.py:create_message]
- `recompute_thread_stats` writes `reply_count` and `last_reply_at` on the
  thread root [backend/app/services/messages.py:recompute_thread_stats]
- `edit_message` writes the new body and sets `edited_at`
  [backend/app/services/messages.py:edit_message]
- `delete_message` writes `deleted_body`, sets `deleted_at`, clears `body`, and
  recomputes the parent thread's stats
  [backend/app/services/messages.py:delete_message]
- `restore_message` writes `body` back from `deleted_body`, clears
  `deleted_body` and `deleted_at`, and recomputes the parent thread's stats
  [backend/app/services/messages.py:restore_message]
- `toggle_reaction` deletes the existing `Reaction` row when the user already
  reacted, and inserts a new one (`new_id(REACTION_PREFIX)`) otherwise
  [backend/app/services/messages.py:toggle_reaction]
- `set_pinned` writes the message's pinned flag
  [backend/app/services/messages.py:set_pinned]
- `mark_read` inserts a `ReadState` row (`new_id(READ_STATE_PREFIX)`) with
  `last_read_message_id` and `last_read_at`, or updates the existing row, and
  opens a nested transaction (savepoint) around the insert to survive a
  concurrent unique-constraint violation
  [backend/app/services/messages.py:mark_read]
- `create_unit` inserts an `OrgUnit` row with `position=0` and the stripped
  name/kind/description; `update_unit` and `_move_unit` write the changed
  fields; `delete_unit` deletes the row (its manager rows go with it)
  [backend/app/services/org.py:create_unit]
- `add_unit_member` inserts an `OrgUnitMember` row (`new_id(ORG_MEMBER_PREFIX)`)
  and `remove_unit_member` deletes it
  [backend/app/services/org.py:add_unit_member]
- `appoint_manager` inserts an `OrgUnitManager` row
  (`new_id(ORG_MANAGER_PREFIX)`) with `appointed_by`; `dismiss_manager` deletes
  it [backend/app/services/org.py:appoint_manager]
- `create_workspace` inserts a `Workspace` row (`new_id(WORKSPACE_PREFIX)`) and
  a `WorkspaceMembership` row (`new_id(MEMBER_PREFIX)`) with role `owner` for
  the creator [backend/app/services/workspaces.py:create_workspace]
- `set_role` writes `membership.role`; `remove_member` deletes the
  `WorkspaceMembership` row [backend/app/services/workspaces.py:remove_member]
- `create_project` inserts the `Project` row and flushes it
  [backend/app/services/projects.py:create_project]
- `_sync_members` deletes `ProjectMember` rows for users no longer wanted and
  inserts new ones (`new_id(PROJECT_MEMBER_PREFIX)`)
  [backend/app/services/projects.py:_sync_members]
- `update_project` mutates project fields and flushes; `delete_project` deletes
  the project and flushes [backend/app/services/projects.py:update_project]
- `create_task` inserts the `Task` row with `position = next_position(project.id,
  status)` and flushes [backend/app/services/projects.py:create_task]
- `move_task` renumbers the old column to `0..n-1` and sets the moved task's
  position to `next_position` of the target column
  [backend/app/services/projects.py:move_task]
- `reorder_task` renumbers every task of a column to `0..n-1` after inserting
  the task at the requested index
  [backend/app/services/projects.py:reorder_task]
- `_compact` rewrites `Task.position` for every task of a column, skipping
  `exclude_id` [backend/app/services/projects.py:_compact]
- `add_comment` inserts a `TaskComment` row (`new_id(TASK_COMMENT_PREFIX)`) and
  flushes; `delete_comment` deletes it and flushes
  [backend/app/services/projects.py:add_comment]
- `delete_roadmap` runs `UPDATE Task SET roadmap_id = NULL` for all tasks of
  the roadmap before deleting the roadmap
  [backend/app/services/projects.py:delete_roadmap]
- `create_milestone` inserts the `Milestone` row
  (`new_id(MILESTONE_PREFIX)`) and flushes; `update_milestone` mutates the
  milestone fields and flushes
  [backend/app/services/projects.py:create_milestone]
- `link_milestone_tasks` sets `task.milestone_id` for the wanted cards and
  clears it for previously linked cards not named any more
  [backend/app/services/projects.py:link_milestone_tasks]
- `delete_milestone` runs `UPDATE Task SET milestone_id = NULL` for all cards of
  the milestone before deleting it
  [backend/app/services/projects.py:delete_milestone]
- `create_event` inserts the `ScheduleEvent` row (`new_id(EVENT_PREFIX)`) and
  flushes; `update_event` mutates the event fields and flushes;
  `delete_event` deletes the event and flushes
  [backend/app/services/schedule.py:create_event]
- `_sync_attendees` deletes `ScheduleAttendee` rows no longer wanted and
  inserts new ones (`new_id(ATTENDEE_PREFIX)`) with `RESPONSE_PENDING`
  [backend/app/services/schedule.py:_sync_attendees]
- `create_event` sets the creator's attendee response to `RESPONSE_ACCEPTED`
  and flushes [backend/app/services/schedule.py:create_event]
- `remove_attendee` deletes the `ScheduleAttendee` row and flushes
  [backend/app/services/schedule.py:remove_attendee]
- `set_response` inserts an attendee row carrying the response when the caller
  is not yet an attendee, and otherwise updates the existing
  `ScheduleAttendee.response` and flushes
  [backend/app/services/schedule.py:set_response]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
