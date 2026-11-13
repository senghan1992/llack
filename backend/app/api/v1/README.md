# v1 HTTP API

## Overview

Every route of the API contract. `router.py` aggregates the fifteen module
routers into one `api_router`, which `app/main.py` mounts under the prefix
`/api/v1`. Two health probes also sit outside that prefix, at `/health` and
`/api/v1/health`.

A typical handler does four things: resolve a dependency (the current user, a
workspace membership, a channel with access), check a permission, call a
service function, commit, and broadcast a realtime event.

The WebSocket at `/api/v1/ws` is the only non-HTTP endpoint in this package.

## Interface

### Router aggregation (`router.py`)

- `api_router` — `APIRouter` including all fifteen module routers
  [backend/app/api/v1/router.py:api_router]
- `__all__ = ["api_router"]` [backend/app/api/v1/router.py:__all__]

### Auth (`auth.py`) — prefix `/auth`

- `router` — `APIRouter(prefix="/auth", tags=["auth"])`
  [backend/app/api/v1/auth.py:router]
- `AVATAR_COLORS` — tuple of 8 hex avatar colours used at signup
  [backend/app/api/v1/auth.py:AVATAR_COLORS]
- `POST /api/v1/auth/signup` — create account + workspace, returns `Session`
  [backend/app/api/v1/auth.py:signup]
- `POST /api/v1/auth/login` — authenticate email/password, returns `Session`
  [backend/app/api/v1/auth.py:login]
- `POST /api/v1/auth/refresh` — exchange refresh token for a new token pair
  [backend/app/api/v1/auth.py:refresh]
- Helpers `_tokens(user)` and `_session(user, workspace)`
  [backend/app/api/v1/auth.py:_tokens]

### Me (`me.py`)

- `GET /api/v1/me` — current user profile
  [backend/app/api/v1/me.py:read_me]
- `PATCH /api/v1/me` — update own profile (name, title, avatar_color,
  status_text, presence) [backend/app/api/v1/me.py:update_me]

### Workspaces (`workspaces.py`) — prefix `/workspaces`

- `router` — `APIRouter(prefix="/workspaces", tags=["workspaces"])`
  [backend/app/api/v1/workspaces.py:router]
- `RoleUpdate` — request model with `role: Literal["owner", "admin", "member"]`
  [backend/app/api/v1/workspaces.py:RoleUpdate]
- `GET /api/v1/workspaces` -> `list[WorkspaceOut]`
  [backend/app/api/v1/workspaces.py:read_workspaces]
- `POST /api/v1/workspaces` -> `WorkspaceOut`
  [backend/app/api/v1/workspaces.py:create_new_workspace]
- `GET /api/v1/workspaces/{workspace_id}/bootstrap` -> `BootstrapOut`
  [backend/app/api/v1/workspaces.py:bootstrap]
- `GET /api/v1/workspaces/{workspace_id}/channels` -> `list[ChannelOut]`
  [backend/app/api/v1/workspaces.py:read_channels]
- `POST /api/v1/workspaces/{workspace_id}/channels` -> `ChannelOut`
  [backend/app/api/v1/workspaces.py:create_new_channel]
- `GET /api/v1/workspaces/{workspace_id}/dms` -> `list[ChannelOut]`
  [backend/app/api/v1/workspaces.py:read_dms]
- `POST /api/v1/workspaces/{workspace_id}/dms` -> `ChannelOut`
  [backend/app/api/v1/workspaces.py:open_dm]
- `GET /api/v1/workspaces/{workspace_id}/members` -> `list[MemberOut]`
  [backend/app/api/v1/workspaces.py:read_members]
- `PATCH /api/v1/workspaces/{workspace_id}/members/{user_id}` -> `MemberOut`
  [backend/app/api/v1/workspaces.py:update_member_role]
- `DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}` -> 204
  [backend/app/api/v1/workspaces.py:delete_member]
