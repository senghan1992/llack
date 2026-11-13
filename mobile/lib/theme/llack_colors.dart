import 'package:flutter/material.dart';

/// Llack design tokens — Hallmark · theme: Dose · scope: mobile & tablet
/// Converted from `desktop/src/styles/tokens.css` and `DESIGN.md`.
///
/// 색은 **팔레트 두 벌(밝게/어둡게)** 로 모아 두고, 지금 쓰는 것은
/// [LlackColors.current] 이다. (화면 모드를 바꾸면 [LlackColors.usePalette] 로
///  갈아 끼운다. 화면 모드 설정은 `lib/services/device_settings.dart` 가 맡는다.)
class LlackPalette {
  const LlackPalette({
    required this.paper,
    required this.ink,
    required this.ink2,
    required this.muted,
    required this.rule,
    required this.ruleSoft,
    required this.accent,
    required this.accentLift,
    required this.accentDeep,
    required this.accentSoft,
    required this.accentInk,
    required this.bubbleMine,
    required this.bubbleMineInk,
    required this.bubbleMineDim,
    required this.surfaceFrame,
    required this.surfaceRail,
    required this.surfaceCanvas,
    required this.surfaceRaise,
    required this.surfaceWell,
    required this.surfaceSelected,
  });

  // ── Paper & Ink ──────────────────────────────────────────────
  /// Warm paper canvas
  final Color paper;
  /// Green-black ink
  final Color ink;
  /// Secondary ink
  final Color ink2;
  /// Muted text and iconography
  final Color muted;
  /// Divider rule
  final Color rule;
  /// Soft divider rule
  final Color ruleSoft;

  // ── The One Signal (ArcheAI Terracotta Orange) ───────────────
  /// Primary signal orange
  final Color accent;
  /// Lit top edge of primary key
  final Color accentLift;
  /// Shaded bottom edge of primary key
  final Color accentDeep;
  /// Soft orange wash for badges / tags
  final Color accentSoft;
  /// Text on accent
  final Color accentInk;

  // ── My Message Bubble ─────────────────────────────────────────
  /// The signal as a surface — your own message
  final Color bubbleMine;
  /// Text inside your message bubble
  final Color bubbleMineInk;
  /// Timestamp inside your message bubble
  final Color bubbleMineDim;

  // ── Surfaces Ladder ───────────────────────────────────────────
  /// Top-level app frame
  final Color surfaceFrame;
  /// Left sidebar rail
  final Color surfaceRail;
  /// Chat canvas / background
  final Color surfaceCanvas;
  /// Raised card / popover / dialog surface
  final Color surfaceRaise;
  /// Input well / recessed surface
  final Color surfaceWell;
  /// Selected item highlight
  final Color surfaceSelected;
}

/// 화면 모드에 따라 바뀌는 색. (지금 적용된 팔레트)
class LlackColors {
  LlackColors._();

  /// 밝은 팔레트. (종이 위의 따뜻한 흙빛)
  static const LlackPalette light = LlackPalette(
    paper: Color(0xFFFBF9F5),
    ink: Color(0xFF1E2B27),
    ink2: Color(0xFF364741),
    muted: Color(0xFF5C6F68),
    rule: Color(0xFFD9E2DE),
    ruleSoft: Color(0xFFE8EFEB),
    accent: Color(0xFFED6B40),
    accentLift: Color(0xFFF37D56),
    accentDeep: Color(0xFFD6582E),
    accentSoft: Color(0xFFFDEEE8),
    accentInk: Color(0xFFFFFFFF),
    bubbleMine: Color(0xFFED6B40),
    bubbleMineInk: Color(0xFFFFFFFF),
    bubbleMineDim: Color(0xCCFFFFFF),
    surfaceFrame: Color(0xFFEDE9E1),
    surfaceRail: Color(0xFFF3EFE7),
    surfaceCanvas: Color(0xFFFAF8F5),
    surfaceRaise: Color(0xFFFFFFFF),
    surfaceWell: Color(0xFFF2EFE9),
    surfaceSelected: Color(0xFFE2EFE9),
  );

  /// 어두운 팔레트. (같은 색을 "종이" 에서 "석판" 으로 옮긴 것)
  static const LlackPalette dark = LlackPalette(
    paper: Color(0xFF141A18),
    ink: Color(0xFFE6EDEA),
    ink2: Color(0xFFC3D0CB),
    muted: Color(0xFF8E9E98),
    rule: Color(0xFF26302C),
    ruleSoft: Color(0xFF1D2522),
    accent: Color(0xFFF0805A),
    accentLift: Color(0xFFF79070),
    accentDeep: Color(0xFFE06438),
    accentSoft: Color(0xFF3A231B),
    accentInk: Color(0xFF1A0F0C),
    bubbleMine: Color(0xFFC0562C),
    bubbleMineInk: Color(0xFFFDF6F3),
    bubbleMineDim: Color(0xCCFDF6F3),
    surfaceFrame: Color(0xFF0C100E),
    surfaceRail: Color(0xFF121816),
    surfaceCanvas: Color(0xFF161D1A),
    surfaceRaise: Color(0xFF1E2623),
    surfaceWell: Color(0xFF232B27),
    surfaceSelected: Color(0xFF2A3A34),
  );

