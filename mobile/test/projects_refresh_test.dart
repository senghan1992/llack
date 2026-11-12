import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';
import 'package:provider/provider.dart';

/// F-6: 프로젝트 탭에 당겨서 고침(새로고침)이 없다.
///
/// 실기: 일정/조직도/메시지 탭은 당기면 갱신되는데 프로젝트 탭만 아무 일도 일어나지 않았다.
///
/// `projects_screen.dart` 에 `RefreshIndicator` 가 없어서였다.
/// 여기서는 새로고침 경로가 존재하는지, 당기면 `loadProjects()` 가 정확히 1회 호출되는지 확인한다.

User _user() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace() =>
    Workspace(id: 'w1', name: '한빛', slug: 'hanbit', createdAt: DateTime(2026, 1, 1));

Project _project() => Project(
      id: 'p1',
      workspaceId: 'w1',
      name: '프로젝트 하나',
      createdBy: 'me',
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
    );

class _FakeApi extends ApiService {
  int projectsCalls = 0;

  /// 서버가 돌려줄 프로젝트 목록 (테스트에서 비울 수 있다)
  List<Project> projects = [_project()];
  int tasksCalls = 0;
  int roadmapsCalls = 0;
  int milestonesCalls = 0;

  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace()];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
        workspace: _workspace(),
        channels: const [],
        dms: const [],
        members: const [],
        me: _user(),
      );

  @override
  Future<List<Project>> getProjects(String workspaceId) async {
    projectsCalls++;
    return projects;
  }

  @override
  Future<List<Task>> getProjectTasks(String projectId) async {
    tasksCalls++;
    return const [];
  }

  @override
  Future<List<Roadmap>> getRoadmaps(String projectId) async {
    roadmapsCalls++;
    return const [];
  }

  @override
  Future<List<Milestone>> getMilestones(String projectId) async {
    milestonesCalls++;
    return const [];
  }

  @override
  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async =>
      const [];

  @override
  Future<OrgOverview> getOrgOverview(String workspaceId) async =>
      OrgOverview(units: const [], admins: const [], myRole: Role.member);
}

class _FakeWsService extends WsService {
  @override
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late _FakeWsService ws;
  late AppState state;

  setUp(() async {
    api = _FakeApi();
    ws = _FakeWsService();
    state = AppState(api: api, ws: ws);
    await state.selectWorkspace(_workspace());
    // 워크스페이스를 고를 때 한 번 불러왔으므로 카운터를 초기화한다.
    api.projectsCalls = 0;
  });

  tearDown(() {
    state.dispose();
  });

  Future<void> pumpProjects(WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: ProjectsScreen()),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  testWidgets('프로젝트 화면에 새로고침 경로(RefreshIndicator)가 있다', (WidgetTester tester) async {
    await pumpProjects(tester);

    expect(find.byType(RefreshIndicator), findsOneWidget);
  });

  testWidgets('당겨서 고침은 loadProjects() 를 정확히 1회 호출한다', (WidgetTester tester) async {
    await pumpProjects(tester);
    expect(api.projectsCalls, 0);

    final indicator = tester.widget<RefreshIndicator>(find.byType(RefreshIndicator));
    await indicator.onRefresh();

    expect(api.projectsCalls, 1);
  });

  testWidgets('화면을 아래로 당기면 실제로 갱신된다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await pumpProjects(tester);
    expect(api.projectsCalls, 0);

    // 카드 목록 위에서 아래로 당긴다.
    await tester.drag(find.text('카드가 없습니다'), const Offset(0, 300));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 1));

    expect(api.projectsCalls, 1);
  });

  testWidgets('프로젝트가 하나도 없어도 당겨서 고침이 된다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // 프로젝트 목록이 비어 있는 상태로 다시 만든다.
    state.dispose();
    api = _FakeApi()..projects = [];
    state = AppState(api: api, ws: ws);
    await state.selectWorkspace(_workspace());
    api.projectsCalls = 0;

    await pumpProjects(tester);
    expect(find.text('프로젝트가 없습니다'), findsOneWidget);

    await tester.drag(find.text('프로젝트가 없습니다'), const Offset(0, 300));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 1));

    expect(api.projectsCalls, 1);
  });
}