- `_guard_last_owner(session, workspace_id)` — keeps a workspace from losing
  its last owner [backend/app/api/v1/workspaces.py:_guard_last_owner]

### Channels (`channels.py`) — prefix `/channels`

- `GET /api/v1/channels/{channel_id}` -> `ChannelOut`
  [backend/app/api/v1/channels.py:read_channel]
- `PATCH /api/v1/channels/{channel_id}` -> `ChannelOut`
  [backend/app/api/v1/channels.py:update_channel]
- `POST /api/v1/channels/{channel_id}/join` -> `ChannelOut`
  [backend/app/api/v1/channels.py:join_channel]
- `POST /api/v1/channels/{channel_id}/leave` -> 204
  [backend/app/api/v1/channels.py:leave_channel]
- `GET /api/v1/channels/{channel_id}/members` -> `list[MemberOut]`
  [backend/app/api/v1/channels.py:read_channel_members]
- `POST /api/v1/channels/{channel_id}/members` -> 204
  [backend/app/api/v1/channels.py:add_member_to_channel]
- `DELETE /api/v1/channels/{channel_id}` -> 204
  [backend/app/api/v1/channels.py:delete_channel_route]
- `GET /api/v1/channels/{channel_id}/pins` -> `list[MessageOut]`
  [backend/app/api/v1/channels.py:read_pins]
- `POST /api/v1/channels/{channel_id}/read` -> 204
  [backend/app/api/v1/channels.py:mark_channel_read]
- `GET /api/v1/channels/{channel_id}/messages` -> `MessagePage`
  [backend/app/api/v1/channels.py:read_messages]
- `POST /api/v1/channels/{channel_id}/messages` -> `MessageOut`
  [backend/app/api/v1/channels.py:post_message]

### Messages (`messages.py`) — prefix `/messages`

- `PATCH /api/v1/messages/{message_id}` -> `MessageOut`
  [backend/app/api/v1/messages.py:update_message]
- `DELETE /api/v1/messages/{message_id}` -> 204
  [backend/app/api/v1/messages.py:delete_message_route]
- `POST /api/v1/messages/{message_id}/restore` -> `MessageOut`
  [backend/app/api/v1/messages.py:restore_message_route]
- `POST /api/v1/messages/{message_id}/reactions` -> `MessageOut`
  [backend/app/api/v1/messages.py:add_reaction]
- `DELETE /api/v1/messages/{message_id}/reactions/{emoji}` -> `MessageOut`
  [backend/app/api/v1/messages.py:delete_reaction]
- `POST /api/v1/messages/{message_id}/pin` -> `MessageOut`
  [backend/app/api/v1/messages.py:pin_message]
- `DELETE /api/v1/messages/{message_id}/pin` -> `MessageOut`
  [backend/app/api/v1/messages.py:unpin_message]
- `GET /api/v1/messages/{message_id}/replies` -> `list[MessageOut]`
  [backend/app/api/v1/messages.py:read_replies]
- Helpers `_load_message(session, user, message_id)` and `_can_modify(user,
  message, membership)` [backend/app/api/v1/messages.py:_load_message]

### Users (`users.py`)

- `GET /api/v1/users?q=` -> `list[UserOut]`
  [backend/app/api/v1/users.py:read_users]

### Files (`files.py`) — prefix `/files`

- `POST /api/v1/files` -> `FileOut` — multipart upload of a file into a
  workspace [backend/app/api/v1/files.py:upload_file]
- `GET /api/v1/files/{file_id}` — download a file as `FileResponse`
  [backend/app/api/v1/files.py:download_file]
- `_file_out(record)` — builds `FileOut` with url `"{api_prefix}/files/{id}"`
  [backend/app/api/v1/files.py:_file_out]
- `_can_read(session, file_id, user_id)` — true when the file is attached to a
  message in a readable channel
  [backend/app/api/v1/files.py:_can_read]

### Search (`search.py`) — prefix `/workspaces`

