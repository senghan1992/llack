part of 'app_state.dart';

/// 모든 탭이 공유하는 상태의 뼈대.
///
/// 필드와 getter, 인증, 그리고 다른 영역에서도 쓰는 헬퍼만 여기에 둔다.
/// (나머지 영역은 아래 클래스들이 상속해서 이어받는다)
///
/// 상속 순서: _AppStateCore → _AppStateRealtime → _AppStateMessages
///           → _AppStateWorkspace → AppState
abstract class _AppStateCore extends ChangeNotifier with WidgetsBindingObserver {
  /// [api]/[ws] 를 주입할 수 있게 한다.
  /// (테스트에서 서버 호출을 가짜로 바꾸기 위해서. 기본값이 있어 그대로 쓸 수 있다)
  _AppStateCore({ApiService? api, WsService? ws})
    : api = api ?? ApiService(),
      ws = ws ?? WsService();

  final ApiService api;
  final WsService ws;

  bool _isBooting = true;
  String? _bootError;

  /// 로그인/회원가입 진행 중. `isBooting` 과 분리해야 로그인 폼이 스플래시로
  /// 교체되지 않아 입력값과 에러 메시지가 살아남는다.
  bool _isAuthenticating = false;
  String? _authError;

  User? _currentUser;
  Session? _session;

  List<Workspace> _workspaces = [];
  Workspace? _activeWorkspace;

  List<Channel> _channels = [];
  List<Member> _members = [];
  String? _activeChannelId;

  final Map<String, List<Message>> _messages = {};
  final Map<String, bool> _hasMore = {};
  /// 채널별로 "아직 더 최신 메시지가 있는가" (점프한 뒤 최신까지 갈 수 있는지).
  final Map<String, bool> _hasMoreNewer = {};
  final Map<String, bool> _isLoadingMessages = {};

  /// 아직 스크롤/강조가 처리되지 않은 대상 메시지 id.
  String? _pendingFocusMessageId;
  /// 점프 실패 사유 (한국어).
  String? _focusErrorMessage;

  /// 히스토리를 실제로 불러온 채널. (WS 로 먼저 도착한 메시지만 있는 채널을
  /// "불러온 것"으로 오인해 과거 메시지가 영영 안 뜨는 것을 막는다)
  final Set<String> _historyLoaded = {};

  /// 삭제 직후 "실행 취소" 로 되돌리기 위한 원본 보관.
  final Map<String, Message> _deletedMessages = {};

  /// 채널별 멤버 캐시 (채널 정보 다이얼로그가 매번 서버를 때리지 않도록)
  final Map<String, List<Member>> _channelMembers = {};

  /// 채널별 "서버에서 마지막으로 받은 최신 메시지 id".
  /// (WS 로 새 메시지가 목록에 붙어도 이 커서는 그대로 두어야
  ///  점프한 창 뒤에 못 본 메시지를 놓치지 않는다)
  final Map<String, String> _newerCursor = {};

  /// 채널별로 "읽음 신호를 보냈고 서버 확인을 아직 못 받은" 상태.
  /// (이 동안 서버가 보내는 '절대값' 배지는 믿지 않는다)
  /// 읽음 확인 플래그를 채널별로 들고 있는가.
  final Set<String> _readAckPending = {};

  /// 이번 세션에서 이미 WS 'hello' 를 받았는지.
  ///
  /// 첫 'hello' 는 최초 연결이므로 (재동기화하지 않는다).
  /// 재연결로 오는 'hello' 에서만 놓친 이벤트를 복구한다.
  bool _hasSeenHello = false;

  /// 현재 열려 있는 대화창에서 "새 메시지가 화면에 보이는가" 를 물어보는 훅.
  ///
  /// 담당 B(chat_screen.dart) 가 **대화창이 열려 있는 동안에만** 값을 채운다.
  /// (dialog 를 띄운 사이에 조-dialog 닫히면 null 로 되돌린다)
  /// - 대화창이 열려 있지 않으면 **null** (= 사용자가 그 채널의 메시지를 보고 있지 않다)
  /// - 열려 있으면 "최신 메시지가 화면에 보이는가" 를 반환
  /// - true  : 최신 구간에 붙어 있음 → 도착한 메시지는 화면에 보임 → 읽음 처리 가능
  /// - false : 위로 스크롤해 있음 → 도착한 메시지는 화면에 안 보임 → 읽음 처리하면 안 됨
  bool Function(String channelId)? isNewestMessageVisible;

  Message? _threadRoot;
  List<Message> _threadReplies = [];
  bool _isLoadingReplies = false;

  Message? _replyToMessage;

  /// 채널 → (이름 → 마지막 입력 시각). 5초가 지나면 자동으로 만료된다.
  final Map<String, Map<String, DateTime>> _typing = {};
  String? _typingChannelId;

