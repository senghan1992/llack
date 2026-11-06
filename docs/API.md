# Llack API contract

Base URL `http://127.0.0.1:8000`, prefix `/api/v1`. Every response is JSON except
file downloads. All timestamps are ISO-8601 UTC strings (`2026-11-02T09:14:00Z`).

## Errors

```json
{ "error": { "code": "not_found", "message": "channel not found", "field": null } }
```

Codes: `unauthorized` (401), `forbidden` (403), `not_found` (404), `conflict` (409),
`validation_error` (422), `rate_limited` (429), `internal` (500).

## Auth

`Authorization: Bearer <access_token>` on every protected route.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/auth/signup` | `{email, password, name, workspace_name}` | `Session` |
| POST | `/auth/login` | `{email, password}` | `Session` |
| POST | `/auth/refresh` | `{refresh_token}` | `Tokens` |
| GET | `/me` | | `User` |
| PATCH | `/me` | `{name?, title?, avatar_color?, status_text?, presence?}` | `User` |
| POST | `/files?workspace_id=…` | multipart `file` | `File` |
| GET | `/files/{id}` | | binary |

`PATCH /me` accepts `presence` of `"online"`, `"busy"`, `"dnd"`, `"away"` or
`"brb"` — a person may say they are busy, away or unreachable, but never that
they are offline. The change is broadcast to the workspace as a `presence`
event.

`GET /files/{id}` takes the access token either as a bearer header or as a
`?token=` query parameter — an `<img>` tag cannot send a header, so the browser
needs it in the URL.

`POST /files` needs the workspace the file belongs to (`workspace_id`); the
caller must be a member of it. The workspace decides where the file is kept and
how much room it may take — the whole rule is in
[docs/FILES.md](FILES.md). The stored type is the one the **bytes** prove,
not the one the browser declared.

`Session` = `{access_token, refresh_token, user: User, workspace: Workspace}`.
`Tokens` = `{access_token, refresh_token}`. Access tokens live 30 minutes, refresh
tokens 30 days. Passwords are hashed with argon2. Emails are lowercased and unique.

## Workspace, channels, members

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/workspaces` | | `Workspace[]` |
| POST | `/workspaces` | `{name}` | `Workspace` |
| GET | `/workspaces/{wid}/bootstrap` | | `Bootstrap` |
| GET | `/workspaces/{wid}/channels` | | `Channel[]` |
| POST | `/workspaces/{wid}/channels` | `{name, topic?, is_private?, member_ids?}` | `Channel` |
| GET | `/workspaces/{wid}/dms` | | `Channel[]` |
| POST | `/workspaces/{wid}/dms` | `{user_id}` | `Channel` |
| GET | `/workspaces/{wid}/members` | | `Member[]` |
| PATCH | `/workspaces/{wid}/members/{uid}` | `{role}` | `Member` |
| DELETE | `/workspaces/{wid}/members/{uid}` | | `204` |
| GET | `/workspaces/{wid}/search` | `?q=&limit=30` | `SearchResult[]` |
| GET | `/users` | `?q=` | `User[]` |
| GET | `/workspaces/{wid}/invites` | | `Invite[]` |
| POST | `/workspaces/{wid}/invites` | `{email, role?}` | `Invite` |
| DELETE | `/workspaces/{wid}/invites/{id}` | | `204` |
| POST | `/invites/accept` | `{token}` | `Workspace` |
| GET | `/channels/{cid}` | | `Channel` |
| PATCH | `/channels/{cid}` | `{name?, topic?, purpose?}` | `Channel` |
| POST | `/channels/{cid}/join` | | `Channel` |
| POST | `/channels/{cid}/leave` | | `204` |
| GET | `/channels/{cid}/members` | | `Member[]` |
| POST | `/channels/{cid}/members` | `{user_id}` | `204` |
| DELETE | `/channels/{cid}` | | `204` |
| GET | `/channels/{cid}/pins` | | `Message[]` |
| POST | `/channels/{cid}/read` | `{message_id?}` | `204` |
| GET | `/channels/{cid}/messages` | `?limit=50&before=<message_id>` | `{messages: Message[], has_more: bool}` |
| POST | `/channels/{cid}/messages` | `{body, parent_id?, reply_to_id?, inline?, attachment_ids?}` | `Message` |

