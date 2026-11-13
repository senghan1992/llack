import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/task_detail_sheet.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 의견(댓글) 삭제 대역.
class _CommentAppState extends FakeAppState {
  _CommentAppState(this.task);

  final Task task;

  @override
  List<Task> get activeProjectTasks => [task];

  @override
  User? get currentUser => User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진');

  String? deletedCommentId;
  String? deletedTaskId;
  bool deleteFails = false;

  @override
  Future<bool> deleteTaskComment(String taskId, String commentId) async {
    if (deleteFails) return false;
    deletedTaskId = taskId;
    deletedCommentId = commentId;
    return true;
  }
}

TaskComment _comment(String id, String userId, String authorName, String body) => TaskComment(
  id: id,
  taskId: 't1',
  userId: userId,
  author: User(id: userId, email: '$userId@hanbit.co.kr', name: authorName),
  body: body,
  createdAt: DateTime(2026, 3, 1, 10, 30),
);

Task _task() => Task(
  id: 't1',
  projectId: 'p1',
  title: '로그인 고치기',
  status: TaskStatus.todo,
  createdBy: 'u1',
  createdAt: DateTime(2026, 1, 1),
  updatedAt: DateTime(2026, 1, 1),
  comments: [
    _comment('c1', 'u1', '김현진', '제가 볼까요'),
    _comment('c2', 'u2', '이채원', '네 부탁해요'),
  ],
);

/// 할 일 상세 시트를 연다. (앱에서 하는 것처럼 showModalBottomSheet 로)
Future<void> _openSheet(WidgetTester tester, AppState state, Task task) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showModalBottomSheet<void>(
                  context: ctx,
                  isScrollControlled: true,
                  backgroundColor: Colors.transparent,
                  builder: (_) => TaskDetailSheet(task: task),
                ),
                child: const Text('열기'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('열기'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    // 폰 크기 화면에서 검사한다.
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(411 * 3, 914 * 3);
    view.devicePixelRatio = 3.0;
    addTearDown(view.reset);
  });

  testWidgets('내 의견에만 지우는 버튼이 보인다', (tester) async {
    final state = _CommentAppState(_task());

    await _openSheet(tester, state, _task());

    expect(find.text('의견 (2)'), findsOneWidget);
    // 두 개의 의견 중 내 의견에만 지우는 버튼이 있다.
    expect(find.byTooltip('의견 삭제'), findsOneWidget);
  });

  testWidgets('내 의견을 지우면 deleteTaskComment 로 넘어간다', (tester) async {
    final task = _task();
    final state = _CommentAppState(task);

    await _openSheet(tester, state, task);

    await tester.tap(find.byTooltip('의견 삭제'));
    await tester.pumpAndSettle();

    expect(state.deletedTaskId, 't1');
    expect(state.deletedCommentId, 'c1');
  });

  testWidgets('지우지 못하면 사유를 알려준다', (tester) async {
    final task = _task();
    final state = _CommentAppState(task)..deleteFails = true;

    await _openSheet(tester, state, task);

    await tester.tap(find.byTooltip('의견 삭제'));
    await tester.pumpAndSettle();

    expect(state.deletedCommentId, isNull);
    expect(find.text('의견을 삭제하지 못했습니다'), findsOneWidget);
  });
}
