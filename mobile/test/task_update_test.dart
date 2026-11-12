import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 서버 대신 쓸 가짜 API.
class _FakeApiService extends ApiService {
  _FakeApiService({
    required this.workspace,
    required this.me,
    this.projects = const [],
    this.tasks = const [],
  });

  final Workspace workspace;
  final User me;
  final List<Project> projects;
  final List<Task> tasks;

  /// updateTask 가 실패해야 할 때 true
  bool updateTaskFails = false;

  /// updateTask 로 넘긴 인자 (기록용)
  String? lastRoadmapId;

  @override
  String? get accessToken => 'fake-token';

  @override
  Future<void> init() async {}

  @override
  Future<User> getMe() async => me;

  @override
  Future<List<Workspace>> getWorkspaces() async => [workspace];

  @override
  Future<Bootstrap> getBootstrap(String workspaceId) async => Bootstrap(
    workspace: workspace,
    channels: const [],
    dms: const [],
    members: const [],
    me: me,
  );

  @override
  Future<List<ScheduleEvent>> getEvents(
    String workspaceId, {
    DateTime? from,
    DateTime? to,
  }) async => const [];

  @override
  Future<List<Project>> getProjects(String workspaceId) async => projects;

  @override
  Future<OrgOverview> getOrgOverview(String workspaceId) async =>
      OrgOverview(units: const [], admins: const [], myRole: Role.member);

  @override
  Future<(List<Message>, bool, bool)> getMessages(
    String channelId, {
    int? limit,
    String? before,
    String? after,
    String? around,
  }) async => (<Message>[], false, false);

  @override
  Future<List<Task>> getProjectTasks(String projectId) async => tasks;

  @override
  Future<List<Roadmap>> getRoadmaps(String projectId) async => const [];

  @override
  Future<List<Milestone>> getMilestones(String projectId) async => const [];

  @override
  Future<Task> updateTask(
    String taskId, {
    String? title,
    String? description,
    TaskStatus? status,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
  }) async {
    if (updateTaskFails) throw Exception('수정 실패');
    lastRoadmapId = roadmapId;
    return tasks.firstWhere((t) => t.id == taskId);
  }
}

/// WS 로 들어오는 이벤트를 직접 쏠 수 있는 가짜 소켓.
class _FakeWsService extends WsService {
  WsEventHandler? handler;

  @override
  void addListener(WsEventHandler handler) {
    this.handler = handler;
  }

  @override
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {}

  void emit(Map<String, dynamic> event) => handler?.call(event);
}

Workspace _workspace() => Workspace(
  id: 'w1',
  name: '한빛',
  slug: 'hanbit',
  createdAt: DateTime.utc(2026, 1, 1),
);

User _user() => User(
  id: 'u1',
  email: 'hyunjin@hanbit.co.kr',
  name: '김현진',
  createdAt: DateTime.utc(2026, 1, 1),
);

Project _project() => Project(
  id: 'prj1',
  workspaceId: 'w1',
  name: '결재 시스템 개편',
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

Task _task() => Task(
  id: 'tsk1',
  projectId: 'prj1',
  title: '원래 제목',
  status: TaskStatus.todo,
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

Map<String, dynamic> _taskJson() => {
  'id': 'tsk1',
  'project_id': 'prj1',
  'title': '원래 제목',
  'description': '',
  'status': 'todo',
  'created_by': 'u1',
  'position': 0,
  'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'comments': <Map<String, dynamic>>[],
  'comment_count': 0,
};

/// 실제 네트워크 대신 가짜 클라이언트로 PATCH 본문을 확인하기 위한 서비스.
class _RecordingApiService extends ApiService {
  @override
  String get apiEndpoint => 'http://127.0.0.1:8000/api/v1';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('할 일 수정 (§9-24 A)', () {
    late _FakeApiService api;
    late AppState state;

    setUp(() async {
      api = _FakeApiService(
        workspace: _workspace(),
        me: _user(),
        projects: [_project()],
        tasks: [_task()],
      );
      state = AppState(api: api, ws: _FakeWsService());
      await state.boot();
    });

    tearDown(() => state.dispose());

    test('실패하면 false 를 돌려주고 목록은 그대로 둔다', () async {
      api.updateTaskFails = true;
      final before = state.activeProjectTasks.map((t) => t.title).toList();

      final ok = await state.updateTask(taskId: 'tsk1', title: '고친 제목');

      expect(ok, isFalse);
      expect(state.activeProjectTasks.map((t) => t.title).toList(), before);
    });

    test('성공하면 true 를 돌려주고 목록을 갱신한다', () async {
      final ok = await state.updateTask(taskId: 'tsk1', title: '고친 제목');

      expect(ok, isTrue);
      expect(state.activeProjectTasks.length, 1);
    });

    test('roadmapId 를 넘기면 그대로 API 로 전달된다', () async {
      final ok = await state.updateTask(taskId: 'tsk1', roadmapId: 'rm1');

      expect(ok, isTrue);
      expect(api.lastRoadmapId, 'rm1');
    });
  });

  group('할 일 수정 PATCH 본문', () {
    test('roadmapId 를 넘기면 body 에 roadmap_id 가 들어간다', () async {
      Map<String, dynamic>? captured;
      final client = MockClient((req) async {
        captured = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(_taskJson()),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      await http.runWithClient(() async {
        await _RecordingApiService().updateTask('tsk1', title: '고친 제목', roadmapId: 'rm1');
      }, () => client);

      expect(captured, isNotNull);
      expect(captured!['roadmap_id'], 'rm1');
      expect(captured!['title'], '고친 제목');
    });

    test('roadmapId 를 넘기지 않으면 body 에 roadmap_id 가 없다', () async {
      Map<String, dynamic>? captured;
      final client = MockClient((req) async {
        captured = jsonDecode(req.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode(_taskJson()),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      await http.runWithClient(() async {
        await _RecordingApiService().updateTask('tsk1', title: '고친 제목');
      }, () => client);

      expect(captured, isNotNull);
      expect(captured!.containsKey('roadmap_id'), isFalse);
    });
  });
}