`DELETE /channels/{cid}` deletes a **direct message** — for both of the people
in it. A conversation between two people is theirs alone: when one of them
ends it, it ends for the other one too. Ordinary channels are not deleted
this way.

A message answers another one in two ways at once. `reply_to_id` names the
message it answers — the one it quotes — and `inline: true` says it was written
in the channel, so it shows there as well as in that message's thread. The
server puts the reply in the thread of the message it answers either way, and
replies are one level deep: answering an answer joins the thread of the messagethat answer answered. A message whose channel differs, or which has been
deleted, cannot be answered.
| GET | `/messages/{mid}/replies` | `?limit=100` | `Message[]` |
| PATCH | `/messages/{mid}` | `{body}` | `Message` |
| DELETE | `/messages/{mid}` | | `204` |
| POST | `/messages/{mid}/reactions` | `{emoji}` | `Message` |
| DELETE | `/messages/{mid}/reactions/{emoji}` | | `Message` |
| POST | `/messages/{mid}/pin` | | `Message` |
| DELETE | `/messages/{mid}/pin` | | `Message` |

## Schedule

The team calendar. An event belongs to a workspace. Most events are open to the
whole team; a private one (`is_private`) is visible only to its creator and the
people it invites.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/workspaces/{wid}/events` | `?from=&to=` | `Event[]` |
| POST | `/workspaces/{wid}/events` | `EventCreate` | `Event` |
| GET | `/events/{eid}` | | `Event` |
| PATCH | `/events/{eid}` | `EventUpdate` | `Event` |
| DELETE | `/events/{eid}` | | `204` |
| POST | `/events/{eid}/attendees` | `{user_id}` | `Event` |
| DELETE | `/events/{eid}/attendees/{uid}` | | `204` |
| POST | `/events/{eid}/rsvp` | `{response}` | `Event` |

`GET /workspaces/{wid}/events` returns the events that overlap the window, and
only those the caller may see. `from` and `to` are ISO-8601 instants; without
them the window is 30 days back and 180 days ahead.

`EventCreate` = `{title, starts_at, ends_at, description?, location?, all_day?,
is_private?, channel_id?, attendee_ids?}`. `EventUpdate` takes the same fields,
all optional. `response` is one of `accepted`, `declined`, `tentative`.

Only the creator or a workspace admin may change or delete an event. Anyone the
event is visible to may answer for themselves.

## Projects

The board of work. A project belongs to a workspace and is open to everyone in
it — the way a public channel is. What makes it *yours* is its roster: the
people named on the project are its members.

A project may point at a channel (`channel_id`): the room where it is talked
about. That is the whole link between the two — a project is not a place of
its own, it is another way of looking at the same team.

A project may also carry several **roadmaps** — the lanes of work it is
planned in, one per chip above its board. A task belongs to at most one of
them. Deleting a roadmap cuts the link and leaves its tasks on the board.
There is no way to open a new one: the roadmaps of a project are given, not
made.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/workspaces/{wid}/projects` | | `Project[]` |
| POST | `/workspaces/{wid}/projects` | `ProjectCreate` | `Project` |
| GET | `/workspaces/{wid}/tasks` | | `Task[]` |
| GET | `/projects/{pid}` | | `Project` |
| PATCH | `/projects/{pid}` | `ProjectUpdate` | `Project` |
| DELETE | `/projects/{pid}` | | `204` |
| POST | `/projects/{pid}/members` | `{user_id}` | `Project` |
| DELETE | `/projects/{pid}/members/{uid}` | | `204` |
| GET | `/projects/{pid}/roadmaps` | | `Roadmap[]` |
| PATCH | `/roadmaps/{rid}` | `{name?}` | `Roadmap` |
| DELETE | `/roadmaps/{rid}` | | `204` |
| GET | `/projects/{pid}/tasks` | | `Task[]` |
| POST | `/projects/{pid}/tasks` | `TaskCreate` | `Task` |
| PATCH | `/tasks/{tid}` | `TaskUpdate` | `Task` |
| DELETE | `/tasks/{tid}` | | `204` |
| POST | `/tasks/{tid}/comments` | `{body}` | `TaskComment` |
| DELETE | `/task-comments/{cid}` | | `204` |

`ProjectCreate` = `{name, description?, purpose?, deliverables?, channel_id?,
member_ids?}`. `description` is what the project is about, in the words of
the team doing it — the one line the board shows under the name.
`ProjectUpdate` takes the same fields, all optional. The creator is on the
roster either way, and cannot be taken off it.

