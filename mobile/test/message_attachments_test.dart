import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/widgets/message_bubble.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

Message _messageWith(List<FileRef> attachments) {
  return Message(
    id: 'm1',
    channelId: 'c1',
    userId: 'u1',
    author: User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동'),
    body: '첨부 있음',
    createdAt: DateTime(2026, 1, 1, 10),
    attachments: attachments,
  );
}

Widget _bubble(Message message, {AppState? state}) {
  final bubble = Scaffold(
    body: MessageBubble(
      message: message,
      isMine: false,
      fileUrlResolver: (url) => 'https://example.test$url',
    ),
  );
  return MaterialApp(
    home: state == null ? bubble : ChangeNotifierProvider<AppState>.value(value: state, child: bubble),
  );
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('파일 첨부는 파일 칩으로 그려진다', (tester) async {
    await tester.pumpWidget(
      _bubble(
        _messageWith([
          FileRef(
            id: 'f1',
            name: 'report.pdf',
            url: '/api/v1/files/f1',
            mime: 'application/pdf',
            size: 2048,
          ),
        ]),
      ),
    );
    await tester.pump();

    expect(find.text('report.pdf'), findsOneWidget);
    expect(find.text('2.0 KB'), findsOneWidget);
  });

  testWidgets('이미지 첨부는 인증 헤더가 있으면 썸네일(Image) 로 그려진다', (tester) async {
    final state = AppState();
    await state.api.setTokens('test-token', 'test-refresh');

    await tester.pumpWidget(
      _bubble(
        _messageWith([
          FileRef(
            id: 'f2',
            name: 'pixel.png',
            url: '/api/v1/files/f2',
            mime: 'image/png',
            size: 77,
          ),
        ]),
        state: state,
      ),
    );
    await tester.pump();

    expect(find.byType(Image), findsOneWidget);
  });

  testWidgets('인증 헤더가 없으면 이미지도 파일 칩으로 fallback 한다', (tester) async {
    final state = AppState(); // 로그인 전이라 토큰이 없다.

    await tester.pumpWidget(
      _bubble(
        _messageWith([
          FileRef(
            id: 'f3',
            name: 'no-token.png',
            url: '/api/v1/files/f3',
            mime: 'image/png',
            size: 77,
          ),
        ]),
        state: state,
      ),
    );
    await tester.pump();

    expect(find.byType(Image), findsNothing);
    expect(find.text('no-token.png'), findsOneWidget);
  });

  testWidgets('첨부가 없으면 아무것도 그리지 않는다', (tester) async {
    await tester.pumpWidget(_bubble(_messageWith(const [])));
    await tester.pump();

    expect(find.byType(Image), findsNothing);
    expect(find.byType(InkWell), findsNothing);
  });
}