- `GET /api/v1/workspaces/{workspace_id}/search?q=&limit=` -> `list[SearchResult]`
  [backend/app/api/v1/search.py:search]

### Schedule (`schedule.py`)

- `GET /api/v1/workspaces/{workspace_id}/events?from=&to=` -> `list[EventOut]`
  [backend/app/api/v1/schedule.py:read_events]
- `POST /api/v1/workspaces/{workspace_id}/events` -> `EventOut`
  [backend/app/api/v1/schedule.py:post_event]
- `GET /api/v1/events/{event_id}` -> `EventOut`
  [backend/app/api/v1/schedule.py:read_event]
- `PATCH /api/v1/events/{event_id}` -> `EventOut`
  [backend/app/api/v1/schedule.py:patch_event]
- `DELETE /api/v1/events/{event_id}` -> 204
  [backend/app/api/v1/schedule.py:remove_event]
- `POST /api/v1/events/{event_id}/attendees` -> `EventOut`
  [backend/app/api/v1/schedule.py:post_attendee]
- `DELETE /api/v1/events/{event_id}/attendees/{user_id}` -> 204
  [backend/app/api/v1/schedule.py:delete_attendee]
- `POST /api/v1/events/{event_id}/rsvp` -> `EventOut`
  [backend/app/api/v1/schedule.py:post_rsvp]

### Projects (`projects.py`)

- `GET /api/v1/workspaces/{workspace_id}/projects` -> `list[ProjectOut]`
  [backend/app/api/v1/projects.py:read_projects]
- `POST /api/v1/workspaces/{workspace_id}/projects` -> `ProjectOut`
  [backend/app/api/v1/projects.py:post_project]
- `GET /api/v1/workspaces/{workspace_id}/tasks` -> `list[TaskOut]`
  [backend/app/api/v1/projects.py:read_my_tasks]
- `GET /api/v1/projects/{project_id}` -> `ProjectOut`
  [backend/app/api/v1/projects.py:read_project]
- `PATCH /api/v1/projects/{project_id}` -> `ProjectOut`
  [backend/app/api/v1/projects.py:patch_project]
- `DELETE /api/v1/projects/{project_id}` -> 204
  [backend/app/api/v1/projects.py:remove_project]
- `POST /api/v1/projects/{project_id}/members` -> `ProjectOut`
  [backend/app/api/v1/projects.py:post_project_member]
- `DELETE /api/v1/projects/{project_id}/members/{user_id}` -> 204
  [backend/app/api/v1/projects.py:delete_project_member]
- `GET /api/v1/projects/{project_id}/roadmaps` -> `list[RoadmapOut]`
  [backend/app/api/v1/projects.py:read_roadmaps]
- `PATCH /api/v1/roadmaps/{roadmap_id}` -> `RoadmapOut`
  [backend/app/api/v1/projects.py:patch_roadmap]
- `DELETE /api/v1/roadmaps/{roadmap_id}` -> 204
  [backend/app/api/v1/projects.py:remove_roadmap]
- `GET /api/v1/projects/{project_id}/tasks` -> `list[TaskOut]`
  [backend/app/api/v1/projects.py:read_tasks]
- `POST /api/v1/projects/{project_id}/tasks` -> `TaskOut`
  [backend/app/api/v1/projects.py:post_task]
- `PATCH /api/v1/tasks/{task_id}` -> `TaskOut`
  [backend/app/api/v1/projects.py:patch_task]
- `DELETE /api/v1/tasks/{task_id}` -> 204
  [backend/app/api/v1/projects.py:remove_task]
- `POST /api/v1/tasks/{task_id}/comments` -> `TaskCommentOut`
  [backend/app/api/v1/projects.py:post_task_comment]
- `DELETE /api/v1/task-comments/{comment_id}` -> 204
  [backend/app/api/v1/projects.py:remove_task_comment]
- `_require_workspace_member(session, workspace_id, user_id)`
  [backend/app/api/v1/projects.py:_require_workspace_member]

