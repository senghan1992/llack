import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/widgets/app_snack_bar.dart';

/// 루트 오버레이에 직접 얹힌 스낵바가 어떤 Scaffold 안에도 없는지 확인한다.
/// (ScaffoldMessenger 방식이면 Scaffold 안에 있으므로 이 단언이 실패한다)
bool _isInsideScaffold(WidgetTester tester, Finder finder) {
  final element = tester.element(finder);
  var inside = false;
  element.visitAncestorElements((ancestor) {
    if (ancestor.widget is Scaffold) inside = true;
    return true;
  });
  return inside;
}

/// 모달(다이얼로그) 안에서 스낵바를 띄우는 화면.
Widget _appWithDialog({
  required void Function(BuildContext) onShowFromDialog,
  void Function(BuildContext)? onShowFromScreen,
}) {
  return MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (screenContext) => Column(
          children: [
            if (onShowFromScreen != null)
              TextButton(
                onPressed: () => onShowFromScreen(screenContext),
                child: const Text('화면에서 띄우기'),
              ),
            TextButton(
              onPressed: () => showDialog<void>(
                context: screenContext,
                builder: (ctx) => AlertDialog(
                  content: Builder(
                    builder: (dialogContext) => TextButton(
                      onPressed: () => onShowFromDialog(dialogContext),
                      child: const Text('모달에서 띄우기'),
                    ),
                  ),
                ),
              ),
              child: const Text('다이얼로그 열기'),
            ),
          ],
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('모달 안에서 불린 스낵바는 루트 오버레이에 직접 얹힌다', (WidgetTester tester) async {
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(context, '모달 안에서도 보인다'),
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);

    // 모달 안에서 스낵바를 띄운다
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();

    // 기존 ScaffoldMessenger 방식의 스낵바는 없어야 한다 (1)
    expect(find.byType(SnackBar), findsNothing);
    // 커스텀 스낵바는 1건 보여야 한다 (2)
    expect(find.byType(AppSnackBar), findsOneWidget);
    expect(find.text('모달 안에서도 보인다'), findsOneWidget);
    // 어떤 Scaffold 안에도 들어있지 않아야 한다 (루트 오버레이에 직접 얹혔다는 뜻) (3)
    expect(_isInsideScaffold(tester, find.byType(AppSnackBar)), isFalse);
  });

  testWidgets('일반 화면에서 불린 스낵바는 기존 ScaffoldMessenger 경로를 쓴다', (WidgetTester tester) async {
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(context, '모달'),
        onShowFromScreen: (context) => showAppSnackBar(context, '화면에서도 보인다'),
      ),
    );

    await tester.tap(find.text('화면에서 띄우기'));
    await tester.pump();

    // 일반 화면 → 기존 경로: SnackBar 가 1건, 커스텀 스낵바는 없음
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.text('화면에서도 보인다'), findsOneWidget);
    expect(find.byType(AppSnackBar), findsNothing);
  });

  testWidgets('새 메시지가 오면 이전 것을 교체한다', (WidgetTester tester) async {
    var count = 0;
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) {
          count++;
          showAppSnackBar(context, count == 1 ? '첫 번째' : '두 번째');
        },
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();
    expect(find.byType(AppSnackBar), findsOneWidget);
    expect(find.text('첫 번째'), findsOneWidget);

    // 두 번째 메시지를 띄우면 이전 것이 교체된다
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();
    expect(find.byType(AppSnackBar), findsOneWidget);
    expect(find.text('첫 번째'), findsNothing);
    expect(find.text('두 번째'), findsOneWidget);
  });

  testWidgets('시간이 지나면 자동으로 사라진다', (WidgetTester tester) async {
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(
          context,
          '사라지는 스낵바',
          duration: const Duration(seconds: 2),
        ),
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();
    expect(find.byType(AppSnackBar), findsOneWidget);

    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.byType(AppSnackBar), findsNothing);
  });

  testWidgets('탭하면 즉시 닫힌다', (WidgetTester tester) async {
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(
          context,
          '탭하면 닫힘',
          duration: const Duration(seconds: 30),
        ),
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();
    expect(find.byType(AppSnackBar), findsOneWidget);

    await tester.tap(find.text('탭하면 닫힘'));
    await tester.pumpAndSettle();
    expect(find.byType(AppSnackBar), findsNothing);
  });

  testWidgets('액션을 주면 오른쪽에 보이고, 탭하면 콜백이 불린다', (WidgetTester tester) async {
    var actionCalls = 0;
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(
          context,
          '메시지를 삭제했습니다',
          actionLabel: '실행 취소',
          onAction: () => actionCalls++,
        ),
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();

    expect(find.text('실행 취소'), findsOneWidget);
    await tester.tap(find.text('실행 취소'));
    await tester.pumpAndSettle();

    expect(actionCalls, 1);
    expect(find.byType(AppSnackBar), findsNothing);
  });

  testWidgets('액션을 주지 않으면 액션이 보이지 않는다', (WidgetTester tester) async {
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(context, '저장하지 못했습니다'),
      ),
    );

    await tester.tap(find.text('다이얼로그 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('모달에서 띄우기'));
    await tester.pump();

    expect(find.text('저장하지 못했습니다'), findsOneWidget);
    expect(find.text('실행 취소'), findsNothing);
  });

  testWidgets('일반 화면 경로에서도 액션이 동작한다', (WidgetTester tester) async {
    var actionCalls = 0;
    await tester.pumpWidget(
      _appWithDialog(
        onShowFromDialog: (context) => showAppSnackBar(context, '모달'),
        onShowFromScreen: (context) => showAppSnackBar(
          context,
          '메시지를 삭제했습니다',
          actionLabel: '실행 취소',
          onAction: () => actionCalls++,
        ),
      ),
    );

    await tester.tap(find.text('화면에서 띄우기'));
    await tester.pumpAndSettle();

    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.text('실행 취소'), findsOneWidget);
    await tester.tap(find.text('실행 취소'));
    await tester.pumpAndSettle();

    expect(actionCalls, 1);
  });
}
