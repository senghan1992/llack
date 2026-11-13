import 'dart:async';
import 'package:flutter/widgets.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/ws_service.dart';
import 'list_upsert.dart';

// 상태가 여러 영역으로 나뉘어 있어도 전부 하나의 라이브러리(part)다.
// 그래서 영역 사이에서 private 멤버를 서로 그대로 쓸 수 있다.
part 'app_state_core.dart';
part 'app_state_realtime.dart';
part 'app_state_messages.dart';
part 'app_state_workspace.dart';

/// 앱 전체 상태.
///
/// 영역별 구현은 아래 part 파일의 클래스가 상속해서 이어받는다.
/// - _AppStateCore : 필드/게터, 인증, 공용 헬퍼
/// - _AppStateRealtime : WebSocket 이벤트 처리
/// - _AppStateMessages : 메시지, 채널/DM
/// - _AppStateWorkspace : 일정, 프로젝트, 조직도, 검색
class AppState extends _AppStateWorkspace {
  AppState({super.api, super.ws}) {
    ws.addListener(_handleWsEvent);
    ws.onStatusChanged = (connected, error) {
      _isConnected = connected;
      _connectionError = error;
      // "일시적 단절" 과 "인증 만료" 를 구분한다.
      _isSessionExpired = ws.isAuthExpired;
      _notify();
    };
    // WS 가 인증 실패(4401)로 닫혔을 때 토큰을 한 번 갱신해 본다.
    ws.authRefresher = () async => api.refreshAccessToken();
    // 토큰이 갱신되면 WS 도 새 토큰으로 다시 붙인다.
    api.onTokensChanged = () {
      _connectWs();
    };
    WidgetsBinding.instance.addObserver(this);
  }

  /// 세션이 만료되었는지. (WS 4401 + 토큰 갱신 실패)
  bool _isSessionExpired = false;

  /// 인증 만료로 세션이 끝났는지.
  /// (true 면 다시 로그인해야 한다)
  bool get isSessionExpired => _isSessionExpired;

  @override
  void dispose() {
    _disposed = true;
    WidgetsBinding.instance.removeObserver(this);
    ws.removeListener(_handleWsEvent);
    ws.onStatusChanged = null;
    ws.disconnect();
    tabIndex.dispose();
    super.dispose();
  }

  // ── Initialization ──────────────────────────────────────────

  /// 콜드 스타트 전용. `_isBooting` 은 이 메서드에서만 true 가 된다.
  Future<void> boot() async {
    _isBooting = true;
    _bootError = null;
    _notify();

    try {
      await api.init();
      if (api.accessToken != null) {
        try {
          _currentUser = await api.getMe();
          await _bootstrapWorkspaces();
        } catch (e) {
          debugPrint('[Boot] session restore failed: $e');
          await api.clearTokens();
          _currentUser = null;
        }
      }
    } catch (e) {
      _bootError = e.toString();
    } finally {
      _isBooting = false;
      _notify();
    }
  }

  Future<void> _bootstrapWorkspaces() async {
    _workspaces = await api.getWorkspaces();
    if (_workspaces.isNotEmpty) {
      _activeWorkspace = _workspaces.first;
      await _loadWorkspaceData(_activeWorkspace!.id);
      _connectWs();
    }
  }

  void _connectWs() {
    // 토큰을 복사하지 않는다. 연결할 때마다 그 시점의 토큰을 물어본다.
    ws.connect(baseUrl: api.baseUrl, tokenProvider: () => api.accessToken);
  }

  Future<void> _loadWorkspaceData(String workspaceId) async {
    try {
      final bootstrap = await api.getBootstrap(workspaceId);
      _channels = [...bootstrap.channels, ...bootstrap.dms];
      _members = bootstrap.members;
      for (final m in _members) {
        _presence[m.user.id] = m.user.presence;
      }
      if (_currentUser != null) {
        _presence[_currentUser!.id] = _currentUser!.presence;
      }
      _channelsError = null;
      if (_channels.isNotEmpty && _activeChannelId == null) {
        _activeChannelId = _channels.first.id;
        loadMessages(_activeChannelId!);
      }
    } catch (e) {
      debugPrint('[Bootstrap error] $e');
      _channelsError = '채널 목록을 불러오지 못했습니다. 다시 시도해주세요.';
    }

    // 다른 탭(일정/프로젝트/조직도)은 IndexedStack 안이라 화면이 다시 만들어지지 않는다.
    // 워크스페이스가 바뀌면 데이터를 직접 다시 불러와야 한다.
    await loadEvents();
    await loadProjects();
    await loadOrg();
    _notify();
  }

  /// 서버 주소를 바꾸고 WS 를 재연결하며 데이터를 다시 불러온다.
  Future<void> changeApiBaseUrl(String url) async {
    await api.setBaseUrl(url);
    ws.disconnect();
    if (_currentUser == null || api.accessToken == null) {
      _notify();
      return;
    }
    _connectWs();
    await refreshWorkspace();
    final cid = _activeChannelId;
    if (cid != null) {
      await loadMessages(cid);
    }
    await loadEvents();
    await loadProjects();
    await loadOrg();
    _notify();
  }

