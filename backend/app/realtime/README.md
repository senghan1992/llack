# Realtime Hub & Event Emitters

## Overview

The WebSocket delivery layer of the backend, split in two:

- `hub.py` owns the **routing** — an in-memory registry of open sockets and the
  primitives that write JSON to them. It deliberately knows nothing about the
  database or about who is allowed to see what.
- `events.py` owns the **audience** — one `emit_*` function per domain event.
  Each one queries the services layer for the recipient set, renders a
  per-viewer payload, and hands it to the hub.

Per-viewer data (a reaction's "did I react" flag, a channel's unread count) is
rendered once per recipient so every client sees its own truth
[backend/app/realtime/events.py] module docstring.

## Interface

### Hub (`hub.py`)

- `Connection` — dataclass (`eq=False`) holding per-socket state: `user_id`,
  `websocket`, and a per-socket `asyncio.Lock`
  [backend/app/realtime/hub.py:Connection]
- `Hub` — the in-memory connection registry keyed by `user_id`
  [backend/app/realtime/hub.py:Hub]
- `Hub.register(user_id, websocket) -> Connection` — creates a `Connection` and
  adds it to the user's socket set [backend/app/realtime/hub.py:Hub.register]
- `Hub.unregister(connection) -> None` — removes the socket from the registry
  [backend/app/realtime/hub.py:Hub.unregister]
- `Hub.socket_count(user_id) -> int` — number of open sockets for one user
  [backend/app/realtime/hub.py:Hub.socket_count]
- `Hub.is_online(user_id) -> bool` — whether the user has any socket
  [backend/app/realtime/hub.py:Hub.is_online]
- `Hub.online_user_ids() -> set[str]` — every user with at least one socket
  [backend/app/realtime/hub.py:Hub.online_user_ids]
- `Hub.send(connection, payload) -> bool` — writes one JSON payload to one
  socket; returns `False` when the socket died
  [backend/app/realtime/hub.py:Hub.send]
- `Hub.send_to_user(user_id, payload) -> None` — fans a payload out to every
  socket of one user [backend/app/realtime/hub.py:Hub.send_to_user]
- `Hub.send_to_users(user_ids, payload) -> None` — fans a payload out to every
  socket of every listed user [backend/app/realtime/hub.py:Hub.send_to_users]
- `hub` — the module-level singleton `Hub` instance
  [backend/app/realtime/hub.py:hub]
- Package re-exports: `__all__ = ["Connection", "Hub", "hub"]`
  [backend/app/realtime/__init__.py:__all__]

### Event emitters (`events.py`)

Each function takes an `AsyncSession` plus the domain row, computes an audience,
and broadcasts one payload.

