import 'package:flutter/material.dart';
import 'llack_colors.dart';

class LlackTypography {
  LlackTypography._();

  static const List<String> fontFallbacks = [
    'Pretendard',
    'Apple SD Gothic Neo',
    'Noto Sans KR',
    'Roboto',
    'sans-serif',
  ];

  static const List<String> monoFallbacks = [
    'DM Mono',
    'Menlo',
    'Consolas',
    'monospace',
  ];

  // Headings
  static const TextStyle display = TextStyle(
    fontSize: 26,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.5,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  static const TextStyle title = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.3,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  static const TextStyle subtitle = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.2,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  // Body
  static const TextStyle body = TextStyle(
    fontSize: 14.5,
    fontWeight: FontWeight.w400,
    height: 1.45,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  static const TextStyle bodySmall = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.4,
    color: LlackColors.ink2,
    fontFamilyFallback: fontFallbacks,
  );

  static const TextStyle caption = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    color: LlackColors.muted,
    fontFamilyFallback: fontFallbacks,
  );

  // Dose pharmacy label: monospace timestamp
  static const TextStyle monoTimestamp = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.2,
    color: LlackColors.muted,
    fontFamilyFallback: monoFallbacks,
  );

  static const TextStyle monoTimestampOnMine = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.2,
    color: LlackColors.bubbleMineDim,
    fontFamilyFallback: monoFallbacks,
  );

  // Author name in message header
  static const TextStyle authorName = TextStyle(
    fontSize: 13.5,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  // 작은 제목 / 버튼 라벨용 (Material 위젯이 TextTheme 역할을 참조하도록 채워둔다)
  static const TextStyle titleSmall = TextStyle(
    fontSize: 13.5,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.2,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  static const TextStyle labelLarge = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: LlackColors.ink,
    fontFamilyFallback: fontFallbacks,
  );

  /// 앱 전역 TextTheme.
  /// 화면에서 fontSize 를 직접 박지 않고 역할(role)로 크기를 참조하게 하면
  /// 시스템 글자 크기 설정이 반영될 때 함께 커지고, 최소 크기도 12 로 보장된다.
  static const TextTheme textTheme = TextTheme(
    displayLarge: display,
    titleLarge: title,
    titleMedium: subtitle,
    titleSmall: titleSmall,
    bodyLarge: body,
    bodyMedium: body,
    bodySmall: bodySmall,
    labelLarge: labelLarge,
    labelMedium: bodySmall,
    labelSmall: caption,
  );
}
