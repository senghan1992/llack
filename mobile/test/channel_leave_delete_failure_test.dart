import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/channel_info_dialog.dart';
import 'package:llack_mobile/widgets/app_snack_bar.dart';
import 'package:provider/provider.dart';

/// 채널 나가기 / 1:1 대화 삭제가 실패하면
/// 사용자에게 사유가 보이고 Unhandled exception 이 남지 않아야 한다.
class _FailingLeaveAppState extends AppState {
  @override
  Future<void> deleteDm(String channelId) async {
    throw Exception('서버 오류');
  }

  @override
  Future<void> leaveChannel(String channelId) async {
    throw Exception('서버 오류');
  }

  @override
  Future<List<Member>> membersForChannel(String channelId) async => const [];
}

Channel _channel({required bool isDm}) {
  return Channel(
    id: 'c1',
    workspaceId: 'w1',
    name: isDm ? '김민수' : 'general',
    kind: isDm ? 'dm' : 'channel',
    isPrivate: isDm,
    createdBy: 'u1',
    createdAt: DateTime(2026, 1, 1),
  );
}

/// 실제 앱과 똑같이 **다이얼로그로** 열고, 확인까지 진행한다.
Future<void> _openAndConfirm(WidgetTester tester, {required bool isDm}) async {
  final channel = _channel(isDm: isDm);

  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: _FailingLeaveAppState(),
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => ChannelInfoDialog(channel: channel),
                ),
                child: const Text('채널 정보 열기'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();

  await tester.tap(find.text('채널 정보 열기'));
  await tester.pumpAndSettle();

  await tester.tap(find.text(isDm ? '대화방 삭제' : '채널 나가기'));
  await tester.pumpAndSettle();

  // 확인 다이얼로그에서 확정
  await tester.tap(find.text(isDm ? '삭제' : '나가기'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('1:1 대화 삭제가 실패하면 사유가 보이고 예외가 남지 않는다', (tester) async {
    await _openAndConfirm(tester, isDm: true);

    expect(find.text('대화를 삭제하지 못했습니다'), findsOneWidget);
    // Unhandled exception 이 남지 않았는지 확인
    expect(tester.takeException(), isNull);
  });

  testWidgets('채널 나가기가 실패하면 사유가 보이고 예외가 남지 않는다', (tester) async {
    await _openAndConfirm(tester, isDm: false);

    expect(find.text('채널을 나가지 못했습니다'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('실패 안내는 루트 오버레이의 공용 스낵바로 보인다', (tester) async {
    await _openAndConfirm(tester, isDm: false);

    // 공용 스낵바(루트 오버레이에 직접 얹힘)
    expect(find.byType(AppSnackBar), findsOneWidget);
    // 루트 ScaffoldMessenger 경로의 스낵바는 쓰지 않는다
    expect(find.byType(SnackBar), findsNothing);
  });
}
