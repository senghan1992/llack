import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 선택 날짜를 지정할 수 있는 일정 대역.
class _AllDayAppState extends FakeAppState {
  _AllDayAppState(this.event, {required this.selectedDay});

  final ScheduleEvent event;
  final DateTime selectedDay;

  @override
  List<ScheduleEvent> get events => [event];

  @override
  DateTime get selectedDate => selectedDay;
}

/// 달력 칸(날짜 숫자) 안에 있는 점(5x5 원)의 개수
int _dotsInDayCell(WidgetTester tester, String dayNumber) {
  const dotConstraints = BoxConstraints.tightFor(width: 5, height: 5);
  final cell = find.ancestor(of: find.text(dayNumber), matching: find.byType(InkWell));
  return find
      .descendant(of: cell, matching: find.byType(Container))
      .evaluate()
      .where((e) => (e.widget as Container).constraints == dotConstraints)
      .length;
}

Future<void> _pumpSchedule(WidgetTester tester, AppState state) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
    ),
  );
  await tester.pump();
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('종일 일정은 시작 날짜에만 보인다 (다음 날 자정은 exclusive)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // 백엔드 규약: 종일 일정은 12일 00:00Z ~ "다음 날 자정"(exclusive)
    final event = ScheduleEvent(
      id: 'e_allday',
      workspaceId: 'w1',
      title: '분기 계획',
      startsAt: DateTime.utc(2026, 11, 12),
      endsAt: DateTime.utc(2026, 11, 13),
      allDay: true,
      createdBy: 'u1',
      createdAt: DateTime.utc(2026, 11, 1),
      updatedAt: DateTime.utc(2026, 11, 1),
    );

    // 1) 시작 날짜(=로컬 11월 12일)에는 목록에 보인다
    await _pumpSchedule(tester, _AllDayAppState(event, selectedDay: DateTime(2026, 11, 12)));
    expect(find.text('분기 계획'), findsOneWidget);

    // 달력 점도 시작 날짜(12일)에만 있다 → 목록과 달력 점이 같은 기준
    expect(_dotsInDayCell(tester, '12'), 1);
    expect(_dotsInDayCell(tester, '13'), 0);

    // 2) 다음 날(로컬 11월 13일)에는 목록에 보이지 않는다
    //    (endsAt 이 다음 날 자정(exclusive)이라 종료 날짜에 붙으면 이틀에 걸쳐 보인다)
    await _pumpSchedule(tester, _AllDayAppState(event, selectedDay: DateTime(2026, 11, 13)));
    expect(find.text('분기 계획'), findsNothing);

    // 달력 점은 여전히 시작 날짜에만 있다 (선택 날짜와 무관하게 같은 기준)
    expect(_dotsInDayCell(tester, '12'), 1);
    expect(_dotsInDayCell(tester, '13'), 0);
  });
}