`TaskCreate` = `{title, description?, status?, assignee_id?, roadmap_id?,
milestone_id?, start_at?, due_at?}`. `TaskUpdate` takes the same fields plus
`position`, all optional. `status` is one of `request`, `todo`, `in-progress`,
`done` — the four columns of the board. `roadmap_id` pins the task to one of the
project's roadmaps; leave it out and the task sits on the board alone.
`milestone_id` gives the task one of the project's milestones.
A task that moves to another column is placed at the end of it; a `position`
names the exact place. A column renumbers itself from zero whenever a card
leaves or arrives.

`GET /workspaces/{wid}/tasks` returns the tasks of the whole workspace that are
**mine** and not finished — the list that answers "what is mine to do?".

Only the creator of a project or a workspace admin may change the project or
its roster. Anyone in the workspace may add and change tasks; a task may be
deleted by its author, the owner of the project, or an administrator. A
comment may be deleted by its author or an administrator.

A roadmap may be listed by anyone in the workspace, and renamed or deleted by
the owner of the project or a workspace admin. There is no way to open a new
one: the roadmaps of a project are given, not made.

## Milestones

The dated markers of what a project is to deliver. A milestone has a title, a
start and an end, a colour of its own, a description and the cards that
deliver it — a card belongs to at most one milestone.

A milestone says *when* the work is to be delivered — a dated marker above the
cards, not a column of its own.

A milestone that holds cards shows their progress: the share of them that is
done. One that holds none shows the progress the team wrote down by hand.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/milestones` | | `Milestone[]` |
| POST | `/projects/{pid}/milestones` | `MilestoneCreate` | `Milestone` |
| PATCH | `/milestones/{mid}` | `MilestoneUpdate` | `Milestone` |
| DELETE | `/milestones/{mid}` | | `204` |

`MilestoneCreate` = `{title, start_at, end_at, color?, progress?, description?,
task_ids?}`. `MilestoneUpdate` takes the same fields, all optional.
`title` is required, trimmed, 1..120 characters. `start_at` and `end_at` are
ISO-8601 instants, and the end may not be before the start. `color` is at most
16 characters, `#4f6cff` by default. `progress` is 0..100 — the progress
written by hand, which shows only while the milestone holds no cards.
`description` is at most 4000 characters. `task_ids` names the cards that
deliver the milestone; a card named here leaves the milestone it was in.

`GET /projects/{pid}/milestones` lists the milestones of a project, the ones
that start first in front.

Only the creator of the project or a workspace admin may open, change or
delete a milestone. Anyone in the workspace may read them.

## Organization

The shape of the company. A workspace holds a tree of **org units** — 부서, 팀,
whatever the team calls them — and the people who sit in them. The tree is
flat on the wire: every unit names its `parent_id`, and a unit without a
parent sits at the top.

Two tiers of authority live here. The first is the workspace role: the owner
(최초 관리자) and the admins (워크스페이스 관리자) may do anything inside the
workspace. The second is the scoped one: a person appointed to look after a
unit looks after that unit **and everything below it**.

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/workspaces/{wid}/org` | | `OrgOverview` |
| POST | `/workspaces/{wid}/org/units` | `OrgUnitCreate` | `OrgUnit` |
| PATCH | `/org/units/{uid}` | `OrgUnitUpdate` | `OrgUnit` |
| DELETE | `/org/units/{uid}` | | `204` |
| POST | `/org/units/{uid}/members` | `{user_id}` | `204` |
| DELETE | `/org/units/{uid}/members/{user_id}` | | `204` |
| POST | `/org/units/{uid}/managers` | `{user_id}` | `204` |
| DELETE | `/org/units/{uid}/managers/{user_id}` | | `204` |

`OrgUnitCreate` = `{name, parent_id?, kind?, description?}`. `OrgUnitUpdate`
takes `{name?, kind?, description?, parent_id?}` — a null `parent_id` moves the
unit to the top of the tree. `name` is required, trimmed, 1..120 characters.
`kind` is a free label the workspace picks for itself ("부서", "팀"), at most
24 characters, `team` by default. `description` is at most 4000 characters.
`parent_id` must name a unit of the same workspace.

`GET /workspaces/{wid}/org` returns the whole organization at once: the units,
the workspace admins, the caller's own role, and the units the caller looks
after. For an owner or an admin that is every unit of the workspace; for
everybody else it is the units they look after.

The permission rules:

- A unit at the top of the tree is opened by the workspace owner and admins
  alone. Every other unit may be opened by a manager whose reach holds its
  parent.
- A unit is renamed, written about, moved, deleted and given a roster by
  whoever looks after it.
- Moving a unit needs the reach over both the unit and its new parent, and a
  unit is never hung below one of its own units.
- A unit is only deleted when it is empty — no people, no units below it. Its
  managers go with it.
- People are put into a unit and taken out of it by whoever looks after it.
  They must already be members of the workspace.
- The managers of a unit are appointed and dismissed by whoever looks after
  it. A person may not appoint themselves — they are the manager already — but
  they may step down.
- The roles of the workspace members (`owner`, `admin`, `member`) are changed
  only through `PATCH /workspaces/{wid}/members/{uid}`, and only by an owner
  or an admin: looking after an organization is not looking after the
  workspace.

## Objects

```jsonc
User {
  id: "usr_01H...",
  email: "hyunjin@hanbit.co.kr",
  name: "김현진",
  title: "백엔드 엔지니어",
  avatar_color: "#3f6f52",
  avatar_url: null,          // string|null
  presence: "online",        // online | busy | dnd | away | brb | offline
  last_seen_at: "2026-11-02T09:14:00Z",
  created_at: "2026-11-01T02:00:00Z"
}

