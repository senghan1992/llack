# Llack Mobile Blueprint

## System Overview

`mobile/` is the Flutter client for the Llack backend (FastAPI + WebSocket).
It is a single-app Flutter project named `llack_mobile`
(`mobile/pubspec.yaml`), version `1.0.0+1`, published as `'none'`.

The app follows a one-way, three-layer architecture:

```
  screens/ + widgets/          presentation (Flutter widgets, provider reads)
        │
        ▼
  providers/AppState           the single ChangeNotifier holding all app state
        │
        ▼
  services/                    transport boundary
        ├── ApiService         REST over /api/v1 (http package)
        ├── WsService          WebSocket over /api/v1/ws (web_socket_channel)
        └── DeviceSettings     이 기기에 남는 설정 (화면 모드 · 시간 표기)
        │
        ▼
  models/                      immutable data classes decoded from the payloads
```

Two rules hold the whole client together:

1. **One state container.** `AppState` (`mobile/lib/providers/app_state.dart`)
   is created once in `main()` and installed with
   `ChangeNotifierProvider.value`. Every screen reads it with
   `context.watch<AppState>()` / `context.read<AppState>()`; no screen owns a
   second copy of server data.
2. **One upsert rule.** The backend emits a WebSocket event *before* the
   matching HTTP response, so the same object can arrive twice. Every merge
   goes through `upsertById` (`mobile/lib/providers/list_upsert.dart`), which
   keeps exactly one entry per id regardless of arrival order.

Runtime environment:

- Dart SDK constraint `^3.13.3` (`mobile/pubspec.yaml`, `environment.sdk`).
- Flutter stable channel, revision `e8113bf45620cbeb8aff64947ee4c93e16adb4cf`,
  project type `app` (`mobile/.metadata`).
- Lints: `flutter_lints ^6.0.0`, `include: package:flutter_lints/flutter.yaml`
  (`mobile/analysis_options.yaml`). The analyzer excludes `build/**` and every
  platform directory (`android/**`, `ios/**`, `web/**`, `windows/**`,
  `macos/**`, `linux/**`).
- Runtime dependencies: `http ^1.6.0`, `web_socket_channel ^3.0.3`,
  `shared_preferences ^2.5.6`, `intl ^0.20.3`, `provider ^6.1.5+1`,
  `cupertino_icons ^1.0.8`, plus `flutter_localizations` from the SDK.
- The app is Korean-first: the locale is fixed to `ko_KR`
  (`mobile/lib/main.dart:LlackMobileApp.build`), and `initializeDateFormatting('ko_KR', null)`
  runs before `runApp`.

## Subdirectories & System Boundaries

- [lib/](./lib/README.md) — the Dart source root: `main.dart` plus the `models/`, `providers/`, `responsive/`, `screens/`, `services/`, `theme/`, and `widgets/` packages. The only directory in this subtree with a contract.
- `test/` — Flutter widget/unit tests. Excluded from this subtree's contract scope; it is the target of the `flutter test` verification command below.
- `android/`, `ios/`, `linux/`, `macos/`, `windows/`, `web/` — generated Flutter platform scaffolding. Excluded from this subtree's contract scope.
- `pubspec.yaml`, `pubspec.lock`, `analysis_options.yaml`, `.metadata`, `.gitignore` — package manifests and tool configuration, described in the runtime environment section above.

## Global Invariants

- **Transport prefix.** Every REST path is built as `'$_baseUrl/api/v1$path'`
  (`mobile/lib/services/api_service.dart:ApiService.apiEndpoint`), and the
  WebSocket URL is `'$scheme://$hostPort/api/v1/ws?token=...'` where the scheme
  is `wss` for an `https://` base URL and `ws` otherwise
  (`mobile/lib/services/ws_service.dart:WsService._open`).
- **Authentication.** The access token is sent as `Authorization: Bearer <token>`
  only when a token is present
  (`mobile/lib/services/api_service.dart:ApiService._request`). A 401 triggers
  at most one token refresh and one retry
  (`mobile/lib/services/api_service.dart:ApiService._request`), and the refresh
  endpoint is `POST /auth/refresh` with body `{'refresh_token': ...}`
  (`mobile/lib/services/api_service.dart:ApiService._refreshAccessToken`).
- **Session expiry vs. bad password.** A 401 on `/auth/login` or `/auth/signup`
  is reported as a wrong email/password; any other 401 is reported as an
  expired session
  (`mobile/lib/services/api_service.dart:ApiService._unauthorizedMessage`).
  The WebSocket close code `4401` is the realtime counterpart
  (`mobile/lib/services/ws_service.dart:WsService.authFailedCloseCode`).
- **Timeouts.** Every REST request is capped at 15 seconds
  (`mobile/lib/services/api_service.dart:ApiService.requestTimeout`) and is
  converted into an `ApiException` rather than hanging the UI.
