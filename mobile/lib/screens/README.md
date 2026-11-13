# Screens

## Overview

The screen layer. This directory holds the two top-level screens of the app
(`AuthScreen` and `MainShell`) and groups the seven feature areas into
subdirectories. The people area owns workspace membership, role management,
server-backed user search, and invitation management.

`MainShell` owns the responsive shell: on a compact (phone) form factor it
shows a four-tab bottom-navigation layout with an `IndexedStack`; on a
non-compact (tablet) form factor it shows a 72dp icon rail plus a 280dp
channel list beside the content pane. The layout choice is made by
`FormFactor(context).isPad` (`mobile/lib/responsive/screen_type.dart`).

## Interface

### Local symbols

- `class AuthScreen` — public `StatefulWidget` with const constructor `AuthScreen({super.key})`; the login / sign-up form (`mobile/lib/screens/auth_screen.dart`). The form carries an optional invite-code field, the same place the desktop sign-in screen takes it (`desktop/src/components/Gate.tsx`).
- `class LlackAppBar` — public `StatelessWidget implements PreferredSizeWidget` with const constructor `LlackAppBar({super.key, required String tabTitle, Widget? titleWidget, List<Widget> actions = const [], PreferredSizeWidget? bottom, bool showCommonActions = true})` and public fields `tabTitle`, `titleWidget`, `actions`, `bottom`, `showCommonActions`; `preferredSize` returns `Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0))` (`mobile/lib/screens/main_shell.dart`).
- `class SectionErrorBanner` — public `StatelessWidget` with const constructor `SectionErrorBanner({super.key, required String message, required VoidCallback onRetry})` and public fields `message`, `onRetry`.
- `void showWorkspaceSwitcher(BuildContext context)` — top-level function that opens the workspace-switching modal bottom sheet.
- `class MainShell` — public `StatefulWidget` with const constructor `MainShell({super.key})` (`mobile/lib/screens/main_shell.dart`).

### Subdirectories

- [Chat](./chat/README.md) — `ChatTab`, `ChatScreen`, `ThreadScreen` and the chat dialogs.
- [Org](./org/README.md) — `OrgScreen`, the organization chart.
- People (`./people/`) — `PeopleScreen`, `PersonPicker`, `showPersonPicker`, `InviteScreen`, and `buildInviteCode`.
- [Projects](./projects/README.md) — `ProjectsScreen`, project settings, milestone/timeline panels, `MyTasksScreen`, `TaskDetailSheet`, and `TaskDialog`.
- [Schedule](./schedule/README.md) — `ScheduleScreen`, `EventDialog`, the event detail sheet.
- [Search](./search/README.md) — `SearchDialog`.
- [Settings](./settings/README.md) — `SettingsSheet`, `ServerSettingsDialog`.

### People directory

- `class PeopleScreen` — public `StatefulWidget` with const constructor `PeopleScreen({super.key})` (`mobile/lib/screens/people/people_screen.dart`).
- `class PersonPicker` — public `StatefulWidget` with public fields `String title`, `Set<String> excludedUserIds`, `bool searchAllUsers`, and `ValueChanged<User>? onSelected`; constructor `const PersonPicker({super.key, String title = '사람 선택', Set<String> excludedUserIds = const {}, bool searchAllUsers = false, ValueChanged<User>? onSelected})` (`mobile/lib/screens/people/person_picker.dart`).
- `Future<User?> showPersonPicker(BuildContext context, {String title = '사람 선택', Set<String> excludedUserIds = const {}, bool searchAllUsers = false})` — top-level helper that opens `PersonPicker` and returns the selected user (`mobile/lib/screens/people/person_picker.dart`).
- `class InviteScreen` — public `StatefulWidget` with const constructor `InviteScreen({super.key})` (`mobile/lib/screens/people/invite_screen.dart`).
- `String buildInviteCode(String token)` — top-level helper that returns the trimmed invitation token (`mobile/lib/screens/people/invite_screen.dart`).

## Invariants

