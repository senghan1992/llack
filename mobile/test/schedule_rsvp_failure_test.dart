import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// RSVP 실패를 흉내내는 대역.
class _RsvpAppState extends FakeAppState {
  _RsvpAppState(this.event);

  final ScheduleEvent event;
  int rsvpCalls = 0;

  @override
  List<ScheduleEvent> get events => [event];

  @override
  Future<bool> rsvpEvent(String eventId, EventResponse response) async {
    rsvpCalls++;
    // 실패를 알린다 (코어의 시그니처: 성공 true / 실패 false)
    return false;
  }
}

ScheduleEvent _event() {
  final now = DateTime.now();
  return ScheduleEvent(
    id: 'e1',
    workspaceId: 'w1',
    title: '주간 회의',
    startsAt: now,
    endsAt: now.add(const Duration(hours: 1)),
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
    myResponse: EventResponse.accepted,
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('RSVP 변경이 실패하면 사유를 스낵바로 알려준다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _RsvpAppState(_event());
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    // "미정" 칩을 누른다
    final chip = find.text('미정');
    expect(chip, findsOneWidget);
    await tester.tap(chip);
    await tester.pumpAndSettle();

    expect(state.rsvpCalls, 1);
    // 실패 이유가 사라지지 않고 안내된다
    expect(find.text('참석 여부를 바꾸지 못했습니다'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