Member { user: User, role: "owner" | "admin" | "member", joined_at: "..." }

Workspace { id: "wsp_...", name: "한빛", slug: "hanbit", created_at: "..." }

Channel {
  id: "chl_...",
  workspace_id: "wsp_...",
  name: "design",                 // for dm: the other user's name
  topic: "디자인 리뷰와 배포",
  purpose: "",
  kind: "channel" | "dm",
  is_private: false,
  created_by: "usr_...",
  created_at: "...",
  member_count: 12,
  unread_count: 3,
  last_message_at: "..." | null,
  dm_user: User | null,          // set for kind=dm: the other participant
  members: User[] | null,        // populated on GET /channels/{cid}
  is_member: true                // whether the caller is in this channel
}

Message {
  id: "msg_...",
  channel_id: "chl_...",
  user_id: "usr_...",
  author: User,
  body: "배포 준비 끝났습니다.",
  kind: "text" | "system",
  parent_id: "msg_..." | null,   // thread root; null for a top-level message
  reply_to_id: "msg_..." | null, // the message this one answers
  reply_to: { id, author_name, body, deleted } | null,
  inline: false,                // true when it was written in the channel
  created_at: "...",
  edited_at: "..." | null,
  deleted_at: "..." | null,
  reply_count: 4,
  last_reply_at: "..." | null,
  pinned: false,
  reactions: [{ emoji: "👍", count: 3, user_ids: ["usr_..."], me: false }],
  attachments: [File]
}

File { id: "fil_...", name: "design.png", url: "/api/v1/files/fil_...",
       mime: "image/png", size: 184320 }

Bootstrap {
  workspace: Workspace,
  channels: Channel[],   // kind=channel, the caller's membership resolved
  dms: Channel[],        // kind=dm
  members: Member[],
  me: User,
  org: OrgSummary        // { unit_count: 3, managed_unit_ids: ["org_..."] }
}

Invite {
  id: "inv_...",
  workspace_id: "wsp_...",
  email: "newcomer@hanbit.co.kr",
  role: "member",        // owner | admin | member
  token: "a9f3c1...",   // the shareable code; present on create and list
  created_by: "usr_...",
  created_at: "...",
  expires_at: "..."      // seven days out
}

SearchResult { message: Message, channel: Channel }

Event {
  id: "evt_...",
  workspace_id: "wsp_...",
  title: "주간 스탠드업",
  description: "지난주 산출물과 이번 주 목표를 공유합니다.",
  location: "3층 회의실",
  starts_at: "2026-11-03T01:00:00Z",
  ends_at: "2026-11-03T01:30:00Z",
  all_day: false,
  is_private: false,
  created_by: "usr_...",
  channel_id: "chl_..." | null,   // a room this event belongs to
  created_at: "...",
  updated_at: "...",
  attendees: [{ user: User, response: "accepted" }],
  my_response: "accepted" | "declined" | "tentative" | "pending" | null
}