### Milestones (`milestones.py`)

- `GET /api/v1/projects/{project_id}/milestones` -> `list[MilestoneOut]`
  [backend/app/api/v1/milestones.py:read_milestones]
- `POST /api/v1/projects/{project_id}/milestones` -> `MilestoneOut`
  [backend/app/api/v1/milestones.py:post_milestone]
- `PATCH /api/v1/milestones/{milestone_id}` -> `MilestoneOut`
  [backend/app/api/v1/milestones.py:patch_milestone]
- `DELETE /api/v1/milestones/{milestone_id}` -> 204
  [backend/app/api/v1/milestones.py:remove_milestone]
- `_require_workspace_member(session, workspace_id, user_id)`
  [backend/app/api/v1/milestones.py:_require_workspace_member]

### Organization (`org.py`)

- `GET /api/v1/workspaces/{workspace_id}/org` -> `OrgOverview`
  [backend/app/api/v1/org.py:read_org]
- `POST /api/v1/workspaces/{workspace_id}/org/units` -> `OrgUnit`
  [backend/app/api/v1/org.py:post_org_unit]
- `PATCH /api/v1/org/units/{unit_id}` -> `OrgUnit`
  [backend/app/api/v1/org.py:patch_org_unit]
- `DELETE /api/v1/org/units/{unit_id}` -> 204
  [backend/app/api/v1/org.py:delete_org_unit]
- `POST /api/v1/org/units/{unit_id}/members` -> 204
  [backend/app/api/v1/org.py:post_org_member]
- `DELETE /api/v1/org/units/{unit_id}/members/{user_id}` -> 204
  [backend/app/api/v1/org.py:delete_org_member]
- `POST /api/v1/org/units/{unit_id}/managers` -> 204
  [backend/app/api/v1/org.py:post_org_manager]
- `DELETE /api/v1/org/units/{unit_id}/managers/{user_id}` -> 204
  [backend/app/api/v1/org.py:delete_org_manager]
- `_unit_context(...)` — resolves the unit's workspace from the loaded unit
  [backend/app/api/v1/org.py:_unit_context]

### Invites (`invites.py`)

- `GET /api/v1/workspaces/{workspace_id}/invites` -> `list[InviteOut]`
  [backend/app/api/v1/invites.py:read_invites]
- `POST /api/v1/workspaces/{workspace_id}/invites` -> `InviteOut`
  [backend/app/api/v1/invites.py:create_new_invite]
- `DELETE /api/v1/workspaces/{workspace_id}/invites/{invite_id}` -> 204
  [backend/app/api/v1/invites.py:delete_invite]
- `POST /api/v1/invites/accept` -> `WorkspaceOut`
  [backend/app/api/v1/invites.py:accept_invite]

### Realtime (`realtime.py`)

- `WebSocket /api/v1/ws` — the live socket, authenticated by a `token` query
  parameter [backend/app/api/v1/realtime.py:websocket_endpoint]
- `AUTH_FAILED = 4401` — WebSocket close code for failed authentication
  [backend/app/api/v1/realtime.py:AUTH_FAILED]
- Client frame types handled: `"ping"` (answered with `"pong"`), `"typing"`,
  `"read"` [backend/app/api/v1/realtime.py:_handle_client_event]
- Server frame types sent: `"hello"`, `"pong"`, `"unread"`
  [backend/app/api/v1/realtime.py:websocket_endpoint]
- `_handle_client_event(websocket, connection, payload)`,
  `_handle_typing(connection, payload)`, `_handle_read(connection, payload)`
  [backend/app/api/v1/realtime.py:_handle_client_event]

## Invariants

### Auth and profile

- Signup normalizes the email with `strip().lower()` before both the
  uniqueness lookup and the stored value
  [backend/app/api/v1/auth.py:signup]
- A signup for an already-registered email raises
  `conflict("email is already registered")` [backend/app/api/v1/auth.py:signup]