  /// 지금 적용된 팔레트.
  static LlackPalette _current = light;

  static LlackPalette get current => _current;

  /// 화면 모드가 바뀌면 팔레트를 갈아 끼운다.
  /// (MaterialApp 을 다시 그리기 **직전**에 불러야 한다)
  static void usePalette(LlackPalette palette) {
    _current = palette;
  }

  // ── Paper & Ink ──────────────────────────────────────────────
  /// Warm paper canvas
  static Color get paper => _current.paper;
  /// Green-black ink
  static Color get ink => _current.ink;
  /// Secondary ink
  static Color get ink2 => _current.ink2;
  /// Muted text and iconography
  static Color get muted => _current.muted;
  /// Divider rule
  static Color get rule => _current.rule;
  /// Soft divider rule
  static Color get ruleSoft => _current.ruleSoft;

  // ── The One Signal (ArcheAI Terracotta Orange) ───────────────
  /// Primary signal orange
  static Color get accent => _current.accent;
  /// Lit top edge of primary key
  static Color get accentLift => _current.accentLift;
  /// Shaded bottom edge of primary key
  static Color get accentDeep => _current.accentDeep;
  /// Soft orange wash for badges / tags
  static Color get accentSoft => _current.accentSoft;
  /// Text on accent
  static Color get accentInk => _current.accentInk;

  // ── My Message Bubble ─────────────────────────────────────────
  /// The signal as a surface — your own message
  static Color get bubbleMine => _current.bubbleMine;
  /// Text inside your message bubble
  static Color get bubbleMineInk => _current.bubbleMineInk;
  /// Timestamp inside your message bubble
  static Color get bubbleMineDim => _current.bubbleMineDim;

  // ── Surfaces Ladder ───────────────────────────────────────────
  /// Top-level app frame
  static Color get surfaceFrame => _current.surfaceFrame;
  /// Left sidebar rail
  static Color get surfaceRail => _current.surfaceRail;
  /// Chat canvas / background
  static Color get surfaceCanvas => _current.surfaceCanvas;
  /// Raised card / popover / dialog surface
  static Color get surfaceRaise => _current.surfaceRaise;
  /// Input well / recessed surface
  static Color get surfaceWell => _current.surfaceWell;
  /// Selected item highlight
  static Color get surfaceSelected => _current.surfaceSelected;

  // ── Presence Colors ───────────────────────────────────────────
  // (프리전스는 어느 화면 모드에서도 같은 색이다 — 상태의 구분책)
  static const Color presenceOnline = Color(0xFF22C55E); // green
  static const Color presenceBusy = Color(0xFFEF4444);   // red
  static const Color presenceDnd = Color(0xFFE11D48);    // rose
  static const Color presenceAway = Color(0xFFF59E0B);   // amber
  static const Color presenceBrb = Color(0xFF8B5CF6);    // violet
  static const Color presenceOffline = Color(0xFF9CA3AF);// gray

  // ── Status Badges / Tasks ─────────────────────────────────────
  static const Color statusRequest = Color(0xFF6B7280);   // Gray
  static const Color statusTodo = Color(0xFF2563EB);      // Blue
  static const Color statusInProgress = Color(0xFFD97706);// Amber
  static const Color statusDone = Color(0xFF16A34A);      // Green

  // ── Avatars ───────────────────────────────────────────────────
  static const List<Color> avatarColors = [
    Color(0xFF1C785C), // Pharmacy Green
    Color(0xFF0284C7), // Sky Blue
    Color(0xFF7C3AED), // Violet
    Color(0xFFD97706), // Amber
    Color(0xFFDC2626), // Red
    Color(0xFF0D9488), // Teal
    Color(0xFFDB2777), // Pink
    Color(0xFF4B5563), // Slate
  ];

  /// 프로필에서 고를 수 있는 아바타 색.
  /// (데스크톱 `desktop/src/lib/color.ts` 의 AVATAR_PALETTE 와 같다)
  static const List<String> avatarPalette = [
    '#126b47', // Pharmacy Green
    '#8a4141', // Brick
    '#295e90', // Deep Blue
    '#814d0e', // Bronze
    '#644c8a', // Plum
    '#006b71', // Teal
    '#6a5a00', // Olive
  ];

  /// `#rrggbb` 문자열을 색으로 바꾼다. (형식이 다르면 null)
  static Color? colorFromHex(String? hex) {
    if (hex == null) return null;
    var value = hex.trim().replaceFirst('#', '');
    if (value.length == 3) {
      value = value.split('').map((c) => '$c$c').join();
    }
    if (value.length != 6) return null;
    final parsed = int.tryParse(value, radix: 16);
    if (parsed == null) return null;
    return Color(0xFF000000 | parsed);
  }

  static Color avatarColorForName(String name) {
    if (name.isEmpty) return avatarColors.first;
    int hash = 0;
    for (int i = 0; i < name.length; i++) {
      hash = name.codeUnitAt(i) + ((hash << 5) - hash);
    }
    final index = hash.abs() % avatarColors.length;
    return avatarColors[index];
  }
}