Project {
  id: "prj_...",
  workspace_id: "wsp_...",
  name: "결제 시스템 개편",
  description: "구독 결제를 다시 만들고, 정산을 한곳에 모읍니다.",
  purpose: "",                 // legacy: kept on the row, no longer asked for
  deliverables: "",            // legacy: kept on the row, no longer asked for
  channel_id: "chl_..." | null,   // the room this project is talked about
  created_by: "usr_...",
  is_archived: false,
  created_at: "...",
  updated_at: "...",
  members: [User],                // the roster — the people who look after it
  is_member: true,                // whether the caller is on that roster
  open_tasks: 4,                  // tasks not finished yet
  my_open_tasks: 2                // of those, the ones that are mine
}

Roadmap {
  id: "rm_...",
  project_id: "prj_...",
  name: "2분기",
  position: 0,                    // the order of the chips above the board
  created_by: "usr_...",
  created_at: "...",
  task_count: 3                   // the tasks pinned to this roadmap
}

Milestone {
  id: "mst_...",
  project_id: "prj_...",
  title: "v1.0 출시",
  start_at: "2026-03-01T00:00:00Z",
  end_at: "2026-06-30T00:00:00Z",
  color: "#4f6cff",               // the colour the team gave it
  progress: 42,                   // the progress that is shown
  manual_progress: 0,             // the progress the slider holds
  description: "",
  task_count: 5,                  // the cards that deliver it
  done_count: 2,                  // how many of them are done
  auto_progress: true,            // true when the progress comes from the cards
  task_ids: ["tsk_..."],          // the cards that deliver it
  created_by: "usr_...",
  created_at: "...",
  updated_at: "..."
}

Task {
  id: "tsk_...",
  project_id: "prj_...",
  title: "결제 도메인 모델 초안",
  description: "구독·정산·환불을 어떻게 나눌지 적습니다.",
  status: "request" | "todo" | "in-progress" | "done",
  assignee_id: "usr_..." | null,
  assignee: User | null,
  roadmap_id: "rm_..." | null,    // the roadmap this task is planned in
  roadmap_name: "2분기" | null,    // its name, for the badge on the card
  milestone_id: "mst_..." | null, // the milestone this task delivers
  milestone_name: "v1.0 출시" | null,
  milestone_color: "#4f6cff" | null,
  created_by: "usr_...",
  start_at: "..." | null,
  due_at: "2026-11-06T14:59:00Z" | null,
  position: 0,                    // the place inside the column
  created_at: "...",
  updated_at: "...",
  comments: [TaskComment],
  comment_count: 2
}

TaskComment {
  id: "tc_...",
  task_id: "tsk_...",
  user_id: "usr_...",
  author: User,
  body: "법무 검토를 받았습니다.",
  created_at: "..."
}

OrgUnit {
  id: "org_...",
  workspace_id: "wsp_...",
  parent_id: "org_..." | null,   // null for a unit at the top of the tree
  name: "프로덕트 개발부",
  kind: "부서",                  // a free label the workspace picks
  description: "",
  position: 0,
  created_at: "...",
  updated_at: "...",
  member_count: 12,
  child_count: 2,                // the units below this one
  depth: 0,                      // a unit at the top has depth 0
  members: [User],               // the people in the unit
  managers: [User],              // the people who look after it
  is_manager: true,              // the caller is appointed to look after this unit
  can_manage: true,              // the caller may rename, move, delete it and change its roster
  can_appoint_managers: true     // the caller may appoint or dismiss its managers
}

OrgOverview {
  units: OrgUnit[],              // a flat list: the tree is drawn from parent_id
  admins: Member[],              // the workspace owners and admins
  my_role: "owner" | "admin" | "member",
  can_manage_admins: true,
  managed_unit_ids: ["org_..."]  // the units the caller looks after
}
```

## WebSocket

`ws://127.0.0.1:8000/api/v1/ws?token=<access_token>`. The socket closes with code
`4401` when the token is missing or expired. The server sends `hello` on connect.

Server → client:

```jsonc
{ "type": "message.created", "message": Message }
{ "type": "message.updated", "message": Message }
{ "type": "message.deleted", "message_id": "msg_...", "channel_id": "chl_..." }
{ "type": "reaction.updated", "message": Message }
{ "type": "typing", "channel_id": "chl_...", "user_id": "usr_...", "name": "김현진", "on": true }
{ "type": "presence", "user_id": "usr_...", "presence": "away", "last_seen_at": "..." }
{ "type": "channel.created", "channel": Channel }
{ "type": "channel.updated", "channel": Channel }
{ "type": "members.changed", "channel_id": "chl_...", "members": [User] }
{ "type": "unread", "channel_id": "chl_...", "count": 3 }
{ "type": "event.created", "event": Event }
{ "type": "event.updated", "event": Event }
{ "type": "event.deleted", "event_id": "evt_..." }
{ "type": "project.created", "project": Project }
{ "type": "project.updated", "project": Project }
{ "type": "project.deleted", "project_id": "prj_..." }
{ "type": "task.created", "task": Task }
{ "type": "task.updated", "task": Task }
{ "type": "task.deleted", "project_id": "prj_...", "task_id": "tsk_..." }
{ "type": "milestone.created", "milestone": Milestone }
{ "type": "milestone.updated", "milestone": Milestone }
{ "type": "milestone.deleted", "milestone_id": "mst_..." }
{ "type": "org.changed", "workspace_id": "wsp_..." }
{ "type": "pong" }
```

Client → server:

```jsonc
{ "type": "typing", "channel_id": "chl_...", "on": true }
{ "type": "read", "channel_id": "chl_...", "message_id": "msg_..." }
{ "type": "ping" }
```

A socket only receives events for channels the user belongs to, plus their own
DMs, presence changes for users in their workspace, the project, task and
milestone events of every project in the workspace, and the organization
changes of their workspace.

## Behaviour rules

- A public channel lists for every workspace member. A private channel lists
  only for its members. A DM lists only for its two participants.
- `POST /channels/{cid}/join` puts a workspace member into a **public** channel
  and refuses a private one — a private room is entered by being added to it,
  never by joining. Leaving a public channel keeps it in the directory (it
  still lists, with `is_member: false`); leaving a private one takes it out of
  the caller's list for good.
- `unread_count` counts messages in the channel newer than the caller's last read
  message, excluding the caller's own messages.
- Deleting a message soft-deletes it: `deleted_at` is set, `body` is cleared, the
  row stays so thread positions hold.
- Editing a message sets `edited_at` and keeps `body`.
- A reaction is unique per (message, user, emoji). One emoji per user per message.
- `POST /workspaces/{wid}/dms` is idempotent: it returns the existing DM when one
  already exists between the caller and `user_id`.
- Creating a channel requires a `role` of owner or admin for private channels.
  Everyone may create a public channel.
- `POST /workspaces/{wid}/channels` takes `member_ids` — the people who are in
  the room from the start. They must already be members of the workspace; a
  room is not a way around the invite. The creator is in the room either way.
- File uploads accept images, PDF, plain text and CSV, the office formats
  (`.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.odt`, `.ods`, `.odp`,
  `.hwp`, `.hwpx`), archives (`.zip`, `.gz`) and RTF, up to 50 MB
  (`MAX_UPLOAD_BYTES`). Files are served from disk under `backend/var/uploads`.
- The stored MIME type is the one the **bytes** prove, never the one the browser
  claimed. A file whose bytes do not match a shareable format is refused.
- Images open in the browser (`inline`); everything else is handed over as a
  download (`attachment`). SVG is always a download — an SVG is a document that
  can carry script. Every download carries `X-Content-Type-Options: nosniff`.
- An event's attendees must already be members of the workspace.
- The creator of an event is an attendee of it from the start, with the answer
  `accepted`.
- A project is open to the whole workspace; its roster is what marks it as
  somebody's. The roster may only hold people who are already members of the
  workspace.
- A task's assignee must be a member of the workspace. A task with nobody on
  it is not a mistake — it is a task waiting for an owner.
- A task keeps its place inside a column. The column renumbers itself from
  zero when a card leaves it or arrives in it.
- A task belongs to at most one roadmap. `roadmap_id` must name a roadmap of the
  task's own project. `DELETE /roadmaps/{rid}` cuts that link and leaves the
  tasks on the board — only the link goes.
- A task belongs to at most one milestone. `milestone_id` must name a milestone
  of the task's own project. A card that is given a milestone leaves the one it
  was in. `DELETE /milestones/{mid}` cuts the link and leaves the tasks on the
  board.
- The progress of a milestone that holds cards is the share of them that is
  done; the progress written by hand shows only while it holds none.
- `DELETE /channels/{cid}` works on a direct message and on nothing else: it
  ends the conversation for both of the people in it.
