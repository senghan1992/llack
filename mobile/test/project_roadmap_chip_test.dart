import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 로드맵 이름이 붙은 태스크를 가진 대역.
class _RoadmapAppState extends FakeAppState {
  _RoadmapAppState({required this.tasks});

  final List<Task> tasks;

  @override
  List<Project> get projects => [
        Project(
          id: 'p1',
          workspaceId: 'w1',
          name: '테스트 프로젝트',
          createdBy: 'u1',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      ];

  @override
  Project? get activeProject => projects.first;

  @override
  List<Task> get activeProjectTasks => tasks;
}

Task _task({
  required String id,
  required String title,
  String? roadmapName,
  String assigneeName = '이채원',
}) {
  final now = DateTime.now();
  return Task(
    id: id,
    projectId: 'p1',
    title: title,
    status: TaskStatus.request,
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
    assignee: User(id: 'u2', email: 'a@x.com', name: assigneeName),
    assigneeId: 'u2',
    dueAt: now.add(const Duration(days: 5)),
    commentCount: 3,
    roadmapName: roadmapName,
  );
}

const String _longRoadmap =
    '아주아주길고긴로드맵이름이정말로오래되는경우에는카드밖으로넘쳐나가지않아야합니다';

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('긴 로드맵 이름이 있어도 카드가 깨지지 않는다 (§9-41)', (WidgetTester tester) async {
    const screenWidth = 411.0;
    tester.view.physicalSize = const Size(screenWidth * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _RoadmapAppState(
      tasks: [
        _task(id: 't1', title: '긴 로드맵 카드', roadmapName: _longRoadmap),
      ],
    );
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ProjectsScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // ① 예외(overflow 등)가 나지 않는다
    expect(tester.takeException(), isNull);

    // ② 왼쪽 정보(담당자 이름·마감일·댓글수)가 사라지지 않는다
    expect(find.text('이채원'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);

    // ③ 로드맵 칩이 카드 내용 영역의 오른쪽 끝에 정렬되어 있다
    final chip = find.ancestor(of: find.text(_longRoadmap), matching: find.byType(Container)).first;
    final chipRect = tester.getRect(chip);
    final cardRect = tester.getRect(find.byType(Card).first);
    expect(chipRect.right, closeTo(cardRect.right - 14, 2), reason: '칩이 카드 오른쪽 끝에 붙어 있어야 한다');

    // 카드 밖으로 넘치지 않는다
    expect(chipRect.right, lessThanOrEqualTo(cardRect.right));
  });

  testWidgets('로드맵 칩이 있는 카드와 없는 카드의 왼쪽 정보 시작 x 가 같다 (§9-40 유지)', (WidgetTester tester) async {
    const screenWidth = 411.0;
    tester.view.physicalSize = const Size(screenWidth * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _RoadmapAppState(
      tasks: [
        _task(id: 't1', title: '칩 있는 카드', roadmapName: '로드맵'),
        _task(id: 't2', title: '칩 없는 카드', assigneeName: '박지민'),
      ],
    );
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ProjectsScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 왼쪽 정보(담당자 이름)의 시작 x 가 두 카드에서 같다
    final withChip = tester.getRect(find.text('이채원'));
    final withoutChip = tester.getRect(find.text('박지민'));
    expect(withChip.left, closeTo(withoutChip.left, 1));

    // 칩은 여전히 행의 오른쪽 끝에 붙어 있다
    final chip = tester.getRect(find.ancestor(of: find.text('로드맵'), matching: find.byType(Container)).first);
    final cardRect = tester.getRect(find.byType(Card).first);
    expect(chip.right, lessThanOrEqualTo(cardRect.right));
    expect(chip.right, closeTo(cardRect.right - 14, 2));
    expect(tester.takeException(), isNull);
  });
}
