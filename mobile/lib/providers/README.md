# Providers

## Overview

The single global state container for the app. `AppState` is a `ChangeNotifier`
composed from four `part` files, each owning one area of the product:

```
_AppStateCore      fields / getters / auth / common helpers
  └ _AppStateRealtime   WebSocket event handling
      └ _AppStateMessages   messages, channels, DMs
          └ _AppStateWorkspace  schedule, projects, org, search
              └ AppState
```

Because the areas are `part` files of one library, their private members are
shared across areas without widening the public surface. The only public class
is `AppState`; the four mixins are library-private.

`AppState` is registered with `provider` in `mobile/lib/main.dart` via
`ChangeNotifierProvider.value`, and read with `context.watch<AppState>()` /
`context.read<AppState>()` in the screen layer.

`list_upsert.dart` is a separate one-class library holding `upsertById`, the
single id-based list-merge rule shared by the REST and WebSocket paths.

The provider now also owns channel administration and per-channel drafts, file
upload and attachment-id message sending, workspace people and invitations,
project/milestone administration, and organization-unit membership and manager
management. The public failure contract is explicit: boolean-returning channel,
project, milestone, and organization mutations return `false` on request failure;
methods documented as throwing propagate API exceptions; the workspace member
role methods return `false` only when no workspace is active and propagate
server failures; and a few read-only loaders catch and log their own failures.

## Interface

### `AppState` (`mobile/lib/providers/app_state.dart`)

- `AppState({super.api, super.ws})` — `api` is `ApiService?`, `ws` is `WsService?`; defaults are provided, and the injection point exists so tests can fake server calls.
- `Future<void> boot()` — cold-start only entry point.
- `Future<void> changeApiBaseUrl(String url)`
- `Future<bool> login(String email, String password)`
- `Future<bool> signup({required String email, required String password, required String name, required String workspaceName})`
- `Future<void> selectWorkspace(Workspace workspace)`
- `Future<Workspace> acceptInvite(String token)` — accepts an invitation token and selects the returned workspace; API failures propagate.
- `Future<void> retryChannels()`, `retryMessages()`, `retryEvents()`, `retryProjects()`, `retryOrg()`
- `@override void didChangeAppLifecycleState(AppLifecycleState state)`
- `@override void dispose()`
- `bool get isSessionExpired` — true means the session ended and a new login is required.

### `_AppStateCore` (`mobile/lib/providers/app_state_core.dart`)

`abstract class _AppStateCore extends ChangeNotifier with WidgetsBindingObserver`.

- Injectable finals: `final ApiService api`, `final WsService ws`.
- `final ValueNotifier<int> tabIndex = ValueNotifier<int>(0)` — 0 messages, 1 schedule, 2 projects, 3 org chart.
- `bool Function(String channelId)? isNewestMessageVisible` — callback hook.
- Auth getters: `isBooting`, `isAuthenticated`, `bootError`, `currentUser`, `session`, `isAuthenticating`, `authError`.
- Connection getters: `isConnected`, `connectionError`.
- Workspace/channel getters: `workspaces`, `activeWorkspace`, `channels` (non-DM only), `dms`, `allChannels`, `activeChannel`, `members`, `activeChannelId`.
- People/invitation getters: `List<Invite> get invites`, `List<Task> get myTasks`.
- Message getters: `activeMessages`, `hasMoreActiveMessages`, `hasMoreNewerMessages`, `pendingFocusMessageId`, `focusErrorMessage`, `isLoadingActiveMessages`, `threadRoot`, `threadReplies`, `isLoadingReplies`, `replyToMessage`.
- Typing/presence getters: `currentTypingUsers`, `Presence getPresence(String userId)`.
- Schedule/project/org getters: `events`, `isLoadingEvents`, `hasLoadedEvents`, `hasLoadedProjects`, `hasLoadedOrg`, `selectedDate`, `onlyMyEvents`, `projects`, `activeProject`, `activeProjectTasks`, `activeRoadmaps`, `activeMilestones`, `selectedRoadmapId`, `orgOverview`, `isLoadingOrg`.
- Section error getters: `channelsError`, `messagesError`, `eventsError`, `projectsError`, `orgError`.
- Draft methods: `String? draftFor(String channelId)`, `void setDraft(String channelId, String body)`.
- People/invitation methods:
  - `Future<List<User>> searchUsers(String query)` — an empty trimmed query returns `[]`; server failures propagate.
  - `Future<void> loadInvites()` — returns normally without an active workspace; request failures are caught and logged, and the previous invite list is retained.
  - `Future<Invite> createInvite(String email, {String role = 'member'})` — throws `ApiException` when there is no active workspace; server failures propagate.
  - `Future<void> revokeInvite(String inviteId)` — returns normally without an active workspace; server failures propagate.
  - `Future<bool> updateMemberRole(Member member, Role role)` — returns `false` without an active workspace and `true` after success; server failures propagate.
  - `Future<bool> removeMember(Member member)` — returns `false` without an active workspace and `true` after success; server failures propagate.
  - `Future<void> loadMyTasks()` — returns normally without an active workspace; request failures are caught and logged, and the previous task list is retained.
  - `Future<void> updateAvatarColor(String color)` — delegates to `updateMe`; it is a no-op when there is no current user, and update failures propagate.
