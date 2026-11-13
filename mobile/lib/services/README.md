# Services

## Overview

The transport boundary between the Flutter client and the Llack backend
(FastAPI + WebSocket), plus the settings that belong to the device rather
than to the account. Three services sit here:

- `ApiService` — REST client. Every call goes through one private `_request`
  helper that adds the `/api/v1` prefix, the bearer token, a 15-second timeout,
  a single automatic token refresh on 401, and a uniform `ApiException`.
- `WsService` — realtime client. One WebSocket to `/api/v1/ws`, with
  exponential backoff, a keepalive ping, and a one-shot token-refresh attempt
  when the server closes the socket with the auth-failure code `4401`.
- `DeviceSettings` — the settings stored on this device (screen mode, clock
  format). Unlike the other two it is a process-wide singleton
  (`DeviceSettings.instance`), not an injected dependency, because the theme
  and the message timestamps have to read it before/without `AppState`.

`ApiService` and `WsService` are injected into `AppState`
(`mobile/lib/providers/app_state.dart`), so tests can substitute fakes for
both.

## Interface

### `ApiException` (`mobile/lib/services/api_service.dart`)

- `class ApiException implements Exception` — final fields `int status`,
  `String code`, `String message`; constructor `ApiException(this.status, this.code, this.message)`;
  `String toString()` returns `message`.

### `ApiService` (`mobile/lib/services/api_service.dart`)

Static constants:

- `static const String keyAccess = 'llack.access'`
- `static const String keyRefresh = 'llack.refresh'`
- `static const String keyApiBase = 'llack.api_base'`
- `static const Duration requestTimeout = Duration(seconds: 15)`
- `static String ApiService.getDefaultBaseUrl()`

Getters and lifecycle:

- `String get baseUrl`, `String? get accessToken`, `String? get refreshToken`
- `String get apiEndpoint` — `'$_baseUrl/api/v1'`
- `Future<void> init()` — loads base URL and tokens from `SharedPreferences`.
- `Future<void> setBaseUrl(String url)` — strips trailing slashes, persists.
- `String absoluteFileUrl(String url)` — makes a relative file path absolute.
- `Future<void> setTokens(String access, String refresh)` — stores both tokens and fires `onTokensChanged`.
- `void Function()? onTokensChanged` — public mutable hook, fired when tokens change so the WS can re-attach.
- `Future<bool> refreshAccessToken()`
- `Future<void> clearTokens()`

Endpoint methods (each returns a decoded model from `mobile/lib/models/models.dart`):

- Auth: `Future<Session> login(String email, String password)`, `Future<Session> signup({required String email, required String password, required String name, required String workspaceName})`, `Future<User> getMe()`, `Future<User> updateMe({String? name, String? title, String? avatarColor, Presence? presence})`.
- Workspaces: `Future<List<Workspace>> getWorkspaces()`, `Future<Bootstrap> getBootstrap(String workspaceId)`.
- Channels: `getChannels`, `getDms`, `createChannel`, `updateChannel`, `joinChannel`, `deleteChannel`, `openDm`, `leaveChannel`, `deleteDm`, `getChannelMembers`, `addChannelMember`, `markRead`.
- Messages: `getMessages` (returns `(List<Message>, bool, bool)` = messages, `hasMore`, `hasMoreAfter`), `sendMessage`, `editMessage`, `deleteMessage`, `restoreMessage`, `getReplies`, `toggleReaction`, `togglePin`, `getPins`.
- Members, invites and search: `getMembers`, `updateMemberRole`, `removeMember`, `searchUsers`, `getInvites`, `createInvite`, `revokeInvite`, `search`.
- Files: `uploadFile`.
- Schedule: `getEvents`, `createEvent`, `rsvpEvent`, `updateEvent`, `deleteEvent`.
- Projects and tasks: `getProjects`, `createProject`, `updateProject`, `deleteProject`, `addProjectMember`, `removeProjectMember`, `getMyTasks`, `getProjectTasks`, `createTask`, `updateTask`, `deleteTask`, `addTaskComment`, `deleteTaskComment`, `getRoadmaps`, `getMilestones`, `createMilestone`, `updateMilestone`, `deleteMilestone`, `deleteRoadmap`.
- Organization: `getOrgOverview`, `createOrgUnit`, `updateOrgUnit`, `deleteOrgUnit`, `addOrgUnitMember`, `removeOrgUnitMember`, `addOrgUnitManager`, `removeOrgUnitManager`.

