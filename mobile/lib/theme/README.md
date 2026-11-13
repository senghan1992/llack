# Theme

## Overview

Design-token package for the Llack mobile client: the color palette, the
`ThemeData` built from it, and the typography scale.

The package holds **two palettes** — `LlackColors.light` and
`LlackColors.dark` — and exactly one of them is *current*
(`LlackColors.current`). Every mode-dependent color is therefore a **getter**
that reads the current palette, not a `static const`. Switching the screen
mode means calling `LlackColors.usePalette(...)` right before the `MaterialApp`
is drawn; the mode itself is owned by `mobile/lib/services/device_settings.dart`.

The package also registers **two themes**, not one: `LlackTheme.light()` and
`LlackTheme.dark()`. `main.dart` picks between them from
`DeviceSettings.instance.themeMode` (`system` follows the OS brightness) and
swaps the palette in the same pass.

Screens are expected to reference text sizes by role (via
`LlackTypography.textTheme`) rather than hard-coding `fontSize`.

## Interface

### `LlackPalette` (`mobile/lib/theme/llack_colors.dart`)

Public class with a `const LlackPalette({...})` constructor and 20 `final
Color` fields — the complete set of mode-dependent colors:

- Paper & ink: `paper`, `ink`, `ink2`, `muted`, `rule`, `ruleSoft`.
- Accent ramp: `accent`, `accentLift`, `accentDeep`, `accentSoft`, `accentInk`.
- Message bubble: `bubbleMine`, `bubbleMineInk`, `bubbleMineDim`.
- Surface roles: `surfaceFrame`, `surfaceRail`, `surfaceCanvas`,
  `surfaceRaise`, `surfaceWell`, `surfaceSelected`.

### `LlackColors` (`mobile/lib/theme/llack_colors.dart`)

Private constructor `LlackColors._()`. Palettes and the active palette:

- `static const LlackPalette light` — warm paper palette (`paper`
  `0xFFFBF9F5`, `ink` `0xFF1E2B27`, `accent` `0xFFED6B40`, `surfaceRaise`
  `0xFFFFFFFF`).
- `static const LlackPalette dark` — the same hues moved from paper to slate
  (`paper` `0xFF141A18`, `ink` `0xFFE6EDEA`, `accent` `0xFFF0805A`,
  `surfaceRaise` `0xFF1E2623`).
- `static LlackPalette get current` — the palette in effect.
- `static void usePalette(LlackPalette palette)` — swaps the current palette.

Mode-dependent colors (all `static Color get ...`, not `const`): `paper`,
`ink`, `ink2`, `muted`, `rule`, `ruleSoft`, `accent`, `accentLift`,
`accentDeep`, `accentSoft`, `accentInk`, `bubbleMine`, `bubbleMineInk`,
`bubbleMineDim`, `surfaceFrame`, `surfaceRail`, `surfaceCanvas`,
`surfaceRaise`, `surfaceWell`, `surfaceSelected`.

Mode-independent colors (still `static const`):

- Presence: `presenceOnline`, `presenceBusy`, `presenceDnd`, `presenceAway`,
  `presenceBrb`, `presenceOffline`.
- Status: `statusRequest`, `statusTodo`, `statusInProgress`, `statusDone`.
- `static const List<Color> avatarColors` — 8 entries: `0xFF1C785C`,
  `0xFF0284C7`, `0xFF7C3AED`, `0xFFD97706`, `0xFFDC2626`, `0xFF0D9488`,
  `0xFFDB2777`, `0xFF4B5563`.

Avatar helpers:

- `static const List<String> avatarPalette` — 7 hex strings (`#126b47`,
  `#8a4141`, `#295e90`, `#814d0e`, `#644c8a`, `#006b71`, `#6a5a00`), the
  same list as the desktop `AVATAR_PALETTE`.
- `static Color? colorFromHex(String? hex)` — `#rrggbb` / `#rgb` → `Color`;
  `null` when the input is `null` or malformed.
- `static Color LlackColors.avatarColorForName(String name)` —
  deterministic name-to-color mapping.

### `LlackTheme` (`mobile/lib/theme/llack_theme.dart`)

Private constructor `LlackTheme._()`. Public static constants:

- Radii: `radiusInput` (`10.0`), `radiusCard` (`14.0`), `radiusPanel` (`16.0`),
  `radiusPill` (`999.0`).
