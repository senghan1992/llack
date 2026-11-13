import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/main.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:provider/provider.dart';

/// 부팅이 끝난 상태를 흉내내는 대역 (로그인 화면까지 넘어가는지 확인용)
class _BootedAppState extends AppState {
  @override
  bool get isBooting => false;

  @override
  bool get isAuthenticated => false;

  @override
  User? get currentUser => null;
}

void main() {
  testWidgets('부팅 중에는 "Llack 연결 중..." 이 보인다', (WidgetTester tester) async {
    // AppState 의 _isBooting 초기값이 true 이다 (아직 boot() 을 부르지 않은 상태)
    final state = AppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const LlackMobileApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Atrium 연결 중...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('부팅이 끝나면 로그인 화면으로 넘어간다', (WidgetTester tester) async {
    final state = _BootedAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const LlackMobileApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Atrium 연결 중...'), findsNothing);
    expect(find.text('Atrium에 로그인'), findsOneWidget);
  });
}
