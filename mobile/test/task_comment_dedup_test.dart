import 'package:flutter_test/flutter_test.dart';
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
    this.events = const [],
  });

  final Workspace workspace;
  final User me;
  final List<Project> projects;
  final List<Task> tasks;
  final List<ScheduleEvent> events;

  /// REST 응답으로 돌려줄 코멘트 (WS 로 이미 들어온 것과 같은 id 를 쓴다)
  TaskComment? addedComment;

  /// updateEvent 가 실패해야 할 때 true
  bool updateEventFails = false;

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
  }) async => events;

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
  Future<TaskComment> addTaskComment(String taskId, String body) async => addedComment!;

  @override
  Future<ScheduleEvent> updateEvent({
    required String eventId,
    String? title,
    String? description,
    String? location,
    DateTime? startsAt,
    DateTime? endsAt,
    bool? allDay,
    bool? isPrivate,
    String? channelId,
    List<String>? attendeeIds,
  }) async {
    if (updateEventFails) throw Exception('수정 실패');
    return events.firstWhere((e) => e.id == eventId);
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

TaskComment _comment() => TaskComment(
  id: 'tc1',
  taskId: 'tsk1',
  userId: 'u1',
  author: _user(),
  body: 'r8comment',
  createdAt: DateTime.utc(2026, 11, 9, 9),
);

Task _task({List<TaskComment> comments = const []}) => Task(
  id: 'tsk1',
  projectId: 'prj1',
  title: 'round8task',
  status: TaskStatus.todo,
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
  comments: comments,
  commentCount: comments.length,
);

ScheduleEvent _event({String title = 'round8event'}) => ScheduleEvent(
  id: 'evt1',
  workspaceId: 'w1',
  title: title,
  startsAt: DateTime.utc(2026, 11, 9, 9),
  endsAt: DateTime.utc(2026, 11, 9, 10),
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

Map<String, dynamic> _taskJson(Task t) => {
  'id': t.id,
  'project_id': t.projectId,
  'title': t.title,
  'description': t.description,
  'status': t.status.apiValue,
  'created_by': t.createdBy,
  'position': t.position,
  'created_at': t.createdAt.toIso8601String(),
  'updated_at': t.updatedAt.toIso8601String(),
  'comments': [
    {
      'id': 'tc1',
      'task_id': 'tsk1',
      'user_id': 'u1',
      'body': 'r8comment',
      'created_at': DateTime.utc(2026, 11, 9, 9).toIso8601String(),
    },
  ],
  'comment_count': 1,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('태스크 코멘트가 2개로 보이지 않는다 (§9-22)', () {
    late _FakeApiService api;
    late _FakeWsService ws;
    late AppState state;

    setUp(() async {
      api = _FakeApiService(
        workspace: _workspace(),
        me: _user(),
        projects: [_project()],
        tasks: [_task()],
      );
      api.addedComment = _comment();
      ws = _FakeWsService();
      state = AppState(api: api, ws: ws);
      await state.boot();
    });

    tearDown(() => state.dispose());

    test('WS 로 이미 들어온 코멘트를 REST 경로가 받아도 1개로 유지된다', () async {
      // 백엔드는 WS 이벤트를 HTTP 응답보다 먼저 보낸다.
      ws.emit({'type': 'task.updated', 'task': _taskJson(_task())});
      expect(state.activeProjectTasks.first.comments.length, 1);

      await state.addTaskComment('tsk1', 'r8comment');

      expect(state.activeProjectTasks.first.comments.length, 1);
      expect(state.activeProjectTasks.first.comments.first.id, 'tc1');
    });

    test('아무 코멘트도 없던 태스크에는 1개만 추가된다', () async {
      await state.addTaskComment('tsk1', 'r8comment');

      expect(state.activeProjectTasks.first.comments.length, 1);
    });
  });

  group('일정 수정 (§9-23 A)', () {
    late _FakeApiService api;
    late AppState state;

    setUp(() async {
      api = _FakeApiService(
        workspace: _workspace(),
        me: _user(),
        projects: [_project()],
        events: [_event(title: '고친 제목')],
      );
      state = AppState(api: api, ws: _FakeWsService());
      await state.boot();
    });

    tearDown(() => state.dispose());

    test('실패하면 false 를 돌려주고 목록은 그대로 둔다', () async {
      api.updateEventFails = true;
      final before = state.events.map((e) => e.title).toList();

      final ok = await state.updateEvent(eventId: 'evt1', title: '고친 제목');

      expect(ok, isFalse);
      expect(state.events.map((e) => e.title).toList(), before);
    });

    test('성공하면 true 를 돌려주고 목록을 갱신한다', () async {
      final ok = await state.updateEvent(eventId: 'evt1', title: '고친 제목');

      expect(ok, isTrue);
      expect(state.events.length, 1);
      expect(state.events.first.title, '고친 제목');
    });
  });
}