- The password is only persisted as `hash_password(payload.password)`
  [backend/app/api/v1/auth.py:signup]
- New users start with `presence="offline"`, `title=None` and a random
  `avatar_color` drawn from `AVATAR_COLORS`
  [backend/app/api/v1/auth.py:signup]
- Signup must create a workspace via `create_workspace(session, user,
  payload.workspace_name)` and only then commit
  [backend/app/api/v1/auth.py:signup]
- Login fails with `unauthorized("invalid email or password")` when the user is
  missing or the password does not verify
  [backend/app/api/v1/auth.py:login]
- Login fails with `unauthorized("this account has no workspace")` when
  `primary_workspace` returns `None` [backend/app/api/v1/auth.py:login]
- Refresh requires the token to decode under `REFRESH_TOKEN`; any decode
  exception becomes `unauthorized("invalid or expired refresh token")`
  [backend/app/api/v1/auth.py:refresh]
- Refresh requires the decoded `user_id` to still exist, else
  `unauthorized("unknown user")` [backend/app/api/v1/auth.py:refresh]
- The presence field may only be set to a value contained in
  `PRESENCE_SELECTABLE` [backend/app/api/v1/me.py:update_me]
- Setting presence also refreshes `last_seen_at` to `utcnow()`
  [backend/app/api/v1/me.py:update_me]
- In a profile update, `name` and `avatar_color` are applied only when truthy
  while `title` is applied whenever the key is present
  [backend/app/api/v1/me.py:update_me]

### Channels and messages

- Every channel route requires channel access resolved by the `ChannelAccess`
  dependency [backend/app/api/v1/channels.py:router]
- Only the channel creator or a workspace manager may update a channel
  [backend/app/api/v1/channels.py:update_channel]
- A channel update applies only fields present in the payload
  (`model_dump(exclude_unset=True)`) [backend/app/api/v1/channels.py:update_channel]
- Joining is refused for DMs and for private channels
  [backend/app/api/v1/channels.py:join_channel]
- Leaving is refused for DMs [backend/app/api/v1/channels.py:leave_channel]
- Adding to a private channel requires a workspace manager; adding to a public
  channel requires a manager or an existing channel member
  [backend/app/api/v1/channels.py:add_member_to_channel]
- The person being added must already hold a `WorkspaceMembership` in the
  target channel's workspace
  [backend/app/api/v1/channels.py:add_member_to_channel]
- Only a DM (`KIND_DM`) may be deleted through `DELETE /channels/{channel_id}`;
  ordinary channels raise `forbidden`
  [backend/app/api/v1/channels.py:delete_channel_route]
- Message pagination cursors are mutually exclusive: `around` cannot be
  combined with `before` or `after`, and `before` cannot be combined with
  `after` [backend/app/api/v1/channels.py:read_messages]
- The page limit is validated with `ge=1` and defaults to `DEFAULT_PAGE_SIZE`
  [backend/app/api/v1/channels.py:read_messages]
- Any message route requires the caller to pass `require_channel_access` for
  the message's channel [backend/app/api/v1/messages.py:_load_message]
- Only the message author or a workspace manager may edit, delete or restore a
  message [backend/app/api/v1/messages.py:_can_modify]
- Only the message author or a workspace manager may pin or unpin a message
  [backend/app/api/v1/messages.py:pin_message]
- Reactions may be added or removed by any caller with channel access, without
  author or manager rights [backend/app/api/v1/messages.py:add_reaction]
- The thread reply limit defaults to `MAX_PAGE_SIZE` and is validated with
  `ge=1` [backend/app/api/v1/messages.py:read_replies]

### Files, invites and users

- Uploading a file requires the `workspace_id` query parameter; a missing value
  raises `validation_error` [backend/app/api/v1/files.py:upload_file]
- The uploader must be a member of the target workspace
  [backend/app/api/v1/files.py:upload_file]
