# Demo Workspace Seeder

## Overview

A single-module CLI that fills an empty development database with a realistic demo
workspace ("한빛" / slug `hanbit`): five people, public and private channels, threaded
messages, reactions, pins, direct messages, calendar events, a project board with
tasks and milestones, and an organization tree. It is the script behind the
repository-root `make seed` target.

The script owns no HTTP surface of its own; it imports the same service layer the API
uses (`app.core.db`, `app.core.ids`, `app.core.security`, `app.services.invites`,
`app.services.channels`) so the seeded rows are indistinguishable from rows created
through the API.

## Interface

- `BACKEND_ROOT` — backend root directory, prepended to `sys.path` so the `app`
  package imports regardless of the working directory
  [backend/scripts/seed.py:BACKEND_ROOT]
- `WORKSPACE_NAME = "한빛"`, `WORKSPACE_SLUG = "hanbit"` — the fixed demo workspace
  identity used to find an existing workspace [backend/scripts/seed.py:WORKSPACE_NAME]
  [backend/scripts/seed.py:WORKSPACE_SLUG]
- `DEMO_PASSWORD = "hanbit2026"` — shared password for every seeded account
  [backend/scripts/seed.py:DEMO_PASSWORD]
- `INVITED_EMAIL = "newcomer@hanbit.co.kr"` — address of the demo pending invitation
  [backend/scripts/seed.py:INVITED_EMAIL]
- Fixture tables `PEOPLE`, `MESSAGES`, `CHANNELS`, `DIRECT_MESSAGES`, `REACTIONS`,
  `PINS`, `SCHEDULE`, `PROJECTS`, `TASKS`, `MILESTONES`, `ORG_UNITS` — the literal
  seed data [backend/scripts/seed.py:PEOPLE] [backend/scripts/seed.py:CHANNELS]
  [backend/scripts/seed.py:DIRECT_MESSAGES] [backend/scripts/seed.py:REACTIONS]
  [backend/scripts/seed.py:PINS] [backend/scripts/seed.py:SCHEDULE]
  [backend/scripts/seed.py:PROJECTS] [backend/scripts/seed.py:TASKS]
  [backend/scripts/seed.py:MILESTONES] [backend/scripts/seed.py:ORG_UNITS]
- `ORG_MANAGER = "최수아"` — the manager appointed for the head org unit
  [backend/scripts/seed.py:ORG_MANAGER]
- `_now()`, `_at(minutes_ago)` — UTC clock helpers used to place rows in time
  [backend/scripts/seed.py:_now] [backend/scripts/seed.py:_at]
- `_seed(session)` — creates the whole workspace and returns `(users, channels,
  messages)`, or `None` when the workspace already exists
  [backend/scripts/seed.py:_seed]
- `_seed_projects(session, ...)` — creates the demo board if the workspace has no
  projects; returns the number created [backend/scripts/seed.py:_seed_projects]
- `_seed_milestones(session, workspace)` — creates demo milestones on the first
  project; returns the number created [backend/scripts/seed.py:_seed_milestones]
- `_seed_org(session, ...)` — creates demo org units, members and the manager;
  returns the number created [backend/scripts/seed.py:_seed_org]
- `_ensure_invite(session)` — fetches or creates the single demo invitation
  [backend/scripts/seed.py:_ensure_invite]
- `main()` — the CLI entry point: `create_all`, seed, back-fill, invite, print summary
  [backend/scripts/seed.py:main]

## Invariants

- Repeat-safe: when a workspace with slug `hanbit` already exists, `_seed` returns
  `None` and creates nothing [backend/scripts/seed.py:_seed]
- Workspace identity is fixed — the lookup key must stay slug `hanbit` and name `한빛`
  [backend/scripts/seed.py:WORKSPACE_SLUG]
- Every seeded user gets `hash_password(DEMO_PASSWORD)`; the printed login is
  `PEOPLE[0][1]` / `DEMO_PASSWORD` [backend/scripts/seed.py:DEMO_PASSWORD]
- The first entry of `PEOPLE` is the workspace owner (`ROLE_OWNER`); all others are
  `ROLE_MEMBER` [backend/scripts/seed.py:_seed]
- The invite owner is resolved from the `WorkspaceMembership` row whose role is
  `ROLE_OWNER`, not from the `PEOPLE` order [backend/scripts/seed.py:_ensure_invite]
- The demo invitation is created once and reused on later runs; it is always for
  `INVITED_EMAIL` with `ROLE_MEMBER` [backend/scripts/seed.py:_ensure_invite]
- `_ensure_invite` raises `RuntimeError` when the demo workspace is absent
  [backend/scripts/seed.py:_ensure_invite]
