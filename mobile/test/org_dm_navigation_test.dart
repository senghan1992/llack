import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/chat/chat_screen.dart';
import 'package:llack_mobile/screens/org/org_screen.dart';
import 'package:llack_mobile/theme/llack_colors.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 조직도에서 1:1 대화를 열 때의 동작을 확인하기 위한 대역.
///
/// 실패를 흉내내려면 openDm 이 예외를 던져야 한다.
class _DmAppState extends FakeAppState {
  _DmAppState({this.shouldFail = false});

  final bool shouldFail;

  /// 대화창이 열린 횟수 (ChatNavigator 경로를 탔는지 확인)
  int openDmCount = 0;

  @override
  User? get currentUser => User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진');

  /// 조직도 목록에 표시될 구성원 (자기 자신 포함)
  @override
  List<Member> get members => [
        Member(
          user: User(id: 'u2', email: 'other@example.com', name: '이채원'),
          role: Role.member,
        ),
        Member(
          user: User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진'),
          role: Role.owner,
        ),
      ];

  @override
  Future<Channel> openDm(String targetUserId) async {
    openDmCount++;
    if (shouldFail) {
      throw Exception('자신과의 1:1 대화는 만들 수 없습니다.');
    }
    return _projectChannel();
  }

  Channel _projectChannel() {
    return Channel(
      id: 'dm_1',
      workspaceId: 'w1',
      name: 'DM',
      kind: 'dm',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime.now(),
    );
  }
}

void main() {
  setUp(() {
    // SnackBar 는 floating 으로 떠서 테스트 환경에서 화면을 벗어나지 않는다
  });

  testWidgets('조직도의 1:1 대화 버튼이 대화창을 여는 경로를 탄다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DmAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: OrgScreen()),
      ),
    );
    await tester.pump();

    // 구성원 목록의 1:1 대화 버튼을 누른다
    final dmButton = find.byTooltip('1:1 대화');
    expect(dmButton, findsWidgets);
    await tester.tap(dmButton.first);
    await tester.pumpAndSettle();

    // 대화창이 열린다 (ChatNavigator 경로)
    expect(state.openDmCount, 1);
    // ChatScreen 이 떠야 한다 (기존에는 아무 화면도 바뀌지 않았다)
    expect(find.byType(ChatScreen), findsOneWidget);
  });

  testWidgets('조직도의 "나" 배지가 일정 상세 시트와 같은 모양이다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DmAppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: OrgScreen()),
      ),
    );
    await tester.pump();

    // 자기 자신 옆에 "나" 배지가 보인다
    expect(find.text('나'), findsOneWidget);

    // 일정 상세 시트와 동일한 모양 (padding 5/1 · radius 4 · w700 · accentSoft/accentDeep)
    final pill = tester.widget<Container>(
      find.ancestor(of: find.text('나'), matching: find.byType(Container)).first,
    );
    expect(pill.padding, const EdgeInsets.symmetric(horizontal: 5, vertical: 1));
    expect((pill.decoration! as BoxDecoration).borderRadius, BorderRadius.circular(4));
    expect((pill.decoration! as BoxDecoration).color, LlackColors.accentSoft);
    final label = tester.widget<Text>(find.text('나'));
    expect(label.style?.fontWeight, FontWeight.w700);
    expect(label.style?.color, LlackColors.accentDeep);
  });

  testWidgets('대화를 열지 못하면 사유를 스낵바로 알려준다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _DmAppState(shouldFail: true);
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: OrgScreen()),
      ),
    );
    await tester.pump();

    final dmButton = find.byTooltip('1:1 대화');
    await tester.tap(dmButton.first);
    await tester.pumpAndSettle();

    expect(state.openDmCount, 1);
    // 실패 사유가 스낵바로 보인다 (조용히 사라지지 않는다)
    expect(find.textContaining('대화를 열지 못했습니다'), findsOneWidget);
  });
}
