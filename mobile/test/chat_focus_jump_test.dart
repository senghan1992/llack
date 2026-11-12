import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/widgets/message_bubble.dart';
import 'package:provider/provider.dart';

/// 검색 결과로 점프했을 때 대상 메시지가 화면에 보이고 강조되는지 확인한다.
class _FocusAppState extends AppState {
  _FocusAppState(
    this.messages, {
    this.focusId,
    this.errorMessage,
    this.ignoreClear = false,
  });

  final List<Message> messages;
  final String? focusId;
  final String? errorMessage;

  /// pending 을 지우지 않는 core 흉내 (무한 루프 재현용)
  final bool ignoreClear;

  /// pending 을 지우라고 요청한 횟수
  int clearCount = 0;

  bool _focusCleared = false;
  bool _errorCleared = false;

  @override
  Channel? get activeChannel => Channel(
        id: 'c1',
        workspaceId: 'w1',
        name: 'general',
        kind: 'channel',
        isPrivate: false,
        createdBy: 'u1',
        createdAt: DateTime(2026, 1, 1),
      );

  @override
  List<Message> get activeMessages => messages;

  @override
  User? get currentUser => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

  @override
  String? get pendingFocusMessageId => _focusCleared ? null : focusId;

  @override
  String? get focusErrorMessage => _errorCleared ? null : errorMessage;

  @override
  void clearPendingFocusMessageId() {
    clearCount++;
    if (!ignoreClear) _focusCleared = true;
  }

  @override
  void clearFocusErrorMessage() {
    _errorCleared = true;
  }

  @override
  bool get hasMoreNewerMessages => false;
}

Message _message(String id, String body, int index) {
  return Message(
    id: id,
    channelId: 'c1',
    userId: 'u1',
    author: User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동'),
    body: body,
    createdAt: DateTime(2026, 1, 1, 10, index),
  );
}

List<Message> _messages(int count) {
  return List.generate(count, (i) => _message('m$i', '메시지 $i', i));
}

Widget _app(AppState state) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: const MaterialApp(home: Scaffold(body: ChatScreen())),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('점프 대상 메시지가 화면에 보이고 강조된다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    const targetIndex = 20;
    final state = _FocusAppState(
      _messages(40),
      focusId: 'm$targetIndex',
    );

    await tester.pumpWidget(_app(state));
    await tester.pumpAndSettle();

    // 대상 메시지가 화면(뷰포트) 안에 보인다
    final rect = tester.getRect(find.text('메시지 $targetIndex'));
    final screen = tester.view.physicalSize / tester.view.devicePixelRatio;
    expect(rect.top, greaterThanOrEqualTo(0));
    expect(rect.bottom, lessThanOrEqualTo(screen.height));

    // 강조가 적용된 말풍선이다
    final bubble = tester.widget<MessageBubble>(
      find.ancestor(
        of: find.text('메시지 $targetIndex'),
        matching: find.byType(MessageBubble),
      ),
    );
    expect(bubble.highlight, isTrue);

    // 대상이 아닌 메시지는 강조되지 않는다
    final bubbles = tester.widgetList<MessageBubble>(find.byType(MessageBubble));
    expect(bubbles.where((b) => b.highlight).map((b) => b.message.id), ['m$targetIndex']);
  });

  testWidgets('점프가 끝나면 pending 대상이 해제된다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _FocusAppState(_messages(40), focusId: 'm20');

    await tester.pumpWidget(_app(state));
    await tester.pumpAndSettle();

    // 코어가 pending 을 지우면 재점프가 일어나지 않는다
    expect(state.pendingFocusMessageId, isNull);
  });

  testWidgets('점프 대상이 목록에 없으면 사유를 알리고 pending 을 정리한다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // 목록에 없는 id 로 점프를 시도한다 (삭제된 메시지)
    final state = _FocusAppState(_messages(10), focusId: '없는-메시지');

    await tester.pumpWidget(_app(state));
    await tester.pumpAndSettle();

    expect(
      find.text('해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.'),
      findsOneWidget,
    );
    // pending 을 지워야 build 가 다시 시도하지 않는다
    expect(state.clearCount, 1);
  });

  testWidgets('코어가 pending 을 지우지 않아도 같은 대상을 계속 시도하지 않는다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // core 가 pending 을 지워주지 않는 최악의 상황
    final state = _FocusAppState(
      _messages(10),
      focusId: '없는-메시지',
      ignoreClear: true,
    );

    await tester.pumpWidget(_app(state));
    await tester.pumpAndSettle();

    // 실패 처리는 한 번만 일어난다 (무한 루프 없음)
    expect(state.clearCount, 1);
    expect(
      find.text('해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.'),
      findsOneWidget,
    );
  });

  testWidgets('점프 실패 사유가 스낵바로 보인다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _FocusAppState(
      _messages(10),
      errorMessage: '해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.',
    );

    await tester.pumpWidget(_app(state));
    await tester.pumpAndSettle();

    expect(
      find.text('해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.'),
      findsOneWidget,
    );
  });
}
