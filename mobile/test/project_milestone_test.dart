import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/milestone_sheet.dart';
import 'package:llack_mobile/screens/projects/task_dialog.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 마일스톤 관리 대역.
class _MilestoneAppState extends FakeAppState {
  _MilestoneAppState({this.milestones = const [], this.tasks = const []});

  final List<Milestone> milestones;
  final List<Task> tasks;

  @override
  List<Milestone> get activeMilestones => milestones;

  @override
  List<Task> get activeProjectTasks => tasks;

  int createCount = 0;
  String? createdTitle;
  List<String>? createdTaskIds;

  String? deletedMilestoneId;

  @override
  Future<Milestone> createMilestone({
    required String title,
    required DateTime startAt,
    required DateTime endAt,
    String description = '',
    String color = '#4f6cff',
    int progress = 0,
    List<String>? taskIds,
  }) async {
    createCount++;
    createdTitle = title;
    createdTaskIds = taskIds;
    return Milestone(
      id: 'm-new',
      projectId: 'p1',
      title: title,
      startAt: startAt,
      endAt: endAt,
      color: color,
    );
  }

  @override
  Future<bool> deleteMilestone(String milestoneId) async {
    deletedMilestoneId = milestoneId;
    return true;
  }
}

/// 할 일 대화상자 대역. (마일스톤 지정이 그대로 전달되는지 본다)
class _TaskDialogAppState extends FakeAppState {
  @override
  List<Milestone> get activeMilestones => [
        Milestone(
          id: 'm1',
          projectId: 'p1',
          title: '첫 배포',
          startAt: DateTime(2026, 3, 1),
          endAt: DateTime(2026, 3, 31),
          color: '#4f6cff',
        ),
      ];

  String? lastMilestoneId;
  int updateCount = 0;

  @override
  Future<bool> updateTask({
    required String taskId,
    String? title,
    String? description,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
    int? position,
  }) async {
    updateCount++;
    lastMilestoneId = milestoneId;
    return true;
  }
}

Milestone _milestone(String id, String title) => Milestone(
  id: id,
  projectId: 'p1',
  title: title,
  startAt: DateTime(2026, 3, 1),
  endAt: DateTime(2026, 3, 31),
  color: '#4f6cff',
  taskCount: 2,
  doneCount: 1,
);

Task _task(String id, String title) {
  final now = DateTime(2026, 1, 1);
  return Task(
    id: id,
    projectId: 'p1',
    title: title,
    status: TaskStatus.todo,
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
  );
}

/// 마일스톤 대화상자를 연다. (앱에서 하는 것처럼 showDialog 로)
Future<void> _openDialog(WidgetTester tester, AppState state, {Milestone? milestone}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showMilestoneDialog(ctx, milestone: milestone),
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

/// 마일스톤 패널을 그린다.
Future<void> _openPanel(WidgetTester tester, AppState state) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: const MaterialApp(home: Scaffold(body: MilestonePanel())),
    ),
  );
  await tester.pumpAndSettle();
}

