import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/settings/settings_sheet.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 프로필 저장이 실패하도록(updateMe 가 예외를 던지도록) 만든 대역.
class _ProfileAppState extends FakeAppState {
  _ProfileAppState({this.shouldFail = false});

  final bool shouldFail;

  int updateMeCalls = 0;

  @override
  User? get currentUser => User(
        id: 'u1',
        email: 'hyunjin@hanbit.co.kr',
        name: '김현진',
        title: '기획자',
      );

  @override
  Future<void> updateMe({
    String? name,
    String? title,
    String? avatarColor,
    Presence? presence,
  }) async {
    updateMeCalls++;
    // AppState.updateMe 는 실패하면 예외를 던진다 (정상 동작)
    if (shouldFail) throw Exception('서버 오류');
  }
}

Widget _wrap(AppState state) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: MaterialApp(home: Scaffold(body: SettingsSheet())),
  );
}

void main() {
  testWidgets('프로필 저장에 실패하면 사유를 알리고 대화상자를 닫지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ProfileAppState(shouldFail: true);
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    await tester.tap(find.byTooltip('프로필 수정'));
    await tester.pumpAndSettle();
    expect(find.text('프로필 수정'), findsOneWidget);

    await tester.tap(find.widgetWithText(ElevatedButton, '저장'));
    await tester.pumpAndSettle();

    expect(state.updateMeCalls, 1);
    // 실패 이유가 안내된다
    expect(find.textContaining('프로필을 저장하지 못했습니다'), findsOneWidget);
    // 입력한 값을 잃지 않도록 대화상자는 그대로 열린다
    expect(find.text('프로필 수정'), findsOneWidget);
  });

  testWidgets('프로필 저장에 성공하면 대화상자가 닫힌다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ProfileAppState();
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    await tester.tap(find.byTooltip('프로필 수정'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ElevatedButton, '저장'));
    await tester.pumpAndSettle();

    expect(state.updateMeCalls, 1);
    expect(find.text('프로필 수정'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('프로필 대화상자를 닫으면 입력 컨트롤러가 dispose 된다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ProfileAppState();
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    await tester.tap(find.byTooltip('프로필 수정'));
    await tester.pumpAndSettle();

    // 컨트롤러를 먼저 기억해 두고 (다이얼로그가 닫히면 참조가 사라진다)
    final nameField = tester.widget<TextField>(find.byType(TextField).first);
    final controller = nameField.controller!;

    // 다이얼로그 라우트를 제거한다 (사용자가 닫는 것과 동일하게 State.dispose 가 실행된다)
    Navigator.of(tester.element(find.byType(AlertDialog))).pop();
    await tester.pumpAndSettle();

    // dispose 된 컨트롤러를 다시 쓰면 예외가 난다 (ChangeNotifier 의 disposed 단언)
    expect(() => controller.addListener(() {}), throwsA(isA<FlutterError>()));
  });

  testWidgets('상태 변경에 실패하면 사유를 알린다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ProfileAppState(shouldFail: true);
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    // 칩을 누른다 (칩 자체를 찍어야 한다. 라벨 Text 는 칩의 ink 위에 있어 hit test 대상이 아닐 수 있다)
    await tester.tap(find.widgetWithText(ChoiceChip, '바쁨'));
    await tester.pumpAndSettle();

    expect(state.updateMeCalls, 1);
    expect(find.text('상태를 바꾸지 못했습니다'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
