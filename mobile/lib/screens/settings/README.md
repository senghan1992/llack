# Settings Screens

## Overview

The user-settings sheet (profile, presence, avatar color, screen mode, clock
format, server address, logout) and the standalone server-settings dialog used
to point the app at a different Llack backend.

Account-owned settings (name, title, avatar color, presence) are sent to the
server. Device-owned settings (light/dark/system mode and 12/24-hour time) are
stored locally through `DeviceSettings`.

`validateServerUrl` and `checkServerReachable` are the two exported helpers of
the server dialog. They are top-level functions so they can be unit-tested
without pumping a widget.

## Interface

- `class SettingsSheet` — public `StatelessWidget` with `const SettingsSheet({super.key})` (`mobile/lib/screens/settings/settings_sheet.dart`).
- `String? validateServerUrl(String raw)` — top-level function returning a Korean error message, or `null` when the URL is acceptable (`mobile/lib/screens/settings/server_settings_dialog.dart`).
- `Future<bool> checkServerReachable(String baseUrl)` — top-level function that probes the server with an HTTP GET and returns `true` for any successful HTTP response.
- `Future<void> showServerSettingsDialog(BuildContext context)` — top-level function that opens the dialog and shows a snack bar when a new URL was returned.
- `enum ThemeModeSetting` — `light`, `dark`, `system`, with `ThemeModeSetting.fromString(String?)` and Korean labels `밝게`, `어둡게`, `시스템` (`mobile/lib/services/device_settings.dart`).
- `enum ClockFormatSetting` — `h24`, `h12`, with `ClockFormatSetting.fromString(String?)`, Korean labels `24시간` / `12시간`, and `String format(DateTime time)` (`mobile/lib/services/device_settings.dart`).
- `class DeviceSettings` — public device-settings container with `static final DeviceSettings instance`, `ValueNotifier<ThemeModeSetting> themeMode`, `ValueNotifier<ClockFormatSetting> clockFormat`, `Future<void> load()`, `Future<void> setThemeMode(ThemeModeSetting mode)`, and `Future<void> setClockFormat(ClockFormatSetting format)` (`mobile/lib/services/device_settings.dart`).
- `static const String keyThemeMode = 'llack.theme_mode'` and `static const String keyClockFormat = 'llack.clock_format'` — the persisted device-setting keys (`mobile/lib/services/device_settings.dart:DeviceSettings`).
- `static const List<String> avatarPalette` — the seven server-stored avatar hex colors offered by the profile editor (`mobile/lib/theme/llack_colors.dart:LlackColors`).
- `static Color? colorFromHex(String? hex)` — parses a three- or six-digit avatar hex string, returning `null` for an invalid value (`mobile/lib/theme/llack_colors.dart:LlackColors`).

## Invariants

- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` When `state.currentUser` is null the whole sheet renders as `const SizedBox.shrink()`.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` The screen-mode choices are exactly `ThemeModeSetting.values` and the clock choices are exactly `ClockFormatSetting.values`; the selected chip is driven by the corresponding `ValueListenableBuilder` state.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet._changePresence]` `state.updatePresence` is wrapped in try/catch and the failure is reported via `showAppSnackBar(context, '상태를 바꾸지 못했습니다')` with a `context.mounted` guard, because `updatePresence` rethrows the error from `updateMe`.
- `[mobile/lib/screens/settings/settings_sheet.dart:_EditProfileDialogState._save]` Saving is skipped when the trimmed name is empty or `_isSubmitting` is true, and an empty title is sent as `null`. On failure the dialog is intentionally not closed (to keep the user's input), `_isSubmitting` is reset and `showAppSnackBar(context, '프로필을 저장하지 못했습니다: $e')` is shown; the buttons are disabled while submitting.
- `[mobile/lib/screens/settings/settings_sheet.dart:_EditProfileDialogState.initState]` The profile dialog starts with the current user's `avatarColor`; the seven swatches come from `LlackColors.avatarPalette` and store the selected hex string.
- `[mobile/lib/screens/settings/settings_sheet.dart:_EditProfileDialogState._save]` A successful profile save passes the selected `avatarColor` together with name and title to `updateMe`.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.load]` Missing or unknown persisted values default to `ThemeModeSetting.system` and `ClockFormatSetting.h24`.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setThemeMode]` Setting the already-selected theme mode is a no-op; otherwise the notifier is updated before the value is persisted.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setClockFormat]` Setting the already-selected clock format is a no-op; otherwise the notifier is updated before the value is persisted.
- `[mobile/lib/services/device_settings.dart:ClockFormatSetting.format]` The 24-hour formatter emits a zero-padded `HH:mm`; the 12-hour formatter emits `h:mm AM` or `h:mm PM`, with midnight rendered as `12:00 AM`.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:validateServerUrl]` The URL is rejected when empty (`'서버 주소를 입력하세요.'`), when it contains whitespace (`'주소에 공백이 포함되어 있습니다.'`), when it does not start with `http://` or `https://` (`'http:// 또는 https:// 로 시작하는 주소를 입력하세요.'`), or when `Uri.tryParse` fails or the parsed host is empty (`'올바른 서버 주소가 아닙니다.'`).
- `[mobile/lib/screens/settings/server_settings_dialog.dart:checkServerReachable]` Trailing slashes are stripped with `replaceAll(RegExp(r'/+$'), '')` before the probe, and any HTTP response (401/404 included) counts as reachable; only exceptions/timeouts return `false`. The probe uses an 8 second timeout.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:_ServerSettingsDialogState._save]` The save flow is strictly ordered: input validation first, then the reachability check, then `state.changeApiBaseUrl(url)`; a validation or reachability failure returns early and only sets `_errorMessage`. While `_isChecking` is true the text field is disabled (`enabled: !_isChecking`) and both action buttons are disabled (`onPressed: null`).
- `[mobile/lib/screens/settings/server_settings_dialog.dart:_ServerSettingsDialogState.build]` Editing the text clears any previous `_errorMessage`, and the error text is allowed 3 lines (`errorMaxLines: 3`) so the message is not truncated.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:_ServerSettingsDialogState]` The `TextEditingController` is created in `initState` from `context.read<AppState>().api.baseUrl` and disposed in `dispose`, because the dialog widget owns it (the comment explains that disposing after the dialog closes would break the exit animation).

## Side Effects

- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet._showEditProfileDialog]` Opens a modal dialog with `showDialog<void>(context: context, builder: (_) => const _EditProfileDialog())`; it reads `context.read<AppState>().currentUser` first and does nothing when the user is null.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet._changePresence]` Calls `state.updatePresence(presence)`, which ends in `api.updateMe` — `PATCH /me` with the `presence` field.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` The `'서버 주소 설정'` tile opens the server settings via `showServerSettingsDialog(context)` and displays `state.api.baseUrl` as the subtitle. The `'로그아웃'` tile calls `Navigator.pop(context)` and then `state.logout()`, which disconnects the WebSocket and clears the stored tokens.
- `[mobile/lib/screens/settings/settings_sheet.dart:_EditProfileDialogState._save]` Calls `state.updateMe(name:, title:, avatarColor:)` — `PATCH /me` — and pops the dialog with `Navigator.pop(context)` on success.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` Reads provider state via `context.watch<AppState>()` (currentUser, getPresence, api.baseUrl) and listens to `DeviceSettings.instance.themeMode` and `DeviceSettings.instance.clockFormat` for the device preferences.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setThemeMode]` Persists the theme mode under the SharedPreferences key `llack.theme_mode` and updates the in-memory notifier.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setClockFormat]` Persists the clock format under the SharedPreferences key `llack.clock_format` and updates the in-memory notifier.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:checkServerReachable]` Performs an HTTP GET to `Uri.parse('$normalized/api/v1/me')` with header `{'Accept': 'application/json'}` and an 8 second timeout.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:_ServerSettingsDialogState._save]` Calls `state.changeApiBaseUrl(url)`, which writes the base URL to the SharedPreferences key `llack.api_base`, disconnects and reconnects the WebSocket, and reloads workspace data, messages, events, projects and the org chart. On success it pops the dialog with the new URL (`Navigator.pop(context, url)`).
- `[mobile/lib/screens/settings/server_settings_dialog.dart:showServerSettingsDialog]` Opens the dialog with `showDialog<String>(context: context, builder: (_) => const _ServerSettingsDialog())` and, when a URL comes back and the context is still mounted, calls `showAppSnackBar(context, '서버 주소가 변경되었습니다: $savedUrl')`.
- `[mobile/lib/screens/settings/server_settings_dialog.dart:_ServerSettingsDialogState.initState]` Reads `context.read<AppState>().api.baseUrl` to prefill the address field, and `build` reads the current URL via `context.watch<AppState>()`.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