| Function | Event `type` | Payload keys |
| --- | --- | --- |
| `emit_message_created` [backend/app/realtime/events.py:emit_message_created] | `message.created` | `message` |
| `emit_message_updated` [backend/app/realtime/events.py:emit_message_updated] | `message.updated` | `message` |
| `emit_message_deleted` [backend/app/realtime/events.py:emit_message_deleted] | `message.deleted` | `message_id`, `channel_id` |
| `emit_reaction_updated` [backend/app/realtime/events.py:emit_reaction_updated] | `reaction.updated` | `message` |
| `emit_typing` [backend/app/realtime/events.py:emit_typing] | `typing` | `channel_id`, `user_id`, `name`, `on` |
| `emit_presence` [backend/app/realtime/events.py:emit_presence] | `presence` | `user_id`, `presence`, `last_seen_at` |
| `emit_user_updated` [backend/app/realtime/events.py:emit_user_updated] | `user.updated` | `user` |
| `emit_channel_created` [backend/app/realtime/events.py:emit_channel_created] | `channel.created` | `channel` |
| `emit_channel_updated` [backend/app/realtime/events.py:emit_channel_updated] | `channel.updated` | `channel` |
| `emit_members_changed` [backend/app/realtime/events.py:emit_members_changed] | `members.changed` | `channel_id`, `members` |
| `emit_event_created` [backend/app/realtime/events.py:emit_event_created] | `event.created` | `event` |
| `emit_event_updated` [backend/app/realtime/events.py:emit_event_updated] | `event.updated` | `event` |
| `emit_event_deleted` [backend/app/realtime/events.py:emit_event_deleted] | `event.deleted` | `event_id` |
| `emit_project_created` [backend/app/realtime/events.py:emit_project_created] | `project.created` | `project` |
| `emit_project_updated` [backend/app/realtime/events.py:emit_project_updated] | `project.updated` | `project` |
| `emit_project_deleted` [backend/app/realtime/events.py:emit_project_deleted] | `project.deleted` | `project_id` |
| `emit_task_created` [backend/app/realtime/events.py:emit_task_created] | `task.created` | `task` |
| `emit_task_updated` [backend/app/realtime/events.py:emit_task_updated] | `task.updated` | `task` |
| `emit_task_deleted` [backend/app/realtime/events.py:emit_task_deleted] | `task.deleted` | `project_id`, `task_id` |
| `emit_milestone_created` [backend/app/realtime/events.py:emit_milestone_created] | `milestone.created` | `milestone` |
| `emit_milestone_updated` [backend/app/realtime/events.py:emit_milestone_updated] | `milestone.updated` | `milestone` |
| `emit_milestone_deleted` [backend/app/realtime/events.py:emit_milestone_deleted] | `milestone.deleted` | `milestone_id` |
| `emit_org_changed` [backend/app/realtime/events.py:emit_org_changed] | `org.changed` | `workspace_id` |
| `emit_unread_counts` [backend/app/realtime/events.py:emit_unread_counts] | `unread` | `channel_id`, `count` |

- `user_workspace_ids(session, user_id) -> list[str]` — reads the user's
  workspace membership ids [backend/app/realtime/events.py:user_workspace_ids]

## Invariants

- The hub only routes; deciding who may see an event is the caller's job —
  audience computation belongs to the services (`channel_audience`,
  `workspace_member_ids`, `event_audience`) [backend/app/realtime/hub.py:Hub]
- `Connection` is `@dataclass(eq=False)`, so registry membership is
  identity-based: two sockets for the same user are distinct entries
  [backend/app/realtime/hub.py:Connection]
- Each `Connection` carries its own `asyncio.Lock`, so concurrent sends to one
  socket are serialized [backend/app/realtime/hub.py:Connection.lock]
- Every socket write goes through `Hub.send`, which swallows exceptions and
  reports the socket as dead (`False`) rather than raising
  [backend/app/realtime/hub.py:Hub.send]
- Registry mutation is guarded by the hub-wide `asyncio.Lock` in `register` and
  `unregister` [backend/app/realtime/hub.py:Hub._lock]
- `unregister` removes the `user_id` entry entirely when its last socket is
  discarded, so empty sets never linger [backend/app/realtime/hub.py:Hub.unregister]
- `unregister` is a no-op when the `user_id` has no entry in the registry
  [backend/app/realtime/hub.py:Hub.unregister]
- `send_to_user` iterates a snapshot (`list(...)`) of the user's socket set, so
  mutation during iteration is safe
  [backend/app/realtime/hub.py:Hub.send_to_user]
- A single logical event may be delivered to several sockets of the same user;
  every socket of a targeted user receives it
  [backend/app/realtime/hub.py:Hub.send_to_users]
- Payloads containing per-viewer data (the reaction "me" flag, a channel's
  unread count) are rendered once per recipient so every client sees its own
  truth [backend/app/realtime/events.py] module docstring
- If `build_message_out` returns `None` for a viewer, that viewer is skipped and
  receives nothing [backend/app/realtime/events.py:emit_message_created]
- `emit_message_created` emits the per-viewer message event first, then calls
  `emit_unread_counts` for the same channel
  [backend/app/realtime/events.py:emit_message_created]
