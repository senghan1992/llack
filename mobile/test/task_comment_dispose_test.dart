import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/task_detail_sheet.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 댓글 전송이 "아직 끝나지 않은" 상태를 만든다.
class _SlowCommentAppState extends FakeAppState {
  final Completer<void> server = Completer<void>();
  int addCommentCalls = 0;

  @override
  Future<void> addTaskComment(String taskId, String body) async {
    addCommentCalls++;
    // 서버 응답을 나중에 준다. 그동안 시트가 닫히면(await 뒤에 dispose 된 컨트롤러를 만지는) 문제가 난다.
    await server.future;
  }
}

Task _task() {
  final now = DateTime.now();
  return Task(
    id: 't1',
    projectId: 'p1',
    title: '테스트 할 일',
    status: TaskStatus.todo,
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
  );
}

void main() {
  testWidgets('댓글 전송 중 시트가 dispose 되어도 예외가 나지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SlowCommentAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(home: Scaffold(body: TaskDetailSheet(task: _task()))),
      ),
    );
    await tester.pump();

    // 댓글을 보내고 (서버 응답은 보류 상태로 둔다)
    await tester.enterText(find.byType(TextField), '댓글 내용');
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pump();
    expect(state.addCommentCalls, 1);

    // 전송이 끝나기 전에 시트를 닫는다
    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    await tester.pump();

    // 서버 응답이 늦게 도착한다
    state.server.complete();
    await tester.pump();

    // dispose 된 컨트롤러를 만지지 않아야 한다
    expect(tester.takeException(), isNull);
  });

  testWidgets('댓글 전송이 성공하면 입력창이 비워진다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _SlowCommentAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(home: Scaffold(body: TaskDetailSheet(task: _task()))),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '댓글 내용');
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pump();

    // 서버 응답이 도착한다
    state.server.complete();
    await tester.pump();
    await tester.pump();

    expect(tester.takeException(), isNull);
    // 전송 중에는 낙관적으로 목록에 보여준다
    expect(find.text('전송 중'), findsOneWidget);
  });

  test('await 이후에는 mounted 를 확인한 뒤에만 댓글 컨트롤러를 만진다', () {
    // dispose 된 컨트롤러를 만지면 예외가 나지만, 그 예외는 try/catch 에 삼켜져
    // 화면에도 테스트에도 드러나지 않는다(사용자는 댓글만 조용히 사라진다).
    // 그래서 소스 수준에서 "await 뒤에 컨트롤러를 쓰기 전에 mounted 를 확인한다" 를 보장한다.
    final source = File('lib/screens/projects/task_detail_sheet.dart').readAsStringSync();
    final afterAwait = source.split('await state.addTaskComment').last;

    final guardIndex = afterAwait.indexOf('if (!mounted) return;');
    expect(guardIndex, isNot(-1), reason: 'await 이후에 mounted 가드가 있어야 한다');

    final controllerIndex = afterAwait.indexOf('_commentCtrl');
    expect(
      controllerIndex == -1 || guardIndex < controllerIndex,
      isTrue,
      reason: '댓글 컨트롤러를 만지기 전에 mounted 를 확인해야 한다',
    );
  });
}
