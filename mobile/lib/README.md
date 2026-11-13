# Llack Mobile Library

## Overview

The Dart source root of the Flutter client. `main.dart` is the application
entry point: it initializes Korean date formatting, constructs the single
`AppState`, registers it with `provider`, and starts the boot sequence.

The rest of the tree is organised by responsibility:

- `models/` — immutable data classes and enums for the API payloads.
- `services/` — the REST and WebSocket transport boundary.
- `providers/` — the single `AppState` `ChangeNotifier` holding all app state.
- `screens/` — the feature screens.
- `widgets/` — shared presentation widgets.
- `theme/` — colors, `ThemeData`, typography.
- `responsive/` — breakpoint helpers.

## Interface

### Local symbols

- `void main()` — the application entry point (`mobile/lib/main.dart`).
- `class LlackMobileApp` — public `StatelessWidget` with const constructor `LlackMobileApp({super.key})`; the `MaterialApp` root (`mobile/lib/main.dart`).

### Subdirectories

- [Models](./models/README.md) — API data classes and enums.
- [Providers](./providers/README.md) — the `AppState` `ChangeNotifier`.
- [Responsive](./responsive/README.md) — `ScreenType` and `FormFactor`.
- [Screens](./screens/README.md) — the feature screens.
- [Services](./services/README.md) — `ApiService` and `WsService`.
- [Theme](./theme/README.md) — colors, `ThemeData`, typography.
- [Widgets](./widgets/README.md) — shared presentation widgets.

## Invariants

- `[mobile/lib/main.dart:main]` `main()` awaits `initializeDateFormatting('ko_KR', null)` before `runApp`, so `intl` date formatting is available to every screen.
- `[mobile/lib/main.dart:main]` The `AppState` is created and passed to `ChangeNotifierProvider.value`, so the same instance is shared for the whole app lifetime.
- `[mobile/lib/main.dart:main]` The boot sequence starts after the first frame: `appState.boot()` is called after `runApp`, not awaited before it. The inline comment states that awaiting it first would prevent the first Flutter frame from being drawn, so the `'Llack 연결 중...'` splash would never appear.
- `[mobile/lib/main.dart:LlackMobileApp.build]` The app shows `AuthScreen` when `!state.isAuthenticated` and `MainShell` otherwise, while `state.isBooting` renders a `'Llack 연결 중...'` placeholder screen.
- `[mobile/lib/main.dart:LlackMobileApp.build]` The `MaterialApp` is built with `title: 'Llack'`, `debugShowCheckedModeBanner: false`, `theme: LlackTheme.light()`, the three `GlobalMaterialLocalizations` / `GlobalWidgetsLocalizations` / `GlobalCupertinoLocalizations` delegates, `supportedLocales` of `ko_KR` and `en_US`, and a fixed `locale: const Locale('ko', 'KR')`.
- `[mobile/lib/main.dart:LlackMobileApp.build]` The locale is fixed to `ko_KR` because the app is a Korean product; the inline comment states that without a fixed locale the device locale would make the date/time pickers render in English with a 12-hour clock.

## Side Effects

- `[mobile/lib/main.dart:main]` Calls `WidgetsFlutterBinding.ensureInitialized()` and `initializeDateFormatting('ko_KR', null)`, then constructs `AppState()` (which constructs an `ApiService` and a `WsService`) and calls `appState.boot()` after `runApp`.
- `[mobile/lib/main.dart:main]` The `ChangeNotifierProvider.value` owns the `AppState` for the app's lifetime, so the state's `dispose()` (which disconnects the WebSocket) runs when the provider is torn down.
- `[mobile/lib/main.dart:LlackMobileApp.build]` Renders the app-root widget tree: `MaterialApp` → `Consumer<AppState>` → splash / `AuthScreen` / `MainShell`. It performs no direct I/O itself; all network work is delegated to `AppState` and `ApiService` / `WsService`.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