  // ── Auth Actions ─────────────────────────────────────────────

  /// 로그인. 실패하면 예외를 다시 던지지 않고 `authError` 로 알린다.
  Future<bool> login(String email, String password) async {
    _isAuthenticating = true;
    _authError = null;
    _notify();
    try {
      _session = await api.login(email.trim(), password);
      _currentUser = _session!.user;
      _isSessionExpired = false;
      // 새 세션이다. (첫 'hello' 에서 재동기화하지 않도록 초기화)
      _hasSeenHello = false;
      try {
        await _bootstrapWorkspaces();
      } catch (e) {
        // 로그인 자체는 성공했으므로 "인증 실패" 로 보이면 안 된다.
        _channelsError = '워크스페이스 정보를 불러오지 못했습니다. 다시 시도해주세요.';
      }
      _authError = null;
      return true;
    } catch (e) {
      _authError = _authMessage(e);
      return false;
    } finally {
      _isAuthenticating = false;
      _notify();
    }
  }

  /// 회원가입. 실패하면 예외를 다시 던지지 않고 `authError` 로 알린다.
  Future<bool> signup({
    required String email,
    required String password,
    required String name,
    required String workspaceName,
  }) async {
    _isAuthenticating = true;
    _authError = null;
    _notify();
    try {
      _session = await api.signup(
        email: email.trim(),
        password: password,
        name: name.trim(),
        workspaceName: workspaceName.trim(),
      );
      _currentUser = _session!.user;
      _isSessionExpired = false;
      // 새 세션이다. (첫 'hello' 에서 재동기화하지 않도록 초기화)
      _hasSeenHello = false;
      try {
        await _bootstrapWorkspaces();
      } catch (e) {
        // 회원가입 자체는 성공했으므로 "인증 실패" 로 보이면 안 된다.
        _channelsError = '워크스페이스 정보를 불러오지 못했습니다. 다시 시도해주세요.';
      }
      _authError = null;
      return true;
    } catch (e) {
      _authError = _authMessage(e);
      return false;
    } finally {
      _isAuthenticating = false;
      _notify();
    }
  }

  /// 사용자에게 보여줄 한국어 오류 메시지로 바꾼다.
  String _authMessage(Object error) {
    if (error is ApiException) {
      if (error.status == 401) return '이메일 또는 비밀번호가 맞지 않습니다.';
      if (error.code == 'timeout') return '네트워크 응답이 없습니다. 잠시 후 다시 시도해주세요.';
      if (error.code == 'network') {
        return '서버에 연결할 수 없습니다. 서버 주소를 확인해주세요.';
      }
      return error.message;
    }
    return '로그인에 실패했습니다. 잠시 후 다시 시도해주세요.';
  }

  // ── Workspace & Channel Navigation ───────────────────────────

  /// 초대 코드로 팀에 들어간다.
  ///
  /// 로그인한 뒤에 부는 것이라, 이 함수는 **로그인된 상태**에서만 뜻이 있다.
  /// (데스크톱 로그인 화면의 "초대 코드" 와 같은 자리)
  Future<Workspace> acceptInvite(String token) async {
    final workspace = await api.acceptInvite(token);
    await selectWorkspace(workspace);
    _notify();
    return workspace;
  }

  Future<void> selectWorkspace(Workspace workspace) async {
    if (_activeWorkspace?.id == workspace.id) return;
    _activeWorkspace = workspace;
    _activeChannelId = null;
    _messages.clear();
    _historyLoaded.clear();
    _hasMore.clear();
    // 이전 워크스페이스의 "불러옴" 플래그를 물려받으면 안 된다.
    _resetSectionLoadFlags();
    _events = [];
    _projects = [];
    _activeProject = null;
    _projectTasks.clear();
    _projectRoadmaps.clear();
    _projectMilestones.clear();
    _orgOverview = null;
    _notify();
    await _loadWorkspaceData(workspace.id);
    _notify();
  }

  // ── Retry (섹션별 오류 복구) ─────────────────────────────────

  Future<void> retryChannels() => refreshWorkspace();

  Future<void> retryMessages() async {
    final cid = _activeChannelId;
    if (cid == null) return;
    await loadMessages(cid);
  }

  Future<void> retryEvents() => loadEvents();

  Future<void> retryProjects() => loadProjects();

  Future<void> retryOrg() => loadOrg();

  // ── App Lifecycle ────────────────────────────────────────────

  /// 백그라운드로 내려가면 소켓을 끊는다 (몇 시간째 "온라인" 으로 보이는 것을 막는다).
  /// 복귀하면 다시 연결하고 놓친 데이터를 불러온다.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _connectWs();
        refreshWorkspace();
        final cid = _activeChannelId;
        if (cid != null) {
          loadMessages(cid);
        }
        break;
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        ws.disconnect();
        break;
    }
  }
}
