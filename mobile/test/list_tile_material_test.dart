import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_tab.dart';
import 'package:provider/provider.dart';

/// ListTile 이 색이 있는 Container 안에 있으면 매 빌드마다
/// "ListTile background color or ink splashes may be invisible" 오류가 난다.
class _TileAppState extends AppState {
  _TileAppState(this._channels, this._dms, this._activeId);

  final List<Channel> _channels;
  final List<Channel> _dms;
  final String? _activeId;

  @override
  List<Channel> get channels => _channels;

  @override
  List<Channel> get dms => _dms;

  @override
  String? get activeChannelId => _activeId;
}

Channel _channel(String id, String name) => Channel(
      id: id,
      workspaceId: 'w1',
      name: name,
      kind: 'channel',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
    );

Channel _dm(String id, String name, User user) => Channel(
      id: id,
      workspaceId: 'w1',
      name: name,
      kind: 'dm',
      isPrivate: true,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
      dmUser: user,
    );

void main() {
  testWidgets('채널/DM 타일을 그려도 ListTile ink 오류가 발생하지 않는다', (tester) async {
    final state = _TileAppState(
      [_channel('c1', 'general'), _channel('c2', 'design')],
      [
        _dm(
          'd1',
          '김민수',
          User(id: 'u2', email: 'min@hanbit.co.kr', name: '김민수', title: '기획'),
        )
      ],
      // 선택된 채널이 있어야 배경색이 있는 경우(=오류가 나는 경우)가 재현된다.
      'c1',
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ChatTab())),
      ),
    );
    await tester.pump();

    // 타일이 실제로 그려졌는지 확인 (빈 화면이면 테스트가 의미가 없다).
    expect(find.byType(ListTile), findsNWidgets(3));

    // 빌드 중 보고된 오류를 모두 모은다.
    // (ListTile 오류는 FlutterError.reportError 로 올라오므로 takeException 으로 받는다)
    final errors = <String>[];
    for (var i = 0; i < 10; i++) {
      final error = tester.takeException();
      if (error == null) break;
      errors.add(error.toString());
    }

    expect(
      errors.join('\n'),
      isNot(contains('ink splashes may be invisible')),
      reason: 'ListTile 은 자기 Material 안에 있어야 ink 오류가 나지 않는다',
    );
  });
}
