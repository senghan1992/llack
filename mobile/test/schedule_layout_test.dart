import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:llack_mobile/theme/llack_colors.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 선택 날짜를 지정할 수 있는 일정 대역.
class _ScheduleAppState extends FakeAppState {
  _ScheduleAppState({required this.selectedDay});

  final DateTime selectedDay;

  @override
  DateTime get selectedDate => selectedDay;

  @override
  List<ScheduleEvent> get events => [];
}

Future<void> _pumpSchedule(WidgetTester tester, AppState state, {required double width}) async {
  tester.view.physicalSize = Size(width * 3, 914 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
    ),
  );
  await tester.pump();
}

/// 달력 칸(날짜 숫자가 들어 있는 셀)의 높이
double _dayCellHeight(WidgetTester tester, String dayNumber) {
  final cell = find.ancestor(of: find.text(dayNumber), matching: find.byType(InkWell)).first;
  return tester.getSize(cell).height;
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('달력 칸 높이는 44dp 로 고정된다 (가로모드)', (WidgetTester tester) async {
    await _pumpSchedule(
      tester,
      _ScheduleAppState(selectedDay: DateTime(2026, 11, 9)),
      width: 900,
    );

    // 가로모드에서 칸이 폭과 함께 커지지 않는다 (§9-34)
    expect(_dayCellHeight(tester, '9'), closeTo(44, 1));

    // delegate 설정도 고정 높이여야 한다
    final grid = tester.widget<GridView>(find.byType(GridView));
    final delegate = grid.gridDelegate as SliverGridDelegateWithFixedCrossAxisCount;
    expect(delegate.mainAxisExtent, 44);
  });

  testWidgets('세로모드에서도 달력 칸 높이는 기존과 같은 수준이다', (WidgetTester tester) async {
    await _pumpSchedule(
      tester,
      _ScheduleAppState(selectedDay: DateTime(2026, 11, 9)),
      width: 411,
    );

    // 세로모드 기존 높이 ≈ 41.6dp → 44dp 로 바꿔도 시각적 차이는 거의 없다
    expect(_dayCellHeight(tester, '9'), closeTo(44, 1));
    expect(_dayCellHeight(tester, '9'), inInclusiveRange(40, 46));
  });

  testWidgets('달력 제목과 선택된 칸은 선택 날짜의 달을 따른다 (§9-36)', (WidgetTester tester) async {
    await _pumpSchedule(
      tester,
      _ScheduleAppState(selectedDay: DateTime(2026, 12, 15)),
      width: 411,
    );

    // 달력 제목이 선택 날짜의 달(12월)이다
    expect(find.text('2026년 12월'), findsOneWidget);
    expect(find.text('2026년 11월'), findsNothing);

    // 그 달의 선택된 칸(15일)이 강조된다
    final cell = find.ancestor(of: find.text('15'), matching: find.byType(InkWell)).first;
    final selectedBox = tester.widgetList<Container>(
      find.descendant(of: cell, matching: find.byType(Container)),
    );
    expect(
      selectedBox.any(
        (c) => c.decoration is BoxDecoration &&
            (c.decoration as BoxDecoration).color == LlackColors.accent,
      ),
      isTrue,
      reason: '선택된 날짜 칸이 강조되어야 한다',
    );
  });
}
