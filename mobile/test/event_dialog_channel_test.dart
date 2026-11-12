import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/event_dialog.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 채널 목록을 바꿀 수 있는 대역.
class _ChannelAppState extends FakeAppState {
  List<Channel> channelList = [];

  @override
  List<Channel> get channels => channelList;

  /// 상태 변경을 알린다 (목록이 사라진 상황을 재현하기 위해)
  void refresh() => notifyListeners();
}

Channel _channel(String id, String name) {
  return Channel(
    id: id,
    workspaceId: 'w1',
    name: name,
    kind: 'channel',
    isPrivate: false,
    createdBy: 'u1',
    createdAt: DateTime.now(),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('선택한 채널이 사라져도 새 일정 대화상자가 assertion 으로 죽지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _ChannelAppState()..channelList = [_channel('c1', 'general')];
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: MaterialApp(home: Scaffold(body: EventDialog(initialDate: DateTime.now()))),
      ),
    );
    await tester.pump();

    // "general" 채널을 고른다
    await tester.tap(find.byType(DropdownButtonFormField<String?>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('# general').last);
    await tester.pumpAndSettle();

    // 그 채널이 목록에서 사라진다 (다른 사람이 삭제 / 워크스페이스 전환)
    state.channelList = [];
    state.refresh();
    await tester.pumpAndSettle();

    // 예전에는 "There should be exactly one item with [DropdownButton]'s value" 로 빨간 화면이 되었다
    expect(tester.takeException(), isNull);
  });
}
