import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 재진입 병합 갱신 후 "최신 더 불러오기" 가 쓸데없이 돌지 않아야 한다 (§9-48).
///
/// 병합 갱신은 **서버의 최신 40개** 를 받아온 것이므로,
/// 그 시점에는 "더 최신 메시지가 있다" 가 아니라 **없다** 가 맞다.

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
  final List<String> messageCalls = [];
  List<Message> newest = [];

  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace()];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
        workspace: _workspace(),
        channels: [_channel()],
        dms: const [],
        members: const [],
        me: _user(),
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
    if (after != null) {
      messageCalls.add('after:$after');
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
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late AppState state;

  List<String> ids() => state.activeMessages.map((m) => m.id).toList();

  setUp(() async {
    api = _FakeApi();
    state = AppState(api: api, ws: _FakeWsService());
    await state.selectWorkspace(_workspace());
  });

  test('병합 갱신 후에는 "더 최신 메시지가 있다" 가 false 다', () async {
    api.newest = [_message('m1', 1), _message('m2', 2), _message('m3', 3)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    // 새로운 최신 메시지가 발견되는 상황.
    api.newest = [_message('m2', 2), _message('m3', 3), _message('m4', 4)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    expect(ids(), ['m1', 'm2', 'm3', 'm4']);
    // 서버의 최신 40개를 받았으므로 더 최신은 없다.
    expect(state.hasMoreNewerMessages, isFalse);
  });

  test('병합 갱신 후 최신 커서는 최신 메시지 id 다', () async {
    api.newest = [_message('m1', 1), _message('m2', 2)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    api.newest = [_message('m2', 2), _message('m3', 3)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    api.messageCalls.clear();

    // "최신 더 불러오기" 를 부르면 최신 id 뒤를 물어본다.
    await state.loadNewerMessages('c1');

    expect(api.messageCalls, ['after:m3']);
  });

  test('최하단에서 after= 요청이 나가지 않는다 (hasMoreNewer 가 false)', () async {
    api.newest = [_message('m1', 1)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    api.newest = [_message('m1', 1), _message('m2', 2)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    api.messageCalls.clear();

    // 화면(담당 B)은 최하단에 닿으면 hasMoreNewer 가 true 일 때만 부른다.
    expect(state.hasMoreNewerMessages, isFalse);
    expect(api.messageCalls.where((c) => c.startsWith('after:')), isEmpty);
  });

  test('병합 갱신이 커서를 뒤로 물리지 않게 한다', () async {
    api.newest = [_message('m1', 1), _message('m2', 2)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);

    // 최신 커서를 m2 로 민다.
    await state.loadNewerMessages('c1');
    api.messageCalls.clear();

    // 병합 갱신이 예전 메시지들을 받아와도 커서는 물러나면 안 된다.
    api.newest = [_message('m1', 1)];
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    await state.loadNewerMessages('c1');

    expect(api.messageCalls.where((c) => c.startsWith('after:')), ['after:m2']);
  });
}