- Download is allowed only for the file owner or when the file is attached to
  a message in a channel the caller can access
  [backend/app/api/v1/files.py:download_file]
- A file missing from disk raises `forbidden("file is no longer available")`
  [backend/app/api/v1/files.py:download_file]
- Every download response sets `X-Content-Type-Options: nosniff`; inline
  `image/*` responses additionally get a restrictive `Content-Security-Policy`
  [backend/app/api/v1/files.py:download_file]
- Listing, creating and revoking invites all require a manager membership
  [backend/app/api/v1/invites.py:read_invites]
- Revoking requires the invite to exist **and** belong to the `workspace_id` in
  the path, else `not_found` [backend/app/api/v1/invites.py:delete_invite]
- Accepting an invite requires an authenticated caller
  [backend/app/api/v1/invites.py:accept_invite]
- The user directory only returns people who share at least one workspace with
  the caller [backend/app/api/v1/users.py:read_users]
- The directory search term is stripped and literal `%` characters are removed
  before the `ilike` pattern is built
  [backend/app/api/v1/users.py:read_users]
- The directory result set is hard-capped at 50 rows and ordered by
  `(User.name, User.id)` [backend/app/api/v1/users.py:read_users]
- Search requires workspace membership and bounds input: `q` `max_length=200`
  (default `""`) and `limit` `ge=1` (default 30)
  [backend/app/api/v1/search.py:search]

### Workspaces, projects and schedule

- Only owners and admins (managers) may create a private channel
  [backend/app/api/v1/workspaces.py:create_new_channel]
- Channel members must already be workspace members; a missing member raises
  `not_found("that person is not a member of this workspace")`
  [backend/app/api/v1/workspaces.py:create_new_channel]
- Duplicate member ids are de-duplicated while preserving order
  [backend/app/api/v1/workspaces.py:create_new_channel]
- Only owners and admins may change member roles, and only an owner may grant
  the `owner` role [backend/app/api/v1/workspaces.py:update_member_role]
- A workspace must keep at least one owner: demoting or removing an owner
  when fewer than or equal to one owner remains raises
  `conflict("a workspace must keep at least one owner")`
  [backend/app/api/v1/workspaces.py:_guard_last_owner]
- Removing a member requires manager rights and the target must be an existing
  workspace member [backend/app/api/v1/workspaces.py:delete_member]
- A DM can only be opened with a user who is a member of the same workspace
  [backend/app/api/v1/workspaces.py:open_dm]
- All project, roadmap, task and comment routes resolve the owning workspace
  and require workspace membership through `_require_workspace_member`
  [backend/app/api/v1/projects.py:_require_workspace_member]
- Project mutation requires `can_manage_project(project, membership, user.id)`
  [backend/app/api/v1/projects.py:patch_project]
- The project's creator can never be removed from its own project roster
  [backend/app/api/v1/projects.py:delete_project_member]
- Roadmap mutation requires `can_manage_project` on the roadmap's parent
  project [backend/app/api/v1/projects.py:patch_roadmap]
- Deleting a roadmap leaves its tasks in place
  [backend/app/api/v1/projects.py:remove_roadmap]
- Task deletion requires `can_delete_task(task, project, membership, user.id)`
  [backend/app/api/v1/projects.py:remove_task]
- Task creation requires only workspace membership (no manage check)
  [backend/app/api/v1/projects.py:post_task]
- A task comment may be deleted only by its author or by a manager
  [backend/app/api/v1/projects.py:remove_task_comment]
- All milestone routes require the caller to be a member of the project's
  workspace [backend/app/api/v1/milestones.py:_require_workspace_member]
- Creating, updating and deleting a milestone require
  `can_manage_project(project, membership, user.id)`
  [backend/app/api/v1/milestones.py:post_milestone]
- Reading milestones requires only workspace membership, not project management
  rights [backend/app/api/v1/milestones.py:read_milestones]
- Event RSVP values are validated against the `RESPONSES` collection before the
  event is loaded; an unknown value raises `not_found("unknown response")`
  [backend/app/api/v1/schedule.py:post_rsvp]
