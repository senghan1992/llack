import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';
import 'package:llack_mobile/widgets/animated_message_entry.dart';
import 'package:llack_mobile/widgets/message_composer.dart';
import 'package:llack_mobile/widgets/typing_indicator.dart';
import 'package:provider/provider.dart';

User _me() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

Workspace _workspace() => Workspace(
      id: 'w1',
      name: '한빛',
      slug: 'hanbit',
      createdAt: DateTime(2026, 1, 1),
    );

Channel _channel(String id, String name) => Channel(
      id: id,
      workspaceId: 'w1',
      name: name,
      kind: 'channel',
      isPrivate: false,
      createdBy: 'me',
      createdAt: DateTime(2026, 1, 1),
    );

Map<String, dynamic> _messageEvent({
  required String channelId,
  required String messageId,
  required String userId,
  required String name,
  required String body,
}) =>
    {
      'type': 'message.created',
      'message': {
        'id': messageId,
        'channel_id': channelId,
        'user_id': userId,
        'author': {'id': userId, 'email': '$userId@hanbit.co.kr', 'name': name},
        'body': body,
        'created_at': DateTime(2026, 1, 1, 12, 0).toIso8601String(),
      },
    };

class _FakeApi extends ApiService {
  List<Message> initialMessages = [];

  @override
  Future<Session> login(String email, String password) async => Session(
        accessToken: 'tok',
        refreshToken: 'ref',
        user: _me(),
        workspace: _workspace(),
      );

  @override
  Future<List<Workspace>> getWorkspaces() async => [_workspace()];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
        workspace: _workspace(),
        channels: [_channel('c1', 'general'), _channel('c2', 'random')],
        dms: const [],
        members: const [],
        me: _me(),
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
  }) async =>
      (List<Message>.from(initialMessages), false, false);
}

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

  void emit(Map<String, dynamic> event) => handler?.call(event);
}

