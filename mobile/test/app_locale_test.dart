import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/main.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:provider/provider.dart';

/// 앱이 인증되지 않은 상태를 흉내내는 대역 (로그인 화면까지만 렌더되면 충분하다)
class _AuthAppState extends AppState {
  @override
  bool get isAuthenticated => false;

  @override
  bool get isBooting => false;

  @override
  User? get currentUser => null;
}

void main() {
  testWidgets('앱 루트의 로케일은 ko-KR 로 고정된다', (WidgetTester tester) async {
    final state = _AuthAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const LlackMobileApp(),
      ),
    );
    await tester.pump();

    // MaterialApp 이 쓰는 로케일이 한국어로 고정되었는지 확인한다
    final context = tester.element(find.byType(Scaffold).first);
    expect(Localizations.localeOf(context), const Locale('ko', 'KR'));
  });

  testWidgets('시간 선택기가 한국어 + 24시간제로 나온다', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('ko', 'KR'),
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('ko', 'KR'), Locale('en', 'US')],
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => showTimePicker(context: context, initialTime: TimeOfDay(hour: 10, minute: 0)),
              child: const Text('시간 선택'),
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('시간 선택'));
    await tester.pumpAndSettle();

    // 제목/버튼이 한국어여야 한다 (제목은 “시간 선택”, 버튼은 취소/확인)
    expect(find.text('시간 선택'), findsNWidgets(2));
    expect(find.text('취소'), findsOneWidget);
    expect(find.text('확인'), findsOneWidget);
    // 영어 표기(제목/버튼)와 12시간제(AM/PM)는 없어야 한다
    expect(find.text('Select time'), findsNothing);
    expect(find.text('Cancel'), findsNothing);
    expect(find.text('OK'), findsNothing);
    expect(find.textContaining('AM'), findsNothing);
    expect(find.text('10'), findsOneWidget);
  });
}