- Event mutation requires the caller to be the event creator or a workspace
  manager [backend/app/api/v1/schedule.py:patch_event]
- The event creator cannot be removed from their own attendee list
  [backend/app/api/v1/schedule.py:delete_attendee]
- RSVP requires only event access, not creator or manager rights
  [backend/app/api/v1/schedule.py:post_rsvp]
- The audience of a deleted event is captured with `event_audience` **before**
  the row is deleted, so a private event's deletion is not announced to the
  whole workspace [backend/app/api/v1/schedule.py:remove_event]

### Organization

- Every org route requires an authenticated caller; workspace-scoped org routes
  also depend on `WorkspaceMember`
  [backend/app/api/v1/org.py:read_org]
- Unit-scoped org routes take no `workspace_id` in the path: the workspace is
  derived from the loaded unit via `unit.workspace_id`
  [backend/app/api/v1/org.py:_unit_context]
- Unit mutations are bounded by the caller's reach: the `scope` from
  `org_service.managed_unit_ids(...)` is passed into every changing org
  service call [backend/app/api/v1/org.py:post_org_unit]
- A unit can only be deleted when it is empty
  [backend/app/api/v1/org.py:delete_org_unit]
- Mutating org routes commit the session before emitting the realtime event, so
  the broadcast always follows a durable write
  [backend/app/api/v1/org.py:post_org_unit]
- Serialized org units are returned as a list and index `[0]` is taken, so
  `serialize_units` must return a non-empty list for the requested unit
  [backend/app/api/v1/org.py:post_org_unit]

### WebSocket

- The WebSocket requires a valid `token` query parameter; an unauthenticated
  socket is accepted and then closed with code `AUTH_FAILED` (4401)
  [backend/app/api/v1/realtime.py:websocket_endpoint]
- Presence the user chose for themselves (values in `PRESENCE_CLAIMED`) is
  preserved on connect; only a non-claimed presence is overwritten with
  `"online"` [backend/app/api/v1/realtime.py:websocket_endpoint]
- Presence is set to `"offline"` only when the caller's last socket goes away
  (`hub.socket_count(user.id) == 0`)
  [backend/app/api/v1/realtime.py:websocket_endpoint]
- Client payloads must be dicts; a non-dict payload is ignored
  [backend/app/api/v1/realtime.py:_handle_client_event]
- `"ping"` is answered with a `"pong"` frame and no database work
  [backend/app/api/v1/realtime.py:_handle_client_event]
- `"typing"` frames require a string `channel_id`; a missing or non-string
  `channel_id` is ignored
  [backend/app/api/v1/realtime.py:_handle_typing]
- `"read"` frames require a string `channel_id` and, when present, a string
  `message_id` [backend/app/api/v1/realtime.py:_handle_read]
- Typing and read frames require channel access for the socket's user; an
  `AppError` from `require_channel_access` is swallowed and the frame is
  dropped [backend/app/api/v1/realtime.py:_handle_typing]
- The `"hello"` frame carries the persisted user row's presence
  [backend/app/api/v1/realtime.py:websocket_endpoint]

## Side Effects

- Signup inserts a new `User` row and commits, and creates a workspace and its
  owner membership via `create_workspace`
  [backend/app/api/v1/auth.py:signup]
- Signup, login and refresh issue access and refresh JWTs via
  `create_access_token` / `create_refresh_token`
  [backend/app/api/v1/auth.py:_tokens]
- Channel metadata is written to the channel row and committed, and broadcast
  via `events.emit_channel_updated`
  [backend/app/api/v1/channels.py:update_channel]
- Joining and leaving write channel membership rows and commit, and broadcast
  via `events.emit_members_changed` [backend/app/api/v1/channels.py:join_channel]
- Marking a channel read updates the read cursor via `mark_read` and commits,
  then broadcasts `events.emit_unread_counts`
  [backend/app/api/v1/channels.py:mark_channel_read]