  final Map<String, Presence> _presence = {};

  /// 연결 상태 (사용자에게 배너로 보여준다)
  bool _isConnected = false;
  String? _connectionError;

  /// 섹션별 오류 상태. "빈 상태" 와 "오류 상태" 를 구분해서 그리기 위한 것.
  String? _channelsError;
  String? _messagesError;
  String? _eventsError;
  String? _projectsError;
  String? _orgError;

  /// 탭 인덱스 (0 메시지, 1 일정, 2 프로젝트, 3 조직도)
  final ValueNotifier<int> tabIndex = ValueNotifier<int>(0);

  // Schedule
  List<ScheduleEvent> _events = [];
  bool _isLoadingEvents = false;
  /// 일정 데이터를 이미 불러왔는지. (화면이 중복 요청을 피하게)
  bool _hasLoadedEvents = false;
  DateTime _selectedDate = DateTime.now();
  bool _onlyMyEvents = false;

  // Projects & Tasks
  List<Project> _projects = [];
  /// 프로젝트 데이터를 이미 불러왔는지. (화면이 중복 요청을 피하게)
  bool _hasLoadedProjects = false;
  Project? _activeProject;
  final Map<String, List<Task>> _projectTasks = {};
  final Map<String, List<Roadmap>> _projectRoadmaps = {};
  final Map<String, List<Milestone>> _projectMilestones = {};
  String? _selectedRoadmapId; // null = all

  // Org
  OrgOverview? _orgOverview;
  bool _isLoadingOrg = false;
  /// 조직도 데이터를 이미 불러왔는지. (화면이 중복 요청을 피하게)
  bool _hasLoadedOrg = false;

  // People & Invites
  /// 보낸 초대 목록.
  List<Invite> _invites = [];
  /// 내 할 일만 모은 목록. (모든 프로젝트를 훑는 대신 서버가 골라 준다)
  List<Task> _myTasks = [];

  // Drafts
  /// 채널별 임시저장 글. (방을 옮겨도 작성 중인 문장이 남는다)
  final Map<String, String> _drafts = {};

  bool _disposed = false;

  // ── Getters ───────────────────────────────────────────────────

  bool get isBooting => _isBooting;
  bool get isAuthenticated => _currentUser != null && api.accessToken != null;
  String? get bootError => _bootError;
  User? get currentUser => _currentUser;
  Session? get session => _session;

  bool get isAuthenticating => _isAuthenticating;
  String? get authError => _authError;

  bool get isConnected => _isConnected;
  String? get connectionError => _connectionError;

  List<Workspace> get workspaces => _workspaces;
  Workspace? get activeWorkspace => _activeWorkspace;

  List<Channel> get channels => _channels.where((c) => !c.isDm).toList();
  List<Channel> get dms => _channels.where((c) => c.isDm).toList();
  List<Channel> get allChannels => _channels;

  Channel? get activeChannel {
    if (_activeChannelId == null) return null;
    try {
      return _channels.firstWhere((c) => c.id == _activeChannelId);
    } catch (_) {
      return null;
    }
  }

  List<Member> get members => _members;
  String? get activeChannelId => _activeChannelId;

  List<Message> get activeMessages =>
      _activeChannelId != null ? (_messages[_activeChannelId] ?? []) : [];
  bool get hasMoreActiveMessages =>
      _activeChannelId != null ? (_hasMore[_activeChannelId] ?? false) : false;
  /// 활성 채널의 "아직 더 최신 메시지가 있다" 여부.
  bool get hasMoreNewerMessages =>
      _activeChannelId != null ? (_hasMoreNewer[_activeChannelId] ?? false) : false;
  /// 아직 스크롤/강조가 처리되지 않은 대상 메시지 id.
  String? get pendingFocusMessageId => _pendingFocusMessageId;
  /// 점프 실패 사유 (한국어).
  String? get focusErrorMessage => _focusErrorMessage;
  bool get isLoadingActiveMessages =>
      _activeChannelId != null ? (_isLoadingMessages[_activeChannelId] ?? false) : false;

  Message? get threadRoot => _threadRoot;
  List<Message> get threadReplies => _threadReplies;
  bool get isLoadingReplies => _isLoadingReplies;
  Message? get replyToMessage => _replyToMessage;

  /// 현재 채널에서 입력 중인 사용자. 5초 이상 지난 항목은 제외한다.
  List<String> get currentTypingUsers {
    final cid = _activeChannelId;
    if (cid == null) return const [];
    final users = _typing[cid];
    if (users == null) return const [];
    final now = DateTime.now();
    users.removeWhere((_, ts) => now.difference(ts) > const Duration(seconds: 5));
    if (users.isEmpty) return const [];
    return users.keys.toList();
  }

  Presence getPresence(String userId) => _presence[userId] ?? Presence.offline;

