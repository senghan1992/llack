import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 콜드 스타트 때 bootstrap 이 두 번씩 나가지 않아야 한다 (F-4).
///
/// - 세션의 **첫** 'hello' (= 최초 연결) → 재동기화 없음
/// - **재연결** 후의 'hello' → 재동기화 (놓친 이벤트 복구)
/// - 로그아웃 → 재로그인 → 다시 "첫 hello = 재동기화 없음"

User _user() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace() =>
    Workspace(id: 'w1', name: '한빛', slug: 'hanbit', createdAt: DateTime(2026, 1, 1));

Channel _channel() => Channel(
      id: 'c1',
      workspaceId: 'w1',
      name: 'general',
      kind: 'channel',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
    );

Message _message(String id, int minute) => Message(
      id: id,
      channelId: 'c1',
      userId: 'u1',
      author: _user(),
      body: id,
      createdAt: DateTime(2026, 1, 1, 10, minute),
    );

class _FakeApi extends ApiService {
  int bootstrapCalls = 0;
  final List<String> messageCalls = [];
  List<Message> newest = [];

  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace()];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async {
    bootstrapCalls++;
    return Bootstrap(
      workspace: _workspace(),
      channels: [_channel()],
      dms: const [],
      members: const [],
      me: _user(),
    );
  }

  @override
  Future<Session> login(String email, String password) async => Session(
        accessToken: 'a',
        refreshToken: 'r',
        user: _user(),
        workspace: _workspace(),
      );

  @override
  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async =>
      const [];

  @override
  Future<List<Project>> getProjects(String workspaceId) async => const [];

  @override
  Future<OrgOverview> getOrgOverview(String workspaceId) async =>
      OrgOverview(units: const [], admins: const [], myRole: Role.member);

  @override
  Future<(List<Message>, bool, bool)> getMessages(
    String channelId, {
    int limit = 50,
    String? before,
    String? after,
    String? around,
  }) async {
    messageCalls.add('plain');
    return (newest, false, false);
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

  void emit(Map<String, dynamic> event) => handler?.call(event);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late _FakeWsService ws;
  late AppState state;

  setUp(() async {
    // 토큰 저장소(SharedPreferences) 는 테스트에서 가짜를 쓴다.
    SharedPreferences.setMockInitialValues({});
    api = _FakeApi();
    ws = _FakeWsService();
    state = AppState(api: api, ws: ws);
    api.newest = [_message('m1', 1)];
    await state.selectWorkspace(_workspace());
  });

  test('첫 연결의 hello 에서는 bootstrap 이 추가로 호출되지 않는다', () async {
    final before = api.bootstrapCalls;
    api.messageCalls.clear();

    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);

    expect(api.bootstrapCalls, before);
    expect(api.messageCalls, isEmpty);
  });

  test('재연결 후의 hello 에서는 bootstrap 이 호출된다', () async {
    // 첫 연결
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);
    final before = api.bootstrapCalls;
    api.messageCalls.clear();

    // 재연결
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);

    expect(api.bootstrapCalls, before + 1);
    // 활성 채널의 최신 메시지도 같이 맞춘다.
    expect(api.messageCalls.where((c) => c == 'plain').length, 1);
  });

  test('로그아웃 후 재로그인하면 다시 첫 hello 에서 재동기화하지 않는다', () async {
    // 첫 세션: 최초 연결 + 재연결
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);

    // 로그아웃 → 재로그인
    await state.logout();
    await state.login('me@hanbit.co.kr', 'pw');
    final before = api.bootstrapCalls;
    api.messageCalls.clear();

    // 새 세션의 첫 hello → 재동기화 없음
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);

    expect(api.bootstrapCalls, before);
    expect(api.messageCalls, isEmpty);
  });
}
