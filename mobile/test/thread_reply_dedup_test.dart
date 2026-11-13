import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 스레드 답글이 HTTP 응답과 WS 로 두 경로로 들어와도 1개로만 보여야 한다 (§9-44).

User _user() => User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동');

Message _root() => Message(
      id: 'root1',
      channelId: 'c1',
      userId: 'u1',
      author: _user(),
      body: '원본 메시지',
      createdAt: DateTime(2026, 1, 1, 10),
    );

Message _reply(String id) => Message(
      id: id,
      channelId: 'c1',
      userId: 'u1',
      author: _user(),
      body: 'thread test reply',
      parentId: 'root1',
      createdAt: DateTime(2026, 1, 1, 11),
    );

Map<String, dynamic> _wsEvent(Message message) => {
      'type': 'message.created',
      'message': {
        'id': message.id,
        'channel_id': message.channelId,
        'user_id': message.userId,
        'author': {'id': message.userId, 'email': 'a@hanbit.co.kr', 'name': '홍길동'},
        'body': message.body,
        'parent_id': message.parentId,
        'created_at': message.createdAt.toIso8601String(),
      },
    };

/// HTTP 응답을 직접 제어할 수 있는 가짜 API.
class _FakeApi extends ApiService {
  final List<Completer<Message>> pending = [];

  @override
  Future<List<Message>> getReplies(String messageId, {int limit = 100}) async => [];

  @override
  Future<Message> sendMessage({
    required String channelId,
    required String body,
    String? parentId,
    String? replyToId,
    bool inline = false,
    List<String>? attachmentIds,
  }) {
    final completer = Completer<Message>();
    pending.add(completer);
    return completer.future;
  }
}

/// WS 로 들어오는 이벤트를 직접 쏠 수 있는 가짜 소켓.
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

  Future<void> openThread() async {
    state.openThread(_root());
    await Future<void>.delayed(Duration.zero);
  }

  setUp(() {
    api = _FakeApi();
    ws = _FakeWsService();
    state = AppState(api: api, ws: ws);
  });

  test('WS 가 먼저 도착해도 답글은 1개로만 보인다', () async {
    await openThread();
    final reply = _reply('r1');

    // 1) WS 'message.created' 가 먼저 도착
    ws.emit(_wsEvent(reply));
    expect(state.threadReplies.length, 1);

    // 2) 그 뒤 HTTP 응답이 도착
    final sending = state.sendReply('thread test reply');
    await Future<void>.delayed(Duration.zero);
    api.pending.single.complete(reply);
    await sending;

    expect(state.threadReplies.length, 1);
    expect(state.threadReplies.single.id, 'r1');
  });

  test('HTTP 응답이 먼저 도착해도 WS 로 늘어나지 않는다', () async {
    await openThread();
    final reply = _reply('r1');

    // 1) HTTP 응답이 먼저 도착
    final sending = state.sendReply('thread test reply');
    await Future<void>.delayed(Duration.zero);
    api.pending.single.complete(reply);
    await sending;
    expect(state.threadReplies.length, 1);

    // 2) 그 뒤 WS 이벤트
    ws.emit(_wsEvent(reply));
    expect(state.threadReplies.length, 1);
    expect(state.threadReplies.single.id, 'r1');
  });

  test('여러 번 보내면 그만큼 정확히 N 개로 보인다', () async {
    await openThread();
    final sending1 = state.sendReply('첫 번째');
    await Future<void>.delayed(Duration.zero);
    api.pending[0].complete(_reply('r1'));
    await sending1;

    final sending2 = state.sendReply('두 번째');
    await Future<void>.delayed(Duration.zero);
    api.pending[1].complete(_reply('r2'));
    await sending2;

    expect(state.threadReplies.map((r) => r.id), ['r1', 'r2']);
  });

  test('같은 답글이 WS 로 두 번 도착해도 1개다', () async {
    await openThread();
    final reply = _reply('r1');
    ws.emit(_wsEvent(reply));
    ws.emit(_wsEvent(reply));
    expect(state.threadReplies.length, 1);
  });
}
