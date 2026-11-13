# Org Screens

## Overview

The organization-chart tab. It renders the `OrgUnit` tree returned by the
backend's `/workspaces/{id}/org` endpoint, lets the user open a 1:1 DM with any
member, and provides dialogs for creating and editing organization units.

The screen is also the management entry point for organization units,
organization-unit members and managers, workspace members, and workspace
administrators. Organization edits are available to workspace owners and
administrators. The separate "구성원" route owns workspace-member role changes,
removal, and email invitations.

The screen keeps its state across tab switches with
`AutomaticKeepAliveClientMixin`, so the chart is not re-fetched when the user
tabs away and back.

## Interface

- `class OrgScreen` — public `StatefulWidget` with the public field `final bool showCommonActions` and the constructor `const OrgScreen({super.key, this.showCommonActions = true})`; it creates the private state class `_OrgScreenState` (which mixes in `AutomaticKeepAliveClientMixin` and returns `true` from `wantKeepAlive`) (`mobile/lib/screens/org/org_screen.dart`).

## Invariants

- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState.initState]` The org chart is fetched in a post-frame callback only when `!state.hasLoadedOrg`, with an in-code comment stating that the empty-list state is not used to decide (duplicate-request prevention).
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._currentRole]` The current role is resolved from the matching member in `AppState.members` first, then from `orgOverview.myRole`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._canManageOrg]` Organization-unit controls are shown only when the effective role is `Role.owner` or `Role.admin`; a member receives read-only organization controls.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._openPeopleScreen]` The "구성원" entry pushes `PeopleScreen` as a separate route. It is the workspace-membership and invitation entry point, not an organization-unit editor.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._showNewUnitDialog]` A unit created below an existing unit passes that unit's `parentId`; a root unit passes `null`. The dialog title and parent label distinguish the two cases.
- `[mobile/lib/screens/org/org_screen.dart:_EditOrgUnitDialogState._descendantIds]` The edit dialog excludes the unit itself and all transitive descendants from the selectable parent list, preventing a parent cycle.
- `[mobile/lib/screens/org/org_screen.dart:_EditOrgUnitDialogState._save]` A blank trimmed name blocks saving. For an existing root unit the dialog sends `parentId: null`; a chosen non-root parent sends its id. A failed `updateOrgUnit` keeps the dialog open and preserves the entered values.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._deleteUnit]` Unit deletion runs only after the confirmation dialog returns exactly `true`; `deleteOrgUnit` returning `false` leaves the chart in place and reports failure.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._addUnitMember]` Unit-member candidates exclude current members and are chosen with `showPersonPicker(searchAllUsers: true)`. A successful `addOrgUnitMember` reloads the org overview; a `false` result reports failure.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._removeUnitMember]` Removing a unit member requires explicit confirmation, then calls `removeOrgUnitMember`; the chart is reloaded only after a successful request.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._addUnitManager]` Unit-manager candidates exclude current managers and use the same server-backed person picker. Manager assignment and removal use the dedicated `addOrgUnitManager` and `removeOrgUnitManager` APIs; either operation returns `false` on request failure.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._removeUnitManager]` Removing a unit manager does not open a second confirmation dialog; it calls the dedicated manager-removal API directly and reports whether the request succeeded.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._appointWorkspaceAdmin]` The workspace-administrator section is visible only when `overview.myRole == Role.owner`. Appointment excludes users who are already owners or administrators, then changes the selected workspace member's role to `Role.admin` through `updateMemberRole`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._demoteWorkspaceAdmin]` There is no dedicated workspace-administrator removal API, so dismissal changes the administrator's role back to `Role.member` through the same role-update API.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._changeWorkspaceRole]` A successful workspace role change refreshes the workspace bootstrap and org overview so other summaries cannot retain the old role.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._startDmWithUser]` The method returns early when `user.id == state.currentUser?.id`, so a 1:1 DM with oneself is never opened. `Navigator.of(context, rootNavigator: true)` is captured before the `await` because the context disappears once the dialog closes. The catch block checks `context.mounted` before showing the error snack bar.
- `[mobile/lib/screens/org/org_screen.dart:_NewOrgUnitDialogState._create]` Submission is skipped when the trimmed name is empty or `_isSubmitting` is true, and the `kind` field falls back to `'부서'` when the trimmed kind text is empty. Both the cancel and create buttons are disabled (`onPressed: null`) while `_isSubmitting` is true, preventing duplicate creation on rapid taps. `mounted` is checked before `Navigator.pop` and before the `setState` that clears `_isSubmitting` after a failure; failures are reported with `showAppSnackBar` and the dialog stays open.
- `[mobile/lib/screens/org/org_screen.dart:_NewOrgUnitDialogState.dispose]` The three `TextEditingController`s are disposed in `dispose` because the dialog widget owns them directly.

## Side Effects

- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState.initState]` Calls `state.loadOrg()` from a post-frame callback, which issues `GET /workspaces/$workspaceId/org` through `api.getOrgOverview`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState.build]` The `RefreshIndicator.onRefresh` calls `state.loadOrg()`, re-issuing `GET /workspaces/$workspaceId/org`. On load failure a `SectionErrorBanner` is shown whose `onRetry` calls `state.retryOrg()`, which re-runs `loadOrg()`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._openPeopleScreen]` Pushes `PeopleScreen` with `MaterialPageRoute<void>`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._showNewUnitDialog]` Opens a modal dialog with `showDialog<void>(context: context, builder: (_) => _NewOrgUnitDialog(parentId: parentId, parentName: parentName))`.
- `[mobile/lib/screens/org/org_screen.dart:_NewOrgUnitDialogState._create]` Calls `state.createOrgUnit(name:, parentId:, kind:, description:)`, which POSTs to `/workspaces/$workspaceId/org/units` and then reloads the org chart, and on success pops the dialog with `Navigator.pop(context)`.
- `[mobile/lib/screens/org/org_screen.dart:_EditOrgUnitDialogState._save]` Calls `state.updateOrgUnit(unitId:, name:, parentId:, kind:, description:)` (`PATCH /org/units/$unitId`).
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._deleteUnit]` Calls `state.deleteOrgUnit(unit.id)` (`DELETE /org/units/$unitId`) after confirmation.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._addUnitMember]` Calls `state.addOrgUnitMember(unit.id, user.id)` (`POST /org/units/$unitId/members`).
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._removeUnitMember]` Calls `state.removeOrgUnitMember(unit.id, user.id)` (`DELETE /org/units/$unitId/members/$userId`) after confirmation.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._addUnitManager]` Calls `state.addOrgUnitManager(unit.id, user.id)` (`POST /org/units/$unitId/managers`).
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._removeUnitManager]` Calls `state.removeOrgUnitManager(unit.id, user.id)` (`DELETE /org/units/$unitId/managers/$userId`).
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._changeWorkspaceRole]` Calls `state.updateMemberRole(member, role)` (`PATCH /workspaces/$workspaceId/members/$userId`), then `refreshWorkspace()` and `loadOrg()` after a successful change.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._startDmWithUser]` Calls `ChatNavigator.openDm(...)`, which POSTs `/workspaces/$workspaceId/dms` and, when the form factor is compact, pushes `MaterialPageRoute(builder: (_) => const ChatScreen(showBackButton: true))`. On DM failure it calls `showAppSnackBar(context, ChatNavigator.describeDmError(error))`.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState.build]` Reads provider state via `context.watch<AppState>()` (orgOverview, isLoadingOrg, members, orgError, activeWorkspace, currentUser) and `context.read<AppState>()` in the init callback and in the management actions.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
