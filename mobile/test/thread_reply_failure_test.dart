import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/thread_screen.dart';
import 'package:provider/provider.dart';

/// 스레드 답글 전송이 실패하면(스레드가 이미 닫혔거나 서버 오류)
/// 입력창의 글자가 되살아오고 실패 스낵바가 떠야 한다.
class _FailingReplyAppState extends AppState {
  _FailingReplyAppState(this._root);

  final Message _root;

  @override
  Message? get threadRoot => _root;

  @override
  List<Message> get threadReplies => const [];

  @override
  Future<bool> sendReply(String body) async => false;
}

void main() {
  testWidgets('스레드 답글 전송이 실패하면 글자가 되살아오고 실패를 알린다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final root = Message(
      id: 'm1',
      channelId: 'c1',
      userId: 'u1',
      author: User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동'),
      body: '원본 메시지',
      createdAt: DateTime(2026, 1, 1, 10),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: _FailingReplyAppState(root),
        child: MaterialApp(home: ThreadScreen(rootMessage: root)),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '답글입니다');
    await tester.pump();
    await tester.tap(find.byTooltip('전송'));
    await tester.pumpAndSettle();

    // 실패했으므로 입력창의 글자가 그대로 남아 있어야 한다.
    expect(find.text('답글입니다'), findsOneWidget);

    // 실패를 사용자에게 알려준다.
    expect(find.text('전송에 실패했습니다. 다시 시도해주세요.'), findsOneWidget);
  });
}
