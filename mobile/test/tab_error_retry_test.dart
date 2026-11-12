import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/org/org_screen.dart';
import 'package:llack_mobile/screens/projects/projects_screen.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 실제 폰 크기(411x914dp)로 맞춘다. 일정 화면처럼 세로로 긴 목록이 있어야
/// 목록 아래쪽 항목(오류 배너)까지 빌드되어 테스트할 수 있다.
void _usePhoneViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(411 * 3, 914 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Widget _wrap(AppState state, Widget child) {
  return ChangeNotifierProvider<AppState>.value(
    value: state,
    child: MaterialApp(home: child),
  );
}

void main() {
  setUpAll(() async {
    // 일정 화면이 'ko_KR' 날짜 포맷을 쓰므로 로케일 데이터를 먼저 초기화한다
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('일정 탭: 오류가 있으면 다시 시도 가 보인다', (WidgetTester tester) async {
    _usePhoneViewport(tester);
    final state = FakeAppState(eventsErrorMessage: '일정을 불러오지 못했습니다.');
    await tester.pumpWidget(_wrap(state, const ScheduleScreen()));
    await tester.pump();

    expect(find.text('일정을 불러오지 못했습니다.'), findsOneWidget);
    expect(find.text('등록된 일정이 없습니다'), findsNothing);

    final retry = find.text('다시 시도');
    expect(retry, findsOneWidget);
    await tester.ensureVisible(retry);
    await tester.tap(retry);
    await tester.pump();

    expect(state.eventsRetryCount, 1);
  });

  testWidgets('프로젝트 탭: 오류가 있으면 다시 시도 가 보인다', (WidgetTester tester) async {
    _usePhoneViewport(tester);
    final state = FakeAppState(projectsErrorMessage: '프로젝트를 불러오지 못했습니다.');
    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pump();

    expect(find.text('프로젝트를 불러오지 못했습니다.'), findsOneWidget);

    final retry = find.text('다시 시도');
    expect(retry, findsOneWidget);
    await tester.ensureVisible(retry);
    await tester.tap(retry);
    await tester.pump();

    expect(state.projectsRetryCount, 1);
  });

  testWidgets('프로젝트 탭: 카드 화면에서도 다시 시도가 보인다', (WidgetTester tester) async {
    final now = DateTime.now();
    final project = Project(
      id: 'p1',
      workspaceId: 'w1',
      name: '테스트 프로젝트',
      createdBy: 'u1',
      createdAt: now,
      updatedAt: now,
    );
    final state = FakeAppState(
      projectsErrorMessage: '프로젝트를 불러오지 못했습니다.',
      projects: [project],
      activeProject: project,
    );
    await tester.pumpWidget(_wrap(state, const ProjectsScreen()));
    await tester.pump();

    expect(find.text('프로젝트를 불러오지 못했습니다.'), findsOneWidget);

    final retry = find.text('다시 시도');
    expect(retry, findsOneWidget);
    await tester.ensureVisible(retry);
    await tester.tap(retry);
    await tester.pump();

    expect(state.projectsRetryCount, 1);
  });

  testWidgets('조직도 탭: 오류가 있으면 다시 시도 가 보인다', (WidgetTester tester) async {
    _usePhoneViewport(tester);
    final state = FakeAppState(orgErrorMessage: '조직도를 불러오지 못했습니다.');
    await tester.pumpWidget(_wrap(state, const OrgScreen()));
    await tester.pump();

    expect(find.text('조직도를 불러오지 못했습니다.'), findsOneWidget);

    final retry = find.text('다시 시도');
    expect(retry, findsOneWidget);
    await tester.ensureVisible(retry);
    await tester.tap(retry);
    await tester.pump();

    expect(state.orgRetryCount, 1);
  });

  testWidgets('오류가 없으면 빈 상태 문구가 보인다', (WidgetTester tester) async {
    _usePhoneViewport(tester);
    final state = FakeAppState();
    await tester.pumpWidget(_wrap(state, const ScheduleScreen()));
    await tester.pump();

    expect(find.text('다시 시도'), findsNothing);
    expect(find.text('등록된 일정이 없습니다'), findsOneWidget);
  });
}
