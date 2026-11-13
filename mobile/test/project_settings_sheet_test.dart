import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/projects/project_settings_sheet.dart';
import 'package:provider/provider.dart';

import 'support/fake_app_state.dart';

/// 프로젝트 설정 대역.
class _ProjectSettingsAppState extends FakeAppState {
  _ProjectSettingsAppState({this.project});

  final Project? project;

  @override
  List<Member> get members => [
        Member(user: User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진'), role: Role.member),
        Member(user: User(id: 'u2', email: 'min@hanbit.co.kr', name: '이채원'), role: Role.member),
      ];

  String? updatedName;
  String? updatedDescription;
  bool? updatedArchived;
  String? deletedProjectId;
  String? addedMemberId;
  String? removedMemberId;

  @override
  Future<bool> updateProject({
    required String projectId,
    String? name,
    String? description,
    String? channelId,
    List<String>? memberIds,
    bool? isArchived,
  }) async {
    updatedName = name;
    updatedDescription = description;
    updatedArchived = isArchived;
    return true;
  }

  @override
  Future<bool> deleteProject(String projectId) async {
    deletedProjectId = projectId;
    return true;
  }

  @override
  Future<bool> addProjectMember(String projectId, String userId) async {
    addedMemberId = userId;
    return true;
  }

  @override
  Future<bool> removeProjectMember(String projectId, String userId) async {
    removedMemberId = userId;
    return true;
  }
}

Project _project() => Project(
  id: 'p1',
  workspaceId: 'w1',
  name: '결제 시스템 개편',
  description: '구독 결제를 다시 만든다',
  createdBy: 'u1',
  createdAt: DateTime(2026, 1, 1),
  updatedAt: DateTime(2026, 1, 1),
  members: [User(id: 'u1', email: 'me@hanbit.co.kr', name: '김현진')],
);

/// 프로젝트 설정 시트를 연다. (앱에서 하는 것처럼 showModalBottomSheet 로)
Future<void> _openSheet(WidgetTester tester, AppState state, {Project? project}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AppState>.value(
      value: state,
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => Center(
              child: ElevatedButton(
                onPressed: () => showModalBottomSheet<void>(
                  context: ctx,
                  isScrollControlled: true,
                  backgroundColor: Colors.transparent,
                  builder: (_) => ProjectSettingsSheet(project: project),
                ),
                child: const Text('열기'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('열기'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    // 폰 크기 화면에서 검사한다.
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(411 * 3, 914 * 3);
    view.devicePixelRatio = 3.0;
    addTearDown(view.reset);
  });

  testWidgets('프로젝트 이름을 고치고 저장하면 그대로 반영된다', (tester) async {
    final state = _ProjectSettingsAppState(project: _project());

    await _openSheet(tester, state, project: _project());

    expect(find.text('프로젝트 설정'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, '프로젝트 이름'), '결제 시스템 개편 2차');
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();

    expect(state.updatedName, '결제 시스템 개편 2차');
    // 저장되면 시트가 닫힌다.
    expect(find.text('프로젝트 설정'), findsNothing);
  });

  testWidgets('보관을 켜면 isArchived 로 반영된다', (tester) async {
    final state = _ProjectSettingsAppState(project: _project());

    await _openSheet(tester, state, project: _project());

    await tester.tap(find.text('보관'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();

    expect(state.updatedArchived, isTrue);
  });

  testWidgets('멤버를 더하고 뺀 사실이 그대로 전달된다', (tester) async {
    final state = _ProjectSettingsAppState(project: _project());

    await _openSheet(tester, state, project: _project());

    // 함께하는 사람 추가
    await tester.tap(
      find.ancestor(of: find.text('고르세요'), matching: find.byType(DropdownButton<String>)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('이채원').last);
    await tester.pumpAndSettle();

    expect(state.addedMemberId, 'u2');

    // 빼기
    await tester.tap(find.byTooltip('빼기').first);
    await tester.pumpAndSettle();

    expect(state.removedMemberId, 'u1');
  });

  testWidgets('프로젝트를 지우면 확인을 거친 뒤에 지워진다', (tester) async {
    final state = _ProjectSettingsAppState(project: _project());

    await _openSheet(tester, state, project: _project());

    await tester.tap(find.text('프로젝트 삭제'));
    await tester.pumpAndSettle();

    // 확인 대화상자가 먼저 나온다.
    expect(find.text('프로젝트 삭제'), findsWidgets);
    expect(state.deletedProjectId, isNull);

    await tester.tap(find.text('삭제'));
    await tester.pumpAndSettle();

    expect(state.deletedProjectId, 'p1');
  });

  testWidgets('새 프로젝트 만들기는 이름을 물어본다', (tester) async {
    final state = _ProjectSettingsAppState();

    await _openSheet(tester, state);

    expect(find.text('새 프로젝트'), findsOneWidget);
    expect(find.text('프로젝트 삭제'), findsNothing);
  });
}
