import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/task_dialog.dart';
import 'package:llack_mobile/widgets/app_snack_bar.dart';
import 'package:provider/provider.dart';

/// 편집 모드에서 updateTask 가 실제로 불리고, 성공/실패에 따라
/// 다이얼로그가 닫히는지(닫히지 않는지)를 확인한다.
class _TaskEditAppState extends AppState {
  _TaskEditAppState({this.updateSucceeds = true});

  final bool updateSucceeds;

  /// 담당자/로드맵 드롭다운이 기존 값을 표시할 수 있도록 목록을 제공한다.
  @override
  List<Member> get members => [
        Member(
          user: User(id: 'u1', email: 'me@hanbit.co.kr', name: '나', title: '기획'),
          role: Role.member,
        ),
        Member(
          user: User(id: 'u2', email: 'min@hanbit.co.kr', name: '김민수', title: '개발'),
          role: Role.member,
        ),
      ];

  @override
  List<Roadmap> get activeRoadmaps => [
        Roadmap(id: 'r1', projectId: 'p1', name: '1분기 로드맵'),
      ];

  /// updateTask 로 넘어온 인자를 그대로 기록한다.
  String? lastTaskId;
  String? lastTitle;
  String? lastDescription;
  DateTime? lastDueAt;
  int updateCallCount = 0;

  @override
  Future<bool> updateTask({
    required String taskId,
    String? title,
    String? description,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
  }) async {
    updateCallCount++;
    lastTaskId = taskId;
    lastTitle = title;
    lastDescription = description;
    lastDueAt = dueAt;
    return updateSucceeds;
  }
}

Task _editingTask() {
  return Task(
    id: 't1',
    projectId: 'p1',
    title: '기존 제목',
    description: '기존 설명',
    status: TaskStatus.inProgress,
    assigneeId: 'u2',
    dueAt: DateTime(2026, 3, 4),
    roadmapId: 'r1',
    createdBy: 'u1',
    createdAt: DateTime(2026, 1, 1),
    updatedAt: DateTime(2026, 1, 1),
  );
}

/// 실제 앱과 똑같이 **showDialog 로** 연다.
Future<void> _openDialog(WidgetTester tester, AppState state, {Task? editing}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => editing == null
                      ? const TaskDialog()
                      : TaskDialog(editing: editing),
                ),
                child: const Text('열기'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();

  await tester.tap(find.text('열기'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('편집 모드는 기존 값으로 필드가 채워지고 버튼 라벨이 "수정" 이다', (tester) async {
    final state = _TaskEditAppState();

    await _openDialog(tester, state, editing: _editingTask());

    // 제목/설명 필드에 기존 값이 들어가 있다.
    final titleField = tester.widget<TextField>(find.widgetWithText(TextField, '기존 제목'));
    expect(titleField.controller!.text, '기존 제목');

    final descField = tester.widget<TextField>(find.widgetWithText(TextField, '기존 설명'));
    expect(descField.controller!.text, '기존 설명');

    // 담당자/로드맵/마감일도 기존 값으로 표시된다
    expect(find.text('김민수 (개발)'), findsOneWidget);
    expect(find.text('1분기 로드맵'), findsOneWidget);
    expect(find.text('마감일: 2026.03.04'), findsOneWidget);

    // 다이얼로그 제목과 버튼 라벨
    expect(find.text('할 일 수정'), findsOneWidget);
    expect(find.text('수정'), findsOneWidget);
    expect(find.text('만들기'), findsNothing);

    // 편집 모드에서는 상태 드롭다운을 표시하지 않는다 (상태는 시트 헤더가 담당)
    expect(find.text('상태'), findsNothing);
  });

  testWidgets('생성 모드는 제목/버튼 라벨이 기존 그대로다', (tester) async {
    final state = _TaskEditAppState();

    await _openDialog(tester, state);

    expect(find.text('새 할 일 만들기'), findsOneWidget);
    expect(find.text('만들기'), findsOneWidget);
    expect(find.text('수정'), findsNothing);
  });

  testWidgets('편집 모드에서 updateTask 가 성공하면 다이얼로그가 닫힌다', (tester) async {
    final state = _TaskEditAppState(updateSucceeds: true);

    await _openDialog(tester, state, editing: _editingTask());

    await tester.tap(find.text('수정'));
    await tester.pumpAndSettle();

    expect(state.updateCallCount, 1);
    expect(state.lastTaskId, 't1');
    expect(state.lastTitle, '기존 제목');
    // 설명은 항상 문자열로 전달된다 (지우면 빈 문자열 = 서버에서 삭제)
    expect(state.lastDescription, '기존 설명');

    // 다이얼로그가 닫혔다
    expect(find.text('할 일 수정'), findsNothing);
  });

  testWidgets('설명을 지우면 빈 문자열로 전달된다 (서버에서 설명이 지워진다)', (tester) async {
    final state = _TaskEditAppState(updateSucceeds: true);

    await _openDialog(tester, state, editing: _editingTask());

    await tester.enterText(find.widgetWithText(TextField, '기존 설명'), '');
    await tester.pump();
    await tester.tap(find.text('수정'));
    await tester.pumpAndSettle();

    expect(state.lastDescription, '');
  });

  testWidgets('마감일 프리필·전달이 로컬 기준이다 (UTC 인스턴스여도)', (tester) async {
    final state = _TaskEditAppState(updateSucceeds: true);
    // 서버가 UTC 인스턴스로 내려주는 마감일 (KST 에서면 다음날로 넘어간다)
    final dueUtc = DateTime.utc(2026, 3, 4, 15, 30);
    final task = _editingTask().copyWith(dueAt: dueUtc);

    await _openDialog(tester, state, editing: task);

    // 화면에는 **로컬 날짜**로 보인다
    final local = dueUtc.toLocal();
    expect(find.text('마감일: ${DateFormat('yyyy.MM.dd').format(local)}'), findsOneWidget);

    await tester.tap(find.text('수정'));
    await tester.pumpAndSettle();

    // 저장되는 값도 로컬 DateTime 이다 (서버로 보내는 UTC 변환은 A 가 한다)
    expect(state.lastDueAt, local);
    expect(state.lastDueAt!.isUtc, isFalse);
  });

  testWidgets('편집에 실패하면 다이얼로그가 닫히지 않고 실패를 알린다', (tester) async {
    final state = _TaskEditAppState(updateSucceeds: false);

    await _openDialog(tester, state, editing: _editingTask());

    await tester.tap(find.text('수정'));
    await tester.pumpAndSettle();

    expect(state.updateCallCount, 1);
    // 다이얼로그는 그대로 열려 있다
    expect(find.text('할 일 수정'), findsOneWidget);
    // 실패 안내 (모달 위에서 보이는 공용 스낵바)
    expect(find.byType(AppSnackBar), findsOneWidget);
    expect(find.text('할 일 수정에 실패했습니다'), findsOneWidget);
  });
}
