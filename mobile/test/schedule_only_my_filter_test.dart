import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:llack_mobile/theme/llack_colors.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// F-8: "나 일정만" 필터가 달력 점에 적용되지 않는다.
///
/// 실기: 필터를 켜면 그날 팀 일정만 있는 날에도 회색 점이 남아
/// "점을 보라니 일정 있다" 고 눌렀더니 목록은 비어 있었다.
///
/// 판정 로직을 순수 함수로 빼서(목록/점 공통) 단위 테스트하고,
/// 위젯 테스트로 달력 점과 범례가 필터를 따르는지 확인한다.

User _me() => User(id: 'me', email: 'me@hanbit.co.kr', name: '나');
User _other() => User(id: 'other', email: 'other@hanbit.co.kr', name: '남');

/// 11월 9일: 남의 일정 (나는 참석자 아님)
ScheduleEvent _teamEvent() => ScheduleEvent(
      id: 'e1',
      workspaceId: 'w1',
      title: '팀 회의',
      startsAt: DateTime(2026, 11, 9, 10),
      endsAt: DateTime(2026, 11, 9, 11),
      createdBy: 'other',
      createdAt: DateTime(2026, 11, 1),
      updatedAt: DateTime(2026, 11, 1),
      attendees: [ScheduleAttendee(user: _other(), response: EventResponse.accepted)],
    );

/// 11월 9일: 내가 만든 일정
ScheduleEvent _myEvent() => ScheduleEvent(
      id: 'e2',
      workspaceId: 'w1',
      title: '내 일정 제목',
      startsAt: DateTime(2026, 11, 9, 14),
      endsAt: DateTime(2026, 11, 9, 15),
      createdBy: 'me',
      createdAt: DateTime(2026, 11, 1),
      updatedAt: DateTime(2026, 11, 1),
    );

/// 11월 15일: 내가 참석자로 등록된 일정
ScheduleEvent _attendingEvent() => ScheduleEvent(
      id: 'e3',
      workspaceId: 'w1',
      title: '1:1',
      startsAt: DateTime(2026, 11, 15, 10),
      endsAt: DateTime(2026, 11, 15, 11),
      createdBy: 'other',
      createdAt: DateTime(2026, 11, 1),
      updatedAt: DateTime(2026, 11, 1),
      attendees: [ScheduleAttendee(user: _me(), response: EventResponse.accepted)],
    );

/// 11월 20일: 팀 일정만 있는 날 (나 일정만 필터 ON 에서는 점이 사라져야 한다)
ScheduleEvent _teamOnlyEvent() => ScheduleEvent(
      id: 'e4',
      workspaceId: 'w1',
      title: '전체 회의',
      startsAt: DateTime(2026, 11, 20, 10),
      endsAt: DateTime(2026, 11, 20, 11),
      createdBy: 'other',
      createdAt: DateTime(2026, 11, 1),
      updatedAt: DateTime(2026, 11, 1),
      attendees: [ScheduleAttendee(user: _other(), response: EventResponse.accepted)],
    );

class _ScheduleFilterAppState extends FakeAppState {
  _ScheduleFilterAppState({required this.onlyMine});

  final bool onlyMine;

  @override
  DateTime get selectedDate => DateTime(2026, 11, 9);

  @override
  bool get onlyMyEvents => onlyMine;

  @override
  User? get currentUser => _me();

  @override
  List<ScheduleEvent> get events => [_teamEvent(), _myEvent(), _attendingEvent(), _teamOnlyEvent()];
}