- `[mobile/lib/screens/auth_screen.dart:_submit]` The submit handler returns early unless `_formKey.currentState!.validate()` succeeds, so no login/signup request is issued while the form is invalid. Only the email is trimmed before sending; the password is passed as `_passCtrl.text` without trimming. The email, name and workspace name are trimmed before being sent to `state.signup`/`state.login`. A stale auth error is cleared with `state.clearAuthError()` before the request.
- `[mobile/lib/screens/auth_screen.dart:_submit]` After a successful login or sign-up, a non-empty invite code (the `_inviteCtrl` field) is handed to `state.acceptInvite(code)`, which switches the session to the invited workspace; a rejected code is reported with `showAppSnackBar(context, '초대 코드를 사용할 수 없습니다: $e')` and the session stays as it was.
- `[mobile/lib/screens/auth_screen.dart:build]` Email validation requires the field to be non-null and to contain `'@'` (`'올바른 이메일을 입력하세요'`). Password validation requires a non-null value of length at least 6 (`'6자 이상 입력하세요'`). In sign-up mode the workspace name and the personal name are both required. The submit button and the sign-up/sign-in mode toggle are both disabled (`onPressed: null`) while `state.isAuthenticating` is true.
- `[mobile/lib/screens/auth_screen.dart:_prefillEmailIfSessionExpired]` The email is auto-filled only once (`_emailPrefilled` guard) and only when `state.isSessionExpired` is true and `state.currentUser?.email` is non-null and non-empty; the password is never auto-filled.
- `[mobile/lib/screens/auth_screen.dart:_looksLikeConnectionError]` A message is treated as a connection/server-address problem only when it is non-null and non-empty and contains one of `'연결'`, `'네트워크'`, `'서버'`, `'timeout'`, `'host'`, `'소켓'`, `'refused'` (case-insensitive).
- `[mobile/lib/screens/auth_screen.dart:build]` The visible error text is rendered directly from `state.authError` rather than from any local copy, and the session-expired notice is only rendered when `state.isSessionExpired` is true, using a neutral accent color rather than the red error color. The form content is constrained to a maximum width of 420 via a `ConstrainedBox` inside a `SingleChildScrollView`.
- `[mobile/lib/screens/auth_screen.dart:_submit]` The catch block returns early when `!mounted` before showing the failure snack bar.
- `[mobile/lib/screens/auth_screen.dart:_showServerSettings]` The save handler checks `mounted` both before and after awaiting `state.changeApiBaseUrl(url)` before showing the confirmation snack bar.
- `[mobile/lib/screens/main_shell.dart:_MainShellState.build]` The layout is chosen by `FormFactor(context).isPad`: the tablet/pad split layout is used when `isPad` is true, otherwise the phone bottom-nav layout.
- `[mobile/lib/screens/main_shell.dart:_buildPhoneLayout]` The phone layout renders the four tabs in an `IndexedStack` whose index comes from `state.tabIndex`, keeping each tab's state alive across switches, and the bottom navigation bar has exactly four items labeled `'메시지'`, `'일정'`, `'프로젝트'`, `'조직도'`.
- `[mobile/lib/screens/main_shell.dart:_buildTabletLayout]` In the tablet layout index 0 renders a fixed 280dp-wide `ChatTab()` beside a `ChatScreen(showBackButton: false)`, while indices 1-3 render `ScheduleScreen(showCommonActions: false)`, `ProjectsScreen(showCommonActions: false)` or `OrgScreen(showCommonActions: false)` via a switch on the tab index. The tablet left rail is a fixed 72dp-wide `Container` separated from the content by a 1px `VerticalDivider`.
- `[mobile/lib/screens/main_shell.dart:_buildRailIcon]` A rail icon is rendered as the active icon in the accent color when `state.tabIndex.value == index`, otherwise as the inactive icon in the muted color.
- `[mobile/lib/screens/main_shell.dart:LlackAppBar]` The common search and profile actions are only rendered when `showCommonActions` is true, so the tablet rail can avoid duplicating them. The workspace chip is placed before the title inside a `Row` and is deliberately given no flex so the title's `Expanded` consumes the remaining width; the title text is limited to one line with ellipsis overflow.
- `[mobile/lib/screens/main_shell.dart:_ChatTabHost]` The chat tab has no app bar of its own, so the shell supplies exactly one `LlackAppBar(tabTitle: '메시지')` for it, matching the file-level rule that each screen has exactly one app bar.
- `[mobile/lib/screens/main_shell.dart:_WorkspaceChip]` The chip label is truncated to a maximum width of 132 and the name text is limited to one line with ellipsis overflow. When a workspace name is empty the avatar tile falls back to the letter `'W'`, otherwise it uses the first character of the name.
- `[mobile/lib/screens/main_shell.dart:showWorkspaceSwitcher]` A workspace entry is marked as selected only when `ws.id == active?.id`, which drives the accent-colored avatar tile, the bold title and the trailing check icon.
- `[mobile/lib/screens/main_shell.dart:SectionErrorBanner]` The error banner always renders the message plus a `'다시 시도'` button wired to the supplied `onRetry` callback.
- `[mobile/lib/screens/org/org_screen.dart:_OrgScreenState._openPeopleScreen]` The organization tab's "구성원" entry pushes `PeopleScreen` as a route; membership and role controls are therefore separate from the org-chart tree.
- `[mobile/lib/screens/people/people_screen.dart:_PeopleScreenState._myRole]` The effective workspace role comes from the current user's `Member.role`, with `orgOverview.myRole` as a fallback. Only owners and administrators receive role-change and removal controls.
- `[mobile/lib/screens/people/people_screen.dart:_PeopleScreenState._changeRole]` An owner's role cannot be changed. For other members, the role update must succeed before the screen refreshes the workspace and org overview.
- `[mobile/lib/screens/people/people_screen.dart:_PeopleScreenState._removeMember]` Removing a workspace member requires the confirmation dialog to return exactly `true`; the request is sent only after that confirmation.
- `[mobile/lib/screens/people/person_picker.dart:_PersonPickerState._onQueryChanged]` Server-wide search is enabled only when `searchAllUsers` is true and the trimmed query has at least two characters. A 250 ms debounce and a generation counter prevent an older response from replacing a newer result.
- `[mobile/lib/screens/people/invite_screen.dart:buildInviteCode]` The invitation code comes from `Invite.token` and is only trimmed. The screen deliberately does not append the server address; the recipient enters the code in the login screen's "초대 코드" field.
- `[mobile/lib/screens/people/invite_screen.dart:_InviteScreenState._createInvite]` A blank trimmed email blocks invitation creation. The default provider role is `'member'`, and the email field is cleared only after the server returns an invitation.
- `[mobile/lib/screens/people/invite_screen.dart:_InviteScreenState._revokeInvite]` Only one invitation is revoked at a time. The invitation is removed from the provider list only after the server request succeeds.