- Other methods: `void clearAuthError()`, `Future<void> refreshWorkspace()`, `Future<void> logout()`, `Future<void> updateMe({String? name, String? title, String? avatarColor, Presence? presence})`, `Future<void> updatePresence(Presence newPresence)`, `Future<List<Member>> membersForChannel(String channelId)`, `bool hasLoadedHistory(String channelId)`, `void goToTab(int index)`.

### `_AppStateRealtime` (`mobile/lib/providers/app_state_realtime.dart`)

`abstract class _AppStateRealtime extends _AppStateCore`. Private members only:
`_handleWsEvent(Map<String, dynamic> event)` (the WebSocket dispatcher),
`_resyncAfterReconnect()`, `_handleMessageInActiveChannel(Message msg)`,
`_upsertMessage(String channelId, Message message)`,
`_replaceMessageInAll(Message message)`.

### `_AppStateMessages` (`mobile/lib/providers/app_state_messages.dart`)

`abstract class _AppStateMessages extends _AppStateRealtime`. Public methods
reachable through `AppState`:

- History: `loadMessages(String channelId, {bool more = false})`, `refreshNewestMessages(String channelId)`, `loadMessagesAround(String channelId, String messageId)`, `markChannelRead(String channelId, {String? messageId})`, `clearPendingFocusMessageId()`, `clearFocusErrorMessage()`, `loadNewerMessages(String channelId)`.
- Sending: `Future<bool> sendMessage(String body, {List<String>? attachmentIds})` — returns `false` when there is no active channel or when both body and attachments are empty, and also converts request failures to `false`. An attachment-only message is valid.
- `Future<FileRef> uploadFile(String filePath, {String? fileName})` — throws `ApiException` without an active workspace; upload failures propagate.
- Message mutations: `sendReply(String body)`, `editMessage(String messageId, String newBody)`, `deleteMessage(String messageId, String channelId)`, `undoDeleteMessage(String messageId, String channelId)`, `toggleReaction(Message message, String emoji)`, `togglePin(Message message)`.
- Thread and composer state: `openThread(Message message)`, `closeThread()`, `setReplyTo(Message? message)`, `clearReplyTo()`, `sendTyping(bool on, String channelId)`.
- Channel navigation: `selectChannel(String channelId, {String? focusMessageId})`, `createChannel({required String name, String? topic, bool isPrivate = false, List<String>? memberIds})`, `openDm(String targetUserId)`, `leaveChannel(String channelId)`, `deleteDm(String channelId)`.
- Channel administration:
  - `Future<bool> updateChannel({required String channelId, String? name, String? topic, String? purpose})` — returns `true` after success and `false` on request failure.
  - `Future<Channel> joinChannel(String channelId)` — server failures propagate.
  - `Future<bool> deleteChannel(String channelId)` — returns `true` after success and `false` on request failure.
  - `Future<bool> addChannelMember(String channelId, String userId)` — returns `true` after success and `false` on request failure.

### `_AppStateWorkspace` (`mobile/lib/providers/app_state_workspace.dart`)

`abstract class _AppStateWorkspace extends _AppStateMessages`. Public methods
reachable through `AppState`:

- Schedule: `loadEvents()`, `setSelectedDate(DateTime date)`, `toggleOnlyMyEvents()`, `createEvent({required String title, String? description, String? location, required DateTime startsAt, required DateTime endsAt, bool allDay = false, bool isPrivate = false, String? channelId, List<String>? attendeeIds})`, `rsvpEvent(String eventId, EventResponse response)`, `updateEvent({...})`, `deleteEvent(String eventId)`.
- Project loading: `loadProjects()`, `selectProject(Project project)`, `loadTasks(String projectId)`, `loadRoadmaps(String projectId)`, `loadMilestones(String projectId)`, `filterRoadmap(String? roadmapId)`.
- Project and task mutation:
  - `createProject({required String name, String? description, String? channelId, List<String>? memberIds})` — throws without an active workspace; server failures propagate.
  - `createTask({required String title, String? description, TaskStatus status = TaskStatus.todo, String? assigneeId, DateTime? dueAt, String? roadmapId, String? milestoneId})` — throws without a selected project; server failures propagate.
  - `Future<bool> updateTaskStatus(Task task, TaskStatus newStatus)` — returns `false` on request failure.
  - `Future<bool> updateTask({required String taskId, String? title, String? description, String? assigneeId, DateTime? dueAt, String? roadmapId, String? milestoneId, int? position})` — returns `false` on request failure.
  - `addTaskComment(String taskId, String body)` — server failures propagate.
  - `Future<bool> deleteTaskComment(String taskId, String commentId)` — returns `false` on request failure.
  - `Future<bool> deleteTask(String taskId)` — returns `false` on request failure.
