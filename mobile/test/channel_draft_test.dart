import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 채널별 임시저장(draft)을 확인하기 위한 대역.
///
/// 앱에서는 `selectChannel` 로 채널을 바꾸지만, 테스트에서는
/// 활성 채널을 직접 지정해서 화면을 다시 그리게 한다.
class _DraftAppState extends FakeAppState {
  _DraftAppState(this.channelList);

  List<Channel> channelList;

  /// 지금 보고 있는 채널 id
  String? activeId;

  /// 보낸 메시지 (임시저장을 지우는지 확인하기 위해)
  final List<String> sentBodies = [];

  @override
  List<Channel> get channels => channelList;

  @override
  Channel? get activeChannel {
    for (final c in channelList) {
      if (c.id == activeId) return c;
    }
    return null;
  }

  @override
  String? get activeChannelId => activeId;

  @override
  List<Message> get activeMessages => const [];

  @override
  User? get currentUser => User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진');

  @override
  bool get hasMoreNewerMessages => false;

  @override
  Future<bool> sendMessage(String body, {List<String>? attachmentIds}) async {
    sentBodies.add(body);
    return true;
  }

  /// 채널을 바꾼다.
  void switchTo(String channelId) {
    activeId = channelId;
    notifyListeners();
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

/// 입력창에 들어 있는 글
String _composerText(WidgetTester tester) {
  final field = tester.widget<TextField>(find.byType(TextField).first);
  return field.controller?.text ?? '';
}

Widget _app(AppState state) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: const MaterialApp(home: Scaffold(body: ChatScreen())),
  );
}

void main() {
  testWidgets('채널을 바꾸고 돌아오면 작성 중인 글이 복원된다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DraftAppState([_channel('c1', 'general'), _channel('c2', 'random')]);
    state.activeId = 'c1';

    await tester.pumpWidget(_app(state));
    await tester.pump();

    // c1 에 글자를 쓴다
    await tester.enterText(find.byType(TextField).first, '작성 중인 글');
    await tester.pump();

    // 코어에도 임시저장된다
    expect(state.draftFor('c1'), '작성 중인 글');

    // 다른 채널로 옮긴다
    state.switchTo('c2');
    await tester.pump();
    await tester.pump();

    // c2 에는 임시저장이 없으니 입력창이 비어 있다
    expect(_composerText(tester), '');

    // 다시 c1 로 돌아오면 쓰던 글이 그대로 있다
    state.switchTo('c1');
    await tester.pump();
    await tester.pump();

    expect(_composerText(tester), '작성 중인 글');
    expect(state.draftFor('c1'), '작성 중인 글');
  });

  testWidgets('메시지를 보내면 임시저장이 지워진다', (tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DraftAppState([_channel('c1', 'general'), _channel('c2', 'random')]);
    state.activeId = 'c1';

    await tester.pumpWidget(_app(state));
    await tester.pump();

    await tester.enterText(find.byType(TextField).first, '보낼 글');
    await tester.pump();
    expect(state.draftFor('c1'), '보낼 글');

    // 보내기
    await tester.tap(find.byTooltip('전송'));
    await tester.pump();
    await tester.pump();

    expect(state.sentBodies, ['보낼 글']);
    // 보냈으면 임시저장은 남지 않는다
    expect(state.draftFor('c1'), isNull);
  });
}
