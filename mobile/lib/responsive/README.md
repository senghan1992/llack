# Responsive

## Overview

Breakpoint helper for the mobile client. `FormFactor` wraps a `BuildContext` and
derives a coarse screen class from the current viewport width, so screens can
branch between a single-pane (phone) layout and a multi-pane (tablet/desktop)
layout without duplicating their own MediaQuery queries.

The thresholds match the desktop client: `compact` below 650dp, `medium` between
650dp and 1000dp, and `expanded` at 1000dp and above.

## Interface

- `enum ScreenType` — exactly three constants: `compact`, `medium`, `expanded`.
- `class FormFactor`
  - `FormFactor(this.context)` — public positional constructor holding a `final BuildContext context`.
  - `double get FormFactor.width` — `MediaQuery.sizeOf(context).width`.
  - `double get FormFactor.height` — `MediaQuery.sizeOf(context).height`.
  - `ScreenType get FormFactor.screenType` — derived from the current width.
  - `bool get FormFactor.isCompact`, `isMedium`, `isExpanded` — screen-type comparisons.
  - `bool get FormFactor.isPad` — `!isCompact` (true for medium and expanded).
  - `bool get FormFactor.canShowThreePanes` — whether a 3-pane split fits.
  - `bool get FormFactor.canShowTwoPanes` — whether a 2-pane split fits.

## Invariants

- `[mobile/lib/responsive/screen_type.dart:FormFactor.screenType]` Screen type is chosen from width only: `width < 650` returns `ScreenType.compact`, `width < 1000` returns `ScreenType.medium`, and anything wider returns `ScreenType.expanded`.
- `[mobile/lib/responsive/screen_type.dart:ScreenType]` Doc comments state compact covers small screens (< 650dp), medium covers phone landscape / unfolded foldables / mini tablets in portrait (650dp - 1000dp), and expanded covers iPads and large tablets (>= 1000dp).
- `[mobile/lib/responsive/screen_type.dart:FormFactor.canShowThreePanes]` The 3-pane split is only allowed when `width >= 1080`.
- `[mobile/lib/responsive/screen_type.dart:FormFactor.canShowTwoPanes]` The 2-pane split is only allowed when `width >= 650`.
- `[mobile/lib/responsive/screen_type.dart:FormFactor.isPad]` `isPad` is defined as `!isCompact`, so it is true exactly for medium and expanded screen types.
- `[mobile/lib/responsive/screen_type.dart:FormFactor.width]` Width and height are always re-read from the current `MediaQuery.sizeOf(context)` rather than from cached or injected values.

## Side Effects

- None. The package only reads `MediaQuery`; it performs no I/O, no network calls, and no global state mutation.

## Verification

- Run: `flutter test` (from the `mobile/` directory)
