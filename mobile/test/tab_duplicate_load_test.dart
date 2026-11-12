import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/org/org_screen.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';
import 'package:provider/provider.dart';

/// F-5: 탭 데이터 중복 요청.
///
/// 앱 시작 시 `MainShell` 의 IndexedStack 이 세 탭 화면을 한꺼번에 만들고,
/// 각 화면의 `initState` 가 다시 데이터를 부르면 같은 요청이 두 번 나간다.
/// Core 는 이미 불러온 데이터면 건너뛰는 신호(`hasLoadedEvents` 등)를 노출한다.

User _user() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace() =>
    Workspace(id: 'w1', name: '한빛', slug: 'hanbit', createdAt: DateTime(2026, 1, 1));

/// 호출 횟수를 세는 가짜 API.
class _FakeApi extends ApiService {
  int eventsCalls = 0;
  int projectsCalls = 0;
  int orgCalls = 0;
  int roadmapsCalls = 0;
  int milestonesCalls = 0;
  int tasksCalls = 0;

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
  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async {
    eventsCalls++;
    return const [];
  }

  @override
  Future<List<Project>> getProjects(String workspaceId) async {
    projectsCalls++;
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
  Future<List<Task>> getProjectTasks(String projectId) async {
    tasksCalls++;
    return const [];
  }

  @override
  Future<OrgOverview> getOrgOverview(String workspaceId) async {
    orgCalls++;
    return OrgOverview(units: const [], admins: const [], myRole: Role.member);
  }
}

class _FakeWsService extends WsService {
  @override
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {}
}

/// `hasLoaded*` 신호를 강제로 조작해 상황을 흉내내는 대역.
class _TabAppState extends AppState {
  _TabAppState({required super.api, required super.ws, this.forceUnloaded = false});

  /// true 면 "Core 가 아직 못 불러왔다" 상황을 만든다.
  final bool forceUnloaded;

  @override
  bool get hasLoadedEvents => forceUnloaded ? false : super.hasLoadedEvents;

  @override
  bool get hasLoadedProjects => forceUnloaded ? false : super.hasLoadedProjects;

  @override
  bool get hasLoadedOrg => forceUnloaded ? false : super.hasLoadedOrg;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late _FakeWsService ws;
  late AppState state;

  /// 지금까지 일어난 요청 횟수를 초기화한다. (화면을 띄우기 직전에 호출)
  void resetCounts() {
    api
      ..eventsCalls = 0
      ..projectsCalls = 0
      ..orgCalls = 0
      ..roadmapsCalls = 0
      ..milestonesCalls = 0
      ..tasksCalls = 0;
  }

  setUp(() async {
    await initializeDateFormatting('ko_KR', null);
    api = _FakeApi();
    ws = _FakeWsService();
    state = _TabAppState(api: api, ws: ws);
    // 워크스페이스를 고르면 Core 가 데이터를 한 번씩 불러온다.
    await state.selectWorkspace(_workspace());
    resetCounts();
  });

  tearDown(() {
    state.dispose();
  });

  Future<void> pumpScreen(WidgetTester tester, Widget screen) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(home: screen),
      ),
    );
    // initState 의 postFrameCallback 이 실행될 때까지 기다린다.
    await tester.pump();
    await tester.pump();
  }

  testWidgets('Core 가 이미 일정을 불러왔으면 일정 화면이 다시 부르지 않는다', (WidgetTester tester) async {
    expect(state.hasLoadedEvents, isTrue);

    await pumpScreen(tester, const ScheduleScreen());

    expect(api.eventsCalls, 0);
  });

  testWidgets('Core 가 아직 일정을 못 불렀으면 일정 화면이 1회 부른다', (WidgetTester tester) async {
    state.dispose();
    state = _TabAppState(api: api, ws: ws, forceUnloaded: true);
    await state.selectWorkspace(_workspace());
    resetCounts();

    await pumpScreen(tester, const ScheduleScreen());

    expect(api.eventsCalls, 1);
  });

  testWidgets('Core 가 이미 프로젝트를 불러왔으면 프로젝트 화면이 다시 부르지 않는다', (
    WidgetTester tester,
  ) async {
    expect(state.hasLoadedProjects, isTrue);

    await pumpScreen(tester, const ProjectsScreen());

    expect(api.projectsCalls, 0);
  });

  testWidgets('Core 가 아직 프로젝트를 못 불렀으면 프로젝트 화면이 1회 부른다', (
    WidgetTester tester,
  ) async {
    state.dispose();
    state = _TabAppState(api: api, ws: ws, forceUnloaded: true);
    await state.selectWorkspace(_workspace());
    resetCounts();

    await pumpScreen(tester, const ProjectsScreen());

    expect(api.projectsCalls, 1);
  });

  testWidgets('Core 가 이미 조직도를 불러왔으면 조직도 화면이 다시 부르지 않는다', (
    WidgetTester tester,
  ) async {
    expect(state.hasLoadedOrg, isTrue);

    await pumpScreen(tester, const OrgScreen());

    expect(api.orgCalls, 0);
  });

  testWidgets('Core 가 아직 조직도를 못 불렀으면 조직도 화면이 1회 부른다', (WidgetTester tester) async {
    state.dispose();
    state = _TabAppState(api: api, ws: ws, forceUnloaded: true);
    await state.selectWorkspace(_workspace());
    resetCounts();

    await pumpScreen(tester, const OrgScreen());

    expect(api.orgCalls, 1);
  });

  testWidgets('당겨서 고침은 플래그와 무관하게 다시 불러온다', (WidgetTester tester) async {
    // 이미 불러온 상태여도 사용자가 당기면 다시 요청해야 한다.
    await pumpScreen(tester, const ScheduleScreen());
    expect(api.eventsCalls, 0);

    // 당기기 제스처 대신 새로고침 콜백을 직접 실행한다.
    // (빈 목록에서는 스크롤 오버스크롤이 일어나지 않아 제스처로 재현하기 어렵다)
    final indicator = tester.widget<RefreshIndicator>(find.byType(RefreshIndicator));
    await indicator.onRefresh();

    expect(api.eventsCalls, 1);
  });
}
