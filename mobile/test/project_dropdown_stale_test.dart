import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

Project _project(String id, String name) {
  final now = DateTime.now();
  return Project(
    id: id,
    workspaceId: 'w1',
    name: name,
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
  );
}

Widget _wrap(AppState state) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: const MaterialApp(home: ProjectsScreen()),
  );
}

void main() {
  testWidgets('목록을 다시 불러와 인스턴스가 바뀌어도 드롭다운이 죽지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // 이전에 선택된 인스턴스 (목록에는 없음)
    final stale = _project('p1', '리뉴얼');
    // 새로 불러온 목록의 인스턴스 (같은 id, 다른 객체)
    final reloaded = _project('p1', '리뉴얼');
    expect(stale, isNot(same(reloaded)), reason: '서로 다른 인스턴스여야 재현된다');

    final state = FakeAppState(projects: [reloaded], activeProject: stale);
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    // 예전 코드(객체를 value 로 쓰는 드롭다운)는 여기서 assertion 이 터져 앱이 죽는다
    expect(tester.takeException(), isNull);
    expect(find.text('리뉴얼'), findsWidgets);
  });

  testWidgets('선택된 프로젝트가 목록에서 사라지면 빈 값으로 처리한다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final removed = _project('p1', '사라진 프로젝트');
    final state = FakeAppState(projects: [_project('p2', '다른 프로젝트')], activeProject: removed);

    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    expect(tester.takeException(), isNull);
    // 선택된 프로젝트가 없으므로 힌트가 보인다
    expect(find.text('프로젝트 선택'), findsOneWidget);
  });

  testWidgets('드롭다운 선택은 id 로 프로젝트를 찾아 전달된다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final first = _project('p1', '이름이 같은 프로젝트');
    final second = _project('p2', '이름이 같은 프로젝트');
    final state = FakeAppState(projects: [first, second], activeProject: first);

    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();

    // 두 항목의 이름이 같으니 항목 인덱스로 골라 id 로 정확히 찾아야 한다
    await tester.tap(find.text('이름이 같은 프로젝트').last);
    await tester.pumpAndSettle();

    expect(state.lastSelectedProject?.id, 'p2');
    expect(tester.takeException(), isNull);
  });

  testWidgets('목록이 비면(불러오기 실패) 빈 상태와 다시 시도를 보여준다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = FakeAppState(projectsErrorMessage: '프로젝트를 불러오지 못했습니다.');
    await tester.pumpWidget(_wrap(state));
    await tester.pump();

    expect(find.text('프로젝트를 불러오지 못했습니다.'), findsOneWidget);
    expect(find.text('프로젝트가 없습니다'), findsOneWidget);

    await tester.tap(find.text('다시 시도'));
    await tester.pump();
    expect(state.projectsRetryCount, 1);
  });
}
