import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 섹션(일정/프로젝트/조직도) 데이터의 "이미 불러왔다" 신호 (F-4 2차분).
///
/// 화면(initState)이 "이미 불러온 데이터면 다시 부르지 않기" 로 판단할 때 쓴다.
/// **목록이 비어 있는지와는 무관**하다. (빈 목록이어도 "불러온 것" 이다)

User _user() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace(String id) =>
    Workspace(id: id, name: '한빛 $id', slug: 'ws-$id', createdAt: DateTime(2026, 1, 1));

Channel _channel() => Channel(
      id: 'c1',
      workspaceId: 'w1',
      name: 'general',
      kind: 'channel',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
    );

class _FakeApi extends ApiService {
  bool failEvents = false;
  bool failProjects = false;
  bool failOrg = false;

  /// 빈 목록을 돌려줄지 (빈 목록이어도 플래그는 true 여야 한다)
  bool emptyResult = false;

  int eventCalls = 0;
  int projectCalls = 0;
  int orgCalls = 0;

  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace('w1')];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
        workspace: _workspace(workspaceId),
        channels: [_channel()],
        dms: const [],
        members: const [],
        me: _user(),
      );

  @override
  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async {
    eventCalls++;
    if (failEvents) throw Exception('일정 실패');
    return emptyResult ? <ScheduleEvent>[] : <ScheduleEvent>[];
  }

  @override
  Future<List<Project>> getProjects(String workspaceId) async {
    projectCalls++;
    if (failProjects) throw Exception('프로젝트 실패');
    return emptyResult ? <Project>[] : <Project>[];
  }

  @override
  Future<(List<Message>, bool, bool)> getMessages(
    String channelId, {
    int limit = 50,
    String? before,
    String? after,
    String? around,
  }) async => (<Message>[], false, false);

  @override
  Future<OrgOverview> getOrgOverview(String workspaceId) async {
    orgCalls++;
    if (failOrg) throw Exception('조직도 실패');
    return OrgOverview(units: const [], admins: const [], myRole: Role.member);
  }
}

class _FakeWsService extends WsService {
  WsEventHandler? handler;

  @override
  void addListener(WsEventHandler handler) {
    this.handler = handler;
  }

  @override
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late AppState state;

  setUp(() async {
    // 토큰 저장소(SharedPreferences) 는 테스트에서 가짜를 쓴다.
    SharedPreferences.setMockInitialValues({});
    api = _FakeApi();
    state = AppState(api: api, ws: _FakeWsService());
    await state.selectWorkspace(_workspace('w1'));
  });

  test('성공적으로 불러오면 플래그가 true 다', () async {
    // 워크스페이스를 열면 데이터가 이미 불려 있으므로 플래그가 true 다.
    // (화면이 이 플래그로 중복 요청을 막는다)
    expect(state.hasLoadedEvents, isTrue);
    expect(state.hasLoadedProjects, isTrue);
    expect(state.hasLoadedOrg, isTrue);

    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    expect(state.hasLoadedEvents, isTrue);
    expect(state.hasLoadedProjects, isTrue);
    expect(state.hasLoadedOrg, isTrue);
  });

  test('실패하면 플래그는 false 다 (화면이 처음 뜰 때 재시도할 수 있어야 한다)', () async {
    // 플래그가 false 인 상태에서 (워크스페이스를 새로 고침) 실패를 만든다.
    await state.refreshWorkspace();
    expect(state.hasLoadedEvents, isFalse);

    api.failEvents = true;
    api.failProjects = true;
    api.failOrg = true;

    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    // 실패했으면 true 로 세우지 않는다. (그래야 화면이 처음 뜰 때 재시도한다)
    expect(state.hasLoadedEvents, isFalse);
    expect(state.hasLoadedProjects, isFalse);
    expect(state.hasLoadedOrg, isFalse);

    // 다시 부르면 성공한다.
    api.failEvents = false;
    api.failProjects = false;
    api.failOrg = false;
    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    expect(state.hasLoadedEvents, isTrue);
    expect(state.hasLoadedProjects, isTrue);
    expect(state.hasLoadedOrg, isTrue);
  });

  test('목록이 비어 있어도 "불러온 것" 이다 (빈 목록 판단으로 중복 요청이 생기면 안 된다)', () async {
    api.emptyResult = true;

    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    expect(state.events, isEmpty);
    expect(state.projects, isEmpty);
    expect(state.hasLoadedEvents, isTrue);
    expect(state.hasLoadedProjects, isTrue);
    expect(state.hasLoadedOrg, isTrue);
  });

  test('워크스페이스를 바꾸면 플래그가 초기화되고 새 데이터를 다시 불러온 뒤 true 가 된다', () async {
    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();
    expect(state.hasLoadedEvents, isTrue);
    final eventsBefore = api.eventCalls;

    // 다른 워크스페이스로 전환한다. (일정 불러오기는 실패로 만든다)
    api.failEvents = true;
    await state.selectWorkspace(_workspace('w2'));

    // 이전 워크스페이스의 플래그를 물려받으면 안 된다.
    expect(state.hasLoadedEvents, isFalse);
    // 그리고 새 워크스페이스의 데이터는 다시 불러온다.
    expect(api.eventCalls, greaterThan(eventsBefore));

    // 새 워크스페이스 데이터를 다시 불러온 뒤에는 true.
    api.failEvents = false;
    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();
    expect(state.hasLoadedEvents, isTrue);
    expect(state.hasLoadedProjects, isTrue);
    expect(state.hasLoadedOrg, isTrue);
  });

  test('로그아웃하면 플래그가 초기화된다', () async {
    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    await state.logout();

    expect(state.hasLoadedEvents, isFalse);
    expect(state.hasLoadedProjects, isFalse);
    expect(state.hasLoadedOrg, isFalse);
  });

  test('워크크스페이스를 새로 고치면 플래그가 초기화된다', () async {
    await state.loadEvents();
    await state.loadProjects();
    await state.loadOrg();

    await state.refreshWorkspace();

    expect(state.hasLoadedEvents, isFalse);
    expect(state.hasLoadedProjects, isFalse);
    expect(state.hasLoadedOrg, isFalse);
  });
}