- **Credential persistence.** The access token, refresh token, and server base
  URL are persisted in `SharedPreferences` under the keys `llack.access`,
  `llack.refresh`, and `llack.api_base`
  (`mobile/lib/services/api_service.dart:ApiService.keyAccess`,
  `ApiService.keyRefresh`, `ApiService.keyApiBase`).
- **Reconnect backoff.** The WebSocket retries on a 5, 5, 5, 8, 16, 30, 30, ...
  second schedule, and the backoff counter is only reset once a connection has
  survived 10 seconds
  (`mobile/lib/services/ws_service.dart:WsService._reconnectDelay`,
  `WsService.healthyConnectionThreshold`), so a connection that dies
  immediately cannot create a 1-second reconnect loop.
- **Idempotent merges.** Channels, messages, events, tasks, and task comments
  are merged by id, never appended blindly
  (`mobile/lib/providers/list_upsert.dart:upsertById`), because the backend
  delivers the WebSocket event before the HTTP response.
- **Load flags are independent of emptiness.** `hasLoadedEvents`,
  `hasLoadedProjects`, and `hasLoadedOrg` stay true even for an empty
  workspace, and the screens use them (not list emptiness) to avoid duplicate
  requests
  (`mobile/lib/providers/app_state_core.dart:_AppStateCore.hasLoadedEvents`).
- **Responsive rule.** The shell picks the phone bottom-nav layout versus the
  tablet split layout from `FormFactor(context).isPad`, i.e. width >= 650dp
  (`mobile/lib/screens/main_shell.dart:_MainShellState.build`,
  `mobile/lib/responsive/screen_type.dart:FormFactor.isPad`).
- **Single app bar.** Each screen shows exactly one app bar; the shell supplies
  `LlackAppBar` for the chat tab because `ChatTab` has none of its own
  (`mobile/lib/screens/main_shell.dart:_ChatTabHost`).

## Global Side Effects

- **REST.** The client issues `GET|POST|PATCH|DELETE` against `/api/v1` for
  auth (`/auth/login`, `/auth/signup`, `/auth/refresh`), profile (`/me`),
  workspaces (`/workspaces`, `/workspaces/{id}/bootstrap`), channels and DMs
  (`/workspaces/{id}/channels`, `/workspaces/{id}/dms`, `/channels/{id}/...`),
  messages (`/channels/{id}/messages`, `/messages/{id}/...`), schedule
  (`/workspaces/{id}/events`, `/events/{id}/...`), projects and tasks
  (`/workspaces/{id}/projects`, `/projects/{id}/...`, `/tasks/{id}/...`),
  organization (`/workspaces/{id}/org`, `/workspaces/{id}/org/units`), and
  search (`/workspaces/{id}/search`)
  (`mobile/lib/services/api_service.dart`).
- **WebSocket.** One socket to `/api/v1/ws` carries server-pushed event maps
  (`hello`, `presence`, `message.created`, `message.updated`,
  `message.deleted`, `reaction.updated`, `typing`, `channel.created`,
  `event.created|updated|deleted`, `task.created|updated|deleted`, `unread`)
  (`mobile/lib/providers/app_state_realtime.dart:_handleWsEvent`). The client
  sends `{'type': 'ping'}` every 25 seconds, plus `typing` and `read` frames
  (`mobile/lib/services/ws_service.dart:WsService._startPing`,
  `WsService.sendTyping`, `WsService.sendRead`).
- **Disk.** `SharedPreferences` holds exactly three keys — `llack.access`,
  `llack.refresh`, `llack.api_base`
  (`mobile/lib/services/api_service.dart:ApiService.setTokens`,
  `ApiService.setBaseUrl`, `ApiService.clearTokens`).
- **Global state.** `AppState` is the only mutable state container; all its
  mutations are published through `notifyListeners()`
  (`mobile/lib/providers/app_state_core.dart:_AppStateCore._notify`). A
  separate `ValueNotifier<int> tabIndex` carries the bottom-nav selection
  (`mobile/lib/providers/app_state_core.dart:_AppStateCore.tabIndex`).
- **Process lifecycle.** The socket is disconnected when the app is
  backgrounded and reconnected on resume, and the workspace is re-fetched
  (`mobile/lib/providers/app_state.dart:AppState.didChangeAppLifecycleState`).
  On WebSocket reconnect the client re-syncs the workspace bootstrap and the
  newest messages (`mobile/lib/providers/app_state_realtime.dart:_resyncAfterReconnect`).

## System Verification

- Run: `flutter test` (from the `mobile/` directory)
  - Target: `flutter_test` (SDK dev dependency) against the `mobile/test/` suite.
  - Requires a Flutter SDK matching the `stable` channel and the Dart SDK
    constraint `^3.13.3`; the analyzer/lint configuration comes from
    `mobile/analysis_options.yaml`.
  - Static analysis is available as `flutter analyze` (also configured by
    `mobile/analysis_options.yaml`); it is not the primary verification target.

## Developer Note

Flutter learning resources, preserved from the original project README:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)
- [Flutter online documentation](https://docs.flutter.dev/)