/// 날짜 선택기에서 고른 날을 확정한다.
///
/// (날짜를 고른 뒤 "확인" 을 눌러야 선택이 끝난다)
Future<void> _pickDay(WidgetTester tester, String day) async {
  await tester.tap(find.text(day));
  await tester.pumpAndSettle();
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    // 폰 크기 화면에서 검사한다. (대화상자가 여유 있게 펼쳐진다)
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(411 * 3, 914 * 3);
    view.devicePixelRatio = 3.0;
    addTearDown(view.reset);
  });

  testWidgets('마일스톤을 만들면 제목과 연결한 할 일이 그대로 전달된다', (tester) async {
    final state = _MilestoneAppState(tasks: [_task('t1', '로그인 고치기')]);

    await _openDialog(tester, state);

    await tester.enterText(find.widgetWithText(TextField, '마일스톤 제목'), '첫 배포');
    // 할 일을 마일스톤에 연결한다.
    await tester.scrollUntilVisible(
      find.text('로그인 고치기'),
      120,
      scrollable: find
          .descendant(of: find.byType(MilestoneDialog), matching: find.byType(Scrollable))
          .first,
    );
    await tester.tap(find.text('로그인 고치기'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('추가'));
    await tester.pumpAndSettle();

    expect(state.createCount, 1);
    expect(state.createdTitle, '첫 배포');
    expect(state.createdTaskIds, ['t1']);
  });

  testWidgets('제목이 비면 저장하지 않고 사유를 알려준다', (tester) async {
    final state = _MilestoneAppState();

    await _openDialog(tester, state);

    await tester.tap(find.text('추가'));
    await tester.pumpAndSettle();

    expect(state.createCount, 0);
    expect(find.text('마일스톤 제목을 입력해 주세요'), findsOneWidget);
  });

  testWidgets('종료일이 시작일보다 빠르면 저장하지 않고 사유를 알려준다', (tester) async {
    final state = _MilestoneAppState();

    await _openDialog(tester, state);

    await tester.enterText(find.widgetWithText(TextField, '마일스톤 제목'), '첫 배포');

    final now = DateTime.now();
    // 시작일: 이번 달 20일
    await tester.tap(find.textContaining('시작일'));
    await tester.pumpAndSettle();
    await _pickDay(tester, '20');

    // 종료일: 이번 달 10일 (시작일보다 빠르다)
    // 날짜 선택기는 종료일의 현재 값을 showing 하므로, 이번 달로 되돌아간다.
    final endAfterStart = now.add(const Duration(days: 14));
    final start = DateTime(now.year, now.month, 20);
    final end = endAfterStart.isBefore(start) ? start : endAfterStart;
    final monthsBack = (now.year * 12 + now.month) - (end.year * 12 + end.month);
    for (var i = 0; i < monthsBack; i++) {
      await tester.tap(find.byIcon(Icons.chevron_left));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.textContaining('종료일'));
    await tester.pumpAndSettle();
    await _pickDay(tester, '10');

    await tester.tap(find.text('추가'));
    await tester.pumpAndSettle();

    expect(state.createCount, 0);
    expect(find.text('종료일은 시작일보다 빠를 수 없습니다'), findsOneWidget);
  });

  testWidgets('마일스톤을 지우면 확인을 거친 뒤에 지워진다', (tester) async {
    final state = _MilestoneAppState(milestones: [_milestone('m1', '첫 배포')]);

    await _openPanel(tester, state);

    expect(find.text('첫 배포'), findsOneWidget);

    await tester.tap(find.byTooltip('마일스톤 삭제'));
    await tester.pumpAndSettle();

    // 확인 대화상자가 먼저 나온다.
    expect(find.text('마일스톤 삭제'), findsOneWidget);
    expect(state.deletedMilestoneId, isNull);

    await tester.tap(find.text('삭제'));
    await tester.pumpAndSettle();

    expect(state.deletedMilestoneId, 'm1');
  });

  testWidgets('취소를 고르면 마일스톤은 그대로 남는다', (tester) async {
    final state = _MilestoneAppState(milestones: [_milestone('m1', '첫 배포')]);

    await _openPanel(tester, state);

    await tester.tap(find.byTooltip('마일스톤 삭제'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();

    expect(state.deletedMilestoneId, isNull);
  });

  testWidgets('할 일에 마일스톤을 지정하면 그대로 전달된다', (tester) async {    final state = _TaskDialogAppState();
    final task = Task(
      id: 't1',
      projectId: 'p1',
      title: '로그인 고치기',
      status: TaskStatus.todo,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(home: Scaffold(body: TaskDialog(editing: task))),
      ),
    );
    await tester.pumpAndSettle();

    // 마일스톤 고르기 칸이 있다.
    expect(find.text('마일스톤'), findsOneWidget);

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('첫 배포 (2026.03.01)').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('수정'));
    await tester.pumpAndSettle();

    expect(state.updateCount, 1);
    expect(state.lastMilestoneId, 'm1');
  });

  testWidgets('타임라인은 마일스톤 기간을 막대로 보여준다', (tester) async {
    final state = _MilestoneAppState(milestones: [
      _milestone('m1', '첫 배포'),
      _milestone('m2', '두 번째 배포'),
    ]);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: TimelinePanel())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('첫 배포'), findsOneWidget);
    expect(find.text('두 번째 배포'), findsOneWidget);
    // 기간이 보인다.
    expect(find.textContaining('26.03.01'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
