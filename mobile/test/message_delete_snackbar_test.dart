import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/screens/chat/message_actions.dart';
import 'package:llack_mobile/widgets/message_composer.dart';
import 'package:provider/provider.dart';

/// 삭제 SnackBar 가 메시지 영역(ChatScreen 의 중첩 messenger)에만 그려져야 composer 를 덮지 않는다.
class _ChatAppState extends AppState {
  _ChatAppState(this._channel, this._messages);

  final Channel _channel;
  final List<Message> _messages;

  @override
  Channel? get activeChannel => _channel;

  @override
  List<Message> get activeMessages => _messages;

  @override
  User? get currentUser => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

  @override
  Future<void> deleteMessage(String messageId, String channelId) async {}

  @override
  Future<bool> undoDeleteMessage(String messageId, String channelId) async => true;
}

/// 삭제 SnackBar 의 유지 시간 / 되돌리기 affordance 회귀 테스트.
///
/// - persist 가 false 여야 duration 이 적용된다 (액션이 있으면 자동 닫힘이 꺼진다)
/// - 유지 시간은 10초다 (5초였을 때는 취소 버튼을 누르기 전에 사라져버렸다)
///
/// Flutter 의 SnackBar 는 `persist = persist ?? action != null` 이라
/// "실행 취소" 액션이 있는 SnackBar 는 duration 이 무시되고 자동으로 닫히지 않는다.
void main() {
  setUpAll(() async {
    // 채팅 화면의 날짜 구분 헤더가 'ko_KR' 날짜 포맷을 쓰므로 로케일 데이터를 먼저 초기화한다
    await initializeDateFormatting('ko_KR', null);
  });
  testWidgets('삭제 SnackBar 는 persist 가 false 다 (액션이 있어도 duration 이 적용됨)', (tester) async {
    final bar = MessageActions.buildDeleteSnackBar(onUndo: () {});

    expect(bar.persist, isFalse, reason: 'persist: false 가 아니면 스낵바가 닫히지 않는다');
    // 되돌릴 시간을 충분히 주어야 한다 (Material 가이드라인: 액션이 붙은 스낵바는 10초)
    expect(bar.duration, greaterThanOrEqualTo(const Duration(seconds: 10)));
    expect(bar.duration, const Duration(seconds: 10));
    expect(bar.action, isNotNull, reason: '"실행 취소" 액션은 유지되어야 한다');
    expect(bar.action!.label, '실행 취소');
  });

  testWidgets('삭제 SnackBar 는 10초 뒤에 사라진다', (tester) async {
    late ScaffoldMessengerState messenger;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) {
              messenger = ScaffoldMessenger.of(ctx);
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );

    messenger.showSnackBar(MessageActions.buildDeleteSnackBar(onUndo: () {}));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400)); // 등장 애니메이션
    expect(find.text('메시지를 삭제했습니다'), findsOneWidget);

    // 10초가 지나면 자동으로 닫혀야 한다.
    await tester.pump(const Duration(seconds: 11));
    await tester.pumpAndSettle();
    expect(find.text('메시지를 삭제했습니다'), findsNothing);
  });

  testWidgets('삭제 SnackBar 는 사라지기 전까지 계속 살아 있고 "실행 취소" 를 누를 수 있다', (tester) async {
    late ScaffoldMessengerState messenger;
    var undone = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) {
              messenger = ScaffoldMessenger.of(ctx);
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );

    messenger.showSnackBar(
      MessageActions.buildDeleteSnackBar(onUndo: () => undone = true),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    // 6초가 지나도 아직 살아 있어야 한다 (5초였을 때 사라져버리던 구간)
    await tester.pump(const Duration(seconds: 6));
    await tester.pumpAndSettle();
    expect(find.text('메시지를 삭제했습니다'), findsOneWidget);

    // 사라지기 전에 취소 버튼을 누르면 되돌리기 콜백이 호출된다
    await tester.tap(find.text('실행 취소'));
    await tester.pump();
    expect(undone, isTrue);
  });

  testWidgets('삭제 SnackBar 의 "실행 취소" 를 누르면 되돌리기 콜백이 호출된다', (tester) async {
    late ScaffoldMessengerState messenger;
    var undone = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) {
              messenger = ScaffoldMessenger.of(ctx);
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );

    messenger.showSnackBar(
      MessageActions.buildDeleteSnackBar(onUndo: () => undone = true),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.tap(find.text('실행 취소'));
    await tester.pump();

    expect(undone, isTrue);
  });

  testWidgets('삭제 SnackBar 가 composer 를 덮지 않는다', (tester) async {
    // 폰 크기로 맞춰야 롱프레스 메뉴(바텀시트)가 화면 안에 들어온다.
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final me = User(id: 'me', email: 'me@hanbit.co.kr', name: '나');
    final channel = Channel(
      id: 'c1',
      workspaceId: 'w1',
      name: 'general',
      kind: 'channel',
      isPrivate: false,
      createdBy: 'me',
      createdAt: DateTime(2026, 1, 1),
    );
    final message = Message(
      id: 'm1',
      channelId: 'c1',
      userId: 'me',
      author: me,
      body: '삭제될 메시지',
      createdAt: DateTime(2026, 1, 1, 10),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: _ChatAppState(channel, [message]),
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pump();

    // 롱프레스 → "메시지 삭제"
    await tester.longPress(find.text('삭제될 메시지'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('메시지 삭제'));
    await tester.pumpAndSettle();

    expect(find.byType(SnackBar), findsOneWidget);

    final snackRect = tester.getRect(find.byType(SnackBar));
    final composerRect = tester.getRect(find.byType(MessageComposer));
    expect(
      snackRect.bottom,
      lessThanOrEqualTo(composerRect.top + 1),
      reason: 'SnackBar 는 메시지 영역에만 그려져야 composer 를 덮지 않는다',
    );
  });
}
