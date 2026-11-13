// ignore_for_file: use_null_aware_elements
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';

class ApiException implements Exception {
  final int status;
  final String code;
  final String message;

  ApiException(this.status, this.code, this.message);

  @override
  String toString() => message;
}

class ApiService {
  static const String keyAccess = 'llack.access';
  static const String keyRefresh = 'llack.refresh';
  static const String keyApiBase = 'llack.api_base';

  /// 네트워크가 먹통이면 UI 가 응답 없이 멈추므로 모든 요청에 타임아웃을 건다.
  static const Duration requestTimeout = Duration(seconds: 15);

  static String getDefaultBaseUrl() {
    if (!kIsWeb && Platform.isAndroid) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://127.0.0.1:8000';
  }

  String _baseUrl = getDefaultBaseUrl();
  String? _accessToken;
  String? _refreshToken;

  String get baseUrl => _baseUrl;
  String? get accessToken => _accessToken;
  String? get refreshToken => _refreshToken;
  String get apiEndpoint => '$_baseUrl/api/v1';

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(keyApiBase) ?? getDefaultBaseUrl();
    _accessToken = prefs.getString(keyAccess);
    _refreshToken = prefs.getString(keyRefresh);
  }

  Future<void> setBaseUrl(String url) async {
    _baseUrl = url.replaceAll(RegExp(r'/+$'), '');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyApiBase, _baseUrl);
  }

  /// 상대경로({api_prefix}/files/{id}) 를 절대 URL 로 만든다. 이미 절대경로면 그대로 반환.
  /// 첨부파일 썸네일처럼 URL 을 바로 써야 하는 곳에서 사용한다.
  String absoluteFileUrl(String url) {
    if (url.isEmpty) return url;
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    final path = url.startsWith('/') ? url : '/$url';
    return '$_baseUrl$path';
  }

  Future<void> setTokens(String access, String refresh) async {
    _accessToken = access;
    _refreshToken = refresh;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyAccess, access);
    await prefs.setString(keyRefresh, refresh);
    // 토큰이 바뀌었다는 사실을 알린다. (WS 를 새 토큰으로 다시 붙이기 위해)
    onTokensChanged?.call();
  }

  /// 토큰이 갱신되었을 때 호출된다. (AppState 가 WS 재연결에 쓴다)
  void Function()? onTokensChanged;

  /// 만료된 액세스 토큰을 갱신한다.
  /// 성공하면 true, 실패하면(리프레시 토큰까지 만료) false.
  Future<bool> refreshAccessToken() => _refreshAccessToken();

  Future<void> clearTokens() async {
    _accessToken = null;
    _refreshToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(keyAccess);
    await prefs.remove(keyRefresh);
  }

  Future<dynamic> _request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
    bool retry = true,
  }) async {
    final uri = Uri.parse('$apiEndpoint$path');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (_accessToken != null) {
      headers['Authorization'] = 'Bearer $_accessToken';
    }

    http.Response res;
    try {
      if (method == 'POST') {
        res = await http
            .post(uri, headers: headers, body: body != null ? jsonEncode(body) : null)
            .timeout(requestTimeout);
      } else if (method == 'PATCH') {
        res = await http
            .patch(uri, headers: headers, body: body != null ? jsonEncode(body) : null)
            .timeout(requestTimeout);
      } else if (method == 'DELETE') {
        res = await http.delete(uri, headers: headers).timeout(requestTimeout);
      } else {
        res = await http.get(uri, headers: headers).timeout(requestTimeout);
      }
    } on TimeoutException {
      throw ApiException(0, 'timeout', '네트워크 응답이 없습니다. 잠시 후 다시 시도해주세요.');
    } catch (e) {
      throw ApiException(0, 'network', '서버에 연결할 수 없습니다. ($baseUrl)');
    }

    if (res.statusCode == 401 && retry && _refreshToken != null) {
      final renewed = await _refreshAccessToken();
      if (renewed) {
        return _request(path, method: method, body: body, retry: false);
      }
    }

    if (res.statusCode >= 400) {
      throw _errorFromResponse(res, path, method);
    }

    if (res.statusCode == 204 || res.body.isEmpty) {
      return null;
    }

    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  /// 오류 응답을 사람이 읽을 수 있는 예외로 바꾼다.
  /// (서버가 준 코드·메시지를 살리되, 401·409 는 더 분명한 말로 바꾼다)
  ApiException _errorFromResponse(http.Response res, String path, String method) {
    String code = 'error';
    String message = '요청이 실패했습니다 (${res.statusCode})';
    try {
      final errJson = jsonDecode(utf8.decode(res.bodyBytes));
      if (errJson is Map && errJson['error'] is Map) {
        final errObj = errJson['error'] as Map;
        code = errObj['code']?.toString() ?? code;
        message = errObj['message']?.toString() ?? message;
      } else if (errJson is Map && errJson['detail'] != null) {
        message = errJson['detail'].toString();
      }
    } catch (_) {}

    if (res.statusCode == 401) {
      message = _unauthorizedMessage(path, method, message);
    } else if (res.statusCode == 409) {
      message = '이미 존재하는 리소스입니다.';
    }
    return ApiException(res.statusCode, code, message);
  }

  /// 401 이 무슨 뜻인지 경로에 따라 구분한다.
  ///
  /// - 로그인/회원가입: 진짜로 비밀번호가 틀린 것
  /// - 그 밖의 엔드포인트: **세션 만료** (토큰이 유효하지 않다)
  ///
  /// 세션 만료를 "비밀번호가 틀렸다" 라고 말하면, 로그인 화면에 이미 있는 사용자가
  /// 진짜 비밀번호를 다시 눌러보게 된다. (잘못된 인상을 준다)
  String _unauthorizedMessage(String path, String method, String serverMessage) {
    final isLogin = path.contains('/auth/login');
    final isSignup = path.contains('/auth/signup');
    if (method.toUpperCase() == 'POST' && (isLogin || isSignup)) {
      return '이메일 또는 비밀번호가 맞지 않습니다.';
    }
    // 서버가 세션/토큰 만료라고 말했으면 그 말을 우선한다.
    final lower = serverMessage.toLowerCase();
    const keywords = ['expired', 'token', 'session', '만료', '세션', '토큰'];
    if (keywords.any(lower.contains)) {
      return serverMessage;
    }
    return '세션이 만료되었습니다. 다시 로그인해주세요.';
  }

  Future<bool> _refreshAccessToken() async {
    try {
      final uri = Uri.parse('$apiEndpoint/auth/refresh');
      final res = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'refresh_token': _refreshToken}),
          )
          .timeout(requestTimeout);
      if (res.statusCode == 200) {
        final data = jsonDecode(utf8.decode(res.bodyBytes));
        await setTokens(data['access_token'], data['refresh_token']);
        return true;
      }
    } catch (_) {}
    await clearTokens();
    return false;
  }

  // ── Auth ──────────────────────────────────────────────────────

  Future<Session> login(String email, String password) async {
    final res = await _request('/auth/login', method: 'POST', body: {
      'email': email,
      'password': password,
    });
    final session = Session.fromJson(res as Map<String, dynamic>);
    await setTokens(session.accessToken, session.refreshToken);
    return session;
  }

  Future<Session> signup({
    required String email,
    required String password,
    required String name,
    required String workspaceName,
  }) async {
    final res = await _request('/auth/signup', method: 'POST', body: {
      'email': email,
      'password': password,
      'name': name,
      'workspace_name': workspaceName,
    });
    final session = Session.fromJson(res as Map<String, dynamic>);
    await setTokens(session.accessToken, session.refreshToken);
    return session;
  }

  Future<User> getMe() async {
    final res = await _request('/me');
    return User.fromJson(res as Map<String, dynamic>);
  }

  Future<User> updateMe({String? name, String? title, String? avatarColor, Presence? presence}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (title != null) body['title'] = title;
    if (avatarColor != null) body['avatar_color'] = avatarColor;
    if (presence != null) body['presence'] = presence.apiValue;
    final res = await _request('/me', method: 'PATCH', body: body);
    return User.fromJson(res as Map<String, dynamic>);
  }

  // ── Workspaces & Bootstrap ───────────────────────────────────

  Future<List<Workspace>> getWorkspaces() async {
    final res = await _request('/workspaces');
    return (res as List).map((e) => Workspace.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Bootstrap> getBootstrap(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/bootstrap');
    return Bootstrap.fromJson(res as Map<String, dynamic>);
  }

  // ── Channels & DMs ───────────────────────────────────────────

  Future<List<Channel>> getChannels(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/channels');
    return (res as List).map((e) => Channel.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Channel>> getDms(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/dms');
    return (res as List).map((e) => Channel.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Channel> createChannel({
    required String workspaceId,
    required String name,
    String? topic,
    bool isPrivate = false,
    List<String>? memberIds,
  }) async {
    final res = await _request(
      '/workspaces/$workspaceId/channels',
      method: 'POST',
      body: {
        'name': name,
        if (topic != null) 'topic': topic,
        'is_private': isPrivate,
        if (memberIds != null) 'member_ids': memberIds,
      },
    );
    return Channel.fromJson(res as Map<String, dynamic>);
  }

  /// 채널 이름·주제·목적을 고친다. (PATCH /api/v1/channels/{channel_id})
  /// null 인 항목은 "변경 안 함" 이므로 본문에 넣지 않는다.
  Future<Channel> updateChannel(
    String channelId, {
    String? name,
    String? topic,
    String? purpose,
  }) async {
    final res = await _request(
      '/channels/$channelId',
      method: 'PATCH',
      body: {
        if (name != null) 'name': name,
        if (topic != null) 'topic': topic,
        if (purpose != null) 'purpose': purpose,
      },
    );
    return Channel.fromJson(res as Map<String, dynamic>);
  }

  /// 공개 채널에 들어간다. (POST /api/v1/channels/{channel_id}/join)
  Future<Channel> joinChannel(String channelId) async {
    final res = await _request('/channels/$channelId/join', method: 'POST');
    return Channel.fromJson(res as Map<String, dynamic>);
  }

  /// 채널을 삭제한다. (주최자만) (DELETE /api/v1/channels/{channel_id})
  Future<void> deleteChannel(String channelId) async {
    await _request('/channels/$channelId', method: 'DELETE');
  }

  Future<Channel> openDm(String workspaceId, String userId) async {
    final res = await _request('/workspaces/$workspaceId/dms', method: 'POST', body: {
      'user_id': userId,
    });
    return Channel.fromJson(res as Map<String, dynamic>);
  }

  Future<void> leaveChannel(String channelId) async {
    await _request('/channels/$channelId/leave', method: 'POST');
  }

  Future<void> deleteDm(String channelId) async {
    await _request('/channels/$channelId', method: 'DELETE');
  }

  Future<List<Member>> getChannelMembers(String channelId) async {
    final res = await _request('/channels/$channelId/members');
    return (res as List).map((e) => Member.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> addChannelMember(String channelId, String userId) async {
    await _request('/channels/$channelId/members', method: 'POST', body: {'user_id': userId});
  }

  Future<void> markRead(String channelId, {String? messageId}) async {
    await _request(
      '/channels/$channelId/read',
      method: 'POST',
      body: messageId != null ? {'message_id': messageId} : {},
    );
  }

  // ── Messages ─────────────────────────────────────────────────

  /// 메시지 한 페이지와 "더 이전 메시지가 남았는지" 를 함께 돌려준다.
  /// 서버가 준 `has_more` 를 그대로 쓰기 위해 `(List<Message>, bool)` 로 반환한다.
  /// (messages, hasMore, hasMoreAfter)
  ///
  /// [before] 은 과거 방향, [after] 는 최신 방향, [around] 은 기준 메시지를 가운데 둔 창.
  /// 커서는 전부 exclusive 다 (기준 메시지는 [around] 일 때만 포함된다).
  Future<(List<Message>, bool, bool)> getMessages(
    String channelId, {
    int limit = 50,
    String? before,
    String? after,
    String? around,
  }) async {
    String query = '?limit=$limit';
    if (before != null) query += '&before=$before';
    if (after != null) query += '&after=$after';
    if (around != null) query += '&around=$around';
    final res = await _request('/channels/$channelId/messages$query') as Map<String, dynamic>;
    final list = (res['messages'] as List<dynamic>? ?? []);
    final messages = list.map((e) => Message.fromJson(e as Map<String, dynamic>)).toList();
    final hasMore = res['has_more'] as bool? ?? false;
    final hasMoreAfter = res['has_more_after'] as bool? ?? false;
    return (messages, hasMore, hasMoreAfter);
  }

  Future<Message> sendMessage({
    required String channelId,
    required String body,
    String? parentId,
    String? replyToId,
    bool inline = false,
    List<String>? attachmentIds,
  }) async {
    final payload = <String, dynamic>{
      'body': body,
      if (parentId != null) 'parent_id': parentId,
      if (replyToId != null) 'reply_to_id': replyToId,
      'inline': inline,
      if (attachmentIds != null && attachmentIds.isNotEmpty) 'attachment_ids': attachmentIds,
    };
    final res = await _request('/channels/$channelId/messages', method: 'POST', body: payload);
    return Message.fromJson(res as Map<String, dynamic>);
  }

  Future<Message> editMessage(String messageId, String body) async {
    final res = await _request('/messages/$messageId', method: 'PATCH', body: {'body': body});
    return Message.fromJson(res as Map<String, dynamic>);
  }

  Future<void> deleteMessage(String messageId) async {
    await _request('/messages/$messageId', method: 'DELETE');
  }

  /// 삭제했던 메시지를 서버에서 되돌린다 ("실행 취소").
  /// 서버가 되돌린 메시지를 그대로 돌려준다.
  Future<Message> restoreMessage(String messageId) async {
    final res = await _request('/messages/$messageId/restore', method: 'POST');
    return Message.fromJson(res as Map<String, dynamic>);
  }

  Future<List<Message>> getReplies(String messageId, {int limit = 100}) async {
    final res = await _request('/messages/$messageId/replies?limit=$limit');
    return (res as List).map((e) => Message.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Message> toggleReaction(String messageId, String emoji, bool currentMe) async {
    if (currentMe) {
      final res = await _request('/messages/$messageId/reactions/${Uri.encodeComponent(emoji)}', method: 'DELETE');
      return Message.fromJson(res as Map<String, dynamic>);
    } else {
      final res = await _request('/messages/$messageId/reactions', method: 'POST', body: {'emoji': emoji});
      return Message.fromJson(res as Map<String, dynamic>);
    }
  }

  Future<Message> togglePin(String messageId, bool currentPinned) async {
    final method = currentPinned ? 'DELETE' : 'POST';
    final res = await _request('/messages/$messageId/pin', method: method);
    return Message.fromJson(res as Map<String, dynamic>);
  }

  Future<List<Message>> getPins(String channelId) async {
    final res = await _request('/channels/$channelId/pins');
    return (res as List).map((e) => Message.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ── 구성원 · 초대 ───────────────────────────────────────────

  /// 워크스페이스 구성원 목록. (GET /api/v1/workspaces/{id}/members)
  Future<List<Member>> getMembers(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/members');
    return (res as List).map((e) => Member.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 구성원의 역할을 바꾼다. (owner · admin · member)
  Future<Member> updateMemberRole(String workspaceId, String userId, String role) async {
    final res = await _request(
      '/workspaces/$workspaceId/members/$userId',
      method: 'PATCH',
      body: {'role': role},
    );
    return Member.fromJson(res as Map<String, dynamic>);
  }

  /// 구성원을 워크스페이스에서 내보낸다.
  Future<void> removeMember(String workspaceId, String userId) async {
    await _request('/workspaces/$workspaceId/members/$userId', method: 'DELETE');
  }

  /// 전역 사용자 검색. (초대 대상 찾기 · 조직원 추가에 쓴다)
  Future<List<User>> searchUsers(String query) async {
    final res = await _request('/users?q=${Uri.encodeComponent(query)}');
    return (res as List).map((e) => User.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 보낸 초대 목록. (GET /api/v1/workspaces/{id}/invites)
  Future<List<Invite>> getInvites(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/invites');
    return (res as List).map((e) => Invite.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 이메일로 초대장을 만든다. (POST /api/v1/workspaces/{id}/invites)
  Future<Invite> createInvite(String workspaceId, {required String email, String role = 'member'}) async {
    final res = await _request(
      '/workspaces/$workspaceId/invites',
      method: 'POST',
      body: {'email': email, 'role': role},
    );
    return Invite.fromJson(res as Map<String, dynamic>);
  }

  /// 초대장을 취소한다.
  Future<void> revokeInvite(String workspaceId, String inviteId) async {
    await _request('/workspaces/$workspaceId/invites/$inviteId', method: 'DELETE');
  }

  /// 초대 코드로 팀에 들어간다. (POST /api/v1/invites/accept)
  ///
  /// 로그인한 뒤에 부른다. (코드만으로는 로그인할 수 없다)
  Future<Workspace> acceptInvite(String token) async {
    final res = await _request('/invites/accept', method: 'POST', body: {'token': token.trim()});
    return Workspace.fromJson(res as Map<String, dynamic>);
  }

  // ── 파일 업로드 ─────────────────────────────────────────────

  /// 워크스페이스에 파일을 올린다. (POST /api/v1/files?workspace_id=…)
  ///
  /// 데스크톱처럼 "먼저 올리고 그 id 를 메시지에 붙이는" 방식이다.
  /// (메시지를 먼저 보내고 파일을 나중에 붙일 수는 없다)
  Future<FileRef> uploadFile({
    required String workspaceId,
    required String filePath,
    String? fileName,
  }) async {
    final uri = Uri.parse('$apiEndpoint/files?workspace_id=${Uri.encodeComponent(workspaceId)}');
    final request = http.MultipartRequest('POST', uri);
    final token = _accessToken;
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(
      await http.MultipartFile.fromPath('file', filePath, filename: fileName),
    );

    http.Response res;
    try {
      final streamed = await request.send().timeout(requestTimeout);
      res = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw ApiException(0, 'timeout', '파일 업로드가 시간 내에 끝나지 않았습니다.');
    } catch (_) {
      throw ApiException(0, 'network', '서버에 연결할 수 없습니다. ($baseUrl)');
    }

    if (res.statusCode >= 400) {
      throw _errorFromResponse(res, '/files', 'POST');
    }
    final data = jsonDecode(utf8.decode(res.bodyBytes));
    return FileRef.fromJson(data as Map<String, dynamic>);
  }

  // ── Schedule ─────────────────────────────────────────────────

  Future<List<ScheduleEvent>> getEvents(String workspaceId, {DateTime? from, DateTime? to}) async {
    String query = '';
    if (from != null && to != null) {
      query = '?from=${from.toUtc().toIso8601String()}&to=${to.toUtc().toIso8601String()}';
    }
    final res = await _request('/workspaces/$workspaceId/events$query');
    return (res as List).map((e) => ScheduleEvent.fromJson(e as Map<String, dynamic>)).toList();
  }

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
  }) async {
    final res = await _request(
      '/workspaces/$workspaceId/events',
      method: 'POST',
      body: {
        'title': title,
        'description': description ?? '',
        'location': location ?? '',
        'starts_at': startsAt.toUtc().toIso8601String(),
        'ends_at': endsAt.toUtc().toIso8601String(),
        'all_day': allDay,
        'is_private': isPrivate,
        if (channelId != null) 'channel_id': channelId,
        if (attendeeIds != null) 'attendee_ids': attendeeIds,
      },
    );
    return ScheduleEvent.fromJson(res as Map<String, dynamic>);
  }

  Future<ScheduleEvent> rsvpEvent(String eventId, EventResponse response) async {
    final res = await _request(
      '/events/$eventId/rsvp',
      method: 'POST',
      body: {'response': response.name},
    );
    return ScheduleEvent.fromJson(res as Map<String, dynamic>);
  }

  /// 일정을 고친다. (PATCH /api/v1/events/{event_id})
  /// null 인 항목은 "변경 안 함" 이므로 본문에 넣지 않는다.
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
    final res = await _request(
      '/events/$eventId',
      method: 'PATCH',
      body: {
        if (title != null) 'title': title,
        if (description != null) 'description': description,
        if (location != null) 'location': location,
        if (startsAt != null) 'starts_at': startsAt.toUtc().toIso8601String(),
        if (endsAt != null) 'ends_at': endsAt.toUtc().toIso8601String(),
        if (allDay != null) 'all_day': allDay,
        if (isPrivate != null) 'is_private': isPrivate,
        if (channelId != null) 'channel_id': channelId,
        if (attendeeIds != null) 'attendee_ids': attendeeIds,
      },
    );
    return ScheduleEvent.fromJson(res as Map<String, dynamic>);
  }

  Future<void> deleteEvent(String eventId) async {
    await _request('/events/$eventId', method: 'DELETE');
  }

  // ── Projects & Tasks ─────────────────────────────────────────

  Future<List<Project>> getProjects(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/projects');
    return (res as List).map((e) => Project.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Project> createProject({
    required String workspaceId,
    required String name,
    String? description,
    String? channelId,
    List<String>? memberIds,
  }) async {
    final res = await _request(
      '/workspaces/$workspaceId/projects',
      method: 'POST',
      body: {
        'name': name,
        'description': description ?? '',
        if (channelId != null) 'channel_id': channelId,
        if (memberIds != null) 'member_ids': memberIds,
      },
    );
    return Project.fromJson(res as Map<String, dynamic>);
  }

  /// 프로젝트를 고친다. (PATCH /api/v1/projects/{project_id})
  Future<Project> updateProject(
    String projectId, {
    String? name,
    String? description,
    String? channelId,
    List<String>? memberIds,
    bool? isArchived,
  }) async {
    final res = await _request(
      '/projects/$projectId',
      method: 'PATCH',
      body: {
        if (name != null) 'name': name,
        if (description != null) 'description': description,
        if (channelId != null) 'channel_id': channelId,
        if (memberIds != null) 'member_ids': memberIds,
        if (isArchived != null) 'is_archived': isArchived,
      },
    );
    return Project.fromJson(res as Map<String, dynamic>);
  }

  /// 프로젝트를 지운다.
  Future<void> deleteProject(String projectId) async {
    await _request('/projects/$projectId', method: 'DELETE');
  }

  /// 프로젝트에 사람을 넣는다.
  Future<void> addProjectMember(String projectId, String userId) async {
    await _request('/projects/$projectId/members', method: 'POST', body: {'user_id': userId});
  }

  /// 프로젝트에서 사람을 뺀다.
  Future<void> removeProjectMember(String projectId, String userId) async {
    await _request('/projects/$projectId/members/$userId', method: 'DELETE');
  }

  /// 내 할 일만 모아서 가져온다. (GET /api/v1/workspaces/{id}/tasks)
  Future<List<Task>> getMyTasks(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/tasks');
    return (res as List).map((e) => Task.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Task>> getProjectTasks(String projectId) async {
    final res = await _request('/projects/$projectId/tasks');
    return (res as List).map((e) => Task.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Task> createTask({
    required String projectId,
    required String title,
    String? description,
    TaskStatus status = TaskStatus.todo,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
  }) async {
    final res = await _request(
      '/projects/$projectId/tasks',
      method: 'POST',
      body: {
        'title': title,
        'description': description ?? '',
        'status': status.apiValue,
        if (assigneeId != null) 'assignee_id': assigneeId,
        if (dueAt != null) 'due_at': dueAt.toUtc().toIso8601String(),
        if (roadmapId != null) 'roadmap_id': roadmapId,
        if (milestoneId != null) 'milestone_id': milestoneId,
      },
    );
    return Task.fromJson(res as Map<String, dynamic>);
  }

  Future<Task> updateTask(
    String taskId, {
    String? title,
    String? description,
    TaskStatus? status,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
    int? position,
  }) async {
    final body = <String, dynamic>{};
    if (title != null) body['title'] = title;
    if (description != null) body['description'] = description;
    if (status != null) body['status'] = status.apiValue;
    if (assigneeId != null) body['assignee_id'] = assigneeId;
    if (dueAt != null) body['due_at'] = dueAt.toUtc().toIso8601String();
    if (roadmapId != null) body['roadmap_id'] = roadmapId;
    if (milestoneId != null) body['milestone_id'] = milestoneId;
    if (position != null) body['position'] = position;

    final res = await _request('/tasks/$taskId', method: 'PATCH', body: body);
    return Task.fromJson(res as Map<String, dynamic>);
  }

  Future<void> deleteTask(String taskId) async {
    await _request('/tasks/$taskId', method: 'DELETE');
  }

  Future<TaskComment> addTaskComment(String taskId, String body) async {
    final res = await _request('/tasks/$taskId/comments', method: 'POST', body: {'body': body});
    return TaskComment.fromJson(res as Map<String, dynamic>);
  }

  /// 의견(댓글)을 지운다.
  Future<void> deleteTaskComment(String commentId) async {
    await _request('/task-comments/$commentId', method: 'DELETE');
  }

  /// 마일스톤을 만든다. (POST /api/v1/projects/{project_id}/milestones)
  Future<Milestone> createMilestone(
    String projectId, {
    required String title,
    required DateTime startAt,
    required DateTime endAt,
    String description = '',
    String color = '#4f6cff',
    int progress = 0,
    List<String>? taskIds,
  }) async {
    final res = await _request(
      '/projects/$projectId/milestones',
      method: 'POST',
      body: {
        'title': title,
        'start_at': startAt.toUtc().toIso8601String(),
        'end_at': endAt.toUtc().toIso8601String(),
        'description': description,
        'color': color,
        'progress': progress,
        if (taskIds != null) 'task_ids': taskIds,
      },
    );
    return Milestone.fromJson(res as Map<String, dynamic>);
  }

  /// 마일스톤을 고친다. (PATCH /api/v1/milestones/{milestone_id})
  Future<Milestone> updateMilestone(
    String milestoneId, {
    String? title,
    DateTime? startAt,
    DateTime? endAt,
    String? description,
    String? color,
    int? progress,
    List<String>? taskIds,
  }) async {
    final res = await _request(
      '/milestones/$milestoneId',
      method: 'PATCH',
      body: {
        if (title != null) 'title': title,
        if (startAt != null) 'start_at': startAt.toUtc().toIso8601String(),
        if (endAt != null) 'end_at': endAt.toUtc().toIso8601String(),
        if (description != null) 'description': description,
        if (color != null) 'color': color,
        if (progress != null) 'progress': progress,
        if (taskIds != null) 'task_ids': taskIds,
      },
    );
    return Milestone.fromJson(res as Map<String, dynamic>);
  }

  /// 마일스톤을 지운다.
  Future<void> deleteMilestone(String milestoneId) async {
    await _request('/milestones/$milestoneId', method: 'DELETE');
  }

  /// 로드맵을 지운다.
  Future<void> deleteRoadmap(String roadmapId) async {
    await _request('/roadmaps/$roadmapId', method: 'DELETE');
  }

  Future<List<Roadmap>> getRoadmaps(String projectId) async {
    final res = await _request('/projects/$projectId/roadmaps');
    return (res as List).map((e) => Roadmap.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Milestone>> getMilestones(String projectId) async {
    final res = await _request('/projects/$projectId/milestones');
    return (res as List).map((e) => Milestone.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ── Organization ─────────────────────────────────────────────

  Future<OrgOverview> getOrgOverview(String workspaceId) async {
    final res = await _request('/workspaces/$workspaceId/org');
    return OrgOverview.fromJson(res as Map<String, dynamic>);
  }

  Future<OrgUnit> createOrgUnit({
    required String workspaceId,
    required String name,
    String? parentId,
    String kind = '부서',
    String description = '',
  }) async {
    final res = await _request(
      '/workspaces/$workspaceId/org/units',
      method: 'POST',
      body: {
        'name': name,
        if (parentId != null) 'parent_id': parentId,
        'kind': kind,
        'description': description,
      },
    );
    return OrgUnit.fromJson(res as Map<String, dynamic>);
  }

  /// 조직 단위를 고친다. (PATCH /api/v1/org/units/{unit_id})
  /// parentId 를 빈 문자열로 주면 상위 조직을 떼는 것으로 본다.
  Future<OrgUnit> updateOrgUnit(
    String unitId, {
    String? name,
    String? parentId,
    String? kind,
    String? description,
  }) async {
    final res = await _request(
      '/org/units/$unitId',
      method: 'PATCH',
      body: {
        if (name != null) 'name': name,
        if (parentId != null) 'parent_id': parentId,
        if (kind != null) 'kind': kind,
        if (description != null) 'description': description,
      },
    );
    return OrgUnit.fromJson(res as Map<String, dynamic>);
  }

  /// 조직 단위를 지운다.
  Future<void> deleteOrgUnit(String unitId) async {
    await _request('/org/units/$unitId', method: 'DELETE');
  }

  /// 조직에 사람을 넣는다.
  Future<void> addOrgUnitMember(String unitId, String userId) async {
    await _request('/org/units/$unitId/members', method: 'POST', body: {'user_id': userId});
  }

  /// 조직에서 사람을 뺀다.
  Future<void> removeOrgUnitMember(String unitId, String userId) async {
    await _request('/org/units/$unitId/members/$userId', method: 'DELETE');
  }

  /// 조직 관리자로 임명한다.
  Future<void> addOrgUnitManager(String unitId, String userId) async {
    await _request('/org/units/$unitId/managers', method: 'POST', body: {'user_id': userId});
  }

  /// 조직 관리자에서 해임한다.
  Future<void> removeOrgUnitManager(String unitId, String userId) async {
    await _request('/org/units/$unitId/managers/$userId', method: 'DELETE');
  }

  // ── Search ───────────────────────────────────────────────────

  Future<List<SearchResult>> search(String workspaceId, String query) async {
    final res = await _request('/workspaces/$workspaceId/search?q=${Uri.encodeComponent(query)}&limit=30');
    return (res as List).map((e) => SearchResult.fromJson(e as Map<String, dynamic>)).toList();
  }
}
