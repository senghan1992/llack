import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:provider/provider.dart';

/// 대역 AppState.
/// - 안읽음 카운터를 가진 채널
/// - markChannelRead 호출 횟수 기록
class _ReadAppState extends AppState {
  _ReadAppState({this.unreadCount = 1});

  final int unreadCount;

  int markReadCount = 0;
  int loadNewerCount = 0;

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
        unreadCount: unreadCount,
      );

  @override
  List<Message> get activeMessages => List.generate(
        40,
        (i) => Message(
          id: 'm$i',
          channelId: 'c1',
          userId: 'u1',
          author: User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동'),
          body: '메시지 $i',
          createdAt: DateTime(2026, 1, 1, 10, i),
        ),
      );

  @override
  User? get currentUser => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');

  @override
  void markChannelRead(String channelId, {String? messageId}) {
    markReadCount++;
  }

  @override
  Future<void> loadMessages(String channelId, {bool more = false}) async {}

  @override
  Future<void> loadNewerMessages(String channelId) async {
    loadNewerCount++;
  }
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('대화창이 열려 있는 동안에만 "최신 구간인가" 훅이 등록된다', (tester) async {
    final state = _ReadAppState();

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 열려 있는 동안 훅이 살아 있다
    expect(state.isNewestMessageVisible, isNotNull);
    // 처음에는 최신 구간(맨 아래)에 있다
    expect(state.isNewestMessageVisible!('c1'), isTrue);

    // 대화창을 닫으면(화면 교체) 훅이 해제된다
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: SizedBox.shrink())),
      ),
    );
    await tester.pump();

    expect(state.isNewestMessageVisible, isNull);
  });

  testWidgets('최신 구간으로 되돌아오면 안읽음이 남아 있을 때만 읽음 처리한다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ReadAppState(unreadCount: 1);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 손가락을 아래로 쓸어 이전 메시지 쪽으로 스크롤 (최신 구간에서 벗어남)
    await tester.drag(find.byType(ListView), const Offset(0, 600));
    await tester.pumpAndSettle();
    expect(state.isNewestMessageVisible!('c1'), isFalse, reason: '최신 구간에서 벗어나야 한다');
    expect(state.markReadCount, 0, reason: '최신 구간이 아니면 읽음 처리하지 않는다');

    // 다시 최신 구간으로 내려옴
    await tester.drag(find.byType(ListView), const Offset(0, -3000));
    await tester.pumpAndSettle();
    expect(state.isNewestMessageVisible!('c1'), isTrue, reason: '다시 최신 구간에 도착해야 한다');

    expect(state.markReadCount, 1);
  });

  testWidgets('안읽음이 없으면 최신 구간으로 돌아와도 읽음 신호를 보내지 않는다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ReadAppState(unreadCount: 0);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    await tester.drag(find.byType(ListView), const Offset(0, 600));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, -3000));
    await tester.pumpAndSettle();

    expect(state.markReadCount, 0, reason: '이미 읽음 처리된 채널은 다시 신호를 보내지 않는다');
  });
}
