import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/schedule/schedule_screen.dart';
import 'package:llack_mobile/theme/llack_colors.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 일정이 있는 워크스페이스를 흉내내는 대역.
class _EventAppState extends FakeAppState {
  _EventAppState(this.event, {this.selectedDateOverride});

  final ScheduleEvent event;

  /// 선택된 날짜 (기본값은 코어의 "오늘")
  final DateTime? selectedDateOverride;

  @override
  DateTime get selectedDate => selectedDateOverride ?? super.selectedDate;

  @override
  List<ScheduleEvent> get events => [event];

  @override
  List<Member> get members => [
        Member(user: User(id: 'u1', email: 'me@x.com', name: '김현진'), role: Role.owner),
        Member(user: User(id: 'u2', email: 'a@x.com', name: '이채원'), role: Role.member),
        Member(user: User(id: 'u3', email: 'b@x.com', name: '박지민'), role: Role.member),
      ];

  @override
  User? get currentUser => User(id: 'u1', email: 'me@x.com', name: '김현진');

  @override
  Future<bool> rsvpEvent(String eventId, EventResponse response) async => true;
}

const String _longDescription =
    '월별 정산이 한눈에 들어오는 화면을 만든다.\n'
    '이번 분기 목표는 결제 처리 시간 단축과 정산 대시보드 개편이다.\n'
    '세부 항목은 별도 문서 참고.';

ScheduleEvent _event({bool includeSelf = false}) {
  final now = DateTime.now();
  return ScheduleEvent(
    id: 'e1',
    workspaceId: 'w1',
    title: '정산 데스크톱 화면',
    description: _longDescription,
    location: '2층 디자이너룸',
    startsAt: now,
    endsAt: now.add(const Duration(hours: 1)),
    createdBy: 'u1',
    createdAt: now,
    updatedAt: now,
    attendees: [
      if (includeSelf)
        ScheduleAttendee(
          user: User(id: 'u1', email: 'me@x.com', name: '김현진'),
          response: EventResponse.accepted,
        ),
      ScheduleAttendee(
        user: User(id: 'u2', email: 'a@x.com', name: '이채원'),
        response: EventResponse.accepted,
      ),
      ScheduleAttendee(
        user: User(id: 'u3', email: 'b@x.com', name: '박지민'),
        response: EventResponse.tentative,
      ),
    ],
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('ko_KR', null);
  });

  testWidgets('일정 카드를 탭하면 상세 시트가 뜨고 참석자/설명 전체가 보인다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _EventAppState(_event());
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    // 카드를 탭한다
    await tester.tap(find.text('정산 데스크톱 화면'));
    await tester.pumpAndSettle();

    // 상세 시트가 열렸다
    expect(find.text('참석자 (2명)'), findsOneWidget);
    // 참석자 목록 (이름 + RSVP 상태)
    expect(find.text('이채원'), findsOneWidget);
    expect(find.text('박지민'), findsOneWidget);
    // RSVP 라벨은 카드의 칩(1) + 상세 시트의 배지(1) = 2건
    expect(find.text('참석'), findsNWidgets(2));
    expect(find.text('미정'), findsNWidgets(2));
    // 장소/작성자 (장소는 카드에도 있으므로 2건)
    expect(find.text('2층 디자이너룸'), findsNWidgets(2));
    expect(find.textContaining('작성자: 김현진'), findsOneWidget);
    // 생성자에게 수정·삭제 버튼이 보인다
    expect(find.widgetWithText(OutlinedButton, '수정'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, '삭제'), findsOneWidget);

    // 설명은 시트에서 잘리지 않는다 (카드는 2줄로 자른다)
    final descriptionTexts = tester.widgetList<Text>(find.text(_longDescription));
    expect(descriptionTexts.any((t) => t.maxLines == null), isTrue, reason: '상세 시트에서는 설명 전체가 보인다');
    expect(descriptionTexts.any((t) => t.maxLines == 2), isTrue, reason: '카드는 2줄로 잘린다');
  });

  testWidgets('UTC 로 저장된 일정은 로컬 날짜 기준으로 카드에 뜬다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // UTC 로 저장된 일정: 2026-11-09T19:00:00Z → 이 기기(로컬)로는 11월 10일 04:00
    final utcStart = DateTime.utc(2026, 11, 9, 19);
    final localDay = utcStart.toLocal();
    final event = ScheduleEvent(
      id: 'e_utc',
      workspaceId: 'w1',
      title: 'UTC 저장 일정',
      startsAt: utcStart,
      endsAt: utcStart.add(const Duration(hours: 1)),
      createdBy: 'u1',
      createdAt: utcStart,
      updatedAt: utcStart,
    );

    final state = _EventAppState(event, selectedDateOverride: localDay);
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    // 로컬 날짜(11월 10일)를 선택하면 그 날짜의 일정으로 묶여야 보인다
    expect(find.text('UTC 저장 일정'), findsOneWidget);

    // 상세 시트도 같은(로컬) 날짜를 보여준다
    await tester.tap(find.text('UTC 저장 일정'));
    await tester.pumpAndSettle();
    // (기기의 시간대에 따라 로컬 날짜가 달라지므로 직접 계산한 날짜를 본다)
    expect(
      find.textContaining('${localDay.year}년 ${localDay.month}월 ${localDay.day}일'),
      findsOneWidget,
    );
  });

  testWidgets('참석자 목록의 "나" 배지는 이름 바로 뒤에 온다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    // 자기 자신이 참석자에 포함된 일정
    final event = _event(includeSelf: true);
    final state = _EventAppState(event);
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('정산 데스크톱 화면'));
    await tester.pumpAndSettle();

    // 이름 → "나" 배지 → (오른쪽 끝) RSVP 배지 순서여야 한다
    final nameX = tester.getCenter(find.text('김현진')).dx;
    final meX = tester.getCenter(find.text('나')).dx;
    final responseX = tester.getCenter(find.text('참석').last).dx;

    expect(meX, greaterThan(nameX), reason: '"나" 배지는 이름 뒤에 있어야 한다');
    expect(meX, lessThan(responseX), reason: 'RSVP 배지는 오른쪽 끝에 있어야 한다');

    // 배지가 서로 겹치지 않는다
    final meRect = tester.getRect(find.text('나'));
    final responseRect = tester.getRect(find.text('참석').last);
    expect(meRect.right, lessThanOrEqualTo(responseRect.left), reason: '"나" 배지와 RSVP 배지가 겹치면 안 된다');

    // 모양은 조직도의 "나" 배지와 동일해야 한다 (padding 5/1 · radius 4 · w700)
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

  testWidgets('RSVP 칩을 탭해도 상세 시트는 열리지 않는다', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(411 * 3, 914 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    final state = _EventAppState(_event());
    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: ScheduleScreen())),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('미정'));
    await tester.pumpAndSettle();

    // 상세 시트가 뜨지 않아야 한다
    expect(find.text('참석자 (2명)'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
