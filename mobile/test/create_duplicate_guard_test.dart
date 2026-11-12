import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/providers/list_upsert.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// id 를 가진 항목 (upsertById 단위 테스트용)
class _Item {
  final String id;
  final String name;

  _Item(this.id, this.name);
}

/// 서버 대신 쓸 가짜 API.
class _FakeApiService extends ApiService {
  _FakeApiService({
    required this.workspace,
    required this.me,
    this.projects = const [],
  });

  final Workspace workspace;
  final User me;
  final List<Project> projects;

  /// REST 응답으로 돌려줄 항목들 (WS 로 이미 들어온 것과 같은 id 를 쓴다)
  ScheduleEvent? createdEvent;
  Channel? createdChannel;
  Task? createdTask;

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
    int limit = 50,
    String? before,
    String? after,
    String? around,
  }) async => (<Message>[], false, false);

  @override
  Future<List<Task>> getProjectTasks(String projectId) async => const [];

  @override
  Future<List<Roadmap>> getRoadmaps(String projectId) async => const [];

  @override
  Future<List<Milestone>> getMilestones(String projectId) async => const [];

  @override
  Future<ScheduleEvent> createEvent({
    required String workspaceId,
    required String title,
    String? description,
    String? location,
    required DateTime startsAt,
    required DateTime endsAt,
    bool allDay = false,
    bool isPrivate = false,
    String? channelId,
    List<String>? attendeeIds,
  }) async => createdEvent!;

  @override
  Future<Channel> createChannel({
    required String workspaceId,
    required String name,
    String? topic,
    bool isPrivate = false,
    List<String>? memberIds,
  }) async => createdChannel!;

  @override
  Future<Task> createTask({
    required String projectId,
    required String title,
    String? description,
    TaskStatus status = TaskStatus.todo,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
  }) async => createdTask!;
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

  /// 서버가 WS 로 보내는 이벤트를 흉내낸다.
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

ScheduleEvent _event() => ScheduleEvent(
  id: 'evt1',
  workspaceId: 'w1',
  title: 'Round5 test event',
  startsAt: DateTime.utc(2026, 11, 9, 9),
  endsAt: DateTime.utc(2026, 11, 9, 10),
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

Channel _channel() => Channel(
  id: 'chl1',
  workspaceId: 'w1',
  name: 'round5test',
  kind: 'channel',
  isPrivate: false,
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
);

Task _task() => Task(
  id: 'tsk1',
  projectId: 'prj1',
  title: 'round5task',
  status: TaskStatus.request,
  createdBy: 'u1',
  createdAt: DateTime.utc(2026, 1, 1),
  updatedAt: DateTime.utc(2026, 1, 1),
);

Map<String, dynamic> _eventJson(ScheduleEvent e) => {
  'id': e.id,
  'workspace_id': e.workspaceId,
  'title': e.title,
  'description': e.description,
  'location': e.location,
  'starts_at': e.startsAt.toIso8601String(),
  'ends_at': e.endsAt.toIso8601String(),
  'all_day': e.allDay,
  'is_private': e.isPrivate,
  'created_by': e.createdBy,
  'created_at': e.createdAt.toIso8601String(),
  'updated_at': e.updatedAt.toIso8601String(),
  'attendees': <Map<String, dynamic>>[],
};

Map<String, dynamic> _channelJson(Channel c) => {
  'id': c.id,
  'workspace_id': c.workspaceId,
  'name': c.name,
  'kind': c.kind,
  'is_private': c.isPrivate,
  'created_by': c.createdBy,
  'created_at': c.createdAt.toIso8601String(),
  'member_count': 1,
  'unread_count': 0,
};

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
  'comments': <Map<String, dynamic>>[],
  'comment_count': 0,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('upsertById', () {
    test('같은 id 를 두 번 넣으면 1개만 남는다', () {
      final once = upsertById<_Item>([_Item('a', '첫 번째')], _Item('a', '두 번째'), (e) => e.id);
      expect(once.length, 1);
      expect(once.first.name, '두 번째');
    });

    test('다른 id 를 넣으면 2개가 된다', () {
      final list = upsertById<_Item>([_Item('a', 'A')], _Item('b', 'B'), (e) => e.id);
      expect(list.length, 2);
      expect(list.map((e) => e.id), ['a', 'b']);
    });

    test('prepend 이면 새 항목을 앞에 넣는다', () {
      final list = upsertById<_Item>([_Item('a', 'A')], _Item('b', 'B'), (e) => e.id, prepend: true);
      expect(list.map((e) => e.id), ['b', 'a']);
    });
  });

  group('만든 항목이 2개로 중복되지 않는다', () {
    late _FakeApiService api;
    late _FakeWsService ws;
    late AppState state;

    setUp(() async {
      api = _FakeApiService(workspace: _workspace(), me: _user(), projects: [_project()]);
      ws = _FakeWsService();
      state = AppState(api: api, ws: ws);
      await state.boot();
    });

    tearDown(() => state.dispose());

    test('WS 가 먼저 도착하고 REST 응답이 나중에 와도 일정은 1개', () async {
      final event = _event();
      api.createdEvent = event;

      // 백엔드는 WS 이벤트를 HTTP 응답보다 먼저 보낸다.
      ws.emit({'type': 'event.created', 'event': _eventJson(event)});
      expect(state.events.length, 1);

      await state.createEvent(
        title: event.title,
        startsAt: event.startsAt,
        endsAt: event.endsAt,
      );

      expect(state.events.length, 1);
    });

    test('REST 응답이 먼저 와도 WS 이벤트가 뒤따르면 일정은 1개', () async {
      final event = _event();
      api.createdEvent = event;

      await state.createEvent(
        title: event.title,
        startsAt: event.startsAt,
        endsAt: event.endsAt,
      );
      expect(state.events.length, 1);

      ws.emit({'type': 'event.created', 'event': _eventJson(event)});
      expect(state.events.length, 1);
    });

    test('WS 가 먼저 도착하고 REST 응답이 나중에 와도 채널은 1개', () async {
      final channel = _channel();
      api.createdChannel = channel;

      ws.emit({'type': 'channel.created', 'channel': _channelJson(channel)});
      expect(state.channels.length, 1);

      await state.createChannel(name: channel.name);

      expect(state.channels.length, 1);
    });

    test('WS 가 먼저 도착하고 REST 응답이 나중에 와도 할 일은 1개', () async {
      final task = _task();
      api.createdTask = task;

      ws.emit({'type': 'task.created', 'task': _taskJson(task)});
      expect(state.activeProjectTasks.length, 1);

      await state.createTask(title: task.title);

      expect(state.activeProjectTasks.length, 1);
    });
  });
}
