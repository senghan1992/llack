import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/screens/chat/chat_tab.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 공개 채널 참가(채널 찾아보기)를 확인하기 위한 대역.
class _JoinAppState extends FakeAppState {
  _JoinAppState(this.channelList);

  List<Channel> channelList;

  /// 참가 요청 횟수
  int joinCount = 0;

  /// 열기로 선택한 채널 id
  String? selectedChannelId;

  @override
  List<Channel> get channels => channelList;

  @override
  Channel? get activeChannel {
    for (final c in channelList) {
      if (c.id == selectedChannelId) return c;
    }
    return null;
  }

  @override
  String? get activeChannelId => selectedChannelId;

  @override
  void selectChannel(String channelId, {String? focusMessageId}) {
    selectedChannelId = channelId;
  }

  @override
  Future<Channel> joinChannel(String channelId) async {
    joinCount++;
    var name = channelId;
    for (final c in channelList) {
      if (c.id == channelId) name = c.name;
    }
    final joined = _channel(channelId, name, isMember: true);
    channelList = [
      for (final c in channelList) if (c.id == channelId) joined else c,
    ];
    notifyListeners();
    return joined;
  }
}

Channel _channel(String id, String name, {bool isMember = true}) {
  return Channel(
    id: id,
    workspaceId: 'w1',
    name: name,
    kind: 'channel',
    isPrivate: false,
    createdBy: 'u1',
    createdAt: DateTime(2026, 1, 1),
    isMember: isMember,
  );
}

void main() {
  testWidgets('아직 속하지 않은 공개 채널에 참가하면 목록에 들어간다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _JoinAppState([
      _channel('c1', 'general'),
      _channel('c2', 'design', isMember: false),
    ]);

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatTab())),
      ),
    );
    await tester.pump();

    // "채널 찾아보기" 를 연다
    await tester.tap(find.text('채널 찾아보기'));
    await tester.pumpAndSettle();

    // 아직 속하지 않은 공개 채널이 보인다
    expect(find.text('#design'), findsOneWidget);

    // 참가한다
    await tester.tap(find.text('참가'));
    await tester.pumpAndSettle();

    expect(state.joinCount, 1);
    // 참가한 채널은 목록에 들어가고 "속한 채널"이 된다
    final joined = state.channels.firstWhere((c) => c.id == 'c2');
    expect(joined.isMember, isTrue);
    // 참가한 채널을 열어 준다
    expect(state.selectedChannelId, 'c2');
    expect(find.byType(ChatScreen), findsOneWidget);
  });
}