- Posting a message creates the message row and commits, and broadcasts
  `events.emit_message_created` [backend/app/api/v1/channels.py:post_message]
- Upload writes the file to disk and creates a file record via `save_upload`,
  then commits; afterwards `purge_orphan_files(session,
  get_settings().orphan_file_hours)` deletes unreferenced files from disk and
  the database [backend/app/api/v1/files.py:upload_file]
- Download streams the file from disk via `FileResponse` using
  `disk_path(record)` [backend/app/api/v1/files.py:download_file]
- Accepting an invite creates the membership and channel access for the user,
  then commits, and broadcasts `events.emit_members_changed` for every public
  channel of the workspace [backend/app/api/v1/invites.py:accept_invite]
- Creating an invite writes an `Invite` row via `invite_service.create_invite`
  and commits; revoking stamps it via `invite_service.revoke_invite` and
  commits [backend/app/api/v1/invites.py:create_new_invite]
- Profile updates write name, title, avatar_color, status_text, presence and
  `last_seen_at` onto the user row and commit, then broadcast
  `events.emit_presence` and `events.emit_user_updated`
  [backend/app/api/v1/me.py:update_me]
- Editing, deleting, restoring, pinning and reacting to a message mutate the
  message and commit, and broadcast the matching `events.emit_message_*` /
  `events.emit_reaction_updated` [backend/app/api/v1/messages.py:update_message]
- Creating, updating and deleting a milestone writes the milestone and commits,
  and broadcasts `events.emit_milestone_*`
  [backend/app/api/v1/milestones.py:post_milestone]
- Every mutating project route commits before emitting its realtime event
  [backend/app/api/v1/projects.py:post_project]
- Comment creation returns the author as `UserOut.model_validate(user)` rather
  than a stored author column
  [backend/app/api/v1/projects.py:post_task_comment]
- Every org mutation commits and then broadcasts an org-changed realtime event
  for the workspace [backend/app/api/v1/org.py:post_org_unit]
- Every event mutation commits before emitting `emit_event_created` /
  `emit_event_updated` / `emit_event_deleted`
  [backend/app/api/v1/schedule.py:post_event]
- Creates a workspace row (and its owner membership) and commits
  [backend/app/api/v1/workspaces.py:create_new_workspace]
- Creates a channel row with its channel members and commits, then broadcasts
  `events.emit_channel_created` and, when the channel was created with members,
  `events.emit_members_changed`
  [backend/app/api/v1/workspaces.py:create_new_channel]
- Creates a DM channel and commits
  [backend/app/api/v1/workspaces.py:open_dm]
- Updates a workspace membership role and commits
  [backend/app/api/v1/workspaces.py:update_member_role]
- Removes a member: deletes `ChannelMember`, `OrgUnitMember` and
  `OrgUnitManager` rows for the removed user in this workspace, removes the
  workspace membership, and commits
  [backend/app/api/v1/workspaces.py:delete_member]
- Registers the WebSocket in the realtime hub on connect and unregisters it on
  disconnect [backend/app/api/v1/realtime.py:websocket_endpoint]
- Writes `User.presence` and `User.last_seen_at` to the database on connect and
  commits, and broadcasts a presence realtime event
  [backend/app/api/v1/realtime.py:websocket_endpoint]
- Sends a `"hello"` frame containing the serialized user to the connecting
  socket, and a `"pong"` frame in answer to a `"ping"` client frame
  [backend/app/api/v1/realtime.py:websocket_endpoint]
- Writes read receipts via `mark_read` and commits, then sends an `"unread"`
  frame with the recalculated channel count to the user
  [backend/app/api/v1/realtime.py:_handle_read]
- Writes `User.presence = "offline"` and `User.last_seen_at` to the database
  when the last socket closes, commits, and broadcasts an offline presence event
  [backend/app/api/v1/realtime.py:websocket_endpoint]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
