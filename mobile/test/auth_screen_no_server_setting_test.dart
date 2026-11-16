import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/auth_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

void main() {
  testWidgets('로그인 화면에는 서버 주소 설정이 없다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: FakeAppState(),
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pumpAndSettle();

    // 서버 주소는 빌드 때 정해집니다 — 화면에서 바꿀 수 없습니다.
    expect(find.textContaining('서버 주소'), findsNothing);
    expect(find.byTooltip('서버 주소 설정'), findsNothing);
    expect(find.byIcon(Icons.dns_outlined), findsNothing);
  });
}
