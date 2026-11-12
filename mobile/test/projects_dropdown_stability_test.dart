import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:provider/provider.dart';

/// 프로젝트 드롭다운 안정성 대역.
class _FakeAppState extends AppState {
  _FakeAppState({this.projects = const [], this.activeProject});

  @override
  final List<Project> projects;
  @override
  final Project? activeProject;

  int selectCount = 0;

  @override
  Future<void> selectProject(Project project) async {
    selectCount++;
  }
}

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

Widget _wrap(AppState state, Widget child) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: MaterialApp(home: child),
  );
}

void main() {
  // 서버 주소를 바꾸면 프로젝트 목록을 다시 불러오고,
  // 선택 중이던 프로젝트 객체는 옛 인스턴스 그대로 남는다.
  // 그 상태에서 드롭다운을 그리면
  // "There should be exactly one item with [DropdownButton]'s value" assertion 으로 죽었다.
  testWidgets('프로젝트 목록을 새로 불러와도 드롭다운이 죽지 않는다', (WidgetTester tester) async {
    final listed = _project('p1', '2026 하반기 리뉴얼');
    // 같은 id 이지만 다른 인스턴스 (새로 불러온 목록의 객체)
    final stale = _project('p1', '2026 하반기 리뉴얼');

    final state = _FakeAppState(projects: [listed], activeProject: stale);
    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('2026 하반기 리뉴얼'), findsWidgets);
  });

  testWidgets('선택했던 프로젝트가 목록에서 사라져도 죽지 않는다', (WidgetTester tester) async {
    final stale = _project('p9', '사라진 프로젝트');
    final state = _FakeAppState(projects: [_project('p1', '남아 있는 프로젝트')], activeProject: stale);

    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pump();

    expect(tester.takeException(), isNull);
  });

  testWidgets('프로젝트를 하나도 못 불러오면 빈 상태 화면을 보여준다', (WidgetTester tester) async {
    final state = _FakeAppState(projects: const [], activeProject: null);
    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('프로젝트가 없습니다'), findsOneWidget);
  });
}
