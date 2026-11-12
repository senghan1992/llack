import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'llack_colors.dart';
import 'llack_typography.dart';

class LlackTheme {
  LlackTheme._();

  static const double radiusInput = 10.0;
  static const double radiusCard = 14.0;
  static const double radiusPanel = 16.0;
  static const double radiusPill = 999.0;

  static const List<BoxShadow> shadowE1 = [
    BoxShadow(
      color: Color(0x0C000000),
      offset: Offset(0, 1),
      blurRadius: 3,
    ),
    BoxShadow(
      color: Color(0x08000000),
      offset: Offset(0, 1),
      blurRadius: 2,
    ),
  ];

  static const List<BoxShadow> shadowE2 = [
    BoxShadow(
      color: Color(0x10000000),
      offset: Offset(0, 4),
      blurRadius: 12,
    ),
    BoxShadow(
      color: Color(0x0A000000),
      offset: Offset(0, 2),
      blurRadius: 4,
    ),
  ];

  static ThemeData light() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      primaryColor: LlackColors.accent,
      scaffoldBackgroundColor: LlackColors.paper,
      colorScheme: const ColorScheme.light(
        primary: LlackColors.accent,
        onPrimary: LlackColors.accentInk,
        primaryContainer: LlackColors.accentSoft,
        onPrimaryContainer: LlackColors.accentDeep,
        surface: LlackColors.surfaceRaise,
        onSurface: LlackColors.ink,
        surfaceContainerHighest: LlackColors.surfaceWell,
        outline: LlackColors.rule,
        outlineVariant: LlackColors.ruleSoft,
      ),
      textTheme: LlackTypography.textTheme,
      appBarTheme: const AppBarTheme(
        backgroundColor: LlackColors.paper,
        foregroundColor: LlackColors.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: LlackTypography.title,
        systemOverlayStyle: SystemUiOverlayStyle.dark,
        iconTheme: IconThemeData(color: LlackColors.ink),
      ),
      dividerTheme: const DividerThemeData(
        color: LlackColors.rule,
        thickness: 1,
        space: 1,
      ),
      // SnackBar 는 기본 검은 배경이라 종이 톤 화면과 어울리지 않는다.
      // 라이트한 표면 + 어두운 글씨로 읽기 좋은 대비를 유지한다.
      snackBarTheme: SnackBarThemeData(
        backgroundColor: LlackColors.surfaceRaise,
        contentTextStyle: LlackTypography.bodySmall.copyWith(color: LlackColors.ink),
        actionTextColor: LlackColors.accentDeep,
        disabledActionTextColor: LlackColors.muted,
        // floating 으로 두는 이유:
        // - fixed 는 본문을 밀어올리지 않고 그 위에 "덮어" 그리므로
        //   메시지 입력창(composer)을 가린다.
        // - floating 은 메시지 영역 안에 떠서 올라오기 때문에 composer 를 가리지 않는다.
        //   (채팅 화면은 중첩 ScaffoldMessenger 안에서 띄우므로 스낵바가 그 안에 그려진다)
        behavior: SnackBarBehavior.floating,
        // floating 은 화면 가장자리에 붙지 않고 여백을 두고 떠야 하므로 inset 을 지정한다.
        // (가로 16 = 앱 공통 여백, 아래 16 = 하단 네비/입력창과의 간격)
        insetPadding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusInput),
          side: const BorderSide(color: LlackColors.rule, width: 1),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: LlackColors.surfaceWell,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        hintStyle: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusInput),
          borderSide: const BorderSide(color: LlackColors.rule, width: 1),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusInput),
          borderSide: const BorderSide(color: LlackColors.rule, width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusInput),
          borderSide: const BorderSide(color: LlackColors.accent, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusInput),
          borderSide: const BorderSide(color: LlackColors.presenceBusy, width: 1),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: LlackColors.accent,
          foregroundColor: LlackColors.accentInk,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusInput),
          ),
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: LlackColors.ink,
          side: const BorderSide(color: LlackColors.rule, width: 1),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusInput),
          ),
          textStyle: const TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: LlackColors.accent,
          textStyle: const TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      cardTheme: CardThemeData(
        color: LlackColors.surfaceRaise,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusCard),
          side: const BorderSide(color: LlackColors.rule, width: 1),
        ),
        margin: EdgeInsets.zero,
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: LlackColors.surfaceRail,
        selectedItemColor: LlackColors.accent,
        unselectedItemColor: LlackColors.muted,
        type: BottomNavigationBarType.fixed,
        elevation: 4,
        // 최소 크기 12 유지 (접근성) — 시스템 글자 크기도 함께 반영된다.
        selectedLabelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        unselectedLabelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
      ),
    );
  }
}
