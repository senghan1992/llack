import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/settings/server_settings_dialog.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

void main() {
  testWidgets('서버 주소 오류 문구가 잘리지 않고, 고치면 사라진다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = FakeAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => showServerSettingsDialog(context),
                child: const Text('서버 주소 설정 열기'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('서버 주소 설정 열기'));
    await tester.pumpAndSettle();

    // 스킴이 없는 주소 → 검증 오류
    await tester.enterText(find.byType(TextField), '192.168.0.10:8000');
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();

    const message = 'http:// 또는 https:// 로 시작하는 주소를 입력하세요.';
    expect(find.text(message), findsOneWidget);

    // 1줄 말줄임으로 잘리지 않아야 한다 (기본값 1 → 3줄로 지정)
    final errorText = tester.widget<Text>(find.text(message));
    expect(errorText.maxLines, 3);

    // 주소를 고치는 순간 오류 문구와 테두리가 사라져야 한다
    await tester.enterText(find.byType(TextField), 'http://192.168.0.10:8000');
    await tester.pumpAndSettle();
    expect(find.text(message), findsNothing);
  });
}