  List<ScheduleEvent> get events => _events;
  bool get isLoadingEvents => _isLoadingEvents;

  /// 일정 데이터를 이미 불러왔는지.
  ///
  /// 화면(일정 탭)이 `initState` 에서 "이미 불러온 데이터면 다시 부르지 않기" 로
  /// 판단할 때 쓰는 신호다. **목록이 비었는지와는 무관하다.**
  /// (일정이 하나도 없는 워크스페이스에서도 `true` 다)
  bool get hasLoadedEvents => _hasLoadedEvents;

  /// 프로젝트 데이터를 이미 불러왔는지.
  ///
  /// 화면(프로젝트 탭)이 `initState` 에서 "이미 불러온 데이터면 다시 부르지 않기" 로
  /// 판단할 때 쓰는 신호다. **목록이 비었는지와는 무관하다.**
  bool get hasLoadedProjects => _hasLoadedProjects;

  /// 조직도 데이터를 이미 불러왔는지.
  ///
  /// 화면(조직도 탭)이 `initState` 에서 "이미 불러온 데이터면 다시 부르지 않기" 로
  /// 판단할 때 쓰는 신호다. **목록이 비었는지와는 무관하다.**
  bool get hasLoadedOrg => _hasLoadedOrg;

  /// 섹션(일정/프로젝트/조직도) 데이터의 "불러옴" 플래그를 모두 초기화한다.
  ///
  /// 워크스페이스가 바뀌거나 로그아웃하면 이전 워크스페이스의 플래그를 물려받으면 안 된다.
  void _resetSectionLoadFlags() {
    _hasLoadedEvents = false;
    _hasLoadedProjects = false;
    _hasLoadedOrg = false;
  }
  DateTime get selectedDate => _selectedDate;
  bool get onlyMyEvents => _onlyMyEvents;

  List<Project> get projects => _projects;
  Project? get activeProject => _activeProject;
  List<Task> get activeProjectTasks =>
      _activeProject != null ? (_projectTasks[_activeProject!.id] ?? []) : [];
  List<Roadmap> get activeRoadmaps =>
      _activeProject != null ? (_projectRoadmaps[_activeProject!.id] ?? []) : [];
  List<Milestone> get activeMilestones =>
      _activeProject != null ? (_projectMilestones[_activeProject!.id] ?? []) : [];
  String? get selectedRoadmapId => _selectedRoadmapId;

  OrgOverview? get orgOverview => _orgOverview;
  bool get isLoadingOrg => _isLoadingOrg;

  /// 보낸 초대 목록.
  List<Invite> get invites => _invites;

  /// 내 할 일 (모든 프로젝트 · 아직 끝나지 않은 것).
  List<Task> get myTasks => _myTasks;

  /// 채널에 임시저장된 글. (없으면 null)
  String? draftFor(String channelId) {
    final body = _drafts[channelId];
    return (body == null || body.isEmpty) ? null : body;
  }

  /// 채널의 임시저장 글을 고친다. (빈 글은 저장을 지운 것으로 본다)
  void setDraft(String channelId, String body) {
    if (body.isEmpty) {
      _drafts.remove(channelId);
    } else {
      _drafts[channelId] = body;
    }
  }

  String? get channelsError => _channelsError;
  String? get messagesError => _messagesError;
  String? get eventsError => _eventsError;
  String? get projectsError => _projectsError;
  String? get orgError => _orgError;

  // ── 공용 헬퍼 ─────────────────────────────────────────────────

  /// 채널의 안읽음 배지 숫자.
  int _unreadOf(String channelId) {
    final idx = _channels.indexWhere((c) => c.id == channelId);
    return idx == -1 ? 0 : _channels[idx].unreadCount;
  }

  /// 채널의 안읽음 배지 숫자를 정한다.
  void _setUnreadCount(String channelId, int count) {
    final idx = _channels.indexWhere((c) => c.id == channelId);
    if (idx == -1) return;
    if (_channels[idx].unreadCount == count) return;
    _channels[idx] = _channels[idx].copyWith(unreadCount: count);
  }

  /// dispose 이후 도착하는 비동기 응답에서 notifyListeners() 가 터지지 않게 한다.
  void _notify() {
    if (_disposed) return;
    notifyListeners();
  }

  void clearAuthError() {
    _authError = null;
    _notify();
  }