- Project administration:
  - `Future<bool> updateProject({required String projectId, String? name, String? description, String? channelId, List<String>? memberIds, bool? isArchived})` — returns `false` on request failure.
  - `Future<bool> deleteProject(String projectId)` — returns `false` on request failure.
  - `Future<bool> addProjectMember(String projectId, String userId)` — returns `false` on request failure.
  - `Future<bool> removeProjectMember(String projectId, String userId)` — returns `false` on request failure.
- Milestones and roadmaps:
  - `Future<Milestone> createMilestone({required String title, required DateTime startAt, required DateTime endAt, String description = '', String color = '#4f6cff', int progress = 0, List<String>? taskIds})` — throws without a selected project; server failures propagate.
  - `Future<bool> updateMilestone({required String milestoneId, String? title, DateTime? startAt, DateTime? endAt, String? description, String? color, int? progress, List<String>? taskIds})` — returns `false` on request failure.
  - `Future<bool> deleteMilestone(String milestoneId)` — returns `false` on request failure.
  - `Future<bool> deleteRoadmap(String roadmapId)` — returns `false` on request failure.
- Organization: `loadOrg()`, `createOrgUnit({required String name, String? parentId, String kind = '부서', String description = ''})`, and the following boolean mutations, each returning `false` on request failure:
  - `Future<bool> updateOrgUnit({required String unitId, String? name, String? parentId, String? kind, String? description})`.
  - `Future<bool> deleteOrgUnit(String unitId)`.
  - `Future<bool> addOrgUnitMember(String unitId, String userId)`.
  - `Future<bool> removeOrgUnitMember(String unitId, String userId)`.
  - `Future<bool> addOrgUnitManager(String unitId, String userId)`.
  - `Future<bool> removeOrgUnitManager(String unitId, String userId)`.
- Search: `search(String query)`.

### `upsertById` (`mobile/lib/providers/list_upsert.dart`)

- `List<T> upsertById<T>(List<T> list, T item, String Function(T) idOf, {bool prepend = false})` — the shared id-based merge rule.

## Invariants

- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._notify]` `_notify()` returns early when `_disposed` is true, so `notifyListeners()` is never fired after disposal.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.isAuthenticated]` `isAuthenticated` requires both `_currentUser != null` and `api.accessToken != null`.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.currentTypingUsers]` `currentTypingUsers` prunes entries whose timestamp is older than `const Duration(seconds: 5)` and returns `const []` for a null channel or empty map.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._setUnreadCount]` `_setUnreadCount` returns without mutating when the channel is unknown or when the count is already equal.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._resetSectionLoadFlags]` `_resetSectionLoadFlags()` resets `_hasLoadedEvents`, `_hasLoadedProjects` and `_hasLoadedOrg` to false so a new workspace or logout does not inherit the previous workspace's load flags.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.hasLoadedEvents]` `hasLoadedEvents`, `hasLoadedProjects` and `hasLoadedOrg` are independent of list emptiness — they stay true even when the workspace has zero items.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._historyLoaded]` `_historyLoaded` tracks channels whose history was actually fetched, so a channel that only received WebSocket messages is not mistaken for "loaded" and past messages never appear.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._newerCursor]` `_newerCursor` keeps the last server-received newest message id per channel; the cursor must not advance when new messages are appended via WS, otherwise unseen messages after a jump are lost.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._readAckPending]` `_readAckPending` marks channels where a read signal was sent but not yet acknowledged by the server; the server's absolute badge value must not be trusted during that window.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.isNewestMessageVisible]` The hook is set only while the chat window is open and reset to null when the dialog closes; null means the user is not looking at that channel so read-marking must not happen.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore._isAuthenticating]` `_isAuthenticating` is kept separate from `_isBooting` so the login form is not replaced by the splash screen and the entered values and error message survive.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.refreshWorkspace]` `refreshWorkspace` returns early when there is no active workspace and does not switch to the splash screen nor clear the token, so a pull-to-refresh failure cannot escalate to a logout; on failure it sets `_channelsError = '채널 목록을 불러오지 못했습니다. 다시 시도해주세요.'`.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.logout]` `logout` resets `_hasSeenHello = false` with the comment that a new login must again treat the first 'hello' as "no resync", and clears sessions, workspaces, channels, messages, `_historyLoaded`, `_deletedMessages`, all section load flags, thread state and every section error field.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.getPresence]` `getPresence` returns `Presence.offline` for an unknown user id.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.draftFor]` Drafts are keyed by channel id. `draftFor` returns `null` for a missing or empty draft, and `setDraft` removes the map entry when the new body is empty; this is an in-memory cache and does not notify listeners.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.logout]` `logout` does not clear `_drafts`, `_invites`, or `_myTasks`; those collections remain in memory across logout.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.searchUsers]` `searchUsers` trims the query, returns an empty list for a blank query, and lets API exceptions propagate.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.createInvite]` `createInvite` trims the email, prepends the newly created invitation to `_invites`, and throws when no workspace is active; `revokeInvite` removes the invitation only after the API call succeeds.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.updateMemberRole]` `updateMemberRole` and `removeMember` return `false` only when no workspace is active. API exceptions are not converted to `false`; on success the member list is updated and the methods return `true`.
- `[mobile/lib/providers/app_state_core.dart:_AppStateCore.loadInvites]` `loadInvites` and `loadMyTasks` catch request failures, log them, and retain the previous list rather than replacing it with an error value.
- `[mobile/lib/providers/app_state.dart:AppState.boot]` `boot()` sets `_isBooting = true` and `_bootError = null`; `_isBooting` becomes true only in this method and is reset to false in the `finally` block. If session restore fails, `boot` calls `api.clearTokens()` and sets `_currentUser = null`.
- `[mobile/lib/providers/app_state.dart:AppState._bootstrapWorkspaces]` `_bootstrapWorkspaces` selects `_workspaces.first` as the active workspace and only then calls `_loadWorkspaceData` and `_connectWs`; it does nothing when the workspace list is empty.
- `[mobile/lib/providers/app_state.dart:AppState._loadWorkspaceData]` `_loadWorkspaceData` sets `_activeChannelId` to the first channel only when `_channels.isNotEmpty && _activeChannelId == null`, then loads that channel's messages. It always reloads events, projects and org data after the channel bootstrap because the other tabs live in an `IndexedStack` and are not rebuilt when the workspace changes.
- `[mobile/lib/providers/app_state.dart:AppState._connectWs]` `_connectWs` passes `tokenProvider: () => api.accessToken` instead of copying the token, so each connection uses the token current at connect time.
- `[mobile/lib/providers/app_state.dart:AppState]` The `ws.onStatusChanged` callback sets `_isConnected`, `_connectionError` and `_isSessionExpired = ws.isAuthExpired`, distinguishing a transient disconnect from an expired session.
- `[mobile/lib/providers/app_state.dart:AppState.login]` `login` trims the email before calling the API, sets `_isSessionExpired = false` and `_hasSeenHello = false` for the new session. A workspace-bootstrap failure during `login` is caught separately and reported as `_channelsError` so a failed login is not shown as an auth failure. `login` and `signup` return `true`/`false` instead of rethrowing and always reset `_isAuthenticating = false` in `finally`.
- `[mobile/lib/providers/app_state.dart:AppState.selectWorkspace]` `selectWorkspace` returns early when the requested workspace has the same id as the current active workspace; otherwise it clears `_activeChannelId`, `_messages`, `_historyLoaded`, `_hasMore`, `_events`, `_projects`, `_activeProject`, the project task/roadmap/milestone maps, `_orgOverview` and resets the section load flags before reloading.
- `[mobile/lib/providers/app_state.dart:AppState.acceptInvite]` `acceptInvite` sends the trimmed token to the server, selects the returned workspace, and returns that workspace; invitation API failures propagate to the caller.
- `[mobile/lib/providers/app_state.dart:AppState.changeApiBaseUrl]` `changeApiBaseUrl` disconnects the WebSocket and returns without reconnecting when `_currentUser == null || api.accessToken == null`.
- `[mobile/lib/providers/app_state.dart:AppState.didChangeAppLifecycleState]` On `AppLifecycleState.resumed` the socket is reconnected and `refreshWorkspace()`, `loadMessages(cid)` and the section loads run again; on `inactive`, `paused`, `hidden` and `detached` the socket is disconnected, so the app never shows "online" for hours.
- `[mobile/lib/providers/app_state.dart:AppState.dispose]` `dispose` sets `_disposed = true` as its first statement, removes the WidgetsBinding observer, removes the WS listener, nulls `ws.onStatusChanged`, disconnects the socket and disposes `tabIndex`.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` Events without a `type` field are ignored. The `hello` branch clears `_readAckPending` and only calls `_resyncAfterReconnect()` when `_hasSeenHello` was already true — the first `hello` is the initial connection, not a reconnect.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` A `message.created` reply (`parentId != null`) is added to `_threadReplies` only when `_threadRoot?.id == msg.parentId`, and the parent message's `replyCount` is incremented by 1 with `lastReplyAt` set to the reply's `createdAt`. An inline reply is also upserted into the channel message list; a non-inline reply is not.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` A top-level message increments the channel's `unreadCount` only when `_activeChannelId != msg.channelId` and `msg.userId != _currentUser?.id`.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` `message.updated` and `reaction.updated` are handled identically via `_replaceMessageInAll(msg)`. `message.deleted` stores the pre-delete original in `_deletedMessages.putIfAbsent(mid, () => list[idx])` and blanks `body` while setting `deletedAt` to `DateTime.now()`.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` `typing` events are ignored when `uid == _currentUser?.id`; `on=true` stores `users[name] = DateTime.now()` and `on=false` removes the name, so the indicator expires after 5 seconds.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` `channel.created` uses `upsertById(_channels, ch, (c) => c.id, prepend: true)` so a WS-delivered channel and a REST-delivered channel leave exactly one entry. `event.created`/`event.updated` upsert into `_events` by id and `event.deleted` removes from `_events` by id; `task.created`/`task.updated` upsert into `_projectTasks[t.projectId]` by id, and `task.deleted` applies only when `_activeProject != null`.
- `[mobile/lib/providers/app_state_realtime.dart:_handleWsEvent]` The `unread` payload is documented in code as `{"type":"unread","channel_id":"...","count":3}`; while `_readAckPending` contains the channel the server count is ignored unless it is 0, in which case the pending flag is removed and the badge is set to 0.
- `[mobile/lib/providers/app_state_realtime.dart:_handleMessageInActiveChannel]` A message is marked read only when the `isNewestMessageVisible` hook is non-null and returns true for the channel; then it sends `ws.sendRead`, zeroes the badge and adds the channel to `_readAckPending`, otherwise it removes the pending flag and increments the local unread count by 1.
- `[mobile/lib/providers/app_state_messages.dart:loadMessages]` Returns early if a load for that channel is already in flight; pagination uses `before` = the id of the first message of the current list, page size is `limit: 40`. A non-`more` load replaces the list, sets `_hasMoreNewer[channelId] = false` and sets `_newerCursor[channelId]` to the last fetched id; a `more` load prepends the fetched page and does not touch `_hasMoreNewer`/`_newerCursor`. On success the channel id is added to `_historyLoaded` and `_messagesError` is cleared; on failure `_messagesError` is set to `'메시지를 불러오지 못했습니다. 다시 시도해주세요.'`.
- `[mobile/lib/providers/app_state_messages.dart:refreshNewestMessages]` Merges instead of replacing (upsert by id) so already-loaded history and scroll position survive, then re-sorts with `_compareMessages`. The newer cursor is never moved backwards, `_hasMoreNewer[channelId]` is set to false, and the channel is deliberately NOT added to `_historyLoaded`.
- `[mobile/lib/providers/app_state_messages.dart:_loadMessagesAroundWindow]` Waits for an in-flight load of the same channel to finish before opening the window — up to 100 iterations of 30 ms — so the window is not overwritten by the newest list.
- `[mobile/lib/providers/app_state_messages.dart:_compareMessages]` Orders messages by `createdAt` then `id`, the same order the server uses.
- `[mobile/lib/providers/app_state_messages.dart:loadNewerMessages]` The anchor is `_newerCursor[channelId]` (the last message received from the server) and not the last element of the list, so WS-delivered messages at the end are not skipped; with no anchor it returns without requesting.
- `[mobile/lib/providers/app_state_messages.dart:sendMessage]` `sendMessage` returns `false` when there is no active channel, or when the body is blank and no attachment ids were supplied. It clears `_replyToMessage` before the request and restores it on failure; `inline` is set to true when the message is a reply-to. A request failure is logged and converted to `false`.
- `[mobile/lib/providers/app_state_messages.dart:uploadFile]` `uploadFile` requires an active workspace and throws `ApiException('워크스페이스가 없습니다.')` when none exists; successful uploads return the server `FileRef` whose id can be passed to `sendMessage`.
- `[mobile/lib/providers/app_state_messages.dart:sendReply]` Returns false when there is no thread root or the body is blank; the response is discarded if `_threadRoot?.id` changed while awaiting; the reply is upserted by id so the HTTP response and the WS `message.created` event leave one entry; `replyCount` is not incremented locally because the server announces it over WS.
- `[mobile/lib/providers/app_state_messages.dart:deleteMessage]` Stores the original with `_deletedMessages.putIfAbsent(messageId, () => list[idx])` so the first saved original wins even if the WS `message.deleted` event arrives first.
- `[mobile/lib/providers/app_state_messages.dart:sendTyping]` Sends `off` to the previously typing channel when the channel changes, so no stale "typing" indicator is left in another channel.
- `[mobile/lib/providers/app_state_messages.dart:selectChannel]` Re-opening the same channel without a focus id does not reset the list: it merges the newest messages, sends a read signal and zeroes the badge. Switching to a different channel clears `_readAckPending`, resets `_replyToMessage`, `_threadRoot` and `_threadReplies`, and sets `_pendingFocusMessageId`; with a focus id it opens the around-window and returns without loading history, otherwise it loads history when `hasLoadedHistory(channelId)` is false and otherwise merges the newest messages.
- `[mobile/lib/providers/app_state_messages.dart:createChannel]` Throws `Exception('활성 워크스페이스가 없습니다')` when `_activeWorkspace == null`; `openDm` throws the same exception and inserts the DM at index 0 when the channel id is not already in `_channels`.
- `[mobile/lib/providers/app_state_messages.dart:leaveChannel]` `leaveChannel` and `deleteDm` remove the channel from `_channels`, drop its messages from `_messages`, remove it from `_historyLoaded`, and call `_afterActiveChannelRemoved()` when it was the active channel; that helper sets `_activeChannelId = null` when no channels remain, otherwise it selects `_channels.first`.
- `[mobile/lib/providers/app_state_messages.dart:updateChannel]` `updateChannel` upserts the returned channel by id and returns `true`; any request failure is logged and converted to `false`, leaving the current channel list unchanged.
- `[mobile/lib/providers/app_state_messages.dart:joinChannel]` `joinChannel` upserts the joined channel at the front of `_channels` and returns it; API exceptions propagate rather than becoming a `false` result.
- `[mobile/lib/providers/app_state_messages.dart:deleteChannel]` `deleteChannel` removes the channel, its messages, and its history only after the delete request succeeds. A failed request returns `false` and leaves local state intact.
- `[mobile/lib/providers/app_state_messages.dart:addChannelMember]` `addChannelMember` invalidates the cached channel-member list after a successful add so the next read fetches fresh membership; a failed request returns `false`.
- `[mobile/lib/providers/app_state_workspace.dart:loadEvents]` Returns early when `_activeWorkspace == null`; on success it sets `_hasLoadedEvents = true` even for an empty list, and on failure sets `_eventsError` to `'일정을 불러오지 못했습니다. 다시 시도해주세요.'`.
- `[mobile/lib/providers/app_state_workspace.dart:updateEvent]` Updates the list with `upsertById(_events, updated, (e) => e.id)` because the backend sends the same event over WS right after the PATCH.
- `[mobile/lib/providers/app_state_workspace.dart:deleteEvent]` Removes the event from `_events` only after the API call succeeds; on failure the list is left unchanged and false is returned.
- `[mobile/lib/providers/app_state_workspace.dart:loadProjects]` On success sets `_hasLoadedProjects = true` even for an empty list; when no project was selected it selects `_projects.first`; when the previously selected project is gone it clears `_activeProject` and `_selectedRoadmapId` and selects `_projects.first`; otherwise it re-points `_activeProject` at the new list instance and reloads tasks, roadmaps and milestones, because a `DropdownButton` whose value is missing from the items list throws.
- `[mobile/lib/providers/app_state_workspace.dart:selectProject]` Always keeps the selected project as an instance contained in `_projects` (adding it to the list when it is missing), resets `_selectedRoadmapId` to null, and loads tasks, roadmaps and milestones concurrently via `Future.wait`.
- `[mobile/lib/providers/app_state_workspace.dart:createTask]` Throws `Exception('선택된 프로젝트가 없습니다')` when `_activeProject == null` and upserts the task into `_projectTasks[_activeProject!.id]` by id.
- `[mobile/lib/providers/app_state_workspace.dart:updateTaskStatus]` Replaces the task in `_projectTasks[task.projectId]` by index and returns false without changing the list on failure.
- `[mobile/lib/providers/app_state_workspace.dart:addTaskComment]` Merges the comment into the task's comments with `upsertById(t.comments, comment, (c) => c.id)` so a comment already delivered over WS is not duplicated.
- `[mobile/lib/providers/app_state_workspace.dart:updateTask]` `updateTask` accepts `milestoneId` and `position` in addition to the existing task fields, and returns `false` on request failure. Null arguments mean “leave unchanged”.
- `[mobile/lib/providers/app_state_workspace.dart:deleteTaskComment]` `deleteTaskComment` removes the comment from the active project's cached task only after the server delete succeeds, and returns `false` on failure.
- `[mobile/lib/providers/app_state_workspace.dart:updateProject]` `updateProject` upserts the returned project and updates `_activeProject` when it is the selected project; request failures return `false`. `deleteProject` removes the project and its task, roadmap, and milestone caches only after a successful delete.
- `[mobile/lib/providers/app_state_workspace.dart:addProjectMember]` `addProjectMember` and `removeProjectMember` update the project's `members` list through `Project.copyWith`; request failures return `false`.
- `[mobile/lib/providers/app_state_workspace.dart:createMilestone]` `createMilestone` requires a selected project, throws `Exception('선택된 프로젝트가 없습니다')` otherwise, and uses the default color `'#4f6cff'`.
- `[mobile/lib/providers/app_state_workspace.dart:updateMilestone]` `updateMilestone`, `deleteMilestone`, and `deleteRoadmap` mutate the corresponding project caches only after the request succeeds and return `false` on failure. Deleting the selected roadmap also clears `_selectedRoadmapId`.
- `[mobile/lib/providers/app_state_workspace.dart:loadOrg]` Returns early when `_activeWorkspace == null`, sets `_hasLoadedOrg = true` on success even for an empty list, and sets `_orgError` to `'조직도를 불러오지 못했습니다. 다시 시도해주세요.'` on failure.
- `[mobile/lib/providers/app_state_workspace.dart:updateOrgUnit]` `updateOrgUnit`, `deleteOrgUnit`, `addOrgUnitMember`, `removeOrgUnitMember`, `addOrgUnitManager`, and `removeOrgUnitManager` each return `false` on request failure and reload the org overview after a successful mutation.
- `[mobile/lib/providers/app_state_workspace.dart:search]` Returns an empty list when there is no active workspace or the trimmed query is empty, otherwise it searches with the trimmed query.
- `[mobile/lib/providers/list_upsert.dart:upsertById]` `upsertById` replaces the existing element in place when the id matches (preserving list position) and otherwise appends, or prepends when `prepend` is true; it never mutates the input list — it returns a new copy.
- `[mobile/lib/providers/list_upsert.dart:library]` The library doc comment states the backend sends WebSocket events before the HTTP response (`POST /channels` → `emit_channel_created` → then the HTTP response), so the same item can arrive via both the WS and REST paths and only a shared id-based upsert rule keeps exactly one entry regardless of ordering.

