# Settings Screens

## Overview

The user-settings sheet (profile, presence, avatar color, screen mode, clock
format, logout).

Account-owned settings (name, title, avatar color, presence) are sent to the
server. Device-owned settings (light/dark/system mode and 12/24-hour time) are
stored locally through `DeviceSettings`.

There is no server-address setting here. The address is fixed when the app is
built (`--dart-define=LLACK_SERVER_URL=…`), so there is nothing for a person
to change and nothing to store.

## Interface

- `class SettingsSheet` — public `StatelessWidget` with `const SettingsSheet({super.key})` (`mobile/lib/screens/settings/settings_sheet.dart`).
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

## Side Effects

- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet._showEditProfileDialog]` Opens a modal dialog with `showDialog<void>(context: context, builder: (_) => const _EditProfileDialog())`; it reads `context.read<AppState>().currentUser` first and does nothing when the user is null.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet._changePresence]` Calls `state.updatePresence(presence)`, which ends in `api.updateMe` — `PATCH /me` with the `presence` field.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` The `'로그아웃'` tile calls `Navigator.pop(context)` and then `state.logout()`, which disconnects the WebSocket and clears the stored tokens. There is no server-address tile — the address is fixed at build time.
- `[mobile/lib/screens/settings/settings_sheet.dart:_EditProfileDialogState._save]` Calls `state.updateMe(name:, title:, avatarColor:)` — `PATCH /me` — and pops the dialog with `Navigator.pop(context)` on success.
- `[mobile/lib/screens/settings/settings_sheet.dart:SettingsSheet.build]` Reads provider state via `context.watch<AppState>()` (currentUser, getPresence) and listens to `DeviceSettings.instance.themeMode` and `DeviceSettings.instance.clockFormat` for the device preferences.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setThemeMode]` Persists the theme mode under the SharedPreferences key `llack.theme_mode` and updates the in-memory notifier.
- `[mobile/lib/services/device_settings.dart:DeviceSettings.setClockFormat]` Persists the clock format under the SharedPreferences key `llack.clock_format` and updates the in-memory notifier.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
