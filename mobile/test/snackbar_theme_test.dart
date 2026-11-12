import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/theme/llack_theme.dart';

void main() {
  group('SnackBar 테마', () {
    test('behavior 는 floating 이다 (composer 를 가리지 않아야 한다)', () {
      final theme = LlackTheme.light();
      expect(theme.snackBarTheme.behavior, SnackBarBehavior.floating);
    });

    test('floating 여백이 앱 공통 여백(16)으로 지정되어 있다', () {
      final inset = LlackTheme.light().snackBarTheme.insetPadding;
      expect(inset, isNotNull);
      expect(inset!.resolve(TextDirection.ltr).left, 16);
      expect(inset.resolve(TextDirection.ltr).right, 16);
    });

    test('기존 색/모서리/테두리는 그대로 유지된다', () {
      final bar = LlackTheme.light().snackBarTheme;
      expect(bar.backgroundColor, isNotNull);
      expect(bar.actionTextColor, isNotNull);
      expect(bar.shape, isNotNull);
    });

    test('주석에 실제와 반대인 설명(밀어올려 등)이 남아 있지 않다', () {
      final source = File('lib/theme/llack_theme.dart').readAsStringSync();
      expect(source, isNot(contains('밀어올려')));
      expect(source, isNot(contains('SnackBarBehavior.fixed')));
      // 왜 floating 인지 근거는 주석으로 남아 있어야 한다
      expect(source, contains('floating'));
    });
  });
}
