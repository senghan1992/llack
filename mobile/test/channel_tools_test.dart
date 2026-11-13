import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/channel_info_dialog.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 채널 설정(이름·주제 수정 · 삭제)과 사람 추가, "최신 메시지" 버튼을 확인한다.
class _ChannelToolsAppState extends FakeAppState {
  _ChannelToolsAppState(this.channelList, {this.messages = const []});

  List<Channel> channelList;
  List<Message> messages;

  /// updateChannel 으로 넘긴 값
  String? updatedName;
  String? updatedTopic;
  String? updatedPurpose;

  /// deleteChannel 을 불렀는지
  bool deleteCalled = false;

  /// addChannelMember 로 넘긴 사람 id
  String? addedUserId;

  @override
  List<Channel> get channels => channelList;

  @override
  Channel? get activeChannel {
    for (final c in channelList) {
      if (c.id == 'c1') return c;
    }
    return null;
  }

  @override
  String? get activeChannelId => 'c1';

  @override
  List<Message> get activeMessages => messages;

  @override
  User? get currentUser => User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진');

  @override
  bool get hasMoreNewerMessages => false;

  /// 워크스페이스 구성원 (이 채널에 있는 사람 + 없는 사람)
  @override
  List<Member> get members => [
        Member(user: User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진'), role: Role.owner),
        Member(user: User(id: 'u2', email: 'lee@hanbit.co.kr', name: '이채원'), role: Role.member),
      ];

  @override
  Future<List<Member>> membersForChannel(String channelId) async => [
        Member(user: User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진'), role: Role.owner),
      ];

  @override
  Future<bool> updateChannel({
    required String channelId,
    String? name,
    String? topic,
    String? purpose,
  }) async {
    updatedName = name;
    updatedTopic = topic;
    updatedPurpose = purpose;
    return true;
  }

  @override
  Future<bool> deleteChannel(String channelId) async {
    deleteCalled = true;
    return true;
  }

  @override
  Future<bool> addChannelMember(String channelId, String userId) async {
    addedUserId = userId;
    return true;
  }
}

Channel _channel(String id, String name) {
  return Channel(
    id: id,
    workspaceId: 'w1',
    name: name,
    kind: 'channel',
    isPrivate: false,
    createdBy: 'u1',
    createdAt: DateTime(2026, 1, 1),
  );
}

Message _message(int index) {
  return Message(
    id: 'm$index',
    channelId: 'c1',
    userId: 'u1',
    author: User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진'),
    body: '메시지 $index',
    createdAt: DateTime(2026, 1, 1, 10, index),
  );
}

/// 채널 정보 다이얼로그를 연다.
Future<void> _openInfoDialog(WidgetTester tester, AppState state) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => ChannelInfoDialog(channel: _infoChannel),
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
}

final _infoChannel = _channel('c1', 'general');

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('채널 설정에서 이름과 주제를 고쳐 저장한다', (tester) async {
    final state = _ChannelToolsAppState([_infoChannel]);
    await _openInfoDialog(tester, state);

    // 설정 시트를 연다
    await tester.tap(find.byTooltip('채널 설정'));
    await tester.pumpAndSettle();

    expect(find.text('채널 설정'), findsOneWidget);

    // 이름과 주제를 고친다
    await tester.enterText(find.byType(TextField).first, '새이름');
    await tester.enterText(find.byType(TextField).at(1), '새 주제');
    await tester.pump();

    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();

    expect(state.updatedName, '새이름');
    expect(state.updatedTopic, '새 주제');
  });

  testWidgets('채널 삭제는 확인을 거쳐야 한다', (tester) async {
    final state = _ChannelToolsAppState([_infoChannel]);
    await _openInfoDialog(tester, state);

    await tester.tap(find.byTooltip('채널 설정'));
    await tester.pumpAndSettle();

    // 삭제 버튼을 누르면 확인 다이얼로그가 열린다
    await tester.tap(find.text('채널 삭제'));
    await tester.pumpAndSettle();
    expect(state.deleteCalled, isFalse);

    await tester.tap(find.text('삭제'));
    await tester.pumpAndSettle();

    expect(state.deleteCalled, isTrue);
  });

  testWidgets('채널에 사람이 없으면 후보를 보여주고 추가한다', (tester) async {
    final state = _ChannelToolsAppState([_infoChannel]);
    await _openInfoDialog(tester, state);

    await tester.tap(find.text('사람 추가'));
    await tester.pumpAndSettle();

    // 채널에 없는 사람만 후보로 보인다
    // (김현진은 이미 채널에 있어서 후보에 없다)
    expect(find.text('이채원'), findsOneWidget);
    expect(find.text('추가'), findsOneWidget);

    await tester.tap(find.text('추가'));
    await tester.pumpAndSettle();

    expect(state.addedUserId, 'u2');
  });

  testWidgets('과거를 보고 있으면 "최신 메시지" 버튼이 보인다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ChannelToolsAppState(
      [_infoChannel],
      messages: List.generate(40, (i) => _message(i)),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 최신 구간에서는 버튼이 없다
    expect(find.text('최신 메시지'), findsNothing);

    // 과거 쪽으로 스크롤한다
    await tester.drag(find.byType(ListView), const Offset(0, 600));
    await tester.pumpAndSettle();

    expect(find.text('최신 메시지'), findsOneWidget);

    // 누르면 최신으로 간다
    await tester.tap(find.text('최신 메시지'));
    await tester.pumpAndSettle();

    expect(find.text('최신 메시지'), findsNothing);
  });
}
