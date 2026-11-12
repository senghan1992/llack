import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/widgets/message_bubble.dart';

/// 메시지 수정 다이얼로그의 TextEditingController 가
/// 다이얼로그를 닫으면 확실히 dispose 되는지 확인한다.
void main() {
  testWidgets('수정 다이얼로그를 닫으면 컨트롤러가 dispose 된다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final message = Message(
      id: 'm1',
      channelId: 'c1',
      userId: 'me',
      author: User(id: 'me', email: 'me@hanbit.co.kr', name: '나'),
      body: '원본 내용',
      createdAt: DateTime(2026, 1, 1, 10),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(message: message, isMine: true),
        ),
      ),
    );
    await tester.pump();

    // 롱프레스 → "메시지 수정"
    await tester.longPress(find.text('원본 내용'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('메시지 수정'));
    await tester.pumpAndSettle();

    expect(find.byType(TextField), findsOneWidget);
    final controller = tester.widget<TextField>(find.byType(TextField)).controller!;
    expect(controller, isNotNull);

    // 다이얼로그를 닫는다
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();

    expect(find.byType(TextField), findsNothing);

    // dispose 된 컨트롤러에 addListener 를 붙이면 FlutterError 가 난다.
    // (text getter 는 dispose 후에도 예외를 안 던지므로 addListener 로 확인한다)
    expect(
      () => controller.addListener(() {}),
      throwsFlutterError,
      reason: '수정 다이얼로그가 닫히면 컨트롤러가 dispose 되어야 한다',
    );
  });
}
