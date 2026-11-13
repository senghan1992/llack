# HTTP API Layer

## Overview

The transport layer. Two pieces:

- `deps.py` — the shared FastAPI dependencies. Every route that needs a user, a
  database session, a workspace membership or a channel with access resolves
  them here, so the permission rules are stated once instead of in every
  handler.
- `v1/` — the routes themselves, one module per domain.

## Interface

- `WorkspaceId`, `ChannelId`, `MessageId` — `Annotated[str, Path(...)]` aliases
  describing the path parameters [backend/app/api/deps.py:WorkspaceId]
- `CurrentUser` — `Annotated[User, Depends(current_user)]`
  [backend/app/api/deps.py:CurrentUser]
- `DbSession` — `Annotated[AsyncSession, Depends(get_session)]`
  [backend/app/api/deps.py:DbSession]
- `WorkspaceMember` — `Annotated[WorkspaceMembership, Depends(workspace_membership)]`
  [backend/app/api/deps.py:WorkspaceMember]
- `ChannelAccess` — `Annotated[tuple[Channel, WorkspaceMembership], Depends(channel_with_access)]`
  [backend/app/api/deps.py:ChannelAccess]
- `workspace_membership(workspace_id, user, session) -> WorkspaceMembership` —
  the caller's membership of the workspace, or 404/403
  [backend/app/api/deps.py:workspace_membership]
- `channel_with_access(channel_id, user, session) -> tuple[Channel, WorkspaceMembership]`
  — the channel plus the caller's membership, enforcing visibility rules
  [backend/app/api/deps.py:channel_with_access]
- Subdirectory contracts:
  - [v1](./v1/README.md) — every route of the API contract, mounted under
    `/api/v1`

## Invariants

- `workspace_membership` resolves the workspace first
  (`get_workspace_or_404`), so an unknown workspace is a 404 rather than a 403
  [backend/app/api/deps.py:workspace_membership]
- `workspace_membership` then requires a membership row
  (`require_membership`), so a non-member is a 403
  [backend/app/api/deps.py:workspace_membership]
- `channel_with_access` resolves the channel first (`get_channel_or_404`) and
  then requires channel access (`require_channel_access`)
  [backend/app/api/deps.py:channel_with_access]
- `CurrentUser` depends on `app.core.security.current_user`, so an
  unauthenticated request never reaches a handler
  [backend/app/api/deps.py:CurrentUser]
- `DbSession` depends on `app.core.db.get_session`, giving one request-scoped
  session per request [backend/app/api/deps.py:DbSession]

## Side Effects

- `workspace_membership` reads the workspace and the membership rows from the
  database [backend/app/api/deps.py:workspace_membership]
- `channel_with_access` reads the channel row and the membership rows from the
  database [backend/app/api/deps.py:channel_with_access]
- The `DbSession` dependency opens an `AsyncSession` and closes it when the
  request ends [backend/app/api/deps.py:DbSession]

## Verification

- Run: `cd backend && .venv/bin/pytest -q`