Signatures of the added methods:

- `Future<Channel> updateChannel(String channelId, {String? name, String? topic, String? purpose})`
- `Future<Channel> joinChannel(String channelId)`
- `Future<void> deleteChannel(String channelId)`
- `Future<List<Member>> getMembers(String workspaceId)`
- `Future<Member> updateMemberRole(String workspaceId, String userId, String role)`
- `Future<void> removeMember(String workspaceId, String userId)`
- `Future<List<User>> searchUsers(String query)`
- `Future<List<Invite>> getInvites(String workspaceId)`
- `Future<Invite> createInvite(String workspaceId, {required String email, String role = 'member'})`
- `Future<void> revokeInvite(String workspaceId, String inviteId)`
- `Future<FileRef> uploadFile({required String workspaceId, required String filePath, String? fileName})`
- `Future<OrgUnit> updateOrgUnit(String unitId, {String? name, String? parentId, String? kind, String? description})`
- `Future<void> deleteOrgUnit(String unitId)`
- `Future<void> addOrgUnitMember(String unitId, String userId)`
- `Future<void> removeOrgUnitMember(String unitId, String userId)`
- `Future<void> addOrgUnitManager(String unitId, String userId)`
- `Future<void> removeOrgUnitManager(String unitId, String userId)`
- `Future<Project> updateProject(String projectId, {String? name, String? description, String? channelId, List<String>? memberIds, bool? isArchived})`
- `Future<void> deleteProject(String projectId)`
- `Future<void> addProjectMember(String projectId, String userId)`
- `Future<void> removeProjectMember(String projectId, String userId)`
- `Future<List<Task>> getMyTasks(String workspaceId)`
- `Future<Milestone> createMilestone(String projectId, {required String title, required DateTime startAt, required DateTime endAt, String description = '', String color = '#4f6cff', int progress = 0, List<String>? taskIds})`
- `Future<Milestone> updateMilestone(String milestoneId, {String? title, DateTime? startAt, DateTime? endAt, String? description, String? color, int? progress, List<String>? taskIds})`
- `Future<void> deleteMilestone(String milestoneId)`
- `Future<void> deleteRoadmap(String roadmapId)`
- `Future<void> deleteTaskComment(String commentId)`
- `Future<Message> sendMessage({required String channelId, required String body, String? parentId, String? replyToId, bool inline = false, List<String>? attachmentIds})`

### `DeviceSettings` (`mobile/lib/services/device_settings.dart`)

Enums:

- `enum ThemeModeSetting { light, dark, system }` — `static ThemeModeSetting fromString(String? value)`, `String get label`.
- `enum ClockFormatSetting { h24, h12 }` — `static ClockFormatSetting fromString(String? value)`, `String get label`, `String format(DateTime time)`.

Class:

- `class DeviceSettings` — private constructor `DeviceSettings._()`; `static final DeviceSettings instance`; `ValueNotifier<ThemeModeSetting> themeMode`; `ValueNotifier<ClockFormatSetting> clockFormat`; `Future<void> load()`; `Future<void> setThemeMode(ThemeModeSetting mode)`; `Future<void> setClockFormat(ClockFormatSetting format)`; `static const String keyThemeMode = 'llack.theme_mode'`; `static const String keyClockFormat = 'llack.clock_format'`.

### `WsService` (`mobile/lib/services/ws_service.dart`)

Typedefs:

- `typedef WsEventHandler = void Function(Map<String, dynamic> event)`
- `typedef WsStatusCallback = void Function(bool connected, String? error)`
- `typedef WsTokenProvider = String? Function()`
- `typedef WsAuthRefresher = Future<bool> Function()`

Seam:

- `abstract class WsConnection` — `Future<void> get ready`, `Stream<dynamic> get stream`, `int? get closeCode`, `void add(String data)`, `void close()`.

`class WsService`:

- Static constants: `authFailedCloseCode` (`4401`), `sessionExpiredMessage`, `healthyConnectionThreshold` (10s), `minReconnectDelay` (5s), `maxReconnectDelay` (30s).
- Getters: `bool get isConnected`, `bool get isAuthExpired`, `String? get lastError`.
- Mutable hooks: `WsStatusCallback? onStatusChanged`, `WsAuthRefresher? authRefresher`, `@visibleForTesting WsConnection Function(Uri uri)? connectionFactory`.
- Methods: `void addListener(WsEventHandler handler)`, `void removeListener(WsEventHandler handler)`, `void connect({required String baseUrl, required WsTokenProvider tokenProvider})`, `void send(Map<String, dynamic> payload)`, `void sendTyping(String channelId, {bool on = true})`, `void sendRead(String channelId, {String? messageId})`, `void disconnect()`.

## Invariants

- `[mobile/lib/services/api_service.dart:ApiService.getDefaultBaseUrl]` Returns `'http://10.0.2.2:8000'` only when `!kIsWeb && Platform.isAndroid`, otherwise returns `'http://127.0.0.1:8000'`.
- `[mobile/lib/services/api_service.dart:ApiService._request]` Every request is wrapped in `.timeout(requestTimeout)` (15 seconds); a `TimeoutException` becomes `ApiException(0, 'timeout', ...)` and any other exception becomes `ApiException(0, 'network', ...)`, so the UI never hangs without a response.
- `[mobile/lib/services/api_service.dart:ApiService._request]` Request headers always contain `'Content-Type': 'application/json'` and `'Accept': 'application/json'`; the `'Authorization': 'Bearer $_accessToken'` header is added only when `_accessToken != null`.
- `[mobile/lib/services/api_service.dart:ApiService._request]` A 401 response triggers a token refresh and a single retry with `retry: false`, so at most one refresh-and-retry happens per request; the refresh path is only taken when `_refreshToken != null`.
- `[mobile/lib/services/api_service.dart:ApiService._request]` Any status `>= 400` throws the `ApiException` built by `_errorFromResponse(res, path, method)`; a 204 status or an empty body returns `null` instead of parsing JSON; otherwise the UTF-8 decoded body is returned via `jsonDecode`.
- `[mobile/lib/services/api_service.dart:ApiService._errorFromResponse]` The error parsing lives in its own helper: `code`/`message` come from the JSON body's `error.code`/`error.message`, otherwise the message comes from the body's `detail` field, falling back to `'error'` and `'요청이 실패했습니다 (<status>)'`. A 401 replaces the message with `_unauthorizedMessage(path, method, message)` and a 409 replaces it with `'이미 존재하는 리소스입니다.'`.
- `[mobile/lib/services/api_service.dart:ApiService._unauthorizedMessage]` For a POST to a path containing `'/auth/login'` or `'/auth/signup'` the message is `'이메일 또는 비밀번호가 맞지 않습니다.'`; otherwise, if the server message contains any of `'expired'`, `'token'`, `'session'`, `'만료'`, `'세션'`, `'토큰'` (case-insensitive) the server message is kept, else the message is `'세션이 만료되었습니다. 다시 로그인해주세요.'`.
- `[mobile/lib/services/api_service.dart:ApiService._refreshAccessToken]` Only a 200 response is treated as success; `access_token` and `refresh_token` are stored via `setTokens`, and any non-200 status or thrown exception falls through to `clearTokens()` and returns false.
- `[mobile/lib/services/api_service.dart:ApiService.init]` The base URL is read from SharedPreferences key `'llack.api_base'` and falls back to `getDefaultBaseUrl()` when absent; tokens are read from `'llack.access'` and `'llack.refresh'`.
- `[mobile/lib/services/api_service.dart:ApiService.setBaseUrl]` Trailing slashes are stripped with `url.replaceAll(RegExp(r'/+$'), '')` before the URL is stored in memory and persisted.
- `[mobile/lib/services/api_service.dart:ApiService.absoluteFileUrl]` An empty string is returned unchanged, a string starting with `'http://'` or `'https://'` is returned unchanged, and a relative path is prefixed with `'/'` and concatenated onto `_baseUrl`.
- `[mobile/lib/services/api_service.dart:ApiService.setTokens]` Both tokens are written to memory and to SharedPreferences, and `onTokensChanged` is invoked afterwards so the WebSocket can be re-attached with the new token.
- `[mobile/lib/services/api_service.dart:ApiService.getMessages]` The returned tuple is `(messages, hasMore, hasMoreAfter)`, where a missing `'messages'` list defaults to empty and `'has_more'`/`'has_more_after'` default to false; the query always starts with `?limit=$limit` and appends `'&before='`, `'&after='`, `'&around='` only for non-null cursors. The documented cursor semantics are that before/after/around cursors are all exclusive (the reference message is included only for `around`).
- `[mobile/lib/services/api_service.dart:ApiService.sendMessage]` `attachment_ids` is only written into the body when the list is non-null **and** non-empty, so a message without attachments keeps the previous payload shape.
- `[mobile/lib/services/api_service.dart:ApiService.updateChannel]` Fields whose value is null are omitted from the request body, which the doc comment states means "unchanged".
- `[mobile/lib/services/api_service.dart:ApiService.updateOrgUnit]` The same omission rule applies; the doc comment adds that passing an empty `parentId` detaches the unit from its parent.
- `[mobile/lib/services/api_service.dart:ApiService.updateProject]` Null fields are omitted from the request body, so only the fields that were actually passed are sent; `is_archived` is sent only when it is non-null.
- `[mobile/lib/services/api_service.dart:ApiService.createInvite]` The role defaults to `'member'` and is always sent next to the email.
- `[mobile/lib/services/api_service.dart:ApiService.createMilestone]` The defaults are an empty description, the color `'#4f6cff'` and progress `0`; `start_at` and `end_at` are sent as UTC ISO-8601 strings.
- `[mobile/lib/services/api_service.dart:ApiService.searchUsers]` The query is URL-encoded into the `q` parameter of `GET /users`; the endpoint is global (not workspace-scoped).
- `[mobile/lib/services/api_service.dart:ApiService.getMyTasks]` The path is `GET /workspaces/{workspaceId}/tasks` — the workspace's task list, filtered by the server to the current user.
- `[mobile/lib/services/api_service.dart:ApiService.deleteTaskComment]` The path is `DELETE /task-comments/{commentId}`; the comment is not addressed through its task.
- `[mobile/lib/services/api_service.dart:ApiService.deleteRoadmap]` The path is `DELETE /roadmaps/{roadmapId}`.
- `[mobile/lib/services/api_service.dart:ApiService.uploadFile]` The upload does not go through `_request`: it builds the URI itself (`/files?workspace_id=…`), adds the bearer header only when a token exists, and sends a `http.MultipartRequest` with the 15-second timeout. A timeout becomes `ApiException(0, 'timeout', '파일 업로드가 시간 내에 끝나지 않았습니다.')` and any other failure becomes `ApiException(0, 'network', ...)`; a `>= 400` response is converted with `_errorFromResponse(res, '/files', 'POST')`.
- `[mobile/lib/services/api_service.dart:ApiService.getEvents]` The `?from=`/`?to=` query is only appended when both `from` and `to` are non-null, and both are converted with `toUtc().toIso8601String()`.
- `[mobile/lib/services/api_service.dart:ApiService.createEvent]` `'description'` and `'location'` are always sent, defaulting to empty strings when null, and `'starts_at'`/`'ends_at'` are sent as UTC ISO-8601 strings.
- `[mobile/lib/services/api_service.dart:ApiService.updateEvent]` Fields whose value is null are omitted from the request body, which the doc comment states means "unchanged".
- `[mobile/lib/services/api_service.dart:ApiService.toggleReaction]` When `currentMe` is true the request is a DELETE with the emoji URL-encoded into the path; otherwise it is a POST with body `{'emoji': emoji}`.
- `[mobile/lib/services/api_service.dart:ApiService.togglePin]` The HTTP method is DELETE when `currentPinned` is true and POST otherwise.
- `[mobile/lib/services/api_service.dart:ApiService.rsvpEvent]` The request body sends the enum's Dart name via `response.name` under the key `'response'`.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.instance]` The instance is a `static final` singleton with a private constructor, so the whole app reads and writes the same settings.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.load]` The stored strings are read from SharedPreferences and mapped with `ThemeModeSetting.fromString` / `ClockFormatSetting.fromString`; a missing or unknown value falls back to `system` / `h24`.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setThemeMode]` The setter returns early when the value is unchanged, so neither the notifier nor SharedPreferences is touched; otherwise the value is published first and then persisted under `'llack.theme_mode'` with the enum's Dart name.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setClockFormat]` The same rule applies to `'llack.clock_format'`.
- `[mobile/lib/services/device_settings.dart:ThemeModeSetting.fromString]` Only `'light'` and `'dark'` map to their own value; every other input (including `null`) becomes `system`.
- `[mobile/lib/services/device_settings.dart:ClockFormatSetting.fromString]` Only `'12h'` maps to `h12`; every other input (including `null`) becomes `h24`.
- `[mobile/lib/services/device_settings.dart:ClockFormatSetting.format]` The timestamp is converted to local time and the seconds are dropped; `h24` renders `HH:mm`, `h12` renders `h:mm AM/PM`, and midnight and noon both render as `12`.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.themeMode]` Both settings are exposed as `ValueNotifier`s, so the theme and the message timestamps can listen to them without depending on `AppState`.
- `[mobile/lib/services/ws_service.dart:WsService.connect]` The token provider is consulted at connect time and the connection is not attempted when the token is null or empty.
- `[mobile/lib/services/ws_service.dart:WsService.connect]` If the base URL and token are unchanged and a connection exists or is in progress (`_isConnected || _channel != null`), the call returns without reconnecting. An explicit connect resets `_attempt` to 0, cancels the pending reconnect timer, clears `_reconnectScheduled`, and resets `_isAuthExpired` to false.
- `[mobile/lib/services/ws_service.dart:WsService._open]` `_open` returns immediately when `_closed` is true or when a channel already exists, so only one connection is open at a time. The token is re-fetched from `_tokenProvider` at each open attempt, so a refreshed token is used on the next connection.
- `[mobile/lib/services/ws_service.dart:WsService._open]` The WebSocket scheme is `'wss'` when the base URL starts with `'https://'` and `'ws'` otherwise; the host is derived by stripping the leading `^https?://` and trailing `/+` from the base URL. The URL is built as `'$scheme://$hostPort/api/v1/ws?token=${Uri.encodeComponent(token)}'`.
- `[mobile/lib/services/ws_service.dart:WsService._open]` On a successful `ready` future the service sets status to connected, starts the ping timer, and starts a 10-second healthy timer that resets `_attempt` to 0 and `_authRefreshTried` to false only if the connection survived that long.
- `[mobile/lib/services/ws_service.dart:WsService._open]` Stale-connection guards of the form `if (_closed || _channel != connection) return;` are applied in the ready handler, the error handler and the done handler so an old socket cannot change state.
- `[mobile/lib/services/ws_service.dart:WsService._open]` Incoming frames are parsed with `jsonDecode(data as String)` and are only dispatched to listeners when the result is a `Map<String, dynamic>`; the listener list is iterated as a snapshot (`List.of(_listeners)`). A parse failure is swallowed with `debugPrint` and does not close the connection. The stream subscription is created with `cancelOnError: true`.
- `[mobile/lib/services/ws_service.dart:WsService._open]` When the connection closes, a close code of 4401 routes to `_handleAuthFailed()` instead of the normal disconnect path; any other close code reports `'연결이 끊어졌습니다.'` and schedules a reconnect.
- `[mobile/lib/services/ws_service.dart:WsService._handleAuthFailed]` The token refresh is attempted at most once (`_authRefreshTried` guard); a second 4401 sets `_isAuthExpired = true` and reports `sessionExpiredMessage` without reconnecting. If the `authRefresher` hook is null, throws, or returns false, `_isAuthExpired` is set to true and the status error becomes `sessionExpiredMessage`.
- `[mobile/lib/services/ws_service.dart:WsService._scheduleReconnect]` The ping timer and healthy timer are always cancelled when a reconnect is scheduled. Reconnects are guarded by `_closed` and `_reconnectScheduled` so the same failure arriving via ready / stream-error / onDone schedules only one reconnect.
- `[mobile/lib/services/ws_service.dart:WsService._reconnectDelay]` The raw delay is `(1 << _attempt)` seconds while `_attempt < 5` and `maxReconnectDelay.inSeconds` (30) otherwise, then clamped up to `minReconnectDelay.inSeconds` (5), producing 5, 5, 5, 8, 16, 30, 30, ... seconds. `_attempt` is incremented when a reconnect is scheduled, so a connection that dies immediately keeps growing the backoff rather than resetting it.
- `[mobile/lib/services/ws_service.dart:WsService._setStatus]` `onStatusChanged` is called only when the connected flag or the error string actually changed, and `_lastError` is forced to null whenever connected is true.
- `[mobile/lib/services/ws_service.dart:WsService.send]` A frame is written only when a channel exists and `_isConnected` is true; send failures are caught and logged with `debugPrint` instead of propagating.
- `[mobile/lib/services/ws_service.dart:WsService.disconnect]` Disconnecting sets `_closed = true`, cancels all three timers, closes the channel, resets `_attempt` to 0, `_authRefreshTried` to false, `_isAuthExpired` to false, and sets the status to disconnected with a null error.
- `[mobile/lib/services/ws_service.dart:WsService._closeChannel]` `_channel` is cleared before `close()` is called so the resulting `onDone` cannot schedule a reconnect.

