import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/widgets/message_bubble.dart';
import 'package:provider/provider.dart';

/// 멤버 목록만 가진 AppState 대역
class _MembersAppState extends AppState {
  _MembersAppState(this.members);

  @override
  final List<Member> members;
}

Message _messageWithReactions(List<Reaction> reactions) {
  return Message(
    id: 'm1',
    channelId: 'c1',
    userId: 'u1',
    author: User(id: 'u1', email: 'a@hanbit.co.kr', name: '작성자'),
    body: '반응해 주세요',
    createdAt: DateTime(2026, 1, 1, 10),
    reactions: reactions,
  );
}

Widget _bubble(Message message, {AppState? state, void Function(Reaction)? onShow}) {
  final bubble = Scaffold(
    body: MessageBubble(
      message: message,
      isMine: false,
      onShowReactionParticipants: onShow,
    ),
  );
  return MaterialApp(
    home: state == null ? bubble : ChangeNotifierProvider<AppState>.value(value: state, child: bubble),
  );
}

void main() {
  testWidgets('반응 칩을 길게 누르면 반응한 사람 이름을 보여준다', (tester) async {
    final state = _MembersAppState([
      Member(user: User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동'), role: Role.member),
      Member(user: User(id: 'u2', email: 'b@hanbit.co.kr', name: '김영희'), role: Role.member),
    ]);

    await tester.pumpWidget(
      _bubble(
        _messageWithReactions([
          Reaction(emoji: '👍', count: 2, userIds: ['u1', 'u2'], me: false),
        ]),
        state: state,
      ),
    );
    await tester.pump();

    await tester.longPress(find.text('👍'));
    await tester.pumpAndSettle();

    expect(find.text('홍길동'), findsOneWidget);
    expect(find.text('김영희'), findsOneWidget);
  });

  testWidgets('이름을 모르면 짧게 자른 id 로 보여준다', (tester) async {
    await tester.pumpWidget(
      _bubble(
        _messageWithReactions([
          Reaction(emoji: '🎉', count: 1, userIds: ['abcdefgh1234'], me: false),
        ]),
      ),
    );
    await tester.pump();

    await tester.longPress(find.text('🎉'));
    await tester.pumpAndSettle();

    expect(find.textContaining('abcdefgh'), findsOneWidget);
  });

  testWidgets('onShowReactionParticipants 를 주면 그쪽이 대신 보여준다', (tester) async {
    Reaction? shown;

    await tester.pumpWidget(
      _bubble(
        _messageWithReactions([
          Reaction(emoji: '🔥', count: 1, userIds: ['u1'], me: false),
        ]),
        onShow: (reaction) => shown = reaction,
      ),
    );
    await tester.pump();

    await tester.longPress(find.text('🔥'));
    await tester.pumpAndSettle();

    expect(shown?.emoji, '🔥');
    // 기본 시트는 열리지 않는다
    expect(find.textContaining('반응한 사람'), findsNothing);
  });
}