Widget _wrapChat(AppState state) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: const MaterialApp(home: Scaffold(body: ChatScreen())),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  test('formatTypingUsers 는 인원 수에 맞는 한국어 안내 문구를 돌려준다', () {
    expect(formatTypingUsers(const []), '');
    expect(formatTypingUsers(const ['김현진']), '김현진님이 입력 중입니다');
    expect(formatTypingUsers(const ['김현진', '박지민']), '김현진, 박지민님이 입력 중입니다');
    expect(formatTypingUsers(const ['김현진', '박지민', '이채원']), '김현진, 박지민 외 1명이 입력 중입니다');
    expect(
      formatTypingUsers(const ['김현진', '박지민', '이채원', '최수아']),
      '김현진, 박지민 외 2명이 입력 중입니다',
    );
  });

  testWidgets('AppState 실시간 타이핑 수신, 5초 자동 만료, 메시지 도착/오프라인 정리 및 채널 전환', (tester) async {
    final api = _FakeApi();
    final ws = _FakeWsService();
    final state = AppState(api: api, ws: ws);
    addTearDown(state.dispose);

    await state.login('me@hanbit.co.kr', 'password');
    state.selectChannel('c1');
    await tester.pump();

    var notifyCount = 0;
    state.addListener(() => notifyCount++);

    // 본인 typing 은 무시된다
    ws.emit({
      'type': 'typing',
      'channel_id': 'c1',
      'user_id': 'me',
      'name': '나',
      'on': true,
    });
    expect(state.currentTypingUsers, isEmpty);

    // 다른 사람 typing 수신
    ws.emit({
      'type': 'typing',
      'channel_id': 'c1',
      'user_id': 'u2',
      'name': '김현진',
      'on': true,
    });
    expect(state.currentTypingUsers, ['김현진']);
    expect(notifyCount, greaterThan(0));

    // 5초 경과 시 타이머가 만료시켜 UI에 통지한다
    final beforeExpireNotify = notifyCount;
    await tester.pump(const Duration(seconds: 5, milliseconds: 50));
    expect(state.currentTypingUsers, isEmpty);
    expect(notifyCount, greaterThan(beforeExpireNotify));

    // 다시 입력 중 → 메시지 도착 시 즉시 타이핑 해제 및 애니메이션 대상 등록
    ws.emit({
      'type': 'typing',
      'channel_id': 'c1',
      'user_id': 'u2',
      'name': '김현진',
      'on': true,
    });
    expect(state.currentTypingUsers, ['김현진']);

    ws.emit(_messageEvent(
      channelId: 'c1',
      messageId: 'm_live',
      userId: 'u2',
      name: '김현진',
      body: '방금 보낸 메시지',
    ));
    expect(state.currentTypingUsers, isEmpty);
    expect(state.shouldAnimateMessage('m_live'), isTrue);
    state.markMessageAnimated('m_live');
    expect(state.shouldAnimateMessage('m_live'), isFalse);

    // 오프라인 전환 시 전 채널 타이핑 제거
    ws.emit({
      'type': 'typing',
      'channel_id': 'c1',
      'user_id': 'u3',
      'name': '박지민',
      'on': true,
    });
    expect(state.currentTypingUsers, ['박지민']);
    ws.emit({'type': 'presence', 'user_id': 'u3', 'presence': 'offline'});
    expect(state.currentTypingUsers, isEmpty);

    // 채널 전환 시 이전 채널 입력 중 상태에 off 전송
    ws.sent.clear();
    state.sendTyping(true, 'c1');
    state.selectChannel('c2');
    await tester.pump();
    expect(
      ws.sent.any((p) => p['type'] == 'typing' && p['channel_id'] == 'c1' && p['on'] == false),
      isTrue,
    );
  });

  testWidgets('ChatScreen 에서 타이핑 표시는 입력창 아래에 나타나고 해제 후 정착한다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final api = _FakeApi()
      ..initialMessages = [
        Message(
          id: 'm1',
          channelId: 'c1',
          userId: 'u2',
          author: User(id: 'u2', email: 'u2@hanbit.co.kr', name: '김현진'),
          body: '기존 메시지',
          createdAt: DateTime(2026, 1, 1, 10, 0),
        ),
      ];
    final ws = _FakeWsService();
    final state = AppState(api: api, ws: ws);
    addTearDown(state.dispose);

    await state.login('me@hanbit.co.kr', 'password');
    state.selectChannel('c1');

    await tester.pumpWidget(_wrapChat(state));
    await tester.pumpAndSettle();

    // 기존 메시지는 입장 애니메이션 대상이 아니다
    final initialEntries = tester.widgetList<AnimatedMessageEntry>(find.byType(AnimatedMessageEntry));
    expect(initialEntries.every((w) => !w.animate), isTrue);

    // 상대방 입력 시작
    ws.emit({
      'type': 'typing',
      'channel_id': 'c1',
      'user_id': 'u2',
      'name': '김현진',
      'on': true,
    });
    await tester.pump(const Duration(milliseconds: 220));

    final typingFinder = find.text('김현진님이 입력 중입니다');
    expect(typingFinder, findsOneWidget);

    // 입력창(TextField) 아래에 배치되어야 한다
    final inputRect = tester.getRect(find.byType(TextField).first);
    final typingRect = tester.getRect(typingFinder);
    expect(typingRect.top, greaterThanOrEqualTo(inputRect.bottom));

    // 상대방이 새 메시지를 전송하면 타이핑 표시는 사라지고 새 메시지는 애니메이션으로 등장한다
    ws.emit(_messageEvent(
      channelId: 'c1',
      messageId: 'm2',
      userId: 'u2',
      name: '김현진',
      body: '새로 올라오는 메시지',
    ));
    await tester.pump();
    expect(find.text('새로 올라오는 메시지'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.text('김현진님이 입력 중입니다'), findsNothing);
    expect(find.text('새로 올라오는 메시지'), findsOneWidget);
  });

  testWidgets('MessageComposer 는 커서 이동을 무시하고, 스로틀 및 빈 입력/전송 시 off 를 보낸다',
      (tester) async {
    final typingEvents = <bool>[];
    var sendCalls = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageComposer(
            onTyping: typingEvents.add,
            onSend: (_) async {
              sendCalls++;
              return true;
            },
          ),
        ),
      ),
    );

    // 커서(selection)만 바꾸면 onTyping 을 부르지 않는다
    tester.testTextInput.updateEditingValue(
      const TextEditingValue(text: '', selection: TextSelection.collapsed(offset: 0)),
    );
    await tester.pump();
    expect(typingEvents, isEmpty);

    // 첫 글자 입력 → 즉시 true
    await tester.enterText(find.byType(TextField), '안');
    await tester.pump();
    expect(typingEvents, [true]);

    // 2초 이내 추가 입력 → 스로틀되어 중복 true 를 보내지 않는다
    await tester.pump(const Duration(milliseconds: 500));
    await tester.enterText(find.byType(TextField), '안녕');
    await tester.pump();
    expect(typingEvents, [true]);

    // 2초 경과 후 입력 → heartbeat true 전송
    await tester.pump(const Duration(seconds: 2));
    await tester.enterText(find.byType(TextField), '안녕하');
    await tester.pump();
    expect(typingEvents, [true, true]);

    // 3초 무입력 → 자동 false 전송
    await tester.pump(const Duration(seconds: 3, milliseconds: 50));
    expect(typingEvents, [true, true, false]);

    // 다시 입력 후 전부 지우면 즉시 false
    await tester.enterText(find.byType(TextField), '다시');
    await tester.pump();
    expect(typingEvents, [true, true, false, true]);
    await tester.enterText(find.byType(TextField), '');
    await tester.pump();
    expect(typingEvents, [true, true, false, true, false]);

    // 입력 후 전송하면 가짜 true 재전송 없이 false 만 나온다
    await tester.enterText(find.byType(TextField), '보낼게');
    await tester.pump();
    expect(typingEvents, [true, true, false, true, false, true]);

    await tester.tap(find.byTooltip('전송'));
    await tester.pumpAndSettle();
    expect(sendCalls, 1);
    expect(typingEvents, [true, true, false, true, false, true, false]);
  });
}