## Side Effects

### REST (`mobile/lib/services/api_service.dart`)

Every request is issued against `Uri.parse('$apiEndpoint$path')` where `apiEndpoint` is `'$_baseUrl/api/v1'`:

- `POST /auth/login` body `{email, password}`; `POST /auth/signup` body `{email, password, name, workspace_name}`; `POST /auth/refresh` body `{refresh_token}`.
- `GET /me`; `PATCH /me` body `{name?, title?, avatar_color?, presence?}`.
- `GET /workspaces`; `GET /workspaces/$workspaceId/bootstrap`.
- `GET /workspaces/$workspaceId/channels`; `POST /workspaces/$workspaceId/channels`; `GET /workspaces/$workspaceId/dms`; `POST /workspaces/$workspaceId/dms`.
- `PATCH /channels/$channelId` body `{name?, topic?, purpose?}`; `POST /channels/$channelId/join`; `POST /channels/$channelId/leave`; `DELETE /channels/$channelId` (channel deletion and DM deletion); `GET /channels/$channelId/members`; `POST /channels/$channelId/members`; `POST /channels/$channelId/read`.
- `GET /channels/$channelId/messages?limit=..[&before=..][&after=..][&around=..]`; `POST /channels/$channelId/messages` (body adds `attachment_ids` when there are attachments); `PATCH /messages/$messageId`; `DELETE /messages/$messageId`; `POST /messages/$messageId/restore`; `GET /messages/$messageId/replies?limit=..`; `POST|DELETE /messages/$messageId/reactions[/$emoji]`; `POST|DELETE /messages/$messageId/pin`; `GET /channels/$channelId/pins`.
- `GET /workspaces/$workspaceId/members`; `PATCH /workspaces/$workspaceId/members/$userId` body `{role}`; `DELETE /workspaces/$workspaceId/members/$userId`.
- `GET /users?q=..`; `GET /workspaces/$workspaceId/invites`; `POST /workspaces/$workspaceId/invites` body `{email, role}`; `DELETE /workspaces/$workspaceId/invites/$inviteId`.
- `POST /files?workspace_id=..` (multipart upload of one file).
- `GET /workspaces/$workspaceId/events[?from=..&to=..]`; `POST /workspaces/$workspaceId/events`; `POST /events/$eventId/rsvp`; `PATCH /events/$eventId`; `DELETE /events/$eventId`.
- `GET /workspaces/$workspaceId/projects`; `POST /workspaces/$workspaceId/projects`; `PATCH /projects/$projectId`; `DELETE /projects/$projectId`; `POST /projects/$projectId/members` body `{user_id}`; `DELETE /projects/$projectId/members/$userId`; `GET /projects/$projectId/tasks`; `POST /projects/$projectId/tasks`; `PATCH /tasks/$taskId`; `DELETE /tasks/$taskId`; `POST /tasks/$taskId/comments`; `DELETE /task-comments/$commentId`; `GET /projects/$projectId/roadmaps`; `GET /projects/$projectId/milestones`; `POST /projects/$projectId/milestones`; `PATCH /milestones/$milestoneId`; `DELETE /milestones/$milestoneId`; `DELETE /roadmaps/$roadmapId`.
- `GET /workspaces/$workspaceId/tasks` (the tasks assigned to the current user).
- `GET /workspaces/$workspaceId/org`; `POST /workspaces/$workspaceId/org/units`; `PATCH /org/units/$unitId`; `DELETE /org/units/$unitId`; `POST /org/units/$unitId/members` body `{user_id}`; `DELETE /org/units/$unitId/members/$userId`; `POST /org/units/$unitId/managers` body `{user_id}`; `DELETE /org/units/$unitId/managers/$userId`.
- `GET /workspaces/$workspaceId/search?q=..&limit=30`.

