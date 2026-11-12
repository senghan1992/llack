import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 놓친 실시간 이벤트가 영영 복구되지 않는 문제 (§9-46).
///
/// 대화방을 다시 열면 최신 메시지를 병합해서 가져와야 하고,
/// 이미 불러온 과거 메시지는 사라지면 안 된다.

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

/// 응답을 직접 지정할 수 있는 가짜 API.
class _FakeApi extends ApiService {
  int bootstrapCalls = 0;
  final List<String> messageCalls = [];

  /// 최신 40개 응답 (서버가 주는 "최신" 목록)
  List<Message> newest = [];

  /// around 응답 (검색 점프)
  List<Message> aroundResult = [];

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
    if (around != null) {
      messageCalls.add('around:$around');
      return (aroundResult, true, true);
    }
    if (after != null) {
      messageCalls.add('after:$after');
      return (<Message>[], false, false);
    }
    if (before != null) {
      messageCalls.add('before:$before');
      return (<Message>[], false, false);
    }
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

  /// 서버가 WS 로 보내는 이벤트를 흉내낸다.
  void emit(Map<String, dynamic> event) => handler?.call(event);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late _FakeWsService ws;
  late AppState state;

  List<String> ids() => state.activeMessages.map((m) => m.id).toList();

  setUp(() async {
    api = _FakeApi();
    ws = _FakeWsService();
    state = AppState(api: api, ws: ws);
    await state.selectWorkspace(_workspace());
  });

  test('이미 히스토리를 불러온 채널을 다시 열면 놓친 최신 메시지가 들어온다', () async {
    // 처음 열 때: 서버에 m1, m2, m3 이 있다.
    api.newest = [_message('m1', 1), _message('m2', 2), _message('m3', 3)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    expect(ids(), ['m1', 'm2', 'm3']);

    // WS 를 놓쳐서 서버에만 m4 가 생겼다.
    api.newest = [_message('m2', 2), _message('m3', 3), _message('m4', 4)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    expect(ids(), contains('m4'));
  });

  test('병합 갱신 후 기존에 불러온 과거 메시지가 사라지지 않는다', () async {
    api.newest = [_message('m1', 1), _message('m2', 2), _message('m3', 3)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    api.newest = [_message('m3', 3), _message('m4', 4)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    expect(ids(), ['m1', 'm2', 'm3', 'm4']);
  });

  test('병합 갱신 후 순서가 유지된다 (created_at, id)', () async {
    api.newest = [_message('m1', 1), _message('m2', 2)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    // 서버 응답이 순서가 뒤섞여 와도 정렬 기준대로 놓인다.
    api.newest = [_message('m4', 4), _message('m3', 3)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    expect(ids(), ['m1', 'm2', 'm3', 'm4']);
  });

  test('focusMessageId 로 점프할 때는 병합 갱신이 안 돈다', () async {
    api.newest = [_message('m1', 1)];
    api.aroundResult = [_message('m1', 1), _message('m2', 2)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    api.messageCalls.clear();

    // 검색 점프
    state.selectChannel('c1', focusMessageId: 'm2');
    await Future<void>.delayed(Duration.zero);

    expect(api.messageCalls, contains('around:m2'));
    expect(api.messageCalls, isNot(contains('plain')));
  });

  test('WS 재연결(hello) 하면 bootstrap 을 다시 부르고 활성 채널도 다시 맞춘다', () async {
    api.newest = [_message('m1', 1)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    // 최초 연결의 hello (재동기화 없음)
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);
    final before = api.bootstrapCalls;
    api.messageCalls.clear();

    // 재연결
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    await Future<void>.delayed(Duration.zero);

    // 재동기화는 **한 번만** 일어난다. (루프가 아니다)
    expect(api.bootstrapCalls, before + 1);
    expect(api.messageCalls.where((c) => c == 'plain').length, 1);
  });
}
