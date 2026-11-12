import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/main_shell.dart';
import 'package:provider/provider.dart';

/// 화면 밖(오프스크린) 탭의 위젯까지 세면 탭이 4개라 개수가 어긋나므로,
/// 실제로 보이는 앱바만 세기 위해 조상 중 Offstage 를 확인한다.
List<AppBar> _visibleAppBars(WidgetTester tester) {
  return tester.widgetList<AppBar>(find.byType(AppBar)).where((bar) {
    final element = tester.element(find.byWidget(bar));
    var offstage = false;
    element.visitAncestorElements((ancestor) {
      if (ancestor.widget is Offstage && (ancestor.widget as Offstage).offstage) {
        offstage = true;
        return false;
      }
      return true;
    });
    return !offstage;
  }).toList();
}

void main() {
  setUpAll(() async {
    // 일정 화면이 'ko_KR' 날짜 포맷을 쓰므로 로케일 데이터를 먼저 초기화한다
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('탭마다 앱바가 정확히 1개씩만 보인다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = AppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: MainShell()),
      ),
    );
    await tester.pump();

    for (var tab = 0; tab < 4; tab++) {
      state.goToTab(tab);
      await tester.pump();

      expect(_visibleAppBars(tester).length, 1, reason: 'tab $tab 에서 보이는 앱바 개수');
    }
  });

  testWidgets('모든 탭에서 워크스페이스/검색/아바타 진입점이 유지된다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = AppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: MainShell()),
      ),
    );
    await tester.pump();

    for (var tab = 0; tab < 4; tab++) {
      state.goToTab(tab);
      await tester.pump();

      // 워크스페이스 전환 칩
      expect(find.text('Llack'), findsOneWidget, reason: 'tab $tab 의 워크스페이스 칩');
      // 공통 액션: 검색 버튼(툴팁 포함), 아바타
      expect(find.byTooltip('빠른 검색'), findsOneWidget, reason: 'tab $tab 의 검색 버튼');
    }
  });

  testWidgets('탭 인덱스가 유지된다 (워크스페이스 전환 후에도)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = AppState();
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: MainShell()),
      ),
    );
    await tester.pump();

    state.goToTab(2);
    await tester.pump();
    expect(state.tabIndex.value, 2);

    // 워크스페이스 전환은 Core 의 selectWorkspace 가 담당하고 탭 인덱스는 건드리지 않는다
    await tester.pump();
    expect(state.tabIndex.value, 2);
    expect(_visibleAppBars(tester).length, 1);
  });
}