Disk: `init` reads the SharedPreferences keys `'llack.api_base'`, `'llack.access'`, `'llack.refresh'`; `setBaseUrl` writes `'llack.api_base'`; `setTokens` writes `'llack.access'` and `'llack.refresh'` and fires `onTokensChanged`; `clearTokens` removes `'llack.access'` and `'llack.refresh'`.

### Device settings (`mobile/lib/services/device_settings.dart`)

Disk: `load` reads `'llack.theme_mode'` and `'llack.clock_format'`; `setThemeMode` writes `'llack.theme_mode'` and `setClockFormat` writes `'llack.clock_format'` (the enum's Dart name). The notifiers are notified before the write, so the UI reacts immediately.

### WebSocket (`mobile/lib/services/ws_service.dart`)

- Opens a channel to `Uri.parse('$scheme://$hostPort/api/v1/ws?token=${Uri.encodeComponent(token)}')` via `WebSocketChannel.connect(uri)` (or the injected `connectionFactory`).
- Subscribes to the connection's stream, decoding each incoming frame with `jsonDecode` and dispatching the resulting map to every registered `WsEventHandler` listener.
- Sends `{'type': 'ping'}` on a 25-second `Timer.periodic`; `{'type': 'typing', 'channel_id': ..., 'on': ...}`; `{'type': 'read', 'channel_id': ...}` with `'message_id'` only when non-null; and arbitrary JSON payloads via `send`.
- Creates a one-shot reconnect `Timer` with the computed backoff delay, and a one-shot `Timer(healthyConnectionThreshold)` (10 seconds) that resets the reconnect backoff counter.
- `disconnect` cancels the ping, reconnect and healthy timers and closes the underlying channel sink.
- Mutates the internal `_isConnected`/`_lastError` state and calls `onStatusChanged` with `(connected, error)`.
- Emits `debugPrint` diagnostics: `'[WS] connect failed: ...'`, `'[WS] parse error: ...'`, `'[WS] error: ...'`, `'[WS] disconnected (code=...)'`, `'[WS] connection failed: ...'`.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
- Services-specific: `flutter test test/auth_401_message_test.dart` (the `_errorFromResponse` / `_unauthorizedMessage` paths against a fake server), `flutter test test/api_datetime_utc_test.dart` (the request bodies and query strings of `ApiService`, recorded with a fake HTTP client), `flutter test test/auth_session_expired_test.dart` (the session-expired notice on the login screen).