- `emit_typing` discards the typing user from the audience, so the author is
  never notified of their own typing [backend/app/realtime/events.py:emit_typing]
- `emit_presence` discards the subject user from the recipients
  [backend/app/realtime/events.py:emit_presence]
- `emit_user_updated` discards the subject user from the recipients
  [backend/app/realtime/events.py:emit_user_updated]
- `emit_presence` and `emit_user_updated` address the union of
  `workspace_member_ids` over every workspace the user belongs to
  [backend/app/realtime/events.py:emit_presence]
- Channel visibility is asymmetric: `emit_channel_created` targets the whole
  workspace (`workspace_member_ids`), while `emit_channel_updated` targets only
  `channel_audience` [backend/app/realtime/events.py:emit_channel_created]
- Project, task and milestone events are workspace-wide
  (`workspace_member_ids` of `project.workspace_id`), not restricted to the
  channel audience [backend/app/realtime/events.py:emit_project_created]
- `emit_event_deleted` accepts a caller-computed recipient set and performs no
  audience lookup of its own
  [backend/app/realtime/events.py:emit_event_deleted]
- Schedule events are addressed via `event_audience` (per-viewer set), one
  serialization per viewer [backend/app/realtime/events.py:emit_event_created]
- `last_seen_at` is serialized as ISO-8601 with the `+00:00` suffix rewritten to
  `Z` [backend/app/realtime/events.py:emit_presence]
- Unread count falls back to `0` when the channel id is missing from the
  computed counts map [backend/app/realtime/events.py:emit_unread_counts]
- Project/task/milestone serialization takes a single-item list and the emitter
  uses `rendered[0]` — the list result is positional
  [backend/app/realtime/events.py:emit_project_created]
- `emit_members_changed` publishes the member list of the channel to the whole
  channel audience [backend/app/realtime/events.py:emit_members_changed]

## Side Effects

- Adds a new `Connection` to `self._connections[user_id]` under the hub lock
  [backend/app/realtime/hub.py:Hub.register]
- Removes a `Connection` from `self._connections` and pops the user key when
  empty [backend/app/realtime/hub.py:Hub.unregister]
- WebSocket JSON write to a single socket via `websocket.send_json`
  [backend/app/realtime/hub.py:Hub.send]
- WebSocket broadcast to all sockets of one user
  [backend/app/realtime/hub.py:Hub.send_to_user]
- WebSocket broadcast to all sockets of many users
  [backend/app/realtime/hub.py:Hub.send_to_users]
- Logs a debug message with traceback when a socket send fails
  [backend/app/realtime/hub.py:Hub.send]
- DB read: `load_message_bundle(session, [message])` before rendering a message
  event [backend/app/realtime/events.py:emit_message_created]
- DB read: `channel_audience(session, channel)` to compute the recipient set of
  channel-scoped events [backend/app/realtime/events.py:emit_message_updated]
- DB read: `workspace_member_ids(session, workspace_id)` for workspace-wide
  audiences [backend/app/realtime/events.py:emit_channel_created]
- DB read: `list_channel_members(session, channel)` to build the
  `members.changed` payload [backend/app/realtime/events.py:emit_members_changed]
- DB read: `event_audience(session, event)` to compute schedule-event recipients
  [backend/app/realtime/events.py:emit_event_created]
- DB read: `serialize_channel` / `serialize_event` / `serialize_projects` /
  `serialize_tasks` / `serialize_milestones`, each called per viewer
  [backend/app/realtime/events.py:emit_channel_updated]
- DB read: `unread_counts(session, [channel.id], viewer_id)` per viewer for the
  unread event [backend/app/realtime/events.py:emit_unread_counts]
- DB read: `session.scalars(select(WorkspaceMembership.workspace_id)...)` inside
  `user_workspace_ids` [backend/app/realtime/events.py:user_workspace_ids]
- Broadcasts every event `type` listed in the Interface table over the WebSocket
  hub [backend/app/realtime/events.py:emit_message_created] through
  [backend/app/realtime/events.py:emit_org_changed]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