- IDs are minted with `app.core.ids.new_id` using the model-specific prefixes
  (`USER_PREFIX`, `WORKSPACE_PREFIX`, `MEMBER_PREFIX`, `CHANNEL_PREFIX`,
  `CHANNEL_MEMBER_PREFIX`, `MESSAGE_PREFIX`, `REACTION_PREFIX`, `EVENT_PREFIX`,
  `ATTENDEE_PREFIX`, `PROJECT_PREFIX`, `PROJECT_MEMBER_PREFIX`, `TASK_PREFIX`,
  `MILESTONE_PREFIX`, `ORG_UNIT_PREFIX`, `ORG_MEMBER_PREFIX`, `ORG_MANAGER_PREFIX`)
  [backend/scripts/seed.py:_seed]
- Message ordering is positional per channel: `REACTIONS` and `PINS` reference
  top-level message indexes, so reordering `MESSAGES` moves them silently
  [backend/scripts/seed.py:_seed]
- Thread statistics come from persisted replies, not from the fixture:
  `reply_count` and `last_reply_at` are derived from the stored reply rows
  [backend/scripts/seed.py:_seed]
- Channels with `members=None` get every person in `PEOPLE`; private channels get
  only their explicit roster [backend/scripts/seed.py:_seed]
- All seeded users start with presence `offline` [backend/scripts/seed.py:_seed]
- Direct-message channels are keyed by `dm_key(workspace.id, first_user_id,
  second_user_id)`, are `KIND_DM`, private, and have exactly the two participants as
  `ChannelMember` rows [backend/scripts/seed.py:_seed]
- Board positions are per `(project_id, status)` and increment in `TASKS` order
  within each column, starting at 0 [backend/scripts/seed.py:_seed_projects]
- Milestones attach to the first project (ordered by `Project.created_at`,
  `Project.id`) and link to tasks by exact title; an unmatched title is skipped
  [backend/scripts/seed.py:_seed_milestones]
- Org units are created in list order and a unit's parent must already exist earlier
  in `ORG_UNITS`; every unit gets position 0 [backend/scripts/seed.py:_seed_org]
- The head org unit (`ORG_UNITS[0][0]`) gets one manager record for `ORG_MANAGER`,
  appointed by the workspace owner [backend/scripts/seed.py:_seed_org]
- Event starts are `now + day_offset` with time-of-day replaced; a slot that already
  passed is pushed one hour ahead so the demo calendar always opens on a future event
  [backend/scripts/seed.py:_seed]
- All-day events end one day after the start; timed events end after the given number
  of minutes [backend/scripts/seed.py:_seed]
- Attendee responses cycle `RESPONSE_ACCEPTED` / `RESPONSE_TENTATIVE` /
  `RESPONSE_DECLINED` by `(event index + guest index) % 3`, with the first guest always
  `RESPONSE_ACCEPTED` [backend/scripts/seed.py:_seed]
- Projects, milestones and org units are never re-seeded over existing ones
  [backend/scripts/seed.py:_seed_projects]

## Side Effects

- Creates all database tables via `create_all()` [backend/scripts/seed.py:main]
- Inserts `User`, `Workspace`, `WorkspaceMembership`, `Channel`, `ChannelMember`,
  `Message`, `Reaction`, `ScheduleEvent`, `ScheduleAttendee`, `Project`,
  `ProjectMember`, `Task`, `Milestone`, `OrgUnit`, `OrgUnitMember` and
  `OrgUnitManager` rows [backend/scripts/seed.py:_seed]
- Updates `Message` rows in place to set `reply_count`, `last_reply_at` and
  `pinned=True` [backend/scripts/seed.py:_seed]
- Sets `Task.milestone_id` when a task title matches a milestone's card list
  [backend/scripts/seed.py:_seed_projects]
- Commits the session at the end of the seed, after the board back-fill in `main`,
  and after creating the invite [backend/scripts/seed.py:_seed]
- Creates the `Invite` row through `app.services.invites.create_invite`
  [backend/scripts/seed.py:_ensure_invite]
- Issues many intermediate `session.flush()` calls so generated IDs are available
  before the commit [backend/scripts/seed.py:_seed]
- Prints to stdout: the "workspace already exists" notice, the projects/milestones/org
  back-fill counts, the "workspace created" notice with user/channel/message counts,
  the demo login line, the invite email and the invite token
  [backend/scripts/seed.py:main]
- Mutates `sys.path` by inserting `BACKEND_ROOT` at position 0
  [backend/scripts/seed.py:BACKEND_ROOT]
- Runs the async entry point with `asyncio.run(main())` when executed as a script
  [backend/scripts/seed.py:__main__]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
- Seed the demo workspace: `cd backend && .venv/bin/python scripts/seed.py`
  (or `make seed` from the repository root)
