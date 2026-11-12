import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 연결 상태를 흉내내는 대역.
class _ConnectionAppState extends FakeAppState {
  _ConnectionAppState({this.connectionErrorMessage});

  String? connectionErrorMessage;
  bool connected = false;

  @override
  String? get connectionError => connectionErrorMessage;

  @override
  bool get isConnected => connected;

  /// 상태 변경을 알린다 (테스트에서 값을 바꾼 뒤 화면을 갱신할 때 사용)
  void refresh() => notifyListeners();
}

void main() {
  testWidgets('채널 화면에서 연결이 끊어졌으면 배너가 보인다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ConnectionAppState(connectionErrorMessage: '서버에 연결할 수 없습니다.');
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pump();

    expect(find.textContaining('실시간 연결이 끊어졌습니다'), findsOneWidget);
    expect(find.textContaining('서버에 연결할 수 없습니다'), findsOneWidget);
  });

  testWidgets('아직 연결된 적이 없고 오류도 없으면 배너가 보이지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ConnectionAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pump();

    expect(find.textContaining('실시간 연결이 끊어졌습니다'), findsNothing);
  });

  testWidgets('연결이 복구되면 배너가 사라진다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ConnectionAppState(connectionErrorMessage: '끊겼습니다');
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('실시간 연결이 끊어졌습니다'), findsOneWidget);

    // 연결 복구 → 배너가 사라진다
    state.connected = true;
    state.refresh();
    await tester.pump();
    expect(find.textContaining('실시간 연결이 끊어졌습니다'), findsNothing);
  });
}
