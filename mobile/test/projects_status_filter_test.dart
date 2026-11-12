import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 프로젝트/태스크가 있는 대역.
class _ProjectsAppState extends FakeAppState {
  _ProjectsAppState(this.project);

  final Project project;

  @override
  List<Project> get projects => [project];

  @override
  Project? get activeProject => project;

  @override
  List<Task> get activeProjectTasks => [
        Task(
          id: 't1',
          projectId: project.id,
          title: '진행 중 태스크',
          status: TaskStatus.inProgress,
          createdBy: 'u1',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      ];
}

Project _project() {
  final now = DateTime.now();
  return Project(
    id: 'p1',
    workspaceId: 'w1',
    name: '테스트 프로젝트',
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
  );
}

Widget _wrap(AppState state, {Key? screenKey}) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: MaterialApp(home: Scaffold(body: ProjectsScreen(key: screenKey))),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('상태 필터를 바꿔도 화면을 다시 만들면 같은 탭이 선택되어 있다 (§9-38)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ProjectsAppState(_project());
    await tester.pumpWidget(_wrap(state));
    await tester.pumpAndSettle();

    // "진행 중" 필터를 선택한다
    await tester.tap(find.textContaining('진행 중'));
    await tester.pumpAndSettle();
    expect(find.text('진행 중 태스크'), findsOneWidget);

    // 화면을 새로 만든다.
    // (회전으로 폰↔태블릿 레이아웃이 전환되면 element 가 교체되어 State 가 재생성된다.
    //  key 를 바꿔서 같은 상황을 재현한다)
    await tester.pumpWidget(_wrap(state, screenKey: const ValueKey('rotated')));
    await tester.pumpAndSettle();

    // 여전히 "진행 중" 이 선택되어 있어야 한다
    expect(find.text('진행 중 태스크'), findsOneWidget);
    expect(find.text('진행 중 (1)'), findsOneWidget);
  });
}