## Side Effects

- `AppState` owns the server-backed workspace, chat, project, and organization state. Mutations are normally published through `_notify()` → `notifyListeners()` (`mobile/lib/providers/app_state_core.dart:_notify`); the touched collections include `_messages`, `_threadReplies`, `_channels`, `_channelMembers`, `_events`, `_projects`, `_projectTasks`, `_projectRoadmaps`, `_projectMilestones`, `_members`, `_invites`, `_myTasks`, `_drafts`, `_presence`, `_typing`, and `_deletedMessages`. Local device preferences are owned separately by `DeviceSettings` (`mobile/lib/services/device_settings.dart:DeviceSettings`).
- `mobile/lib/providers/app_state.dart:AppState.boot` — calls `api.init()`, then `api.getMe()` and `api.getWorkspaces()` when a token exists; calls `api.clearTokens()` when restoring a stored session fails.
- `mobile/lib/providers/app_state.dart:AppState` — sets `ws.authRefresher = () async => api.refreshAccessToken()` (a WebSocket close with auth failure triggers exactly one access-token refresh attempt), sets `api.onTokensChanged = () { _connectWs(); }` (a token refresh re-connects the socket), registers `ws.addListener(_handleWsEvent)`, and registers itself with `WidgetsBinding.instance.addObserver(this)`.
- `mobile/lib/providers/app_state.dart:AppState._connectWs` — opens the WebSocket with `ws.connect(baseUrl: api.baseUrl, tokenProvider: () => api.accessToken)`.
- `mobile/lib/providers/app_state.dart:AppState.login` / `signup` — call `api.login(email.trim(), password)` and `api.signup(...)`; neither performs any navigator or `ScaffoldMessenger` interaction, errors are surfaced only through the `authError` / `channelsError` state fields.
- `mobile/lib/providers/app_state.dart:AppState.acceptInvite` — calls `api.acceptInvite(token)` (`POST /invites/accept`) and then `selectWorkspace` with the returned workspace.
- `mobile/lib/providers/app_state.dart:AppState.changeApiBaseUrl` — calls `api.setBaseUrl(url)`, then `refreshWorkspace()`, `loadMessages(cid)`, `loadEvents()`, `loadProjects()` and `loadOrg()`, and disconnects the socket before re-pointing the client at the new server.
- `mobile/lib/providers/app_state.dart:AppState.dispose` — calls `ws.removeListener(_handleWsEvent)`, sets `ws.onStatusChanged = null` and calls `ws.disconnect()`.
- `mobile/lib/providers/app_state.dart:AppState.didChangeAppLifecycleState` — calls `ws.disconnect()` when inactive/paused/hidden/detached and `_connectWs()` when resumed.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.refreshWorkspace` — calls `api.getBootstrap(wsId)` and overwrites `_channels`, `_members` and the `_presence` map entries for every member and for the current user.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.updateMe` — calls `api.updateMe(...)` and updates `_currentUser` plus `_presence[updated.id]` on success.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.membersForChannel` — calls `api.getChannelMembers(channelId)` on a cache miss.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.searchUsers` — calls `api.searchUsers(query.trim())` (`GET /users?q=...`).
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.loadInvites` — calls `api.getInvites(workspaceId)` (`GET /workspaces/$workspaceId/invites`); `createInvite` posts to the same collection, and `revokeInvite` deletes `/workspaces/$workspaceId/invites/$inviteId`.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.updateMemberRole` — calls `api.updateMemberRole(workspaceId, userId, role.name)` (`PATCH /workspaces/$workspaceId/members/$userId`); `removeMember` deletes that member resource.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.loadMyTasks` — calls `api.getMyTasks(workspaceId)` (`GET /workspaces/$workspaceId/tasks`).
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.logout` — calls `api.clearTokens()` to drop persisted credentials and `ws.disconnect()`.
- `mobile/lib/providers/app_state_messages.dart:*` — the message area performs the REST calls `GET /channels/$channelId/messages` (with `limit: 40` and the `before`/`after`/`around` cursors), `POST /channels/$channelId/messages` (including `attachment_ids`), `POST /files?workspace_id=...` for uploads, `PATCH /messages/$messageId`, `DELETE /messages/$messageId`, `POST /messages/$messageId/restore`, `POST|DELETE /messages/$messageId/reactions`, `POST|DELETE /messages/$messageId/pin`, `GET /messages/$messageId/replies?limit=100`, `POST /workspaces/$workspaceId/channels`, `PATCH /channels/$channelId`, `POST /channels/$channelId/join`, `DELETE /channels/$channelId`, `POST /channels/$channelId/members`, `POST /workspaces/$workspaceId/dms`, and `POST /channels/$channelId/leave`; and the WebSocket frames `{'type': 'read', 'channel_id': ..., 'message_id': ...}` and `{'type': 'typing', 'channel_id': ..., 'on': ...}`.
- `mobile/lib/providers/app_state_workspace.dart:*` — the workspace area performs the REST calls for events, projects, tasks, comments, roadmaps, milestones, org and search (`GET|POST /workspaces/$workspaceId/events`, `POST /events/$eventId/rsvp`, `PATCH|DELETE /events/$eventId`, `GET|POST /workspaces/$workspaceId/projects`, `PATCH|DELETE /projects/$projectId`, `POST|DELETE /projects/$projectId/members`, `GET /workspaces/$workspaceId/tasks`, `GET|POST /projects/$projectId/tasks`, `PATCH|DELETE /tasks/$taskId`, `POST /tasks/$taskId/comments`, `DELETE /task-comments/$commentId`, `GET /projects/$projectId/roadmaps`, `DELETE /roadmaps/$roadmapId`, `GET|POST /projects/$projectId/milestones`, `PATCH|DELETE /milestones/$milestoneId`, `GET /workspaces/$workspaceId/org`, `POST /workspaces/$workspaceId/org/units`, `PATCH|DELETE /org/units/$unitId`, `POST|DELETE /org/units/$unitId/members`, `POST|DELETE /org/units/$unitId/managers`, `GET /workspaces/$workspaceId/search?q=..&limit=30`).
- `mobile/lib/providers/app_state_realtime.dart:_resyncAfterReconnect` — fires `unawaited(refreshWorkspace())` and `unawaited(refreshNewestMessages(cid))` for the active channel.
- `mobile/lib/providers/app_state_core.dart:_AppStateCore.tabIndex` — `goToTab` mutates the separate `ValueNotifier<int> tabIndex`, which notifies that notifier's own listeners rather than the AppState listeners; `dispose` calls `tabIndex.dispose()`.
- The providers package performs no `SharedPreferences` access and no `Navigator` / `ScaffoldMessenger` interaction of its own; it emits `debugPrint` diagnostics (`'[Boot] session restore failed: $e'`, `'[Bootstrap error] $e'`, `'[refreshWorkspace error] $e'`, `'[membersForChannel error] $e'`).

## Verification

- Run: `flutter test` (from the `mobile/` directory)