- Elevation: `shadowE1`, `shadowE2` — each a `List<BoxShadow>` of two shadows.

Public static methods:

- `static ThemeData LlackTheme.light()` — the light theme, built from
  `LlackColors.light` and `Brightness.light`.
- `static ThemeData LlackTheme.dark()` — the dark theme, built from
  `LlackColors.dark` and `Brightness.dark`.

Both go through the same private `static ThemeData _build(LlackPalette p,
Brightness brightness)`.

### `LlackTypography` (`mobile/lib/theme/llack_typography.dart`)

Private constructor `LlackTypography._()`. Public static members:

- `static const List<String> fontFallbacks` — `Pretendard`,
  `Apple SD Gothic Neo`, `Noto Sans KR`, `Roboto`, `sans-serif`.
- `static const List<String> monoFallbacks` — `DM Mono`, `Menlo`, `Consolas`,
  `monospace`.
- `static TextStyle get ...` — `display`, `title`, `subtitle`, `body`,
  `bodySmall`, `caption`, `monoTimestamp`, `monoTimestampOnMine`,
  `authorName`, `titleSmall`, `labelLarge`.
- `static TextTheme get textTheme` — the app-wide text theme.

## Invariants

- `[mobile/lib/theme/llack_colors.dart:LlackColors.paper]` Every mode-dependent color (`paper`, `ink`, `accent`, `surfaceRaise`, …) is a `static Color get` that reads `LlackColors.current`, **not** a `static const`; because the value can change at runtime it cannot be used in a `const` context.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.current]` The current palette starts as `LlackColors.light` (`static LlackPalette _current = light;`), so a build that never calls `usePalette` renders the light palette.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.usePalette]` The function only assigns `_current = palette`; it performs no I/O and triggers no rebuild on its own, so it has to be called right before the `MaterialApp` is drawn.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.presenceOnline]` Presence (`presence*`), status (`status*`) and `avatarColors` stay `static const`: they are state markers, so they keep the same value in both screen modes.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.avatarPalette]` The palette holds exactly 7 hex strings, and the values are identical to the desktop `AVATAR_PALETTE` in `desktop/src/lib/color.ts` (`#126b47`, `#8a4141`, `#295e90`, `#814d0e`, `#644c8a`, `#006b71`, `#6a5a00`).
- `[mobile/lib/theme/llack_colors.dart:LlackColors.colorFromHex]` A `null` input returns `null`; the value is trimmed and the first `#` is stripped; a 3-character value is expanded by doubling each character; anything that is not exactly 6 hex digits returns `null`; the parsed value is always opaque (`0xFF000000 | parsed`).
- `[mobile/lib/theme/llack_colors.dart:LlackColors.avatarColorForName]` An empty name returns `avatarColors.first` (`0xFF1C785C`) instead of hashing.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.avatarColorForName]` The color is chosen deterministically from a hash computed as `hash = name.codeUnitAt(i) + ((hash << 5) - hash)` over the name's code units, then `index = hash.abs() % avatarColors.length`.
- `[mobile/lib/theme/llack_colors.dart:LlackColors.avatarColors]` The avatar palette is fixed at exactly 8 colors, and the modulo operation always resolves into that list's bounds.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme.light]` The light theme is built with `useMaterial3: true` and `brightness: Brightness.light`, with `primaryColor` = the palette's `accent` and `scaffoldBackgroundColor` = the palette's `paper`.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme.dark]` The dark theme is built from `LlackColors.dark` with `brightness: Brightness.dark`, and its color scheme is `ColorScheme.dark` (not `ColorScheme.light`).
- `[mobile/lib/theme/llack_theme.dart:LlackTheme.dark]` The dark color scheme uses `onPrimaryContainer: p.accent`, while the light color scheme uses `onPrimaryContainer: p.accentDeep`; every other scheme role (primary, onPrimary, primaryContainer, surface, onSurface, surfaceContainerHighest, outline, outlineVariant) is built from the same palette fields in both themes.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme.dark]` The dark theme's app bar uses `systemOverlayStyle: SystemUiOverlayStyle.light` (the light theme uses `SystemUiOverlayStyle.dark`), so the status bar icons stay legible on the dark paper.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The app bar theme sets elevation 0, scrolledUnderElevation 0, centerTitle false, titleTextStyle `LlackTypography.title`, and icon color = the palette's `ink`.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The divider theme uses color = the palette's `rule`, thickness 1 and space 1.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The snack bar is forced to `SnackBarBehavior.floating` (not fixed) because, per the code comment, the fixed behavior paints over the message composer while floating appears inside the message area; the comment also notes the chat screen shows the snack bar inside a nested `ScaffoldMessenger`.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The floating snack bar uses `insetPadding: EdgeInsets.fromLTRB(16, 8, 16, 16)`, elevation 2, background = the palette's `surfaceRaise`, content text `bodySmall` recolored to `ink`, action text = the palette's `accentDeep`, and a rounded shape with `radiusInput` plus a 1px `rule` border.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` Input fields are filled with the palette's `surfaceWell` and use symmetric content padding of 14 horizontal / 12 vertical, with all borders at `radiusInput`: enabled border `rule` width 1, focused border `accent` width 1.5, error border `presenceBusy` width 1.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The elevated button uses background = the palette's `accent`, foreground = the palette's `accentInk`, elevation 0, padding 16 horizontal / 12 vertical, `radiusInput` shape and text style fontSize 14 / w600 / letterSpacing -0.2.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The outlined button uses foreground = the palette's `ink`, a 1px `rule` side, padding 14 horizontal / 10 vertical, `radiusInput` shape and text style fontSize 13.5 / w500; the text button uses foreground = the palette's `accent` with text style fontSize 13.5 / w600.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` Cards use color = the palette's `surfaceRaise`, elevation 0, `radiusCard` shape with a 1px `rule` border and `EdgeInsets.zero` margin.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The bottom navigation bar is `BottomNavigationBarType.fixed` with elevation 4, background = the palette's `surfaceRail`, selected item color = the palette's `accent`, unselected item color = the palette's `muted`, and both label styles at fontSize 12 (w600 selected / w500 unselected) to keep a 12pt minimum for accessibility while still honoring system font scaling.
- `[mobile/lib/theme/llack_theme.dart:LlackTheme._build]` The theme's text theme is taken directly from `LlackTypography.textTheme` so screens reference roles instead of hard-coded sizes.
- `[mobile/lib/theme/llack_typography.dart:LlackTypography.display]` The text styles are `static TextStyle get` accessors (and `textTheme` is `static TextTheme get`), not `static const`: they bake in `LlackColors.ink` / `muted` / `bubbleMineDim`, so their colors follow the current palette.
- `[mobile/lib/theme/llack_typography.dart:LlackTypography.textTheme]` The TextTheme maps roles to styles: displayLarge=display, titleLarge=title, titleMedium=subtitle, titleSmall=titleSmall, bodyLarge=body, bodyMedium=body, bodySmall=bodySmall, labelLarge=labelLarge, labelMedium=bodySmall, labelSmall=caption; displaySmall, headline*, titleTiny, and body* variants not listed are left unset.
- `[mobile/lib/theme/llack_typography.dart:LlackTypography.textTheme]` A code comment states the rule that screens should reference sizes by role rather than hard-coding fontSize so system text-size settings scale them together and the minimum size is guaranteed to be 12.
- `[mobile/lib/theme/llack_typography.dart:LlackTypography.monoTimestamp]` The two monospace styles (`monoTimestamp` and `monoTimestampOnMine`) use `monoFallbacks` while every other style uses `fontFallbacks`.
- `[mobile/lib/theme/llack_typography.dart:LlackTypography.caption]` The smallest shipped text sizes are 11 (`monoTimestamp`, `monoTimestampOnMine`) and 12 (`caption`, bottom nav labels), matching the documented 12pt minimum for user-facing label text.

## Side Effects

- `[mobile/lib/theme/llack_colors.dart:LlackColors.usePalette]` Mutates the file-level palette holder (`_current`), which is process-global state: every later read of `LlackColors.paper` (and the other dynamic getters) returns the new palette. `main.dart` calls it from `LlackMobileApp.build` before the `MaterialApp` is created, so the swap happens before any screen reads a token.
- None beyond that. The theme package performs no I/O, no network calls, and no persistence; the mode setting itself is stored by `mobile/lib/services/device_settings.dart`.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
- Theme-specific: `flutter test test/snackbar_theme_test.dart` (snack bar theme) and `flutter test test/message_markdown_test.dart` (the palette-dependent link/mention colors).
- Manual: switch the screen mode in the settings sheet and confirm `LlackTheme.dark()` is registered, the paper turns slate (`0xFF141A18`), and the status-bar icons stay light.