  /// 워크스페이스 데이터를 다시 불러온다. 스플래시로 바꾸지 않고 토큰도 지우지 않는다.
  /// (당겨서 갱신 실패가 로그아웃으로 이어지면 안 된다)
  Future<void> refreshWorkspace() async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return;
    try {
      final bootstrap = await api.getBootstrap(wsId);
      _channels = [...bootstrap.channels, ...bootstrap.dms];
      _members = bootstrap.members;
      for (final m in _members) {
        _presence[m.user.id] = m.user.presence;
      }
      if (_currentUser != null) {
        _presence[_currentUser!.id] = _currentUser!.presence;
      }
      _channelsError = null;
      // 워크스페이스 데이터를 새로 받는 동안에는 이전 플래그를 물려받으면 안 된다.
      _resetSectionLoadFlags();
    } catch (e) {
      debugPrint('[refreshWorkspace error] $e');
      _channelsError = '채널 목록을 불러오지 못했습니다. 다시 시도해주세요.';
    }
    _notify();
  }

  Future<void> logout() async {
    ws.disconnect();
    await api.clearTokens();
    // 세션이 끝났으므로 다음 로그인에서는 다시 "첫 hello = 재동기화 없음" 이다.
    _hasSeenHello = false;
    _currentUser = null;
    _session = null;
    _workspaces = [];
    _activeWorkspace = null;
    _channels = [];
    _members = [];
    _activeChannelId = null;
    _messages.clear();
    _historyLoaded.clear();
    _deletedMessages.clear();
    _resetSectionLoadFlags();
    _threadRoot = null;
    _threadReplies = [];
    _isConnected = false;
    _connectionError = null;
    _channelsError = null;
    _messagesError = null;
    _eventsError = null;
    _projectsError = null;
    _orgError = null;
    _notify();
  }

  Future<void> updateMe({String? name, String? title, String? avatarColor, Presence? presence}) async {
    if (_currentUser == null) return;
    final updated = await api.updateMe(
      name: name,
      title: title,
      avatarColor: avatarColor,
      presence: presence,
    );
    _currentUser = updated;
    _presence[updated.id] = updated.presence;
    _notify();
  }

  Future<void> updatePresence(Presence newPresence) async {
    await updateMe(presence: newPresence);
  }

  /// 특정 채널의 멤버 목록 (캐시 포함). 없으면 서버에서 불러온다.
  Future<List<Member>> membersForChannel(String channelId) async {
    final cached = _channelMembers[channelId];
    if (cached != null) return cached;
    try {
      final members = await api.getChannelMembers(channelId);
      _channelMembers[channelId] = members;
      return members;
    } catch (e) {
      debugPrint('[membersForChannel error] $e');
      return const [];
    }
  }

  /// 해당 채널의 히스토리를 이미 불러왔는지.
  bool hasLoadedHistory(String channelId) => _historyLoaded.contains(channelId);

  // ── People & Invites ─────────────────────────────────────────

  /// 사람 검색 (초대 대상 · 조직원 추가 후보).
  Future<List<User>> searchUsers(String query) async {
    if (query.trim().isEmpty) return const [];
    return api.searchUsers(query.trim());
  }

  /// 보낸 초대 목록을 불러온다.
  Future<void> loadInvites() async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return;
    try {
      _invites = await api.getInvites(wsId);
    } catch (e) {
      debugPrint('[loadInvites error] $e');
    }
    _notify();
  }

  /// 이메일로 초대장을 보낸다. (만들어진 초대장을 돌려준다)
  Future<Invite> createInvite(String email, {String role = 'member'}) async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) throw ApiException(0, 'error', '워크스페이스가 없습니다.');
    final invite = await api.createInvite(wsId, email: email.trim(), role: role);
    _invites = [invite, ..._invites];
    _notify();
    return invite;
  }

  /// 초대장을 취소한다.
  Future<void> revokeInvite(String inviteId) async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return;
    await api.revokeInvite(wsId, inviteId);
    _invites = _invites.where((i) => i.id != inviteId).toList();
    _notify();
  }

  /// 구성원의 역할을 바꾼다. (소유자 · 관리자 · 멤버)
  Future<bool> updateMemberRole(Member member, Role role) async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return false;
    final updated = await api.updateMemberRole(wsId, member.user.id, role.name);
    _members = [
      for (final m in _members)
        if (m.user.id == member.user.id) updated else m,
    ];
    _notify();
    return true;
  }

  /// 구성원을 워크스페이스에서 내보낸다.
  Future<bool> removeMember(Member member) async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return false;
    await api.removeMember(wsId, member.user.id);
    _members = _members.where((m) => m.user.id != member.user.id).toList();
    _notify();
    return true;
  }

  /// 내 할 일 목록을 불러온다.
  Future<void> loadMyTasks() async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return;
    try {
      _myTasks = await api.getMyTasks(wsId);
    } catch (e) {
      debugPrint('[loadMyTasks error] $e');
    }
    _notify();
  }

  /// 아바타 색을 고른다. (프로필 편집에서 사용)
  Future<void> updateAvatarColor(String color) async {
    await updateMe(avatarColor: color);
  }

  /// 0 메시지, 1 일정, 2 프로젝트, 3 조직도
  void goToTab(int index) {
    tabIndex.value = index;
  }
}
