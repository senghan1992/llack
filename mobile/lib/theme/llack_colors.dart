import 'package:flutter/material.dart';

/// Llack design tokens — Hallmark · theme: Dose · scope: mobile & tablet
/// Converted from `desktop/src/styles/tokens.css` and `DESIGN.md`.
class LlackColors {
  LlackColors._();

  // ── Paper & Ink ──────────────────────────────────────────────
  /// Warm paper canvas
  static const Color paper = Color(0xFFFBF9F5);
  /// Green-black ink
  static const Color ink = Color(0xFF1E2B27);
  /// Secondary ink
  static const Color ink2 = Color(0xFF364741);
  /// Muted text and iconography
  static const Color muted = Color(0xFF5C6F68);
  /// Divider rule
  static const Color rule = Color(0xFFD9E2DE);
  /// Soft divider rule
  static const Color ruleSoft = Color(0xFFE8EFEB);

  // ── The One Signal (ArcheAI Terracotta Orange) ───────────────
  /// Primary signal orange
  static const Color accent = Color(0xFFED6B40);
  /// Lit top edge of primary key
  static const Color accentLift = Color(0xFFF37D56);
  /// Shaded bottom edge of primary key
  static const Color accentDeep = Color(0xFFD6582E);
  /// Soft orange wash for badges / tags
  static const Color accentSoft = Color(0xFFFDEEE8);
  /// Text on accent
  static const Color accentInk = Color(0xFFFFFFFF);

  // ── My Message Bubble ─────────────────────────────────────────
  /// The signal as a surface — your own message
  static const Color bubbleMine = Color(0xFFED6B40);
  /// Text inside your message bubble
  static const Color bubbleMineInk = Color(0xFFFFFFFF);
  /// Timestamp inside your message bubble
  static const Color bubbleMineDim = Color(0xCCFFFFFF);

  // ── Surfaces Ladder ───────────────────────────────────────────
  /// Top-level app frame
  static const Color surfaceFrame = Color(0xFFEDE9E1);
  /// Left sidebar rail
  static const Color surfaceRail = Color(0xFFF3EFE7);
  /// Chat canvas / background
  static const Color surfaceCanvas = Color(0xFFFAF8F5);
  /// Raised card / popover / dialog surface
  static const Color surfaceRaise = Color(0xFFFFFFFF);
  /// Input well / recessed surface
  static const Color surfaceWell = Color(0xFFF2EFE9);
  /// Selected item highlight
  static const Color surfaceSelected = Color(0xFFE2EFE9);

  // ── Presence Colors ───────────────────────────────────────────
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
