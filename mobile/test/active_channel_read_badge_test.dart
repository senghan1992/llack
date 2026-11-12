import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 보고 있는 채널에 도착한 메시지가 안읽음 배지로 남지 않아야 한다 (§9-45).

User _user() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace() => Workspace(id: 'w1', name: '한빛', slug: 'hanbit', createdAt: DateTime(2026, 1, 1));

Channel _channel(String id, String name) => Channel(
      id: id,
      workspaceId: 'w1',
      name: name,
      kind: 'channel',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
    );

Map<String, dynamic> _messageEvent(String channelId, String messageId, String authorId) => {
      'type': 'message.created',
      'message': {
        'id': messageId,
        'channel_id': channelId,
        'user_id': authorId,
        'author': {'id': authorId, 'email': 'other@hanbit.co.kr', 'name': '최수아'},
        'body': 'visible while open',
        'created_at': DateTime(2026, 1, 1, 12).toIso8601String(),
      },
    };

/// 부트스트랩에 채널 2개를 넣어주는 가짜 API.
class _FakeApi extends ApiService {
  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace()];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
        workspace: _workspace(),
        channels: [_channel('c1', 'general'), _channel('c2', 'release')],
        dms: const [],
        members: const [],
        me: _user(),
      );

  @override
  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async => const [];

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
  }) async => (<Message>[], false, false);
}

/// 보낸 WS 메시지를 기록하는 가짜 소켓.
class _FakeWsService extends WsService {
  final List<Map<String, dynamic>> sent = [];
  WsEventHandler? handler;

  @override
  void addListener(WsEventHandler handler) {
    this.handler = handler;
  }

  @override
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {}

  @override
  void send(Map<String, dynamic> payload) {
    sent.add(payload);
  }

  /// 서버가 WS 로 보내는 이벤트를 흉내낸다.
  void emit(Map<String, dynamic> event) => handler?.call(event);

  /// 읽음 신호만 골라낸다.
  List<Map<String, dynamic>> reads() =>
      sent.where((p) => p['type'] == 'read').toList();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeApi api;
  late _FakeWsService ws;
  late AppState state;

  /// 채널 목록에서 채널 하나의 배지 숫자.
  int badge(String channelId) =>
      state.allChannels.firstWhere((c) => c.id == channelId).unreadCount;

  setUp(() async {
    api = _FakeApi();
    ws = _FakeWsService();
    state = AppState(api: api, ws: ws);
    await state.selectWorkspace(_workspace());
    // c1 을 열어 둔다 (채널 진입 시 읽음 신호가 1회 나간다).
    state.selectChannel('c1');
    ws.sent.clear();
  });

  test('활성 채널 + 화면에 보이면 그 메시지 id 로 읽음 신호가 나가고 배지는 0', () {
    state.isNewestMessageVisible = (cid) => true;

    ws.emit(_messageEvent('c1', 'm1', 'other'));

    final reads = ws.reads();
    expect(reads.length, 1);
    expect(reads.first['channel_id'], 'c1');
    expect(reads.first['message_id'], 'm1');
    expect(badge('c1'), 0);
  });

  test('활성 채널 + 화면에 안 보이면 읽음 신호는 없고 배지는 1', () {
    state.isNewestMessageVisible = (cid) => false;

    ws.emit(_messageEvent('c1', 'm1', 'other'));

    expect(ws.reads(), isEmpty);
    expect(badge('c1'), 1);
  });

  test('대화창이 닫혀 있으면(훅이 null) 읽음 신호는 없고 배지는 1', () {
    // 콜드 스타트처럼 목록 화면인데 _activeChannelId 만 채워진 상태.
    state.isNewestMessageVisible = null;

    ws.emit(_messageEvent('c1', 'm1', 'other'));

    expect(ws.reads(), isEmpty);
    expect(badge('c1'), 1);
  });

  test('읽음 신호를 보낸 직후 서버가 보낸 낡은 unread(1) 로 배지가 되살아나지 않는다', () {
    state.isNewestMessageVisible = (cid) => true;

    ws.emit(_messageEvent('c1', 'm1', 'other'));
    expect(badge('c1'), 0);

    // 읽음 신호보다 먼저 계산된 서버 숫자 (아직 확인이 안 온 상태)
    ws.emit({'type': 'unread', 'channel_id': 'c1', 'count': 1});
    expect(badge('c1'), 0);

    // 서버 확인이 오면 플래그가 정리되고 0 이 확정된다.
    ws.emit({'type': 'unread', 'channel_id': 'c1', 'count': 0});
    expect(badge('c1'), 0);

    // 확인이 끝났으니 이후의 서버 숫자는 그대로 반영된다.
    ws.emit({'type': 'unread', 'channel_id': 'c1', 'count': 2});
    expect(badge('c1'), 2);
  });

  test('다른 채널의 unread 는 그대로 적용된다 (회귀 방지)', () {
    state.isNewestMessageVisible = (cid) => true;

    // 다른 채널의 메시지는 로컬 배지가 1 증가하고
    ws.emit(_messageEvent('c2', 'm9', 'other'));
    expect(badge('c2'), 1);
    expect(ws.reads(), isEmpty);

    // 서버 숫자도 그대로 적용된다.
    ws.emit({'type': 'unread', 'channel_id': 'c2', 'count': 5});
    expect(badge('c2'), 5);
  });

  test('markChannelRead 는 읽음 신호를 보내고 배지를 0 으로 만든다', () {
    state.markChannelRead('c1', messageId: 'm7');

    final reads = ws.reads();
    expect(reads.length, 1);
    expect(reads.first['channel_id'], 'c1');
    expect(reads.first['message_id'], 'm7');
    expect(badge('c1'), 0);
  });

  test('WS 가 다시 연결되면(hi) 읽음 확인 플래그가 비워진다', () {
    state.isNewestMessageVisible = (cid) => true;
    ws.emit(_messageEvent('c1', 'm1', 'other'));
    ws.emit({'type': 'unread', 'channel_id': 'c1', 'count': 1});
    expect(badge('c1'), 0);

    // 재연결 → 플래그 초기화
    ws.emit({'type': 'hello', 'user': {'id': 'me'}});
    ws.emit({'type': 'unread', 'channel_id': 'c1', 'count': 1});
    expect(badge('c1'), 1);
  });
}