## Side Effects

- `[mobile/lib/screens/auth_screen.dart:_submit]` Calls `state.clearAuthError()`, then `state.login(_emailCtrl.text.trim(), _passCtrl.text)` — `POST /auth/login` — or `state.signup(email:, password:, name:, workspaceName:)` — `POST /auth/signup`, which persists the session under the SharedPreferences keys `llack.access` and `llack.refresh`. On an unexpected exception it calls `showAppSnackBar(context, '로그인에 실패했습니다: $e')`.
- `[mobile/lib/screens/auth_screen.dart:_showServerSettings]` Opens an `AlertDialog` via `showDialog` whose content is a `TextField` pre-filled with `state.api.baseUrl`; the `'저장'` button pops the dialog then awaits `state.changeApiBaseUrl(url)`, which writes the SharedPreferences key `llack.api_base` and reloads the workspace. After saving it shows `showAppSnackBar(context, '서버 주소가 변경되었습니다: $url')`.
- `[mobile/lib/screens/auth_screen.dart:build]` Reads the AppState via `context.watch<AppState>()` to render `authError`, `isAuthenticating`, `isSessionExpired` and `state.api.baseUrl`, and via `context.read<AppState>()` to mutate state.
- `[mobile/lib/screens/auth_screen.dart:dispose]` Disposes the five `TextEditingController`s `_emailCtrl`, `_passCtrl`, `_nameCtrl`, `_wsNameCtrl` and `_inviteCtrl`.
- `[mobile/lib/screens/auth_screen.dart:_submit]` Calls `state.acceptInvite(_inviteCtrl.text.trim())` when the invite-code field is not empty after the session was established; the invite code is never sent with the credentials themselves.
- `[mobile/lib/screens/auth_screen.dart:didChangeDependencies]` On every dependency change calls `_prefillEmailIfSessionExpired()`, which writes `state.currentUser?.email` into `_emailCtrl.text` when the session has expired.
- `[mobile/lib/screens/main_shell.dart:LlackAppBar]` The search icon button opens `showDialog(builder: (_) => const SearchDialog())` and the avatar opens `showModalBottomSheet(isScrollControlled: true, backgroundColor: Colors.transparent, builder: (_) => const SettingsSheet())`. The same pair is repeated on the tablet rail.
- `[mobile/lib/screens/main_shell.dart:showWorkspaceSwitcher]` Opens `showModalBottomSheet` listing `state.workspaces`; selecting an entry calls `Navigator.pop(ctx)` and then `state.selectWorkspace(ws)`, which clears the old workspace's channels/messages/history and reloads the new one.
- `[mobile/lib/screens/main_shell.dart:_buildPhoneLayout]` The bottom navigation bar's `onTap` calls `state.goToTab(index)`, which writes the shared `ValueNotifier<int> tabIndex` observed by the `ValueListenableBuilder<int>` that drives the `IndexedStack` index. The tablet layout observes the same notifier to pick the rail selection and content pane, and each rail icon's `onPressed` calls `state.goToTab(index)`.
- `[mobile/lib/screens/main_shell.dart:LlackAppBar]` Reads AppState via `context.watch<AppState>()` for `currentUser`, `getPresence(user.id)` and `activeWorkspace?.name`, and via `context.read<AppState>()` inside `showWorkspaceSwitcher`.
- `[mobile/lib/screens/people/people_screen.dart:PeopleScreen]` The people screen watches `AppState.members`, opens `InviteScreen` for invitations, and calls `updateMemberRole` / `removeMember` for membership changes.
- `[mobile/lib/screens/people/person_picker.dart:showPersonPicker]` Opens a `PersonPicker` dialog; when `searchAllUsers` is enabled, a query of at least two characters is debounced and sent through `AppState.searchUsers`.
- `[mobile/lib/screens/people/invite_screen.dart:InviteScreen]` Loads, creates, and revokes invitations through `AppState.loadInvites`, `createInvite`, and `revokeInvite`, and copies invitation codes through the platform clipboard.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
