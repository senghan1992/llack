import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/auth_screen.dart';
import 'package:provider/provider.dart';

/// 세션 만료 상태를 흉내내는 대역.
class _SessionExpiredAppState extends AppState {
  _SessionExpiredAppState({required this.expired, this.user});

  bool expired;
  final User? user;

  @override
  bool get isSessionExpired => expired;

  @override
  User? get currentUser => user;

  /// 로그인 성공처럼 상태를 바꾸고 화면을 갱신할 때 사용
  void refresh() => notifyListeners();
}

User _user(String email) => User(id: 'u1', email: email, name: '테스터');

void main() {
  testWidgets('세션이 만료되면 로그인 화면에 안내가 보인다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SessionExpiredAppState(expired: true, user: _user('hong@company.com'));
    addTearDown(state.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('세션이 만료되었습니다. 다시 로그인해주세요.'), findsOneWidget);
  });

  testWidgets('세션이 만료되지 않으면 안내가 보이지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SessionExpiredAppState(expired: false, user: null);
    addTearDown(state.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('세션이 만료되었습니다. 다시 로그인해주세요.'), findsNothing);
  });

  testWidgets('세션 만료로 튕기면 이메일이 자동으로 채워지고 비밀번호는 비어 있다', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SessionExpiredAppState(expired: true, user: _user('hong@company.com'));
    addTearDown(state.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pump();

    final emailField = tester.widget<TextFormField>(
      find.byWidgetPredicate(
        (w) => w is TextFormField && w.controller?.text == 'hong@company.com',
      ),
    );
    expect(emailField.controller?.text, 'hong@company.com');

    // 비밀번호는 자동으로 채우지 않는다
    // (빈 칸이 여러 개일 수 있으므로 "가려진 칸" 으로 찾는다)
    final passwordField = tester.widget<TextField>(
      find.byWidgetPredicate((w) => w is TextField && w.obscureText),
    );
    expect(passwordField.controller?.text, '');
  });

  testWidgets('사용자가 이메일을 지워도 다시 채워지지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SessionExpiredAppState(expired: true, user: _user('hong@company.com'));
    addTearDown(state.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pump();

    final emailField = find.byWidgetPredicate(
      (w) => w is TextFormField && w.controller?.text == 'hong@company.com',
    );
    expect(emailField, findsOneWidget);

    await tester.enterText(emailField, '');
    await tester.pump();
    state.refresh();
    await tester.pump();

    expect(
      find.byWidgetPredicate((w) => w is TextFormField && w.controller?.text == 'hong@company.com'),
      findsNothing,
    );
  });
}