/// 달력(GridView) 안에 있는 원형 점만 찾는다. (범례 점은 바깥이라 제외된다)
Finder _calendarDots(Color? color) {
  return find.descendant(
    of: find.byType(GridView),
    matching: find.byWidgetPredicate(
      (w) =>
          w is Container &&
          w.decoration is BoxDecoration &&
          (w.decoration as BoxDecoration).shape == BoxShape.circle &&
          (color == null || (w.decoration as BoxDecoration).color == color),
    ),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  group('순수 판정 함수', () {
    final teamDay = DateTime(2026, 11, 9);
    final teamOnlyDay = DateTime(2026, 11, 20);

    test('"내 일정" 판정: 내가 만들었거나 내가 참석자면 내 일정이다', () {
      expect(isMyScheduleEvent(_myEvent(), 'me'), isTrue);
      expect(isMyScheduleEvent(_attendingEvent(), 'me'), isTrue);
      expect(isMyScheduleEvent(_teamEvent(), 'me'), isFalse);
      // 로그인 정보가 없으면 내 일정으로 치지 않는다
      expect(isMyScheduleEvent(_myEvent(), null), isFalse);
    });

    test('필터 OFF: 그날 일정을 모두 보여준다', () {
      final visible = visibleScheduleEvents(
        [_teamEvent(), _myEvent()],
        teamDay,
        onlyMyEvents: false,
        myId: 'me',
      );
      expect(visible.map((e) => e.id).toList(), ['e1', 'e2']);
    });

    test('필터 ON: 내 일정만 보여준다', () {
      final visible = visibleScheduleEvents(
        [_teamEvent(), _myEvent()],
        teamDay,
        onlyMyEvents: true,
        myId: 'me',
      );
      expect(visible.map((e) => e.id).toList(), ['e2']);
    });

    test('필터 ON: 남의 일정만 있는 날은 점을 그리지 않는다', () {
      final dot = calendarDotForDay(
        [_teamEvent()],
        teamDay,
        onlyMyEvents: true,
        myId: 'me',
      );
      expect(dot.show, isFalse);
      expect(dot.mine, isFalse);
    });

    test('필터 OFF: 남의 일정만 있는 날도 점(회색)을 그린다', () {
      final dot = calendarDotForDay(
        [_teamEvent()],
        teamDay,
        onlyMyEvents: false,
        myId: 'me',
      );
      expect(dot.show, isTrue);
      expect(dot.mine, isFalse);
    });

    test('필터 ON: 내 일정이 있는 날은 점(초록)을 그린다', () {
      final dot = calendarDotForDay(
        [_teamEvent(), _myEvent()],
        teamDay,
        onlyMyEvents: true,
        myId: 'me',
      );
      expect(dot.show, isTrue);
      expect(dot.mine, isTrue);
    });

    test('목록과 점의 판정이 항상 일치한다', () {
      for (final onlyMine in [false, true]) {
        for (final day in [DateTime(2026, 11, 9), DateTime(2026, 11, 15), teamOnlyDay]) {
          final events = [_teamEvent(), _myEvent(), _attendingEvent()];
          final visible = visibleScheduleEvents(events, day, onlyMyEvents: onlyMine, myId: 'me');
          final dot = calendarDotForDay(events, day, onlyMyEvents: onlyMine, myId: 'me');
          // 점이 있으면 목록에 최소 하나가 보인다. (목록이 비었는데 점이 있으면 안 된다)
          expect(dot.show, visible.isNotEmpty);
        }
      }
    });
  });

  group('화면', () {
    Future<void> pumpSchedule(WidgetTester tester, bool onlyMine) async {
      final state = _ScheduleFilterAppState(onlyMine: onlyMine);
      await tester.pumpWidget(
        ChangeNotifierProvider<AppState>.value(
          value: state,
          child: const MaterialApp(home: ScheduleScreen()),
        ),
      );
      await tester.pump();
    }

    testWidgets('필터 OFF: 팀 일정 날에도 회색 점이 있고 "팀 일정" 범례가 보인다', (tester) async {
      await pumpSchedule(tester, false);

      expect(find.text('팀 일정'), findsOneWidget);
      expect(find.text('내 일정'), findsOneWidget);

      // 11/9(내 일정), 11/15(내가 참석), 11/20(팀 일정만) → 점 3개
      expect(_calendarDots(null), findsNWidgets(3));
      // 팀 일정만 있는 11/20 은 회색 점
      expect(_calendarDots(LlackColors.muted), findsOneWidget);
    });

    testWidgets('필터 ON: "팀 일정" 범례가 숨겨지고, 팀 일정 날에는 점이 없다', (tester) async {
      await pumpSchedule(tester, true);

      // 범례에서 팀 일정 설명이 사라진다
      expect(find.text('팀 일정'), findsNothing);
      expect(find.text('내 일정'), findsOneWidget);

      // 달력에 회색(팀 일정) 점은 하나도 없다
      expect(_calendarDots(LlackColors.muted), findsNothing);
      // 내 일정이 있는 11/9(선택된 날 → 흰 점), 11/15(초록 점) 만 남는다
      expect(_calendarDots(null), findsNWidgets(2));
      expect(_calendarDots(LlackColors.accent), findsOneWidget);
    });

    testWidgets('필터 ON: 목록에는 내 일정만 보인다 (팀 일정은 빠짐)', (tester) async {
      final state = _ScheduleFilterAppState(onlyMine: true);
      await tester.pumpWidget(
        ChangeNotifierProvider<AppState>.value(
          value: state,
          child: const MaterialApp(home: ScheduleScreen()),
        ),
      );
      await tester.pump();

      // 선택된 날(11/9)에는 내 일정이 있으므로 목록에 보인다
      expect(find.text('내 일정 제목'), findsOneWidget);
    });
  });
}
