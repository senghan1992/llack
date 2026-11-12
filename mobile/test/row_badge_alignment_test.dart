import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/org/org_screen.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 참석자(자기 자신 포함)와 매우 긴 이름을 가진 구성원을 갖는 대역.
class _AttendeeAppState extends FakeAppState {
  _AttendeeAppState(this.event);

  final ScheduleEvent event;

  @override
  User? get currentUser => User(id: 'u1', email: 'me@x.com', name: '김현진');

  @override
  List<ScheduleEvent> get events => [event];

  @override
  List<Member> get members => [
        Member(user: User(id: 'u1', email: 'me@x.com', name: '김현진'), role: Role.owner),
        Member(user: User(id: 'u2', email: 'a@x.com', name: '박지민'), role: Role.member),
        Member(
          user: User(id: 'u3', email: 'b@x.com', name: '이름이 아주 길어서 말줄임되어야 하는 구성원입니다'),
          role: Role.member,
        ),
      ];
}

ScheduleEvent _event() {
  final now = DateTime.now();
  return ScheduleEvent(
    id: 'e1',
    workspaceId: 'w1',
    title: '주간 스탠드업',
    startsAt: now,
    endsAt: now.add(const Duration(hours: 1)),
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
    attendees: [
      // 자기 자신 ("나" pill 이 붙는 행)
      ScheduleAttendee(user: User(id: 'u1', email: 'me@x.com', name: '김현진'), response: EventResponse.accepted),
      ScheduleAttendee(user: User(id: 'u2', email: 'a@x.com', name: '박지민'), response: EventResponse.tentative),
      ScheduleAttendee(
        user: User(id: 'u3', email: 'b@x.com', name: '이름이 아주 길어서 말줄임되어야 하는 구성원입니다'),
        response: EventResponse.declined,
      ),
    ],
  );
}

/// 참석자 목록의 RSVP 배지(컨테이너) 영역
Rect _badgeRect(WidgetTester tester, String label) {
  final badge = find
      .ancestor(of: find.text(label).last, matching: find.byType(Container))
      .first;
  return tester.getRect(badge);
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('참석자 목록의 RSVP 배지는 모두 같은 열(행의 오른쪽 끝)에 있다 (§9-40)', (WidgetTester tester) async {
    const screenWidth = 411.0;
    tester.view.physicalSize = const Size(screenWidth * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _AttendeeAppState(_event());
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('주간 스탠드업'));
    await tester.pumpAndSettle();

    // "나" pill 이 있는 행 / 없는 행 / 이름이 아주 긴 행
    // (같은 문구가 일정 카드 쪽 칩에도 있으므로 시트(위에 뜬 것)의 것만 고른다)
    final accepted = _badgeRect(tester, '참석');
    final tentative = _badgeRect(tester, '미정');
    final declined = _badgeRect(tester, '불참');

    // 모두 같은 열이다
    expect(accepted.right, closeTo(tentative.right, 0.5));
    expect(tentative.right, closeTo(declined.right, 0.5));

    // 그리고 행의 오른쪽 끝에 붙어 있다 (시트 내용 여백 20)
    expect(accepted.right, closeTo(screenWidth - 20, 1));

    // 긴 이름 때문에 overflow 가 나지 않고, 배지도 화면 안에 있다
    expect(tester.takeException(), isNull);
    expect(declined.right, lessThanOrEqualTo(screenWidth));
  });

  testWidgets('조직도의 역할 라벨도 같은 열에 정렬된다 (§9-40)', (WidgetTester tester) async {
    const screenWidth = 411.0;
    tester.view.physicalSize = const Size(screenWidth * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _AttendeeAppState(_event());
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: OrgScreen())),
      ),
    );
    await tester.pump();

    // "나" pill 이 있는 행(소유자)과 없는 행(멤버)의 역할 라벨이 같은 열인지 확인
    final owner = tester.getRect(find.text('소유자'));
    final member = tester.getRect(find.text('멤버').first);

    expect(owner.right, closeTo(member.right, 0.5));
    expect(tester.takeException(), isNull);
  });
}
