import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/my_tasks_screen.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 프로젝트 보드 대역.
class _BoardAppState extends FakeAppState {
  @override
  List<Project> get projects => [
        Project(
          id: 'p1',
          workspaceId: 'w1',
          name: '결제 시스템 개편',
          createdBy: 'u1',
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
          isMember: true,
        ),
        Project(
          id: 'p2',
          workspaceId: 'w1',
          name: '남의 프로젝트',
          createdBy: 'u2',
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
          isMember: false,
        ),
      ];

  @override
  Project? get activeProject => projects.first;

  @override
  List<Task> get activeProjectTasks => [
        Task(
          id: 't1',
          projectId: 'p1',
          title: '로그인 고치기',
          status: TaskStatus.request,
          createdBy: 'u1',
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
          milestoneId: 'm1',
          milestoneName: '첫 배포',
          milestoneColor: '#4f6cff',
          dueAt: DateTime(2026, 3, 4),
        ),
      ];

  @override
  List<Roadmap> get activeRoadmaps => [
        Roadmap(id: 'r1', projectId: 'p1', name: '1분기 로드맵'),
      ];

  @override
  List<Task> get myTasks => [
        Task(
          id: 't2',
          projectId: 'p2',
          title: '남의 카드에 해줄 일',
          status: TaskStatus.todo,
          createdBy: 'u2',
          createdAt: DateTime(2026, 1, 1),
          updatedAt: DateTime(2026, 1, 1),
          dueAt: DateTime(2026, 3, 9),
        ),
      ];

  String? deletedRoadmapId;

  @override
  Future<bool> deleteRoadmap(String roadmapId) async {
    deletedRoadmapId = roadmapId;
    return true;
  }
}

Widget _wrap(AppState state, Widget child) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: MaterialApp(home: Scaffold(body: child)),
  );
}

void main() {
  setUp(() {
    // 폰 크기 화면에서 검사한다.
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(411 * 3, 914 * 3);
    view.devicePixelRatio = 3.0;
    addTearDown(view.reset);
  });

  testWidgets('할 일 카드에 마일스톤 배지(색과 이름)가 보인다', (tester) async {
    final state = _BoardAppState();

    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pumpAndSettle();

    expect(find.text('첫 배포'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('로드맵 칩의 지우기를 누르면 확인 뒤에 로드맵이 지워진다', (tester) async {
    final state = _BoardAppState();

    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pumpAndSettle();

    expect(find.text('1분기 로드맵'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();

    // 확인 대화상자가 먼저 나온다.
    expect(find.text('로드맵 삭제'), findsOneWidget);
    expect(state.deletedRoadmapId, isNull);

    await tester.tap(find.text('삭제'));
    await tester.pumpAndSettle();

    expect(state.deletedRoadmapId, 'r1');
  });

  testWidgets('내 프로젝트 필터는 내가 속한 프로젝트만 남긴다', (tester) async {
    final state = _BoardAppState();

    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pumpAndSettle();

    // 처음에는 두 프로젝트가 모두 보인다.
    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    expect(find.text('결제 시스템 개편'), findsWidgets);
    expect(find.text('남의 프로젝트'), findsOneWidget);
    // 메뉴를 닫는다.
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('내 프로젝트'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();

    expect(find.text('결제 시스템 개편'), findsWidgets);
    expect(find.text('남의 프로젝트'), findsNothing);
  });

  testWidgets('내 할 일 목록은 프로젝트 이름과 상태, 마감일을 보여준다', (tester) async {
    final state = _BoardAppState();

    await tester.pumpWidget(_wrap(state, const MyTasksScreen()));
    await tester.pumpAndSettle();

    expect(find.text('남의 카드에 해줄 일'), findsOneWidget);
    expect(find.text('남의 프로젝트'), findsOneWidget);
    expect(find.text('할 일'), findsOneWidget);
    expect(find.text('3.9'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
