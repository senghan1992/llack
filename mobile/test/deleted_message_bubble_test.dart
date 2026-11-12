import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/widgets/llack_avatar.dart';
import 'package:llack_mobile/widgets/message_bubble.dart';
import 'package:provider/provider.dart';

/// 대역 AppState (메시지 목록만 주입)
class _DeletedAppState extends AppState {
  _DeletedAppState(this.messages);

  final List<Message> messages;

  @override
  String? get activeChannelId => 'c1';

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
  Future<void> loadMessages(String channelId, {bool more = false}) async {}

  @override
  Future<void> loadNewerMessages(String channelId) async {}
}

Message _message({
  required String id,
  required String body,
  bool deleted = false,
  String authorId = 'u1',
  String authorName = '홍길동',
}) {
  return Message(
    id: id,
    channelId: 'c1',
    userId: authorId,
    author: User(id: authorId, email: '$authorId@hanbit.co.kr', name: authorName),
    body: body,
    createdAt: DateTime(2026, 1, 1, 10),
    deletedAt: deleted ? DateTime(2026, 1, 1, 11) : null,
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('삭제된 메시지에는 아바타도 작성자 이름도 없다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: _message(id: 'm1', body: '삭제됨', deleted: true),
            isMine: false,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(LlackAvatar), findsNothing);
    expect(find.text('홍길동'), findsNothing);
    expect(find.text('삭제된 메시지'), findsOneWidget);
    // 타임스탬프도 없다
    expect(find.text('10:00'), findsNothing);
  });

  testWidgets('내 메시지를 삭제해도 같은 컴팩트 한 줄이다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: _message(id: 'm1', body: '내 메시지', deleted: true, authorId: 'me'),
            isMine: true,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('삭제된 메시지'), findsOneWidget);
    expect(find.byType(LlackAvatar), findsNothing);
  });

  testWidgets('삭제된 메시지는 일반 메시지보다 높이가 작다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              MessageBubble(
                message: _message(id: 'm1', body: '삭제됨', deleted: true),
                isMine: false,
              ),
              MessageBubble(
                message: _message(id: 'm2', body: '정상 메시지입니다'),
                isMine: false,
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    final deleted = tester.getSize(find.byType(MessageDeletedMarker)).height;
    final normal = tester.getSize(find.byType(LlackAvatar)).height;
    expect(deleted, lessThan(normal));
  });

  testWidgets('삭제되지 않은 메시지는 아바타와 이름이 그대로 보인다', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: _message(id: 'm1', body: '정상 메시지입니다'),
            isMine: false,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(LlackAvatar), findsOneWidget);
    expect(find.text('홍길동'), findsOneWidget);
    expect(find.text('정상 메시지입니다'), findsOneWidget);
    expect(find.byType(MessageDeletedMarker), findsNothing);
  });

  testWidgets('연속으로 삭제된 메시지는 한 줄로 합쳐진다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DeletedAppState([
      _message(id: 'm1', body: '첫 메시지'),
      _message(id: 'm2', body: '삭제1', deleted: true),
      _message(id: 'm3', body: '삭제2', deleted: true),
      _message(id: 'm4', body: '삭제3', deleted: true),
      _message(id: 'm5', body: '마지막 메시지'),
    ]);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 하나로 합쳐져 한 줄만 보인다
    expect(find.text('삭제된 메시지 3개'), findsOneWidget);
    expect(find.byType(MessageDeletedMarker), findsOneWidget);
    // 삭제되지 않은 메시지는 그대로 보인다
    expect(find.text('첫 메시지'), findsOneWidget);
    expect(find.text('마지막 메시지'), findsOneWidget);
  });

  testWidgets('삭제된 메시지 하나만 있으면 "삭제된 메시지" 한 줄이다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DeletedAppState([
      _message(id: 'm1', body: '첫 메시지'),
      _message(id: 'm2', body: '삭제됨', deleted: true),
      _message(id: 'm3', body: '마지막 메시지'),
    ]);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('삭제된 메시지'), findsOneWidget);
    expect(find.byType(MessageDeletedMarker), findsOneWidget);
  });

  testWidgets('삭제된 메시지의 액션 시트에는 복사/수정/삭제가 없다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: _message(id: 'm1', body: '삭제됨', deleted: true, authorId: 'me'),
            isMine: true,
          ),
        ),
      ),
    );
    await tester.pump();

    // 롱프레스 → 액션 시트
    await tester.longPress(find.text('삭제된 메시지'));
    await tester.pumpAndSettle();

    // 시트는 열린다
    expect(find.text('스레드로 답글 달기'), findsOneWidget);
    // 무의미한 항목은 없다
    expect(find.text('메시지 복사'), findsNothing);
    expect(find.text('메시지 수정'), findsNothing);
    expect(find.text('메시지 삭제'), findsNothing);
  });
}
