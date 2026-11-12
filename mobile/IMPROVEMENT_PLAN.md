# Llack 모바일 — 개선 작업 명세 (모바일 UX 테스트 결과 기반)

에뮬레이터(Android Pixel 7, 411×914dp) + 실제 손동작 테스트와 정적 코드 리뷰로 확인된 문제들이다.
아래는 **3개 병렬 에이전트가 공유하는 계약(contract)** 이다. 각 에이전트는 자기 파일만 수정하고,
`lib/providers/app_state.dart` 의 공개 API 는 아래 명세를 **정확히** 지켜야 한다.

---

## 0. 파일 소유권 (충돌 금지)

| 에이전트 | 담당 파일 (오직 이 파일들만 수정) |
|---|---|
| **A — Core** | `lib/providers/app_state.dart`, `lib/providers/app_state_*.dart`, `lib/providers/list_upsert.dart`, `lib/services/api_service.dart`, `lib/services/ws_service.dart`, `lib/models/models.dart` |
| **B — Chat** | `lib/screens/chat/*.dart`, `lib/widgets/message_bubble.dart`, `lib/widgets/message_composer.dart`, `lib/screens/search/search_dialog.dart` |
| **C — Shell & Tabs** | `lib/screens/main_shell.dart`, `lib/screens/auth_screen.dart`, `lib/screens/settings/settings_sheet.dart`, `lib/screens/schedule/*.dart`, `lib/screens/projects/*.dart`, `lib/screens/org/org_screen.dart`, `lib/theme/*.dart`, `lib/widgets/llack_avatar.dart`, `lib/widgets/presence_badge.dart` |
| **공통(수정 금지)** | `lib/main.dart`, `lib/responsive/screen_type.dart`, `android/**`, `pubspec.yaml` |

`lib/main.dart` 은 어느 에이전트도 건드리지 않는다. (main.dart 는 `isBooting` 만 보고 화면을 갈아끼우도록
작성되어 있는데, 이 동작 자체가 버그다. 그건 §1-A 에서 Core가 해결한다.)

---

## 1. Core 에이전트 (A) — 계약

### 1-0. Core 가 반드시 구현해야 하는 공개 API 목록 (B·C 가 이 시그니처를 그대로 사용한다)

B·C 에이전트는 Core 에게 요청할 수 없다(에이전트 간 통신 없음). 따라서 아래 API 는
**Core(A) 가 이름·시그니처를 정확히 구현하는 것이 필수** 이다. B·C 는 아래 시그니처를
가정하고 코드를 작성한다. (Core 가 이미 비슷한 게 있으면 이름을 맞춰서 시그니처를 맞춘다.)

```dart
// ── 인증 ───────────────────────────────────────────────────────────
bool get isAuthenticating;              // 로그인/회원가입 진행 중 (isBooting 과 별개)
String? get authError;                  // 로그인 실패 사유 (한국어)
void clearAuthError();
// ★ 기존 시그니처를 **그대로 유지**하고 반환 타입만 Future<void> → Future<bool> 로 바꾼다.
//   (호출부가 결과를 무시해도 컴파일되므로 C 에이전트가 부수는 일이 없다)
Future<bool> login(String email, String password);
Future<bool> signup({
  required String email,
  required String password,
  required String name,
  required String workspaceName,
});

// ── 워크스페이스 새로고침 (당겨서 갱신용) ───────────────────────────
Future<void> refreshWorkspace();        // 스플래시 없음, 토큰 삭제 없음, 실패해도 로그아웃 금지

// ── 연결 상태 ──────────────────────────────────────────────────────
bool get isConnected;                   // WebSocket 연결 여부
String? get connectionError;            // 끊긴 사유 (있으면)

// ── 탭 이동 (검색/신규DM/조직도에서 다른 탭으로 갈 때) ─────────────
final ValueNotifier<int> tabIndex;      // MainShell 이 listen
void goToTab(int index);                // 0 메시지, 1 일정, 2 프로젝트, 3 조직도

// ── 메시지 ─────────────────────────────────────────────────────────
Future<bool> sendMessage(String body);  // 실패 시 false 반환 (B가 입력값을 되살린다)
Future<void> undoDeleteMessage(String messageId, String channelId);
bool hasLoadedHistory(String channelId);
Future<List<Member>> membersForChannel(String channelId);
void sendTyping(bool on, String channelId);   // 채널 id 를 명시 (기존 sendTyping(bool) 의 확장)
List<String> get currentTypingUsers;          // 5초 이상 지난 것은 제외

// ── 섹션별 오류 상태 (빈 상태와 구분해서 그리기 위해) ───────────────
String? get channelsError;   Future<void> retryChannels();
String? get messagesError;   Future<void> retryMessages();
String? get eventsError;     Future<void> retryEvents();
String? get projectsError;   Future<void> retryProjects();
String? get orgError;        Future<void> retryOrg();

// ── 서버 주소 변경 (설정 시트) ─────────────────────────────────────
Future<void> changeApiBaseUrl(String url);
```

### 1-0-1. `MainShell` ↔ `AppState` 연결 (C 가 구현)

`MainShell` 은 `IndexedStack` + 하단 네비게이션을 가지고 있다. C 는 `AppState.tabIndex`
(`ValueNotifier<int>`) 를 `ValueListenableBuilder` 로 listen 하여 현재 탭을 표시하고,
`AppState.goToTab(i)` 가 `tabIndex.value = i` 로 바꾸도록 한다. (Core 는 `tabIndex` 를
`ValueNotifier<int>` 로 노출하고 `goToTab` 을 구현한다.)

### 1-A-1. 로그인 실패가 조용히 사라지는 문제 (BLOCKER, 실기 확인됨)

**현상**: 잘못된 비밀번호로 로그인 → 화면이 잠깐 스플래시로 바뀌고 → **에러 메시지가 전혀 없다.**
이메일/비밀번호 칸은 `demo@example.com` / `password123` 으로 되돌아간다.

**원인**: `AppState.login()` 이 `_isBooting = true` 로 만든다. `main.dart` 는 `isBooting` 이면
`AuthScreen` 대신 스플래시 Scaffold 를 렌더한다 → `AuthScreen` 이 dispose 되면서 `_errorMessage` 와
입력 컨트롤러가 사라진다. 에러는 `dispose` 된 State 에 `setState` 되므로 버려진다.

**해결 (A)**:
- `AppState` 에 아래 멤버를 추가한다. `isBooting` 과 **분리**한다.

```dart
  // ── 인증 (isBooting 과 분리: 로그인 폼이 스플래시로 교체되지 않게) ──
  bool _isAuthenticating = false;
  String? _authError;

  bool get isAuthenticating => _isAuthenticating;
  String? get authError => _authError;
  void clearAuthError() { _authError = null; notifyListeners(); }
```

- `login()` / `signup()` 은 `_isBooting` 을 건드리지 말고 `_isAuthenticating` 만 쓴다.
- **`_isBooting` 은 `boot()` 안에서만 true 가 될 수 있다.** (콜드 스타트 전용)
  다른 어디에서도 `_isBooting = true` 를 대입하지 마라. `main.dart` 의
  `if (state.isBooting) return 스플래시` 가 로그인/새로고침 때도 발동하는 것이 버그의 근본이다.
- 실패 시 `catch` 에서 `_authError = <사용자에게 보여줄 한국어 메시지>` 로 저장하고 `notifyListeners()`.
  `ApiException.message` 를 그대로 쓰되, 401 이면 `"이메일 또는 비밀번호가 맞지 않습니다."`.
- 성공 시 `_authError = null`.
- `AppState.login` 은 예외를 다시 던지지 **않는다** (호출부가 세 군데라 중복 처리 방지). 대신
  `authError` 로 결과를 알린다. 그래도 던지길 원하면 `rethrow` 하되 `authError` 도 반드시 세팅한다.

**해결 (C)**: `AuthScreen` 은 `_errorMessage` 로컬 상태를 **삭제**하고 `context.watch<AppState>().authError` 를
그대로 화면에 보여준다. 폼이 dispose 되지 않으므로 사용자가 입력한 이메일/비밀번호도 유지된다.
`_submit()` 의 `catch` 는 `if (!mounted) return;` 가드.

### 1-A-2. 로그인 폼에 존재하지 않는 데모 계정이 미리 채워져 있음

`auth_screen.dart` 의 `_emailCtrl` 기본값 `demo@example.com`, `_passCtrl` 기본값 `password123` 는
**실제 계정이 아니다**(실제 데모: `hyunjin@hanbit.co.kr` / `hanbit2026`). 사용자가 "로그인"을 누르면
항상 실패한다. **두 필드를 빈 값으로 시작**하고, 힌트 텍스트만 넣는다.
(비밀번호 표시는 `obscureText` + **눈 아이콘 토글**을 추가. 비밀번호를 다시 입력하려면
전부 지워야 하는 불편이 있었다.)

### 1-A-3. 새로고침(당겨서 갱신)이 앱 전체를 스플래시로 교체 + 오프라인이면 로그아웃 (BLOCKER, 실기 확인됨)

**현상**: 채널 목록을 아래로 끌면 전체 앱이 "Llack 연결 중..." 스플래시로 바뀐다.
서버가 죽어 있으면 **로그아웃되어 로그인 화면으로 튕긴다**(입력도 초기화).

**원인**: `ChatTab` 의 `RefreshIndicator(onRefresh: () => state.boot())`. `boot()` 은 `_isBooting = true`
로 만들고, `getMe()` 이 실패하면 `api.clearTokens()` + `_currentUser = null` 로 만들어 로그아웃시킨다.

**해결 (A)**:

```dart
  /// 워크스페이스 데이터를 다시 불러온다. 앱을 스플래시로 바꾸지 않고, 토큰도 지우지 않는다.
  Future<void> refreshWorkspace() async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) return;
    try {
      final bootstrap = await api.getBootstrap(wsId);
      _channels = [...bootstrap.channels, ...bootstrap.dms];
      _members = bootstrap.members;
      for (final m in _members) { _presence[m.user.id] = m.user.presence; }
      _channelsError = null;
    } catch (e) {
      _channelsError = '채널 목록을 불러오지 못했습니다. 다시 시도해주세요.';
    }
    notifyListeners();
  }
```

- `boot()` 은 **콜드 스타트 전용**으로만 쓴다. `refreshWorkspace()` 는 토큰을 지우지 않는다.
- `refreshWorkspace()` 는 HTTP 실패 시 토큰을 만지지 않는다. (401 이면 세션 만료로 간주해
  `_currentUser = null` 로 로그아웃시키는 것은 "당겨서 갱신"이 절대 하지 않아야 한다.
  오프라인(네트워크 예외)일 때는 **절대** 로그아웃시키지 않는다.)

### 1-A-4. 부팅 스플래시 없이 바로 렌더 (main.dart 는 손대지 않음)

`main.dart` 는 `await appState.boot()` 후 `runApp` 한다. `boot()` 이 `isBooting` 을 유지하는 동안
`main.dart` 의 `isBooting` 분기가 스플래시를 그린다. **이 구조는 그대로 두고**, A는
`AppState.boot()` 안에서만 `isBooting` 을 다루게 한다. (main.dart 는 어느 에이전트도 수정하지 않는다.)

> **후속 수정 (2026-11-09, §9-30)** — 실기에서 이 구조의 결과가 확인됐다.
> `runApp` 이 `boot()` **뒤에** 있으므로 Flutter 프레임이 그 전엔 아예 안 그려진다 →
> `main.dart` 의 "Llack 연결 중..." 분기가 **죽은 코드**가 되고, 사용자는 6~8초 동안
> **진행 표시 없는 네이티브 스플래시(로고)** 만 본다.
> → **§9-30** 에서 예외 권한을 부여받아 C 가 `main()` 안의 `runApp` / `boot()` **순서만** 바꾼다.
> (`isBooting` 의 의미 — "콜드 스타트 중에만 true" — 는 그대로 살아 있다.)

### 1-A-5. 실시간(WS) 계약 불일치 — 안 읽일 안뜸 배지가 서버와 어긋남 (MAJOR)

서버는 `{"type":"unread","channel_id":...,"count":N}` 을 보낸다. 그런데 모바일은
`event['counts'] as Map<String,dynamic>?` 를 읽는다 → 항상 null → **핸들러가 실행되지 않는다.**

```dart
      case 'unread': {
        final cid = event['channel_id'] as String?;
        final count = event['count'] as int?;
        if (cid != null) {
          final idx = _channels.indexWhere((c) => c.id == cid);
          if (idx != -1) {
            _channels[idx] = _channels[idx].copyWith(unreadCount: count ?? 0);
            notifyListeners();
          }
        }
        break;
      }
```
(백엔드 `app/realtime/events.py` 의 실제 payload 를 먼저 확인하고 거기에 맞춰 작성한다.)

### 1-A-6. 재접속 백오프가 1초 고정이므로 서버가 죽으면 1초마다 소켓을 연다 (MAJOR, 배터리·데이터 소모)

`ws_service.dart` 의 `_open()` 이 성공 여부를 알기도 전에 `_attempt = 0` 으로 만든다 → `1 << _attempt` 가
항상 1. **연결이 실제로 성립했을 때만** `_attempt` 를 초기화하라.

```dart
  // _open() 안에서 _attempt = 0 을 제거하고,
  // 스트림이 처음 메시지를 받았을 때 (또는 ready 상태에서) _attempt = 0 으로 되돌린다.
```

### 1-A-7. 입력 중(typing) 표시가 엉뚱한 채널로 보내지고 영원히 안 꺼진다 (MAJOR)

- `AppState.sendTyping` 은 "지금 활성화된 채널" 로 보낸다. → 타이핑 도중 다른 탭/채널로 옮기면
  엉뚱한 채널에 `off` 가 보내져 **상대 화면에 "입력 중" 이 영구히 남는다.**
- 수신 측에도 만료가 없다.

**해결 (A)**:
- `AppState` 에 `String? _typingChannelId;` 를 두고 `sendTyping(bool on, String channelId)` 는
  **호출한 채널 id** 로 보낸다. `_typingChannelId` 가 다르면 `off` 를 먼저 보낸다.
- 수신 측 `_typing` 은 `Map<String, Map<String, DateTime>>`(채널 → (이름 → 시각)) 로 바꾸고,
  `currentTypingUsers` getter 는 **5초 이상 지난 항목을 제외**하고 돌려준다. 그래야 서버가 죽어도
  무한정 남지 않는다.

```dart
  final Map<String, Map<String, DateTime>> _typing = {};
  List<String> get currentTypingUsers {
    final cid = _activeChannelId;
    if (cid == null) return const [];
    final now = DateTime.now();
    final users = _typing[cid] ?? const {};
    users.removeWhere((_, ts) => now.difference(ts) > const Duration(seconds: 5));
    return users.keys.toList();
  }
  void sendTyping(bool on, String channelId);
```

### 1-A-8. 내 답글을 쓰면 "답글 N개" 가 2씩 늘어난다 (MAJOR)

`sendReply()` 이 로컬에서 `replyCount` 를 +1 하고, 서버가 내 메시지를 WS 로 다시 보내면서
`message.created` 핸들러가 또 +1 한다. → **로컬 증가를 삭제**하고 WS 이벤트만 믿는다.

### 1-A-9. 워크스페이스를 바꾸면 일정/프로젝트/조직도 탭이 비어버린다 (MAJOR)

`selectWorkspace()` 가 `_events`, `_projects`, `_orgOverview` 을 비우지만, 각 탭 스크린은
`initState` 에서만 데이터를 불러온다(`IndexedStack` 안이라 재생성되지 않는다).

**해결 (A)**: `selectWorkspace()` 마지막에 `loadEvents(); loadProjects(); loadOrg();` 를 호출한다.

### 1-A-10. 채널을 떠나면 대화창이 빈 화면이 된다 (MAJOR)

`leaveChannel()` / `deleteDm()` 이 `_activeChannelId` 만 바꿔서 `loadMessages` 를 호출하지 않는다.
→ `selectChannel(_channels.first.id)` 로 바꾸거나, 대입 직후 `loadMessages` 를 부른다.

### 1-A-11. WS 로 먼저 도착한 메시지가 있는 채널은 "메시지 1개만" 보인다 (MAJOR)

`_upsertMessage` 가 아직 열지 않은 채널에 `_messages[cid] = [그 한 개]` 를 만든다.
`selectChannel` 의 `if (!_messages.containsKey(...) || isEmpty) loadMessages(...)` 조건이
"리스트가 비어 있지 않으니" 라고 판단해 **히스토리를 아예 안 불러온다.**
`_hasMore` 도 없으니 무한 스크롤도 안 된다 → 영원히 메시지 1개만 보인다.

**해결 (A)**: "히스토리를 로드했는지" 를 별도 Set 으로 관리한다.

```dart
  final Set<String> _historyLoaded = {};
  bool hasLoadedHistory(String channelId) => _historyLoaded.contains(channelId);
```
`loadMessages` 성공 시 `_historyLoaded.add(channelId)`. `selectChannel` 은
`if (!hasLoadedHistory(channelId)) loadMessages(channelId);` 로 조건을 바꾼다.

### 1-A-12. `has_more` 를 서버에서 받아 쓰고, 요청 timeout 을 건다 (MAJOR)

- `ApiService.getMessages` 가 서버가 주는 `has_more` 를 버리고 `fetched.length >= 40` 으로 추측한다.
  → `ApiService.getMessages` 는 **`(List<Message>, bool)` 를 반환**하게 바꾸고, 호출부
  (`app_state.dart`) 에서 `hasMore` 를 그대로 쓴다. 반환 타입이 바뀌므로 `app_state.dart` 내 모든
  호출부를 함께 고친다.
- 모든 HTTP 호출에 `.timeout(const Duration(seconds: 15))` 를 건다. 타임아웃 시
  `ApiException(0, 'timeout', '네트워크 응답이 없습니다.')` 로 변환한다.

### 1-A-13. API 실패가 "비어 있음" 으로 보인다 (MAJOR)

`loadMessages`, `loadEvents`, `loadProjects`, `loadOrg`, `_loadWorkspaceData` 가 예외를
`debugPrint` 만 하고 삼킨다 → 사용자는 500 에러를 "메시지가 없습니다" 로 본다.
중복 프로젝트를 만들기도 한다.

**해결 (A)**: 섹션별 오류 상태를 노출한다.

```dart
  String? get messagesError;  Future<void> retryMessages();
  String? get eventsError;    Future<void> retryEvents();
  String? get projectsError;  Future<void> retryProjects();
  String? get orgError;       Future<void> retryOrg();
  String? get channelsError;
```
각 로더는 실패 시 해당 error 를 세팅하고, 성공 시 null 로 되돌린다.
"빈 상태"와 "오류 상태"는 UI 가 구분해서 그린다(B/C 에이전트가 사용).

### 1-A-14. 앱 생명주기(백그라운드/복귀) 처리 없음 (MAJOR)

백그라운드로 내려가면 소켓이 남아 있어 **사용자가 몇 시간째 "온라인" 으로 보일 수 있다.**
그리고 OS 가 앱을 죽이면 소켓이 조용히 끊겨 복귀 후 메시지가 오지 않는다.

**해결 (A)**: `AppState` 가 `WidgetsBindingObserver` 가 된다.
- `didChangeAppLifecycleState`: `paused`/`inactive` → `ws.disconnect()`,
  `resumed` → `ws.connect(...)` 재연결 + 활성 채널 `loadMessages` + `refreshWorkspace()`.
- `dispose()` 에서 `removeObserver`.

### 1-A-15. 메시지 보내기가 조용히 사라진다 (BLOCKER)

`MessageComposer._handleSend()` 가 `widget.onSend(text)` 를 **await 하지 않고** 컨트롤러를 바로 비운다.
`AppState.sendMessage` 에 try/catch 가 없어서, 네트워크 실패 시 Future 에러가 어디로도 안 가고
**사용자가 쓴 글은 사라지고 아무 말도 없다.**

**해결 (A)**: `AppState.sendMessage` 를 `Future<bool> sendMessage(String body)` 로 바꾸고,
실패하면 `false` 를 돌려주고 `notifyListeners()` 한다. (B 에이전트가 컨트롤러를 되살린다.)

### 1-A-16. 연결 상태가 사용자에게 전혀 보이지 않는다 (MAJOR)

`WsService.isConnected` 는 어디에서도 읽히지 않는다. 소켓이 끊겨도 화면은 "정상" 처럼 보인다.

**해결 (A)**: `AppState` 에 `bool get isConnected => ws.isConnected;` 와
`String? get connectionError;` 를 노출하고, WS 연결/해제 시 `notifyListeners()` 한다.
(`WsService` 에 `void Function(bool) onConnectionChanged` 콜백을 추가해도 좋다.)

### 1-A-17. `Message.replyTo` / `Message.attachments` 파싱만 있고 렌더링이 없다 (MAJOR)

`models.dart` 는 파싱하지만 화면은 `message.body` 만 그린다 → 파일/사진 메시지는 **빈 말풍선 + 시간만**,
인라인 답글은 "무엇에 대한 답글인지" 알 수 없다.

**확인된 사실 (A 는 이걸 바꾸지 말고 검증만 할 것)**:
- `models.dart` 에 이미 `ReplyTo`(id, authorName, body, deleted) 와
  `FileRef`(id, name, url, mime, size) 클래스가 있고 `Message.fromJson` 이
  `reply_to` / `attachments` 를 올바르게 파싱한다. **새 `Attachment` 클래스 등 도 만들지 마세요.**
- 백엔드 `app/schemas/file.py` 의 `FileOut` = {id, name, url, mime, size}.
  `url` 은 **상대경로**(`{api_prefix}/files/{file_id}`) 다. 이미지 썸네일을 그리려면
  절대 URL 이 필요하다 → `ApiService` 에 `String absoluteFileUrl(String url)` 헬퍼를 추가하고
  B 에이전트가 쓰게 하세요 (절대경로면 그대로 반환).

**해결 (A)**: `ApiService.absoluteFileUrl(String url)` 만 추가/검증한다. **렌더링은 B 에이전트가 한다.**

### 1-A-18. `models.dart` 변경 시 규약

B/C 에이전트는 `models.dart` 를 수정하지 않는다. A 는 **새 모델 클래스를 만들지 말고**,
기존 `Message` / `ReplyTo` / `FileRef` 의 필드 이름과 의미를 그대로 유지한다.
(필요하면 기본값만 보강.)

---

## 2. Chat 에이전트 (B) — 계약

### 2-B-1. 대화방을 열면 "가장 오래된 메시지" 가 보인다 (MAJOR, 실기 확인됨 — 최우선)

백엔드는 메시지를 오래된 순서로 준다. 앱은 `ListView.builder(reverse: false)` + index 0 = 가장 오래된
메시지. → **열자마자 40개 과거 메시지**가 보이고, 최신 메시지는 화면 아래(안 보임).
데스크톱 앱은 이걸 `scrollIntoView` 로 처리한다.

**해결 (B)**: `ChatScreen` 이 다음을 모두 만족하게 한다.
1. 대화방을 열면 **최신 메시지가 보이도록** 자동 스크롤한다.
2. 새 메시지가 도착하면(그리고 사용자가 이미 최신 구간에 있을 때) 자동으로 따라간다.
3. 키보드가 올라오면(입력 필드 포커스) 최신 메시지가 보이면 좋게 스크롤한다.
4. **스크롤 위치를 대화방마다 기억**한다. (같은 채널을 다시 열면 이전 위치로)
5. 위로 스크롤해 과거를 더 불러오면(`loadMessages(more: true)`) 목록이 늘어나도 최신 위치가
   shouldn't 깨진다 — 과거 로드 중에는 자동 스크롤 하지 않는다.

`ChatScreen` 은 `didUpdateWidget`/`didChangeDependencies` 로 채널 변경을 감지하고,
`ScrollController` 는 `PageStorageKey` 또는 `AutomaticKeepAliveClientMixin` 으로 유지한다.
`initState` 에서 매번 새로 만드는 현재 코드는 그대로 두면 안 된다.

### 2-B-2. 메시지 삭제에 확인도, 되돌리기도 없다 (MAJOR, 실기 확인됨)

롱프레스 → "메시지 삭제" → **즉시 삭제**. 한 번의 오터치로 메시지가 영구히 사라진다.

**해결 (B)**: 삭제는 `SnackBar` + `SnackBarAction("실행 취소")` 로 **되돌릴 수 있게** 한다.
되돌리기는 **Core가 반드시 아래 시그니처로 구현한다** (B 에이전트는 이 시그니처를 그대로 사용한다):

```dart
  /// 삭제 직후 "실행 취소" 를 눌렀을 때 메시지를 복구한다.
  Future<void> undoDeleteMessage(String messageId, String channelId);
```

### 2-B-3. 인라인 답글 / 첨부 렌더링 (MAJOR)

- `message.replyTo != null` 이면 본문 위에 **"← 이름: 원문 한 줄"** 형태의 인용 라인을 그린다.
  (`ReplyTo` = id / authorName / body / deleted)
- `message.attachments` 가 있으면:
  - 이미지면 `Image.network` 썸네일(가로 160dp 제한),
  - 그 외면 파일 칩(아이콘 + 이름) 을 그린다.
  (`FileRef` = id / name / url / mime / size)

**모델은 이미 파싱되어 있다** (`models.dart` 의 `ReplyTo`, `FileRef`). **새 모델 클래스를 만들지 마세요.**
첨부 `url` 은 상대경로(`{api_prefix}/files/{id}`)이므로, 이미지 썸네일에는
Core 가 제공하는 `api.absoluteFileUrl(url)` 로 절대 URL 을 만들어 쓰세요.

### 2-B-4. 메시지 헤더 Row 가 길면 overflow 한다 (MAJOR)

`message_bubble.dart` 의 헤더 Row(작성자 이름 + 직함 + 시간 + 고정 아이콘) 에 `Flexible` 이 없다.
긴 이름/직함이 화면 너비를 넘으면 **노란 검정 줄무늬 오버플로** 가 그려진다.

**해결 (B)**: 이름·직함을 `Flexible` + `TextOverflow.ellipsis` 로 감싼다.

### 2-B-5. DM 대화방 이름도 overflow 가능 (MINOR)

`chat_screen.dart` 의 DM 분기는 `Flexible` 이 없다 → 채널 분기와 동일하게 처리.

### 2-B-6. 검색 결과에서 사람/프로젝트를 눌러도 아무 일도 일어나지 않는다 (MAJOR, 실기 확인됨)

`search_dialog.dart`:
- 멤버: `Navigator.pop(context); await state.openDm(...); if (context.mounted) Navigator.push(...)`
  → `await` 후에는 dialog 의 context 가 dispose 되어 **`push` 가 영원히 실행되지 않는다.**
  실제로: DM 은 만들어지지만 **대화창이 열리지 않는다.** 사용자는 아무 반응이 없는 채
  메시지 탭에 새 DM 이 생긴 것만 뒤늦게 발견한다.
- 프로젝트: `state.selectProject(p); Navigator.pop(context);` → 탭이 바뀌지 않아 아무 변화가 없다.

**해결 (B)**:
- `await` **전에** Navigator 를 캡처하거나, `Navigator.pop(context, 결과값)` 로 결과만 넘기고
  **호출부에서** 네비게이션한다. (권장: `showDialog` 의 result 를 사용.)
- 멤버를 누르면 DM 을 열고 **대화창으로 이동**한다.
- 프로젝트를 누르면 **프로젝트 탭으로 이동**한다 (Core가 제공하는 `goToTab(2)` 사용).
- 채널을 누르면 **해당 채널로 이동**한다.

### 2-B-7. "1:1 대화 시작" 버튼도 대화를 열지 않는다 (MAJOR)

`new_dm_dialog.dart` 의 `_startDm` 도 `openDm` 만 하고 `ChatScreen` 을 push 하지 않는다.
→ ChatTab 의 `_onSelectChannel` 과 **똑같이** 대화창을 push 하도록 고친다.

### 2-B-8. 대화창에서 새 DM 을 만든 뒤 대화가 열리지 않음 → 위와 동일 패턴

`ChatTab._onSelectChannel` 은 이미 push 한다. **이 패턴을 공통 헬퍼로** 만들어
검색/신규DM/조직도에서 동일하게 재사용한다.

### 2-B-9. 채널 정보 다이얼로그의 멤버 목록이 항상 비어 있다 (MAJOR)

`channel_info_dialog.dart` 는 `channel.members` 를 그린다. 그런데 bootstrap 은 멤버를 주지 않는다
(`null`) → 항상 "참여 중인 멤버 (0)". `ApiService.getChannelMembers` 는 정의만 있고 **호출된 적 없다.**

**해결 (B)**: `ChannelInfoDialog` 가 `initState` 에서 `api.getChannelMembers(channel.id)` 를 호출해
로컬 상태로 렌더링한다. 헤더에 `channel.memberCount` 가 있으면 그것도 같이 보여준다.
**Core는 반드시 아래 헬퍼를 구현한다** (B 에이전트는 그대로 사용한다):

```dart
  /// 특정 채널의 멤버 목록 (캐시 포함). 없으면 서버에서 불러온다.
  Future<List<Member>> membersForChannel(String channelId);
```

### 2-B-10. 작은 터치 타깃 (MINOR)

`message_bubble.dart` 의 리액션 칩(~22dp), "답글 N개" 버튼(~22dp) 가 작다.
최소 **44dp** 로 키워야 엄지 손가락으로 누를 수 있다. 리액션 칩·답글 버튼·빠른 이모지 버튼 모두.

### 2-B-11. 긴-pressed 메뉴가 Long Press 인 것을 알아차릴 수 없다 (POLISH)

메시지 버블에 시각적 단서("⋯")가 없다. 롱프레스 시 **햅틱 피드백**(`HapticFeedback.mediumImpact()`)
을 준다. 리액션 토글·핀·삭제 등 주요 액션에도 가벼운 햅틱을 준다.

### 2-B-12. 입력창(Composer) 개선 (MAJOR)

- 전송 실패 시 **지운 텍스트를 되살리고** "전송에 실패했습니다" 스낵바를 띄운다. (Core의
  `Future<bool> sendMessage(String body)` 결과를 사용.)
- 전송 버튼은 40dp → 최소 44dp.
- 답글 배너의 ✕ 버튼도 44dp.
- **보내는 동안** 버튼이 잠기거나 전송 중 상태를 보여준다(연타로 중복 전송 방지).

### 2-B-13. 채널 목록의 "+" 버튼 (MINOR)

`chat_tab.dart` 의 채널/직접메시지 추가 버튼은 `padding: EdgeInsets.zero` +
`constraints: BoxConstraints()` 때문에 **아이콘 크기(20dp) 그대로**의 타깃이다 → 44dp 로 키운다.
(라벨이 11dp 대문자 캡션인데 버튼만 조용해서 눈에 잘 안 띈다 → 버튼 대비도 조금 키운다.)

---

## 3. Shell & Tabs 에이전트 (C) — 계약

### 3-C-1. 탭마다 앱바가 두 개 겹친다 (MAJOR, 실기 확인됨)

`MainShell` 의 phone 레이아웃이 `Scaffold(appBar: AppBar(워크스페이스+검색+아바타), body: IndexedStack(...))`
인데, `ScheduleScreen` / `ProjectsScreen` / `OrgScreen` 도 **각자 `Scaffold` + `AppBar`** 를 가진다.
→ "한빛 ⌄ 🔍 (김)" 바로 아래에 "일정" 이 또 나온다. **2줄(112dp)을 날리고 있다.**

**해결 (C)**: **앱바는 화면당 하나만** 있게 한다.
- 권장안: `MainShell` 의 앱바를 없애고(또는 매우 얇게) 각 탭 스크린이 **자기 앱바 하나**를 가지며,
  공통 액션(검색, 아바타, 워크스페이스 전환)은 `InheritedWidget` 또는 `AppState`/`MainShell` 이
  제공하는 공통 위젯으로 공유한다.
- 어떤 방식을 쓰든 **최종 결과는 탭마다 앱바가 정확히 1개**이고, 워크스페이스 이름·검색·아바타에
  접근할 수 있어야 한다.
- chat 탭(`ChatTab`) 은 지금 앱바가 없는데, phone 레이아웃에서는 `MainShell` 의 앱바가 보이므로
  이 화면들만 앱바가 1개가 되도록 정리한다.

### 3-C-2. 일정 FAB 이 이벤트 카드를 겹쳐 가린다 (MINOR)

`ScheduleScreen` 의 FAB 가 리스트 마지막 카드 위에 겹쳐 부분적으로 가린다.
→ 리스트 하단에 FAB 높이만큼 여백을 두거나(`padding`), FAB 를 카드 위가 아닌
**리스트 밖(화면 하단)** 에 두어 겹치지 않게 한다.

### 3-C-3. 일정 달력에서 달을 옮기면 선택 날짜가 안 바뀐다 (MAJOR)

`_prevMonth` / `_nextMonth` 은 `_viewMonth` 만 바꾸고 `state.selectedDate` 는 그대로 둔다.
→ 아래 목록은 이전 달의 날짜/일정을 그대로 보여주고, 새 달의 어느 칸도 선택되어 있지 않아
**화면이 깨진 것처럼 보인다.**

**해결 (C)**: 두 핸들러에서 `state.setSelectedDate(DateTime(_viewMonth.year, _viewMonth.month, 1))`
도 같이 부른다. 목록/하이라이트가 같은 달을 가리키게 한다.

### 3-C-4. 일정 달력에 불필요한 빈 공간 (POLISH)

달력 카드 하단이 크게 비어 있다. 공간을 줄여 **일정 목록이 한 화면에 더 많이 보이게** 한다.

### 3-C-5. 대화방/프로젝트 카드 Row overflow (MINOR)

`projects_screen.dart` 의 담당자 이름·날짜·댓글수 Row, `org_screen.dart` 의 이름+역할 Row,
`task_detail_sheet.dart` 등 — 가변 길이 `Text` 를 `Flexible`/`Expanded` + ellipsis 로 감싼다.

### 3-C-6. 프로젝트 드롭다운이 화면 너비를 넘을 수 있음 (MINOR)

`DropdownButton` 에 `isExpanded: true` 를 주고, `selectedItemBuilder` 로 ellipsis.

### 3-C-7. 오프라인/연결 끊김 배너 (MAJOR)

Core의 `AppState.isConnected` / `connectionError` 를 이용해, `MainShell` 상단에
**"연결이 끊어졌습니다"** slim 배너를 띄우고, 끊긴 동안 메시지 전송을 막거나(보조 문구와 함께)
전송 실패를 즉시 알린다.

### 3-C-8. 접근성 — Semantics / 햅틱 / 텍스트 확대 (MINOR~MAJOR)

- `llack_avatar.dart` : `Semantics(label: '$name, ${presence.label}')`
- `presence_badge.dart` : `Semantics(label: presence.label)`
- 안 읽은 메시지 배지 : `Semantics(label: '읽지 않은 메시지 $count개')`
- 아이콘만 있는 버튼에 `tooltip` 이 이미 있으면 그걸로 충분. 없는 것들은 추가.
- `llack_typography.dart` 의 하드코딩된 `fontSize` 를 `ThemeData.textTheme` 기반으로 바꿔서
  **시스템 글자 크기 설정이 반영**되게 한다. (현재 최대 크기 설정에서 10~11dp 짜리 글씨가 남아 가독 불가)

### 3-C-9. 설정 시트에서 서버 주소를 바꾸면 WebSocket 이 옛 주소에 붙어 있다 (MAJOR)

`ApiService.setBaseUrl` 은 prefs 만 바꾼다. WS 는 여전히 옛 주소에 연결돼 있고, 데이터도 다시 안 불러온다.
→ Core에 다음을 요청 (Core가 이미 있으면 그대로 사용):

```dart
  /// 서버 주소를 바꾸고 WS 를 재연결하며 데이터를 다시 불러온다.
  Future<void> changeApiBaseUrl(String url);
```

### 3-C-10. 물리 기기에서 기본 서버 주소가 동작하지 않는다 (MAJOR, 배포 차단 이슈)

`getDefaultBaseUrl()` 은 Android 에뮬레이터용 `http://10.0.2.2:8000`, iOS 는 `http://127.0.0.1:8000`.
**실제 스마트폰에서는 둘 다 연결 불가**라서 로그인 화면에서 "서버에 연결할 수 없습니다" 만 뜬다.
사용자는 로그인 화면 맨 아래의 아주 작은 "서버 주소 설정" 텍스트 버튼을 찾아 직접 LAN IP 를
입력해야 한다.

**해결 (C)**: 로그인 화면에서 **서버 주소 설정 진입점을 눈에 띄게** 만든다(아이콘 버튼).
그리고 연결에 실패하면(네트워크 에러) **"서버 주소 설정" 버튼이 포함된 안내**를 보여준다.
서버 주소는 저장되므로 두 번 물으면 된다.

### 3-C-11. 메모리 이탈 방지 / 탭 상태 유지 (MINOR)

`IndexedStack` 안의 스크린이 상태를 유지하는지 확인하고, 필요하면
`AutomaticKeepAliveClientMixin` 을 붙인다. 워크스페이스 전환 후에도 탭 인덱스는 유지되어야 한다.

---

## 4. 공통 규약

1. **한국어 UI**. 사용자 노출 문자열은 한국어.
2. 기존 테마 색상(`LlackColors`) / 타이포(`LlackTypography`) 만 사용. 새 색상·폰트 도입 금지.
3. `analysis_options.yaml` 의 린트를 통과해야 한다 (`flutter analyze` 경고 0).
4. `pubspec.yaml` 에 **새 의존성을 추가하지 않는다** (오프라인 빌드 가능). 표준 라이브러리만 사용.
5. 코멘트는 한국어로, "왜 이렇게 했는지" 를 남긴다. 자명한 코멘트는 쓰지 않는다.
6. **쓰레기 코드를 남기지 않는다.** (예: 쓰지 않는 import, 죽은 필드)
7. 함수는 작게. 한 파일이 700줄을 넘으면 분리한다.
8. `debugPrint` 로만 오류를 삼키지 않는다. 사용자에게 보여줄 오류 상태를 만든다.
9. 각 에이전트는 자신이 담당한 파일만 수정한다. 다른 파일을 고칠 필요가 생기면
   **공유 계약에 명시된 API 로만** 넘어간다.

## 5. 완료 시 반드시 실행할 것

```bash
cd /Volumes/samsung/2026/projects/llack/mobile
flutter analyze        # 경고/에러 0 이어야 한다
flutter build apk --debug   # 빌드가 성공해야 한다
```

---

## 6. 2차 라운드 — 메시지 복구(real undo) 계약 (실기 확인됨)

### 6-0. 왜 다시 만드는가

1차는 "메시지 삭제 → SnackBar '실행 취소'" 를 만들었지만 **되돌리기가 실제로는 동작하지 않았다.**
에뮬레이터에서 재현한 사실:

- `AppState.deleteMessage()` 가 `_deletedMessages[mid]` 에 **원본** 을 저장한다.
- 그런데 서버가 `message.deleted` WS 이벤트를 브로드캐스트하고, 클라이언트의 WS 핸들러가
  `_deletedMessages[mid] = list[idx]` 를 다시 실행한다. 이때 `list[idx]` 는 이미 삭제된 복사본
  (body="", deletedAt != null) 이므로 **원본이 덮어써진다**.
- 그래서 `undoDeleteMessage()` 이 되돌려도 body 가 빈 삭제 상태 그대로 → 화면엔 계속 "(삭제된 메시지)".

게다가 서버는 `delete_message()` 에서 `message.body = ""` 로 본문을 **완전히 지워버린다.**
클라이언트만 되돌려도 서버에는 이미 없는 메시지라, 새로고침하면 또 사라진다.
즉 1차의 "실행 취소" 는 **약속만 있고 내용 없는 UX** 였다.

→ 되돌리기를 **서버까지 진짜로** 만들어야 한다. 서버는 이미 soft delete(`deleted_at`) 를 쓰고
있으므로, 삭제된 본문을 따로 보관했다가 복구하는 것이 가장 자연스럽다.

### 6-1. 백엔드 계약 (담당 A)

| 항목 | 내용 |
|---|---|
| 모델 | `Message.deleted_body: str \| None` (Text, nullable) 추가 |
| 마이그레이션 | `app/core/db.py` 의 `ensure_columns()` 에 `deleted_body` 추가 (ALTER TABLE, 존재 확인 후에만) |
| 삭제 | `delete_message()`: `message.deleted_body = message.body` 를 먼저 저장하고 그 다음 body 를 비운다 |
| 복구 | `POST /api/v1/messages/{message_id}/restore` → 200 + `MessageOut` |
| 권한 | 작성자 또는 관리자(can_modify) — 삭제와 동일 |
| 에러 | 이미 삭제되지 않은 메시지 → 400 "이미 삭제되지 않은 메시지입니다" / 본문이 남아있지 않은 예전 메시지 → 400 "이 메시지는 복구할 수 없습니다" |
| 실시간 | 복구 후 `events.emit_message_updated()` 로 채널 전체에 알린다 (다른 기기에서도 바로 보임) |

`MessageOut` 스키마는 바꾸지 않는다 (`deleted_body` 는 서버 내부 전용).

### 6-2. 모바일 코어 계약 (담당 A)

```dart
// api_service.dart
Future<Message> restoreMessage(String messageId);   // POST /messages/{id}/restore

// app_state.dart
Future<bool> undoDeleteMessage(String messageId, String channelId);
```

- 성공하면 **서버가 돌려준 Message 로 로컬 상태를 교체**한다 (body 복구, deletedAt = null).
  `_messages[channelId]`, `_threadRoot`, `_threadReplies` 모두 갱신.
- 실패하면 `false` 를 돌려준다 (UI 가 "복구하지 못했습니다" 를 보여준다).
- **WS `message.deleted` 핸들러가 저장된 원본을 덮어쓰지 않게** `putIfAbsent` 로 바꾼다.
  (이게 1차 되돌리기 실패의 직접 원인이다.)

### 6-3. 채팅 UI 계약 (담당 B)

- 삭제 SnackBar 의 "실행 취소" 는 `undoDeleteMessage()` 를 호출하고,
  `false` 면 "메시지를 복구하지 못했습니다" SnackBar 를 보여준다.
- 스레드(thread) 화면의 답글 삭제에도 같은 되돌리기 affordance 를 넣는다.
- SnackBar 는 앱 테마 색(`LlackColors`) 을 쓰고, 기본 검은 배경을 쓰지 않는다.

### 6-4. 검색 UX (담당 B) — 1차 실기에서 발견

- 검색 결과에 **자기 자신은 나오지 않게** 한다 (자기에게 DM 을 열면 서버가 422 로 거절한다).
- 대화를 열지 못했을 때 "대화를 열지 못했습니다" 같은 막연한 문구 대신 **이유**를 보여준다.

### 6-5. 셸 정리 (담당 C)

- 안드로이드 네이티브 시작 화면이 Flutter 기본 로고다 → Llack 브랜드(색 + "Ll" 마크)로 바꾼다.
- 일정/프로젝트/조직도 탭의 오류 상태에 "다시 시도" 를 붙인다 (이미 `retryEvents/retryProjects/retryOrg` 가 있다).

### 6-6. 첨부파일 이미지가 썸네일로 렌더링되지 않는다 (MAJOR, 실기 확인됨)

백엔드의 `GET /api/v1/files/{file_id}` 는 **인증 필수** (헤더 없으면 401) 이다.
그런데 메시지 버블의 `Image.network(url, ...)` 는 인증 헤더를 붙이지 않아서 항상 401 → `errorBuilder` 로
fallback 하여 **이미지인데도 파일 칩**으로 보인다. 즉 이미지 첨부 썸네일은 한 번도 렌더링된 적이 없다.

- 해결: `Image.network(headers: {'Authorization': 'Bearer $token'})` — 토큰은 `AppState.api.accessToken`.
- 이미지를 탭하면 인증 헤더를 붙인 큰 보기 Dialog.
- 이미지가 아닌 파일 칩을 탭하면 (플러그인 추가 없이) "데스크톱 앱에서 확인할 수 있습니다" 안내.

---

## 7. 3차 라운드 — 실기 재검증에서 발견한 결함 (2026-11-08)

2차 라운드 변경사항을 기기(emulator-5554)에 다시 올려 손으로 돌려보면서 확인한 결과다.

### 7-1. [CRASH] 프로젝트 탭 드롭다운 assertion 으로 화면이 죽는다 (실기 확인됨)

**증상**: 서버 주소 설정에서 "저장" 하거나 프로젝트를 다시 불러오면 프로젝트 탭이 빨간 화면이 된다.

```
'package:flutter/src/material/dropdown.dart': Failed assertion: line 1028 pos 10:
'items == null || items.isEmpty || value == null ||
 items.where((DropdownMenuItem<T> item) { return item.value == value; }).length == 1'
There should be exactly one item with [DropdownButton]'s value: Instance of 'Project'.
```

**원인**:
- `AppState.loadProjects()` 는 `_projects` 를 **새로 불러온 인스턴스**로 교체한다.
- 그런데 `_activeProject` 는 옛 인스턴스를 그대로 들고 있었다.
- `Project` 는 `==` 를 재정의하지 않으므로 `DropdownButton<Project>` 의 `value` 비교는 **참조 비교**가 된다.
- → 목록에 새 인스턴스만 있고 `value` 는 옛 인스턴스라 "일치하는 항목 0개" → assertion → 앱 죽음.
- `changeApiBaseUrl()` (서버 주소 저장) 이 `loadProjects()` 를 다시 부르기 때문에 **서버 주소를 한 번 저장하면 반드시 재현**된다.

**해결**:
1. `loadProjects()` : 이전에 선택했던 프로젝트 **id** 로 새 목록에서 다시 찾아 `_activeProject` 를 목록의 인스턴스로 되돌린다.
   (없어졌다면 첫 번째 프로젝트로 옮긴다)
2. 드롭다운의 값 타입을 `Project` → `String`(id) 로 바꾼다. 객체 참조에 의존하지 않으므로같은 종류의 문제가 재발하지 않는다.
3. 목록이 비었는데 `activeProject` 만 남아 있으면 빈 상태 화면을 보여준다.

**재현 테스트**: `test/projects_dropdown_stability_test.dart` (3개)

### 7-2. [MINOR] 서버 주소 설정의 오류 문구가 잘려서 읽히지 않는다 (실기 확인됨)

`InputDecoration.errorText` 는 기본값이 1줄 + 말줄임이라
"http:// 또는 https:// 로 시작하는 주소를 입력하세요." 가 "… 로 시작하는 주소를 …" 로 잘렸다.
→ `errorMaxLines: 3` 지정.

### 7-3. [MINOR] 주소를 고쳤는데도 이전 오류 문구가 남아 있다 (실기 확인됨)

검증에 실패한 뒤 사용자가 주소를 고쳐도 빨간 오류 문구가 그대로 남아
"이미 실패했다" 고 오해하게 만들었다.
→ `TextField.onChanged` 에서 `errorMessage` 을 `null` 로 초기화.

### 7-4. 실기에서 통과 확인된 항목 (2차 라운드)

- 검색 결과에 **자기 자신이 나오지 않는다** (`hyunjin` 검색 → "검색 결과가 없습니다", `jimin` 검색 → 박지민만 표시).
  다른 멤버를 고르면 1:1 대화가 정상적으로 열린다.
- 일정/프로젝트/조직도 탭의 오류 배너 + "다시 시도" 동작.
  (서버를 내린 상태 → 배너 표시 → 다시 시도 → 서버 복구 후 다시 시도 → 정상 복구)
- 서버 주소 설정: 검증 오류 → 연결 불가 오류 → 저장 성공(WS 재접속 포함) 전체 흐름.

### 7-5. 공통 규약 7 ("한 파일이 700줄을 넘으면 분리한다") 준수

`app_state.dart` 하나가 1279줄로 자라서 더 이상 수정하기 어려웠다. 규약 7 에 따라 분리했다.

**Dart 의 제약**: `part` 파일에는 **최상위 선언만** 둘 수 있다. 클래스 "멤버" 를 part 에 쓰는 것은 불가능하다.
그래서 상속 체인(private 클래스)으로 나누었다. 전부 하나의 라이브러리(`part`)라서
private 멤버를 영역끼리 그대로 주고받을 수 있다.

| 파일 | 내용 | 줄 수 |
|---|---|---|
| `app_state.dart` | import/part 지시 + `AppState` (생성자, dispose, boot, 인증, 워크스페이스 전환, retry, lifecycle) | 270 |
| `app_state_core.dart` | `_AppStateCore` — 필드/게터, 공용 헬퍼, 인증/로그아웃 | 274 |
| `app_state_realtime.dart` | `_AppStateRealtime` — WS 이벤트 처리, 메시지 upsert 헬퍼 | 219 |
| `app_state_messages.dart` | `_AppStateMessages` — 메시지, 스레드, 채널/DM | 276 |
| `app_state_workspace.dart` | `_AppStateWorkspace` — 일정, 프로젝트/태스크, 조직도, 검색 | 281 |

상속 순서(뒤에서 앞의 private 멤버를 쓸 수 있다):

```
_AppStateCore → _AppStateRealtime → _AppStateMessages → _AppStateWorkspace → AppState
```

- `loadMessages` 는 `selectChannel` / `_upsertMessage` 를 쓰므로 메시지 쪽에 둔다.
- `changeApiBaseUrl` / `didChangeAppLifecycleState` / `retry*` 는 메시지·워크스페이스 메서드를
  부르므로 마지막 `AppState` 에 둔다.
- 동작 변화 없음 (메서드 본문은 그대로 이동). 실기 재검증으로 확인:
  앱 재시작 → 세션 복원 → 채널/DM 목록 → 프로젝트 탭(드롭다운) → 일정 → 조직도 → DM 열기 → 메시지 전송/삭제,
  그리고 **서버 주소 저장(과거 크래시 재현 경로)** 까지 모두 정상.

---

## 8. 4차 라운드 — 실기 재검증에서 발견한 결함 (2026-11-09)

3차 라운드 변경사항을 기기(emulator-5554)에 올려 손으로 돌려보면서 확인한 결과다.
이 절의 항목은 **담당자가 명시되어 있다**. 담당 에이전트만 고친다.

### 8-1. [MAJOR] 메시지 삭제 "실행 취소" SnackBar 가 사라지지 않는다 (실기 확인됨)

**증상**: #general 에서 메시지를 하나 지우면 하단에 "메시지를 삭제했습니다 / 실행 취소" 바가 뜬다.
5초가 지나도 **사라지지 않고 계속 화면에 남아 있다**. 게다가 입력창(composer)을 덮고 있어서
그대로는 다음 메시지를 보낼 수 없다. 위젯 트리 덤프로 확인한 사실:

```
T+15초 시점에도 위젯 트리에 SnackBar-[#23bbd] 와
Hero(tag: <SnackBar Hero tag - Text("메시지를 삭제했습니다")>) 가 그대로 살아 있다.
```

**원인**: `lib/screens/chat/message_actions.dart` 의 삭제 SnackBar 에 `SnackBarAction` 이 있다.
Flutter 3.47 의 `SnackBar` 생성자는 이 버전을 포함해

```dart
// flutter/packages/flutter/lib/src/material/snack_bar.dart:303
persist = persist ?? action != null;
```

처럼 **액션이 있으면 자동 닫힘을 기본값으로 끈다**. 즉 `duration: Duration(seconds: 5)` 는
**무시된다**. 액션이 없는 SnackBar 는 `duration` 이 정상 동작하는데, 이 앱에서 유일하게
`SnackBarAction` 을 쓰는 곳이 바로 이 삭제 SnackBar 라서 **유일하게** 닫히지 않는다.

**해결 (담당 B — `lib/screens/chat/*`)**:

1. `SnackBar` 에 **`persist: false` 를 명시**한다. (`duration: 5초` 가 다시 살아난다)
2. "실행 취소" 액션은 **그대로 유지**한다. 되돌리기 UX 자체는 2차 라운드에서 정상 동작 확인됨.
3. **SnackBar 가 composer 를 가리지 않게** 한다.
   `MaterialApp` 의 `ScaffoldMessenger` 는 `Scaffold` 의 **조상**이므로, 루트에서 띄운
   `SnackBar` 는 `ChatScreen` 의 body 안쪽 composer 를 그대로 덮는다.
   → `ChatScreen` 안에 **중첩 `ScaffoldMessenger`** 를 두고 그 안에서 SnackBar 를 띄운다.
   그러면 스낵바는 메시지 영역 안에만 그려지고 composer 는 가리지 않는다.
   (이때 `ScaffoldMessenger.of(context)` 참조가 **가장 가까운** messenger 를 잡게 되므로
   `message_actions.dart` 쪽에서 messenger 를 얻는 방법도 함께 정리해야 한다.)
4. `fixed` / `floating` 선택은 8-2 와 같이 정리한다.

**회귀 테스트**: `test/message_delete_snackbar_test.dart`
- SnackBar 에 `persist: false` 가 설정되어 있다 (액션이 있어도 duration 이 적용됨).
- 삭제를 수행하면 5초 뒤 SnackBar 가 사라진다 (pumpAndSettle + 경과 시간 검증).

### 8-2. [MINOR] SnackBar 동작에 대한 테마 주석이 실제와 반대다 (실기 확인됨)

`lib/theme/llack_theme.dart` 의 `snackBarTheme` 에 이런 주석이 있다.

```dart
// fixed 로 두면 SnackBar 가 본문을 밀어올려 composer 를 가리지 않는다.
behavior: SnackBarBehavior.fixed,
```

**이 주석은 틀렸다.** Flutter 3.47 에서

- `SnackBarBehavior.fixed` : 스낵바를 `contentBottom - snackBarSize.height` 위치에 **덮어 그린다**
  (본문을 밀어올리지 않는다 → composer 를 **가린다**).
- `SnackBarBehavior.floating` : `math.min(contentBottom, safeYOffsetBase)` 에 그린다.

즉 **주석이 말하는 것과 실제 동작이 정반대**다. 이 주석을 믿고 나중에
"fixed 로 해놨으니 괜찮겠지" 하고 넘어가면 composer 가리는 버그가 계속 남는다.

**해결 (담당 C — `lib/theme/*`)**:

1. 주석을 **실제 동작에 맞게** 고친다.
2. `behavior` 를 무엇으로 할지 명시한다.
   8-1 에서 "ChatScreen 안에 중첩 ScaffoldMessenger" 로 확정했으므로,
   `floating` 이 메시지 영역 안에 자연스럽게 뜨고 composer 를 가리지 않는다.
   → **`floating` 로 바꾸는 것을 우선 검토**한다.
   (`fixed` 를 유지하려면 그 근거를 주석에 정확히 적어야 한다.)

**회귀 테스트**: `test/snackbar_theme_test.dart`
- 테마의 `snackBarTheme.behavior` 가 정해진 값인지 확인.
- 주석에 "밀어올려" 처럼 잘못된 설명이 남아 있지 않은지 확인(문자열 검사).

### 8-3. [MINOR] ListTile 배경색 오류가 매 빌드마다 발생한다 (실기 확인됨)

`flutter attach` 콘솔에 매 프레임마다 이 오류가 dozens 번씩 올라온다.

```
Another exception was thrown: ListTile background color or ink splashes may be invisible.
```

**원인**: `lib/screens/chat/chat_tab.dart` 의 `_buildChannelTile` / `_buildDmTile` 이
`ListTile` 을 `Container(decoration: BoxDecoration(color: ...))` 로 감싼다.
Flutter 3.47 의 `ListTile._debugCheckBackgroundIsHidden`
(`flutter/packages/flutter/lib/src/material/list_tile.dart:1147-1210`) 가
ListTile 이 **색이 있는 `DecoratedBox`/`ColoredBox` 안에 들어 있고** 그 사이에
`Material` 이 없을 때 이 오류를 던진다. ListTile 의 ink 는 가장 가까운 `Material` ancestor 에
그려지는데, 그 사이를 중간 배경색이 가리기 때문이다.

**해결 (담당 B — `lib/screens/chat/*`)**:

- `ListTile` 을 **자기 자신의 `Material` 안으로** 넣거나 (예: `Material(type: MaterialType.transparency, ...)`),
  중간 `Container` 의 배경색을 없애고 `Material` 의 `color` 로 옮긴다.
- `lib/` 전체에서 `Container(decoration: BoxDecoration(color: ...))` + `ListTile` 조합이
  **다른 곳에도 있는지** 같이 찾아서 고친다.

**회귀 테스트**: `test/list_tile_material_test.dart`
- 채널 타일/DM 타일을 pump 한 뒤 `FlutterError.onError` 로 모인 오류에
  "ink splashes may be invisible" 가 **없을 것**을 확인.

### 8-4. [관찰 / 재현 안 됨] ``_dependents.isEmpty` 로 일어나는 빨간 화면

`'package:flutter/src/widgets/framework.dart': Failed assertion: line 6280 pos 12:
'_dependents.isEmpty'`

여러 차례 관측됐으나 **4차 라운드에서 재현되지 않았다.** 다음과 같이 검증했다
(각 시점마다 Dart VM service 의 `ext.flutter.debugDumpApp` 으로 위젯 트리를 덤프하고
`ErrorWidget` 이 없는지 확인함):

| 시나리오 | 결과 |
|---|---|
| `am force-stop` → `am start` 콜드 스타트 | ErrorWidget 0 |
| 메시지 탭 전환 | ErrorWidget 0 |
| 로그아웃 → `AuthScreen` | ErrorWidget 0 |
| 로그인 → `MainShell` | ErrorWidget 0 |
| HOME → 앱 복귀(resume) | ErrorWidget 0 |

**진단**: 이 assertion 은 `InheritedElement.debugDeactivated()` 에서 나는 것으로,
**Inherited 위젯이 의존자가 남아 있는 상태에서 비활성화**될 때 발생한다.
관측되던 시점에는 **다른 에이전트가 APK 를 재설치**하면서 프로세스가 프레임 도중에
 tearing down 되는 상황과 겹쳐 있었다. 위 시나리오 전부에서 재현되지 않는다는 점이
"앱 로직 버그" 가 아니라 "개발 중 프로세스 교체 아티팩트" 라는 판단을 뒷받침한다.

**조치**: **소스 수정은 하지 않는다.** 다만 아래 두 가지를 남긴다.

1. `flutter attach` 는 이 환경에서 매우 불안정하다. 타임아웃이 자주 나고,
   **앱을 종료시켜 재기동**시키기 때문에(모바일 테스트 순서를 망가뜨림) 쓰지 않는다.
   상태 확인은 Dart VM service 직접 호출(`adb forward` → `/getVM` → `/ext.flutter.debugDumpApp`)으로 한다.
2. 앞으로 같은 assertion 이 보이면 **동시에 APK 를 reinstall 하고 있는지 먼저 확인할 것.**
   그렇지 않으면 "앱 버그" 로 잘못 보고 코드부터 고치게 된다.

### 8-5. 4차 라운드 실기 재검증 결과 (2026-11-09)

에이전트 작업 후 APK 를 다시 만들어 기기(emulator-5554)에 올려 손으로 확인한 결과다.

| 항목 | 결과 |
|---|---|
| §8-1 SnackBar 자동 닫힘 | **통과.** 삭제 직후(T+1초)에는 "메시지를 삭제했습니다 / 실행 취소" 가 보이고, **T+7초에는 사라져 있다.** (옛 빌드에서는 15초 뒤에도 그대로였다) |
| §8-1 composer 가림 | **통과.** SnackBar 가 `floating` + 16dp inset 으로 떠서 **입력창 위쪽**에 그려진다. "메시지 보내기..." 입력창이 완전히 드러나 바로 입력할 수 있다. |
| §8-1 "실행 취소" 동작 | **통과.** 삭제 직후 "실행 취소" 를 누르면 메시지가 목록에 그대로 복원되고 SnackBar 가 닫힌다. |
| §8-2 테마 behavior | **통과.** `floating` 으로 바뀌어 루트 messenger 를 쓰는 다른 화면(설정, 검색, 일정, 프로젝트) 에서도 스낵바가 하단 네비/입력창을 가리지 않는다. |
| §8-3 ListTile ink 오류 | **통과 (A/B 대조 검증).** 아래에 별도 서술. |
| §8-4 빨간 화면 | **재현 안 됨.** 채널 목록 / #general / 일정 / 프로젝트 / 조직도 각 탭 모두 `ErrorWidget` 0. |

#### §8-3 의 A/B 대조 검증 방법

이 오류는 **logcat 에는 나오지 않는다** (`FlutterError.reportError` 가 `flutter attach` / DevTools
콘솔로만 전달된다). 그래서 "logcat 에 없다" 는 사실만으로는 통과 근거가 되지 않는다.
**옛 코드와 새 코드를 각각 빌드해서 같은 조작을 하고 attach 콘솔을 비교**했다.

1. `chat_tab.dart` 를 임시로 옛 구조(`Container(decoration: BoxDecoration(color:))` + `ListTile`)로 되돌려
   빌드·설치 → attach → 채널 목록 진입/이탈 반복 → 콘솔에
   `Another exception was thrown: ListTile background color or ink splashes may be invisible.` **발생 확인**
2. 수정한 코드(`Material` 로 감싼 구조)로 되돌려 빌드·설치 → **같은 조작** → 콘솔에 해당 오류 **0건**
3. 수정한 소스로 복구 완료.

#### 알아둘 점 (다음 라운드용)

- `flutter attach` 는 **앱을 종료시킨다**(pkill 하면 앱이 사라진다). 콘솔 수집 후에는 반드시
  앱을 다시 띄워야 한다. 차라리 `adb forward` + Dart VM service 직접 호출이 상태 확인에 안전하다.
- `ListTile` ink 오류를 확인하려면 **attach 콘솔**을 봐야 한다. logcat 은 감지기가 아니다.

---

## 9. 5차 라운드 — 실기 + 정적 리뷰에서 발견한 결함 (2026-11-09)

1~4차 라운드에서 손으로 돌려보지 않았던 화면(조직도, 스레드, 검색, 일정 상세, 태스크 상세,
프로젝트 생성)을 실기로 훑고, 아직 손대지 않은 화면을 정적 리뷰로 보완한 결과다.
이 절의 항목은 **담당자가 명시되어 있다**. 담당 에이전트만 고친다.

### 9-1. [MAJOR] 만든 일정/채널/할 일이 목록에 **2개로 중복**된다 (실기 확인됨)

**증상**: 일정 FAB 으로 "Round5 test event" 를 만들면 그날 목록에 **같은 일정이 2개**로 보인다.
메시지 탭의 "+" 로 `round5test` 채널을 만들면 **채널이 2개**로 보인다.
프로젝트 FAB 으로 `round5task` 를 만들면 "요청 (1)" 이 "**요청 (3)**" 로 뛴다(기존 1개 + 새 2개).

**근거 (서버와 앱의 개수 비교)**:

| 대상 | 백엔드 API 응답 | 앱 화면 |
|---|---|---|
| 일정 `Round5 test event` | **1건** (`evt_01M6XZC2`) | **2개** |
| 채널 `round5test` | **1건** (`chl_01M6XZE8EG`) | **2개** |
| 할 일 `round5task` | **1건** (`tsk_01M6XZG59N`) | **2개** |

채널 목록을 **당겨서 새로고침**하면 중복이 사라진다 → 서버에 2개가 있는 게 아니라 **로컬 상태만 2개**다.

**원인**: 백엔드가 **WS 이벤트를 HTTP 응답보다 먼저** 보낸다.

```python
# backend/app/api/v1/workspaces.py:132 (post_channel)
await events.emit_channel_created(session, channel)   # ← WS 먼저
return ...                                             # ← HTTP 응답은 그 다음

# backend/app/api/v1/schedule.py:75 (post_event)
# backend/app/api/v1/projects.py:281 (post_task)  — 동일 순서
```

그래서 **항상 WS 경로가 이기고**, 그다음 REST 응답 경로가 **같은 항목을 또 넣는다.**

WS 핸들러는 id 중복을 확인한다:

```dart
// lib/providers/app_state_realtime.dart
case 'channel.created':
  if (!_channels.any((c) => c.id == ch.id)) { _channels.insert(0, ch); _notify(); }
case 'event.created': case 'event.updated':
  final idx = _events.indexWhere((e) => e.id == ev.id);
  if (idx != -1) { _events[idx] = ev; } else { _events.add(ev); }
case 'task.created': case 'task.updated':
  final idx = list.indexWhere((x) => x.id == t.id);
  if (idx != -1) { list[idx] = t; } else { list.add(t); }
```

REST 응답 경로는 **중복 확인 없이 그냥 넣는다**:

```dart
// lib/providers/app_state_workspace.dart
_events.add(ev);                                       // ← 9-1 createEvent
_projectTasks[_activeProject!.id] = [...list, task];    // ← 9-1 createTask
// lib/providers/app_state_messages.dart
_channels.insert(0, ch);                               // ← 9-1 createChannel
```

**영향 없는 것** (이유를 적어둔다 — 이건 고치지 않는다):
`openDm` 은 idx 로 중복을 확인하고, 백엔드 `open_dm` 도 WS 를 보내지 않아 중복이 없다.
`createProject` 는 `project.created` WS 핸들러가 없어 안전하다.
`createOrgUnit` 은 `loadOrg()` 로 전체를 다시 불러오므로 안전하다.

**해결 (담당 A — `lib/providers/app_state_*.dart`)**:

1. **REST 경로도 id 중복 확인(upsert) 으로 바꾼다.** WS 가 먼저 도착했든 REST 가 먼저 도착했든
   목록에는 **항상 1개**만 있어야 한다. (WS 를 신뢰하지 않아도 되는 구조가 된다)
   - `createChannel` → `_channels` 를 id 기준 upsert
   - `createEvent`  → `_events` 를 id 기준 upsert
   - `createTask`   → `_projectTasks[projectId]` 를 id 기준 upsert
2. **중복 제거 로직은 순수 함수로 뽑아서 테스트 가능하게 한다.**
   ```dart
   // lib/providers/list_upsert.dart  (A 소유 신규 파일)
   List<T> upsertById<T>(List<T> list, T item, String Function(T) idOf);
   ```
   (WS 핸들러도 이 함수를 쓰게 되면 두 경로가 같은 규칙을 공유한다)
3. **테스트 가능하게 `AppState` 가 `ApiService` 를 주입 받게 한다.**
   ```dart
   AppState({ApiService? api, WsService? ws});
   ```
   지금은 `final ApiService api = ApiService();` 라 테스트에서 서버 호출을 바꿀 수 없다.
   (`FakeAppState` 가 `super()` 를 암묵적으로 부르므로 **기본값을 두어** 기존 테스트를 깨지 마라.)
4. `createChannel` / `createEvent` / `createTask` 은 **순서와 무관하게** 1개만 남아야 한다.

**회귀 테스트**: `test/create_duplicate_guard_test.dart`
- `upsertById` 단위 테스트: 같은 id 를 두 번 넣으면 **1개**.
- `AppState` 를 가짜 `ApiService` 로 만든 뒤, **"WS 이벤트가 먼저 도착하고 그다음 REST 응답이 오는"** 순서를
  재현해서 일정/채널/할 일이 각각 **정확히 1개**인지 확인.
- **옛 코드로는 실패해야 한다** (WS 먼저 → 2개). 새 코드에서는 1개.

### 9-2. [MAJOR] 조직도에서 "1:1 대화" 를 눌러도 **아무 화면도 바뀌지 않는다** (실기 확인됨)

**증상**: 조직도 탭 → 부서 펼치기 → 구성원 옆 💬 아이콘(또는 "전체 구성원" 목록의 💬) 누르면
스낵바 **"이채원님과의 대화가 열렸습니다"** 만 잠깐 뜨고, **화면은 그대로 조직도**다.
메시지 탭으로 직접 가서 봐야 새 DM 이 보인다. "버튼이 안 먹는다" 는 느낌이다.

**근거**: `lib/screens/org/org_screen.dart:82-97`

```dart
Future<void> _startDmWithUser(BuildContext context, User user) async {
  final state = context.read<AppState>();
  if (user.id == state.currentUser?.id) return;
  try {
    await state.openDm(user.id);          // ← 채널만 만들고 끝
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${user.name}님과의 대화가 열렸습니다')),  // ← "열렸다"고 말하지만
      );                                    //    실제로는 아무것도 열리지 않는다
    }
  } catch (e) { ... }
}
```

`AppState.openDm()` 은 채널을 만들고 `selectChannel` 만 호출할 뿐, **탭 이동도 대화창 push 도 하지 않는다.**
같은 기능을 하는 검색 다이얼로그(`search_dialog.dart`) 와 신규 DM 다이얼로그(`new_dm_dialog.dart`) 는
모두 공통 헬퍼 `ChatNavigator.openDm()` 을 쓰고 **대화창까지 열어 준다.** **조직도만 이 패턴을 빠졌다.**

**해결 (담당 C — `lib/screens/org/org_screen.dart`)**:

1. `ChatNavigator.openDm(...)` 을 쓰도록 통일한다. (§2-B-8 이 의도한 "공통 헬퍼 재사용" 패턴)
   ```dart
   await ChatNavigator.openDm(
     state: state,
     navigator: Navigator.of(context, rootNavigator: true),
     userId: user.id,
     push: FormFactor(context).isCompact,
   );
   ```
   (모바일 = 대화창 push, 태블릿 = 대화창이 이미 옆에 있으므로 push 하지 않음)
2. **스낵바 문구를 고친다.** 성공 시 "대화가 열렸습니다" 는 이제 맞으므로 유지해도 되지만,
   `ChatNavigator.describeDmError()` 처럼 **실패 사유를 한국어로** 보여준다
   (422/403/404/네트워크 구분).
3. **실패해도 조용히 사라지지 않게** 한다. (9-4 와 같은 규약)

**회귀 테스트**: `test/org_dm_navigation_test.dart`
- 조직도의 💬 버튼이 `ChatNavigator.openDm` 경로(또는 동등한 push)를 탄다.
- 실패 시 스낵바로 사유가 안내된다.

### 9-3. [CRASH] 태스크 상세 시트에서 **댓글을 보내는 도중 시트를 닫으면 앱이 죽는다**

**위치**: `lib/screens/projects/task_detail_sheet.dart:29-45`

```dart
try {
  await state.addTaskComment(widget.task.id, text);
  _commentCtrl.clear();          // ← mounted 가드 없음
} catch (e) {
  if (mounted) { ... }            // catch 쪽만 가드되어 있다
} finally {
  if (mounted) setState(() => _isSubmittingComment = false);
}
```

`await` 동안 사용자가 시트를 내려 닫거나 ✕ 를 누르면 `dispose()` 가 `dispose()` 를 호출한다.
그 뒤 응답이 도착하면 `_commentCtrl.clear()` 가 **dispose 된 컨트롤러**를 건드린다
→ `A TextEditingController was used after being disposed` (ChangeNotifier assert) → **빨간 화면**.

**해결 (담당 C — `lib/screens/projects/*`)**:
1. `await` **이전에** 글자를 떼어 두고, `await` **이후**에는 `if (mounted)` 로만 컨트롤러를 만진다.
2. 가능한 한 **낙관적**으로 처리한다: 보내기 전에 목록에 먼저 반영하고, 서버 응답으로 확정한다.
3. 시트가 이미 닫혔다면(`!mounted`) 컨트롤러는 건드리지 않고 **종료**한다.

**회귀 테스트**: `test/task_comment_dispose_test.dart`
- 댓글 전송 중 시트가 dispose 되어도 예외가 나지 않는다.

### 9-4. [MAJOR] 생성 실패가 **완전히 조용히** 사라진다

**위치**: `lib/screens/projects/projects_screen.dart:69-77`, `lib/screens/org/org_screen.dart:63-74`

**증상**: "새 프로젝트" 또는 "조직 단위 추가" 대화상자에서 이름을 넣고 "생성" 을 누른 뒤
서버 오류/네트워크가 끊기면 **아무 메시지도 안 뜨고 대화상자가 그대로 열린다.**
버튼을 계속 눌러도 같은 결과. (사용자는 "버튼이 죽었다" 고 느낀다)

**원인**: 두 곳 모두 `await state.createProject(...)` / `await state.createOrgUnit(...)` 를
**try/catch 없이** 부른다. 실패하면 예외가 `onPressed` async 콜백에서 버려져
unhandled exception 으로만 콘솔에 찍힌다.
**같은 앱 안에서 동작이 다르다** — 일정 생성(`event_dialog.dart`) 과 할 일 생성(`task_dialog.dart`) 은
catch 해서 스낵바를 띄운다.

**해결 (담당 C — `lib/screens/projects/*`, `lib/screens/org/*`)**:
1. 두 콜백을 `try/catch` 로 감싸고 **실패하면 스낵바로 사유를 알린다.**
   ```dart
   try {
     await state.createProject(...);
     if (ctx.mounted) Navigator.pop(ctx);
   } catch (e) {
     if (ctx.mounted) {
       ScaffoldMessenger.of(ctx).showSnackBar(
         SnackBar(content: Text('프로젝트 생성에 실패했습니다: $e')),
       );
     }
   }
   ```
   (`ctx` = 다이얼로그 context 를 쓴다. 다이얼로그가 닫히면 `ctx.mounted` 가 false 가 된다.)
2. **버튼을 연타해도 중복 생성되지 않게** `_isSubmitting` 가드를 넣는다.
   (일정/할 일 다이얼로그에 이미 있는 패턴을 그대로 쓴다)

### 9-5. [MAJOR] RSVP / 상태 변경 / 삭제 실패가 **아무 반응 없이** 사라진다

**위치**: `lib/providers/app_state_workspace.dart` 의 `rsvpEvent` / `deleteEvent` /
`updateTaskStatus` / `deleteTask`, 호출부 `lib/screens/schedule/schedule_screen.dart`,
`lib/screens/projects/task_detail_sheet.dart`

**증상**:
- 일정 카드의 "참석/미정/불참" 칩을 눌렀는데 서버가 실패하면 **칩이 전혀 바뀌지 않고 아무 안내도 없다.**
- 할 일 상태를 "진행 중" 으로 바꿔도 마찬가지.
- **할 일 삭제는 시트가 먼저 닫히고** 그다음 삭제가 조용히 실패해서, 할 일이 그대로 남아 있고
  "지웠는데 왜 남아 있지?" 라고 혼란스러워한다.

**원인**: 위 메서드들이 예외를 그대로 rethrow 하고, 호출부도
`onTap: () => state.rsvpEvent(ev.id, ...)` 처럼 **Future 를 버린다** → unhandled exception.
또 낙관적 업데이트가 없어서 서버 응답이 도착하기 전까지 화면 변화가 0 이다.

**해결 (담당 A — 코어 / 담당 C — 호출부)**:

**A (코어)** — 실패를 호출부로 알릴 수 있게 시그니처를 바꾼다.

```dart
/// RSVP 를 바꾼다. 실패하면 false 를 돌려준다. (호출부가 스낵바를 띄운다)
Future<bool> rsvpEvent(String eventId, EventResponse response);
Future<bool> deleteEvent(String eventId);
Future<bool> updateTaskStatus(Task task, TaskStatus newStatus);
Future<bool> deleteTask(String taskId);
```

- 기존 동작(성공 시 목록 갱신)은 유지한다.
- 실패 시 `debugPrint` + `false` 반환 (throw 하지 않는다). 호출부가 메시지를 보여줄 수 있어야 한다.

**C (호출부)** — 실패를 사용자에게 알린다.
- RSVP 칩: **낙관적 업데이트 후 실패하면 이전 값으로 되돌리고** 스낵바("참석 여부를 바꾸지 못했습니다")를 띄운다.
- 일정 삭제: 실패하면 **목록에서 지우지 않고** 스낵바를 띄운다.
- 할 일 삭제: **시트를 닫기 전에** 삭제 성공을 확인한다. 실패하면 시트를 그대로 두고 스낵바를 띄운다.

### 9-6. [MAJOR] 스레드 답글이 **조용히 사라진다** (보낸 줄 알았는데 안 나감)

**위치**: `lib/providers/app_state_messages.dart:61-72` (`sendReply`),
`lib/screens/chat/thread_screen.dart:134-149`

**증상**: 스레드 화면에서 답글을 쓰고 전송하면 **입력창만 지워지고** 답글 목록에도 안 뜬다.
사용자는 "보냈다" 고 생각하지만 서버로는 아무것도 안 나갔다.

**원인**: `sendReply()` 의 첫 줄이

```dart
if (_threadRoot == null || body.trim().isEmpty) return;   // ← 예외 없이 "정상" 반환
```

이라서 **성공인 척** 종료한다. `ThreadScreen` 의 `onSend` 는 `catch` 에 걸리지 않으므로
`return true` 를 돌려주고, `message_composer.dart` 의 성공 분기가 실행되어 **입력창만 비운다.**
`_threadRoot` 가 null 이 되는 경로가 `selectChannel()`(채널 전환)과 워크스페이스 전환이다.

**같이 고칠 것 — `openThread()` 의 경쟁(race)**:

```dart
void openThread(Message message) async {
  _threadRoot = message;
  ...
  _threadReplies = await api.getReplies(message.id);   // ← 스레드 A 의 응답이 B 를 덮어쓸 수 있다
}
```

스레드 A 를 열고 곧바로 B 를 열면, A 의 `getReplies` 응답이 늦게 도착해
`_threadReplies` 를 **B 기준으로 덮어쓴다.** 가드가 없다.

**해결 (담당 A — 코어 / 담당 B — 스레드 화면)**:

**A (코어)**:
1. `sendReply` 를 `Future<bool>` 로 바꾼다. `_threadRoot == null` 이면 **false** 를 돌려준다.
   ```dart
   Future<bool> sendReply(String body) async {
     final root = _threadRoot;
     if (root == null || body.trim().isEmpty) return false;
     try {
       final reply = await api.sendMessage(...);
       if (_threadRoot?.id != root.id) return false;   // 그 사이에 다른 스레드로 바뀌었다
       _threadReplies.add(reply);
       _notify();
       return true;
     } catch (e) {
       debugPrint('[sendReply error] $e');
       return false;
     }
   }
   ```
2. `openThread` 에 **응답 가드**를 넣는다.
   ```dart
   final myRoot = message;
   final replies = await api.getReplies(myRoot.id);
   if (_threadRoot?.id != myRoot.id) return;   // 다른 스레드로 바뀌었으면 버린다
   _threadReplies = replies;
   ```

**B (스레드 화면)**:
3. `onSend` 가 `state.sendReply(text)` 의 **반환값을 그대로** 돌려준다.
   (false 면 컴포저가 글자를 되살리고 "전송에 실패했습니다" 스낵바를 띄운다 — 이미 구현되어 있음)

### 9-7. [MINOR] 일정 삭제 버튼 18dp / RSVP 칩 22dp — 엄지로 누르기 어렵다

**위치**: `lib/screens/schedule/schedule_screen.dart` (삭제 `IconButton`, `_buildRsvpChip`)

- 삭제 버튼: `padding: EdgeInsets.zero` + `constraints: const BoxConstraints()` → **아이콘 크기(18dp)만** 터치 영역.
- RSVP 칩: `EdgeInsets.symmetric(horizontal: 10, vertical: 4)` + `labelSmall` → 높이 **약 22dp**.

**해결 (담당 C)**:
- 삭제 버튼: `constraints: const BoxConstraints(minWidth: 44, minHeight: 44)`
  (composer 에 이미 적용된 §2-B-12 방식과 동일).
- RSVP 칩: 세로 패딩을 늘려 **최소 높이 44dp** 로 맞춘다.

### 9-8. [MINOR] 검색 결과가 **늦게 도착한 응답**으로 덮여서 검색어와 어긋난다

**위치**: `lib/screens/search/search_dialog.dart:43-64`

**증상**: "김" 을 검색하다가 "김민" 으로 바꾸면(search 2회) **느린 첫 번째 응답이 나중에 도착**해서,
입력창에는 "김민" 이 표시되는데 **메시지 결과는 "김" 의 결과**로 보여준다.

**원인**: 디바운스는 **타이머만** 취소한다(이미 출발한 HTTP 요청은 취소되지 않는다).
`_messageResults = res` 로 무조건 덮어쓴다.

**해결 (담당 B)**:
1. 요청마다 **시퀀스 번호**를 붙이고, 오래된 응답은 버린다.
   ```dart
   int _searchSeq = 0;
   ...
   final seq = ++_searchSeq;
   final res = await state.search(query);
   if (!mounted || seq != _searchSeq) return;   // 뒤에 newer 요청이 있으면 버린다
   setState(() => _messageResults = res);
   ```
2. (채널/멤버/프로젝트는 로컬 필터라 즉시 반영된다. **메시지 결과만** 어긋나 보인다.)

### 9-9. [MINOR] "새 일정" 의 연결 채널 드롭다운 assertion 으로 죽을 수 있다

**위치**: `lib/screens/schedule/event_dialog.dart:232-244`

```dart
DropdownButtonFormField<String?>(
  initialValue: _selectedChannelId,
  items: [ null 항목, ...channels.map(...) ],
  onChanged: (v) => setState(() => _selectedChannelId = v),
)
```

**발현 조건**: 채널을 골라 둔 상태에서 그 채널이 `state.channels` 에서 사라지면
(다른 사람이 채널을 삭제 → `channel.deleted` WS, 워크스페이스 전환 등)
다이얼로그가 다시 빌드되는 순간 Flutter 의
`There should be exactly one item with [DropdownButton]'s value: <id>` assert 가 터져 **빨간 화면**이 된다.

**해결 (담당 C)**:
- 다시 빌드될 때마다 **현재 값이 목록에 있는지 확인**해 없으면 null 로 되돌린다.
  (`DropdownButtonFormField` 는 `initialValue` 가 첫 빌드에만 쓰이므로,
  `items` 를 만들 때 유효하지 않은 값을 걸러내거나 `didUpdateWidget` 에서 `setValue(null)` 로 맞춘다.)

### 9-10. [MINOR] 리소스 정리 3가지

| # | 위치 | 내용 | 담당 |
|---|---|---|---|
| a | `lib/screens/projects/projects_screen.dart:44-45`, `lib/screens/org/org_screen.dart:32-34` | 대화상자 밖에서 만든 `TextEditingController` 를 **dispose 하지 않는다.** 대화상자를 열 때마다 컨트롤러 2~3개가 회수되지 않는다. | C |
| b | `lib/screens/chat/thread_screen.dart:21` | `ScrollController` 를 dispose 하지 않는다. 스레드를 반복해서 열면 회수되지 않는다. | B |
| c | `lib/screens/projects/task_detail_sheet.dart:83-85` | `MediaQuery.viewInsets.bottom` 을 **정적 패딩**으로 적용 → 키보드 애니메이션과 싱크가 안 맞아 시트 높이가 순간적으로 튄다. | C |

### 9-11. 검토했으나 **결함으로 인정하지 않은** 것 (오탐 정리)

정적 리뷰에서 "문제가 된다" 는 보고를 받았지만, 코드를 다시 읽어 보니 **문제가 아니었거나**
**이미 해결되어 있던** 것들이다. **이 항목들은 고치지 않는다.**

| 보고 내용 | 실제 판단 |
|---|---|
| 검색 다이얼로그의 디바운스 타이머가 `dispose` 후 `setState` 한다 | **문제 아님.** `dispose()` 에서 `_debounceTimer?.cancel()` 하므로 타이머는 실행되지 않는다. 실행 중이던 콜백의 `await` 이후 코드(`if (mounted)`)는 모두 가드되어 있다. `setState`/`context.read` 는 타이머 발화 시점에 **동기적으로** 실행되므로 dispose 와 인터리브되지 않는다. |
| 메시지를 보낸 뒤 상대 화면에 "입력 중" 이 3초 남는다 | **문제 아님.** `_controller.clear()` → 리스너 → `onTyping(true)` + 타이머 재시작이 일어나지만, 바로 뒤에 `_typingTimer?.cancel()` 과 `onTyping(false)` 가 순서대로 실행되어 타이머가 취소된다. `clear()` 의 리스너 발화는 동기적이므로 최종적으로 `false` 가 나간다. |
| `selectProject` 드롭다운 assertion (§7-1) 재발 | **문제 아님.** `value` 를 id 로 받고 목록에 없으면 null 을 돌려준다. (§7-1 에서 이미 해결) |
| `DropdownButtonFormField` 의 `initialValue: null` + `DropdownMenuItem(value: null)` | **문제 아님.** Flutter 3.47 의 `DropdownButtonFormField` assert 를 통과한다. 9-9 는 **선택 후 목록에서 사라질 때**의 별개 문제다. |

### 9-12. 5차 라운드 실기 확인 결과 (2026-11-09)

| 확인 항목 | 결과 |
|---|---|
| 검색 다이얼로그 | **통과.** "test" 검색 → "채널 (1) round5test" + "메시지 (1) attachment test" 가 정상 노출. |
| 조직도 트리 | **통과.** 부서 펼치기/접기, 전체 구성원(5명), "나" 배지, DM 버튼 렌더 정상. 단, DM 버튼은 9-2 로 결함. |
|조직도 DM → 메시지 탭 | **동작.** DM 은 만들어져 메시지 탭 "직접 메시지" 에 나타난다. (단, 화면이 안 이동하는 문제는 9-2) |
| 메시지 보내기 | **통과.** 전송 즉시 말풍선에 반영, 시간 표시 정상. |
| 1:1 대화 진입 | **통과.** 빈 상태 문구("아직 메시지가 없습니다. 첫 번째 메시지를 보내보세요!") 정상. |
| 일정/채널/할 일 **중복** | **결함(9-1).** 서버 1건 / 화면 2건. |

### 9-13. [MINOR] `message_bubble.dart` 가 732줄 — 공통 규약 7(700줄) 초과

**위치**: `lib/widgets/message_bubble.dart` (732줄)

§4 공통 규약 7 은 "**한 파일이 700줄을 넘으면 분리한다**" 고 §7-5 에서 `app_state.dart`(1279줄)를
실제로 나눴다. `message_bubble.dart` 는 732줄로 **같은 규약을 넘었다.**

현재 파일에 같이 들어 있는 것들:

| 내용 | 줄 |
|---|---|
| 말풍선 본체 + 헤더 + 답글 인용 | 11~437 |
| **첨부 렌더링**(이미지 썸네일 / 파일 칩) | 438~628 (약 190줄) |
| 고정 배지 / 리액션 / 스레드 버튼 | 629~732 |

**해결 (담당 B)**:
- 첨부 렌더링(`_buildAttachments` / `_buildAttachment` / `_buildImageAttachment` / `_buildFileChip`)을
  **`lib/widgets/message_attachments.dart`** 로 분리한다. (B 소유)
- `MessageBubble` 은 새 위젯을 불러 쓴다. **동작은 바뀌지 않게** (속성/패딩/애니메이션 그대로).
- 분리 후 두 파일 모두 700줄 아래인지 확인하고, `flutter analyze` / `flutter test` 를 통과시킨다.

### 9-14. [MAJOR] "프로필 수정" 저장이 실패하면 조용히 사라진다 (9-4 와 같은 패턴)

**위치**: `lib/screens/settings/settings_sheet.dart:14-58`

```dart
ElevatedButton(
  onPressed: () async {
    final newName = nameCtrl.text.trim();
    if (newName.isNotEmpty) {
      await state.updateMe(...);      // ← try/catch 없음
      if (ctx.mounted) Navigator.pop(ctx);
    }
  },
  child: const Text('저장'),
),
```

`AppState.updateMe` 는 실패하면 예외를 그대로 던진다(`app_state_core.dart:242`). 여기서 안 잡으므로
사용자는 **"저장" 을 눌렀는데 아무 반응이 없고 대화상자만 열린 채로 남는다.**

**해결 (담당 C — `lib/screens/settings/settings_sheet.dart`)**:
1. `try/catch` 로 감싸고 **실패하면 스낵바로 사유를 알린다.** (9-4 와 같은 방식)
2. **연타 중복 저장 방지** `_isSubmitting` 가드.
3. 이 다이얼로그의 `TextEditingController` 도 **dispose** 해라. (9-10-a 와 같은 문제)
4. **같은 파일의 "내 상태 설정" 칩** (`settings_sheet.dart:158-161`) 도 고쳐라.
   `state.updatePresence(p)` 는 내부에서 `updateMe(presence:)` 를 부르므로 실패하면 예외를 던진다.
   그런데 반환된 Future 를 아무도 await/catch 하지 않아 **Unhandled exception** 으로 끝난다.
   → `try/catch` 로 감싸고 실패하면 스낵바로 알린다.

> 참고: 프로바이더 쪽 `updateMe` 은 그대로 두어도 된다. (A 영역이라 건드리지 않는다.
> 호출부에서 catch 하는 것만으로 충분하다.)

### 9-15. [CRASH] 9-3 수정이 아직 닫히지 않았다 — 댓글 전송 중 시트를 닫으면 여전히 터진다

> **→ 9-3 구현과 함께 닫혔다.** C 가 9-3 을 고칠 때 글자를 `await` **앞**에 떼어두고
> `await` 뒤에는 컨트롤러를 건드리지 않는 구조로 바꿔서, dispose 크래시 경로 자체가 사라졌다.
> 아래는 "9-3 을 이렇게 고치면 된다" 는 원래 지적이며, 그 내용대로 구현되었다.
> (`_deleteTask` 도 삭제 **성공을 확인한 뒤** 시트를 닫고, 실패하면 스낵바를 띄우도록 바뀌었다.)

**위치**: `lib/screens/projects/task_detail_sheet.dart`

9-3 을 고치면서 `dispose()` 에 `_commentCtrl.dispose()` 를 추가했지만,
`await` 뒤의 `clear()` 는 여전히 `mounted` 가드가 없다.

```dart
try {
  await state.addTaskComment(widget.task.id, text);
  _commentCtrl.clear();          // ← dispose() 이후일 수 있다
} catch (e) { ... } finally { if (mounted) setState(...); }
```

사용자가 **댓글 전송 중에 시트를 닫으면** `dispose()` 가 `_commentCtrl` 를 버리고,
그 뒤 `clear()` 가 터진다 → *"A TextEditingController was used after being disposed."*

**해결 (담당 C)**:
- `await` 뒤에 `if (!mounted) return;` 을 넣고 나서만 `clear()` 한다.
- 같은 파일 `_deleteTask()` 는 시트를 **먼저 닫고** 나서 `state.deleteTask(...)` 를 부른다.
  `deleteTask` 은 이제 `Future<bool>` 이므로 **실패를 사용자에게 알려야 한다.** (9-5)
  → 닫기 전에 결과를 확인하거나, 실패 시 살아있는 messenger 로 스낵바를 띄운다.
- 회귀 테스트: `test/task_comment_dispose_test.dart` (9-3 에서 만든 파일) 가 통과해야 한다.

### 9-16. 6차 라운드 실기 검증 결과 (2026-11-09, 에뮬레이터 Pixel_7_API_36)

§9-1~§9-13 까지 실제로 적용한 APK 를 기기에 설치해서 손으로 확인한 결과다.

| 확인 항목 | 결과 |
|---|---|
| **§9-1 채널 중복** | **해결 확인.** `r6dup` 채널 생성 → 서버 1건(`GET /workspaces/{id}/channels` → `r6dup` 1회) / 화면 **1개**. 예전엔 2개였다. |
| **§9-1 일정 중복** | **해결 확인.** `r6event` 생성 → 서버 1건(`GET /workspaces/{id}/events` → 1회) / 화면 **1개**, "11월 9일 2개의 일정" (기존 1 + 신규 1). |
| **§9-1 할 일 중복** | **해결 확인.** `r6task` 생성 → 서버 1건(`GET /projects/{id}/tasks` → 1회) / 화면 **1개**, "요청 (2)". |
| **§9-2 조직도 💬 → DM** | **해결 확인.** 구성원 옆 💬 을 누르면 **박지민 1:1 대화창이 실제로 열린다**(앱바 제목 "박지민", 빈 상태 문구, 입력창 노출). 예전엔 조직도 화면이 그대로였다. |
| **§9-7 터치 타깃** | **확인.** 일정 삭제 🗑 버튼과 RSVP 칩(참석/미정/불참)이 44dp 로 커져 손가락으로 눌리기 편해졌다. |
| **워크스페이스 전환** | **동작 확인.** 앱바 칩 → 전환 시트에 2개 워크스페이스 표시, "한빛 스터디" 선택 시 시트/채널/멤버/일정이 그 워크스페이스 기준으로 **전부 새로 로드**됐다(멤버 1명). |
| **위젯 트리 에러** | **없음.** `ext.flutter.debugDumpApp` + `debugDumpRenderTree` 덤프에서 `ErrorWidget` / `RenderErrorBox` / `There should be exactly one item`(§9-9 assertion) / RenderFlex overflow **모두 0건**. logcat 에 Flutter 예외 없음. |

**6차 라운드에서 만든 테스트 데이터는 모두 삭제했다** (채널 `r6dup` · 일정 `r6event` · 할 일 `r6task`,
그리고 워크스페이스 전환을 시험하려고 임시로 만든 "한빛 스터디" 워크스페이스까지).
DB 를 건드리기 전에는 `backend/llack.db` 백업을 `/tmp/llack.db.bak-r6*` 로 남겼다.

### 9-17. [MAJOR] 모달(다이얼로그/바텀시트) 안에서 띄운 스낵바가 **화면에 안 보인다**

**실기 발견 (2026-11-09, 에뮬레이터 Pixel_7_API_36, 백엔드를 끈 상태로 실패 경로 시험)**

| 순서 | 조작 | 보이는 결과 |
|---|---|---|
| 1 | 백엔드 종료 → 설정 시트(아바타 탭) 열기 | 시트는 정상적으로 열린다 |
| 2 | 시트 안 "내 상태 설정" 의 **바쁨** 칩 탭 | 칩이 **온라인으로 되돌아간다**(롤백은 동작). 그런데 **아무 안내도 없다** — 스낵바가 안 보인다 |
| 3 | 시트 안 ✏️ → "프로필 수정" → **저장** 탭 | **다이얼로그가 열린 채로 남는다**(= 실패 경로로 확정). 그런데 **"프로필을 저장하지 못했습니다" 스낵바가 안 보인다** |
| 4 | (비교) 일정 탭에서 RSVP 칩 탭(같은 종류의 실패) | **"참석 여부를 바꾸지 못했습니다" 스낵바가 보인다** ✅ |

4번과 2·3번의 **차이만은 "모달이 열려 있느냐"** 다.
→ 스낵바 기능 자체는 멀쩡하고, **모달이 열려 있을 때만 안 보인다.**

**근본 원인**

`ScaffoldMessenger.of(context).showSnackBar(...)` 는 스낵바를
**루트 `Scaffold`** 가 그린다. 루트 Scaffold 는 네비게이터의 오버레이보다 **아래 계층**에 있고,
`showDialog()` / `showModalBottomSheet()` 로 올라온 **모달 라우트가 그 위에 얹힌다.**

```
Overlay
 ├─ (일반 화면) Scaffold ── SnackBar        ← 여기 그려진다
 └─ ModalBarrier + ModalBottomSheet/AlertDialog  ← 이게 더 위에 있다 → SnackBar 가 가려진다
```

`showDialog` 안의 `context` 로 `ScaffoldMessenger.of(context)` 를 불러도
**같은 루트 messenger** 를 얻을 뿐이다(가장 가까운 ScaffoldMessenger 가 MaterialApp 의 것).
그래서 §9-14 가 추가한 "프로필을 저장하지 못했습니다" / "상태를 바꾸지 못했습니다" 안내가
**사용자에게는 아예 보이지 않았다.** 사용자는 "버튼이 죽었다"고 느낀다.

**해결 (담당 C — 신규 파일 `lib/widgets/app_snack_bar.dart` + C 소유 파일 전체)**

1. **공용 헬퍼를 만든다.**
   `void showAppSnackBar(BuildContext context, String message, {Duration duration = const Duration(seconds: 4), String? actionLabel, VoidCallback? onAction})`
   (신규 파일 `lib/widgets/app_snack_bar.dart`, **C 영역**)

   **어디서 불렸는지에 따라 그리는 경로를 나눈다.**
   - **모달 안**(`ModalRoute.of(context) is PopupRoute` — `DialogRoute`/`ModalBottomSheetRoute`)
     → `Overlay.of(context, rootOverlay: true)` 의 루트 오버레이에 **직접 얹는다.**
       (`overlay.insert(...)`) → **모든 모달/바텀시트보다 위에** 그려진다.
       - Flutter 3.47 의 `OverlayState.rearrange()` 는 **목록에 없는 엔트리를 버리지 않고**
         끝에 다시 넣어 주므로, 네비게이터가 라우트를 바꾸어도 이 엔트리는 살아남는다.
         (소스 확인: `packages/flutter/lib/src/widgets/overlay.dart:813` `rearrange`, `:660` `_insertionIndex`)
       - 자체 애니메이션(위로 슬라이드 + 페이드), 자동 닫힘(기본 4초), **탭하면 즉시 닫힘**.
       - **키보드가 올라와 있으면 키보드 위(inset)에** 붙는다.
       - 한 번에 하나만: 새 메시지가 오면 **이전 것을 교체**한다(스낵바와 같은 UX).
   - **일반 화면(모달 밖)** → **기존 `ScaffoldMessenger` 경로를 그대로 쓴다.**
     (기존처럼 하단 네비 **위**에 떠서 탭 바를 가리지 않고,
     채팅 화면이면 채팅 영역 안에서 떠서 composer 를 가리지 않는다.)
     단, **기존 스낵바를 먼저 내리고**(`hideCurrentSnackBar()`) 새 것을 띄워야 큐잉되지 않는다.
   - 루트 오버레이를 못 찾으면(극히 드문 예외) **기존 `ScaffoldMessenger` 경로로 폴백**해서
     아무것도 안 뜨는 일이 없게 한다.
   - `actionLabel`/`onAction` 을 주면 오른쪽에 액션(예: "실행 취소")이 붙는다.
     액션이 있으면 `SnackBar` 는 `persist` 가 기본 true 가 되므로 **명시적으로 `persist: false`** 로 둔다.
2. **C 소유 파일의 스낵바를 전부 이 헬퍼로 교체한다.** (총 15곳)
   `main_shell.dart` · `auth_screen.dart` · `settings/settings_sheet.dart` ·
   `settings/server_settings_dialog.dart`(이번 라운드에 C 담당으로 명시) ·
   `schedule/schedule_screen.dart` · `schedule/event_dialog.dart` ·
   `projects/projects_screen.dart` · `projects/task_detail_sheet.dart` ·
   `projects/task_dialog.dart` · `org/org_screen.dart`
3. **B 소유 파일 중 "모달 안에서 나는" 스낵바만** 이 헬퍼로 교체한다. (2차 웨이브 — 담당 B, §9-20)
   나머지(B 의 스낵바)는 **이미 보이고**, 바꾸면 되돌리기 UX 가 깨지므로 **두지 않는다.**
   - `new_channel_dialog.dart` (다이얼로그가 열려 있는 상태 → §9-20)
   - `search_dialog.dart` · `new_dm_dialog.dart` 는 **다이얼로그를 먼저 닫은 뒤** 띄우므로
     이미 보인다. (context 가 사라진 상태라 헬퍼를 쓰면 안 된다 → 그대로 둔다)
   - `message_actions.dart` 의 "실행 취소" 스낵바는 **채팅 영역 안에** 떠야 composer 를 가리지 않는다 →
     중첩 `ScaffoldMessenger` 경로 유지.
   - `message_composer.dart` · `message_attachments.dart` · `message_bubble.dart` 의 스낵바도 이미 보인다.
4. **모두 조용히 실패하지 않게**, 스낵바가 필요한 곳이라면 **상태를 되돌리는 롤백도 유지**한다.
   (9-5 / 9-7 에서 한 RSVP·삭제 롤백이 이미 그렇게 되어 있다.)

**회귀 테스트 (필수)**

- `test/app_snack_bar_test.dart` (신규, C):
  1. **다이얼로그가 열려 있는 상태에서** `showAppSnackBar` 를 부르면 메시지가 **보인다.**
     (구현 확인: `find.byType(SnackBar)` 는 **0건**이고 커스텀 스낵바 위젯이 **1건**,
     그리고 그 위젯이 **어떤 `Scaffold` 안에도 들어있지 않은지**(루트 오버레이에 직접 얹혔는지) 확인한다.
     → 기존 `ScaffoldMessenger` 방식이면 `Scaffold` 안에 있으므로 이 단언이 실패한다. = 실제 회귀 방지)
  2. **일반 화면에서** 부르면 **기존 `ScaffoldMessenger` 경로**를 쓴다
     (`find.byType(SnackBar)` 1건, 커스텀 스낵바 0건) → 기존 화면 모양이 유지된다.
  3. 새 메시지가 오면 이전 것이 교체된다 / 시간이 지나면 사라진다 / 탭하면 닫힌다 /
     액션이 동작한다.
- 기존 테스트 전부 통과 + `flutter analyze` 0 issues.

**주의**

- `flutter analyze` 의 `use_build_context_synchronously` 경고가 늘어난다면
  `context.mounted` 가드를 넣을 것. **기존 코드의 스타일을 바꾸지 말 것.**
- 파일 전체를 `dart format` 하지 말고 **수정한 부분만** 포맷할 것.

### 9-18. [MINOR] 메시지 수정 다이얼로그의 `TextEditingController` 를 dispose 하지 않는다

> **→ 7차 라운드, §9-17 의 2차 웨이브(B) 와 함께 처리한다.**

**위치**: `lib/widgets/message_bubble.dart` 의 `_showEditDialog()` (약 154행)

```dart
void _showEditDialog(BuildContext context) {
  final editController = TextEditingController(text: message.body);
  showDialog(
    context: context,
    builder: (ctx) => AlertDialog(
      content: TextField(controller: editController, ...),
      ...
    ),
  );
}   // ← editController 를 dispose 하지 않는다
```

`showDialog` 로 띄운 **로컬 컨트롤러**는 다이얼로그가 닫힐 때 자동으로 해제되지 않는다.
(Flutter 의 `TextField` 는 컨트롤러를 소유하지 않으므로 `dispose` responsibility 는 만든 쪽에 있다.)
→ 컨트롤러가 그대로 살아남아 메모리를 잡고, "컨트롤러가 dispose 되지 않았다" 는 종류의 버그가 된다.

**해결 (담당 B — `lib/widgets/message_bubble.dart`)**
1. 다이얼로그 본문을 **컨트롤러를 소유하는 StatefulWidget** 으로 분리하고 `dispose()` 에서 `editController.dispose()`.
   (§9-10-a / §9-14 에서 쓴 패턴과 동일)
2. 저장(수정) 버튼을 눌렀을 때도 컨트롤러를 참조한 뒤 `Navigator.pop` 하도록 순서를 지킬 것
   (`await` 뒤에 컨트롤러를 건드리지 않는 규칙).

**회귀 테스트**: `test/message_edit_dialog_dispose_test.dart` (신규)
- 다이얼로그를 열고 닫은 뒤, 컨트롤러에 `addListener` 를 붙이면 `FlutterError` 가 난다(= dispose 된 것).
  (`controller.text` getter 는 dispose 후에도 예외를 안 던지므로 **`addListener` 로 probe 할 것**)

### 9-19. [MAJOR] 채널 나가기 / 1:1 대화 삭제가 조용히 실패한다

> **→ 7차 라운드, §9-17 의 2차 웨이브(B) 와 함께 처리한다.**

**위치**: `lib/screens/chat/channel_info_dialog.dart` 의 `_leaveOrDelete()` (약 86~93행)

```dart
if (confirmed == true && context.mounted) {
  Navigator.pop(context);            // 정보 다이얼로그를 닫는다
  if (isDm) {
    await state.deleteDm(widget.channel.id);      // ← try/catch 가 없다
  } else {
    await state.leaveChannel(widget.channel.id);  // ← try/catch 가 없다
  }
}
```

`deleteDm` / `leaveChannel` 는 `Future<void>` 이고 **실패하면 예외를 던진다.**
여기에는 `try/catch` 가 없으므로:

- 서버 오류/네트워크 단절 시 **Unhandled exception** 으로 끝난다.
- 사용자는 **"삭제/나가기" 가 아무 일도 일어나지 않은 것처럼** 보인다(다이얼로그만 사라짐).
  → "내 대화 목록에서 채널이 안 사라졌는데 왜 하지?" 라는 혼란.

**해결 (담당 B — `lib/screens/chat/channel_info_dialog.dart`)**
1. `await` 를 `try/catch` 로 감싸고, 실패하면 **사유를 스낵바로 알린다.**
   - DM 삭제 실패 → "대화를 삭제하지 못했습니다"
   - 채널 나가기 실패 → "채널을 나가지 못했습니다"
2. 안내는 `showAppSnackBar(context, ...)` 로 띄워라.
   (다이얼로그는 이미 닫힌 상태라 일반 화면 경로로 뜨고 → 하단 네비를 가리지 않는다)
3. `await` 뒤에 `context` 를 쓰지 않도록 순서를 지킬 것
   (컨텍스트가 사라진 뒤에 `ScaffoldMessenger.of(context)` 를 부르면 터진다).

**회귀 테스트**: `test/channel_leave_delete_failure_test.dart` (신규)
- `deleteDm` / `leaveChannel` 이 예외를 던지면 **스낵바에 사유가 보인다** + **Unhandled exception 이 없다**.

### 9-20. [MAJOR] "새 채널" 다이얼로그의 생성 실패 안내가 보이지 않는다

> **→ 7차 라운드, §9-17 의 2차 웨이브(B) 와 함께 처리한다.**

**위치**: `lib/screens/chat/new_channel_dialog.dart` `_submit()` (약 39행)

```dart
} catch (e) {
  if (mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('생성 실패: $e')));
    setState(() { _isCreating = false; });
  }
}
```

`showDialog` 로 열린 다이얼로그가 **아직 열려 있는 상태**에서 스낵바를 띄운다.
`ScaffoldMessenger` 스낵바는 **루트 Scaffold** 가 그리므로 **다이얼로그 뒤에 숨어서 안 보인다.**
→ 사용자는 "이름이 안 먹혔는데 아무 반응이 없다" 고 느낀다. (모달 가림 = §9-17 과 같은 근본 원인)

**해결 (담당 B — `lib/screens/chat/new_channel_dialog.dart`)**
1. `showAppSnackBar(context, '생성 실패: $e')` 로 바꾸라. (C 가 만든 공용 헬퍼)
   → 헬퍼는 **모달 안에서 불리면 루트 오버레이에 직접 얹으므로** 다이얼로그 위에 보인다.
2. `setState(() { _isCreating = false; })` 는 그대로 유지 (버튼이 다시 활성화되어야 재시도할 수 있다).

**주의**: B 영역의 **다른** 스낵바는 **그대로 둬도 된다.**
- `search_dialog.dart` · `new_dm_dialog.dart` 는 **다이얼로그를 먼저 닫은 뒤** 스낵바를 띄우므로
  이미 보인다. (이때는 context 가 사라진 상태라 `showAppSnackBar(context, ...)` 를 쓰면 안 된다!)
- `message_actions.dart` 의 "실행 취소" 스낵바는 **채팅 영역 안에** 떠야 composer 를 가리지 않아야 하므로
  중첩 `ScaffoldMessenger` 경로를 유지한다.
- `message_composer.dart` · `message_bubble.dart` 의 스낵바도 이미 보인다.

### 9-21. 7차 라운드 실기 검증 결과 (2026-11-09, 에뮬레이터 Pixel_7_API_36)

§9-17~§9-20 을 실제로 적용한 APK 를 기기에 설치해서 손으로 확인한 결과다.
실패 경로를 만들기 위해 **백엔드를 잠시 정지**한 상태에서 진행했다(그 뒤 재기동함).

| 확인 항목 | 결과 |
|---|---|
| **§9-17 모달 안 스낵바 (설정 시트)** | **해결 확인.** 시트 안 "바쁨" 칩 탭 → 칩이 "온라인"으로 롤백되고 **"상태를 바꾸지 못했습니다" 가 시트 위에 선명히 보인다.** (스크린샷 `/tmp/r7_02_sheet_snack.png`) |
| **§9-17 모달 안 스낵바 (프로필 다이얼로그)** | **해결 확인.** "프로필 수정" → 저장 → **"프로필을 저장하지 못했습니다: 서버에 연결할 수 없습니다. (http://10.0.2.2:8000)"** 가 **AlertDialog 위에** 보이고, **다이얼로그는 그대로 열려 있으며 입력값도 유지**된다(= §9-14 "실패하면 닫지 않는다" 충족). (`/tmp/r7_03_prof_snack.png`) |
| **§9-20 새 채널 다이얼로그** | **해결 확인.** 이름 "r7test" 입력 → 만들기 → **"생성 실패: 서버에 연결할 수 없습니다. …"** 가 **다이얼로그 위**에 보이고, **입력값 "r7test" 가 유지**되며 다이얼로그도 열려 있다. (`/tmp/r7_09_newchan_fail.png`) |
| **§9-19 채널 나가기 실패** | **해결 확인.** 채널 정보 → "채널 나가기" → 나가기 → **"채널을 나가지 못했습니다"** 가 보인다. (`/tmp/r7_14_leave_fail.png`) |
| **회귀: 일반 화면 스낵바** | **이상 없음.** 일정 탭 RSVP 칩 실패 → **"참석 여부를 바꾸지 못했습니다"** 가 **하단 네비 위**에 떠서 **탭 바를 가리지 않는다**(칩은 "참석"으로 롤백). `ScaffoldMessenger` 경로가 유지됐다는 뜻. (`/tmp/r7_07_rsvp.png`) |
| **회귀: 채팅 화면 스낵바** | **이상 없음.** 백엔드 정지 중 메시지 전송 → **"전송에 실패했습니다. 다시 시도해주세요."** 가 **채팅 영역 안(입력창 위)**에 보이고 **composer 를 가리지 않는다**(중첩 `ScaffoldMessenger` 경로 유지). (`/tmp/r7_16_send_fail.png`) |
| **정적 검사** | `flutter analyze` → **No issues found**. `flutter test` → **66/66 통과**. |
| **위젯 트리 에러** | **없음.** `ext.flutter.debugDumpApp` + `debugDumpRenderTree` 덤프에서 `ErrorWidget` **0건**, `RenderErrorBox` **0건**, `overflowed by` / `RenderFlex overflowed` **0건**, `Failed assertion` **0건**. logcat 에 `EXCEPTION CAUGHT` / `Unhandled exception` **0건**(백엔드 정지 동안의 `[WS] connect failed` 만 존재 — 의도된 실패 경로). |
| **백엔드 재기동** | `GET /api/v1/health` → `{"status":"ok"}`. 앱의 "실시간 연결이 끊어졌습니다" 배너가 **자동으로 사라지고** WS 가 재연결됐다. |

**7차 라운드 테스트 데이터 정리** (API `DELETE /api/v1/messages/{id}` 사용)

- 삭제: `attachment test`(첨부파일 포함) · `live-from-jimin` · `sent-while-backgrounded` 3건
  → `#general` 에는 **시드 데이터와 "(삭제된 메시지)" 자리표시자만** 남는다.
- `r7test` 채널은 백엔드가 정지된 상태에서 만들려 해서 **생성되지 않았고**,
  `r7send` 메시지도 전송에 실패해 **서버에 남지 않았다.**
- 나머지 채널(`engineering`/`release`/`random`)은 **시드 데이터만** 있고 테스트 잔여물이 없다.

**알고 있는 trade-off (결함 아님)**

- §9-19 의 실패 스낵바는 **화면 맨 아래**에 떠서 4초 동안 **메시지 입력창을 가린다.**
  정보 다이얼로그가 열려 있는 동안에야 호출되므로(그때 `context` 가 아직 `PopupRoute` 안이다)
  헬퍼는 **루트 오버레이 경로**를 택한다. 이 경우를 일반 화면 경로(`ScaffoldMessenger`)로
  되돌리면 **스낵바가 채팅 화면(push 된 라우트) 뒤에 숨어서 아예 안 보인다.**
  → "보이지만 composer 를 잠깐 가리는 것"이 "안 보이지만 composer 를 안 가리는 것"보다 나으므로
  **의도된 선택**으로 둔다. (다음 라운드에서 개선 여부를 재점검할 수 있다.)

---

## 8차 라운드 (2026-11-09, 에뮬레이터 Pixel_7_API_36 실기)

### 9-22. 태스크 코멘트가 화면에서 2개로 보인다 (담당 A)

**실기 확인 (2026-11-09)**

프로젝트 `prj_01M6WWCMCV62QPX8JB9R7FG3GH` 의 할 일 `tsk_01M6WWCMD070JM73DTJE3J8CQK` 상세 시트에서
의견 "r8comment" 한 건을 작성했다.

- **서버**: `GET /api/v1/projects/{pid}/tasks` → 해당 태스크의 `comments` **1건**
  (`tc_01M6Y3ZXF47Y4DSY7SXFRG1YZX`)
- **화면**: 코멘트 시트 제목이 **"의견 (2)"** 이 되고, **같은 내용 "r8comment" 가 2줄로 반복**된다.

→ §9-1(채널/이벤트/태스크 생성 중복)과 **같은 근본 원인**이지만, 이번에는 **태스크 자체가 아니라
코멘트 목록**에서 중복이 난다.

**원인**

백엔드는 `POST /api/v1/tasks/{task_id}/comments` 를 처리할 때 **HTTP 응답보다 먼저**
`await events.emit_task_updated(session, project, task)` 로 WS 이벤트를 보낸다
(`backend/app/api/v1/projects.py` 의 `post_task_comment`).

이 WS 이벤트는 **새 코멘트가 이미 포함된 태스크**를 담고 있고, 클라이언트의 WS 핸들러는
태스크 단위로 upsert 한다:

```dart
// lib/providers/app_state_realtime.dart
case 'task.created':
case 'task.updated':
  if (event['task'] != null) {
    final t = Task.fromJson(event['task'] as Map<String, dynamic>);
    final list = _projectTasks[t.projectId] ?? [];
    // REST 응답 경로와 같은 규칙을 쓴다 (둘 중 하나가 먼저 와도 1개).
    _projectTasks[t.projectId] = upsertById(list, t, (x) => x.id);
    _notify();
  }
```

태스크 단위로는 중복이 없으므로 여기까지는 맞다. 문제는 **그 뒤에 오는 REST 응답 경로**다:

```dart
// lib/providers/app_state_workspace.dart  (addTaskComment)
final updatedComments = [...t.comments, comment];   // ← 무조건 append
list[idx] = t.copyWith(comments: updatedComments);
```

REST 응답 경로는 코멘트에 **id 가드 없이 무조건 append** 한다.
→ WS 경로가 이미 `tc_…` 를comments 에 넣어 둔 상태에서 같은 `tc_…` 가 또 들어가서 **2개**가 된다.

같은 파일의 다른 변경 함수들(`createEvent` / `createProject` / `createTask` / `rsvpEvent` /
`updateTaskStatus`)은 전부 id 가드가 있는 규칙을 쓰는데, **주석 추가만 유일하게 예외**다.

**해결 (담당 A — `lib/providers/app_state_workspace.dart`)**

1. `addTaskComment` 의 코멘트 병합을 **id 기준 upsert** 로 바꿔라.
   이미 있는 `lib/providers/list_upsert.dart` 의 `upsertById` 헬퍼를 쓰면 된다.
   ```dart
   final updatedComments = upsertById(t.comments, comment, (c) => c.id);
   ```
   (`upsertById` 는 목록에 같은 id 가 있으면 **교체**, 없으면 **추가** 한다.
   순서가 WS → REST 이든 REST → WS 이든 최종 1개다.)
2. 태스크 교체는 `list[idx] = t.copyWith(comments: updatedComments)` 로 그대로 두어도 되지만,
   `t.comments` 가 이미 WS 로 갱신된 최신 목록일 수 있으므로 **태스크 단위 upsert** 로 통일해도 된다.
3. **WS 핸들러는 그대로 둔다.** 태스크 단위 upsert 는 이미 §9-1 규칙을 만족한다.
   (WS 경로가 먼저 왔을 때 REST 경로가 그 태스크를 덮어쓰지 않게 하려면,
   REST 경로의 병합 결과를 **기존 comments + 새 코멘트** 로 만들어야 한다.
   `upsertById(t.comments, comment, ...)` 가 정확히 그렇게 동작한다.)

**주의**: 카운터("의견 (N)")도 자동으로 1이 된다. `task_detail_sheet.dart` 는
`task.comments.length + _pendingComments.length` 로 계산하므로 별도 수정이 필요 없다.

**테스트**: 새 테스트 1개 추가 — `addTaskComment` 를 호출할 때
**같은 id 의 코멘트가 이미 목록에 있으면 1개로 유지**되는지 검증.

---

### 9-23. 일정 카드에 "상세 보기" 와 "수정" 경로가 없다 (담당 A + C)

**실기 확인 (2026-11-09)**

일정 탭에서 카드(제목 · 시간 · 장소 · 설명)를 **눌러도 아무 일도 일어나지 않는다.**

**원인**

`lib/screens/schedule/schedule_screen.dart` 의 `_buildEventCard()` 가 `Card` + `Padding` + `Column` 이고
**`onTap` / `InkWell` 이 없다.** 카드 안에서 동작하는 것은 두 개뿐이다:

- RSVP 칩 3개 (`참석` / `미정` / `불참`) — `:440`~`:458`
- 생성자에게만 보이는 **삭제** `IconButton` (`:388`) — 44dp 터치 영역 확보 (§9-7)

그래서 모바일에서 가능한 일은 **"참석 여부 표시" 와 "삭제" 뿐**이고,

1. **참석자 목록을 볼 수 없다.** (`ev.attendees` 는 모델에 있지만 화면에 아무 데도 안 나온다)
2. **설명 전체를 볼 수 없다.** 카드는 `maxLines: 2` 로 자른다(`:429`).
3. **작성자도 안 보인다.**
4. **수정할 수 없다.** 제목을 잘못 쓰거나 시간을 틀렸으면 → 삭제 후 다시 만들어야 한다.
   그런데 삭제는 참석자·RSVP 응답을 **모두 유실**시키고, 만들 때도 알림/이력이 남는다.
   → 모바일에서 일정 실수를 고칠 수단이 없다.

**백엔드는 이미 편집을 지원한다**

- `PATCH /api/v1/events/{event_id}` (`EventUpdate`: title / description / location /
  starts_at / ends_at / all_day / is_private / channel_id / attendee_ids)
- `GET  /api/v1/events/{event_id}`
- 권한: **생성자 또는 워크스페이스 관리자**만 변경 가능 (그 외 403)

→ **모바일만 이 경로를 쓰지 않는다.** 서버를 바꿀 필요 없다.

**해결 — A 쪽 (상태/통신 계층)**

`lib/services/api_service.dart` 에 추가:

```dart
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
}) async;
```

- 본문에는 **값이 들어간 항목만** 넣는다 (null 은 "변경 안 함" 의미).
  백엔드 `update_event` 도 `None` 이면 무시한다.
  → Dart 에서 `null` 과 "미지정" 을 구분 못 하므로, `null` = 미지정으로 고정한다.
  (`channel_id` 는 `null` 로 **해제**하는 경로가 필요하면 Dart 에서 별도 플래그를 쓰거나
  이번 라운드에서는 제외한다. → **이번 라운드는 변경만 지원**한다.)

`lib/providers/app_state_workspace.dart` 에 추가:

```dart
Future<bool> updateEvent({
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
}) async;
```

- 성공하면 `true` 를 돌려주고, **일정 목록을 id 기준 upsert** 로 갱신한다
  (`lib/providers/list_upsert.dart` 의 `upsertById` 사용 — §9-1 규칙).
  백엔드가 PATCH 직후 `events.emit_event_updated` 로 WS 를 보내므로
  **WS 경로가 REST 응답보다 먼저 온다.** 이때 WS 가 넘긴 태스크는 이미 새 값이므로,
  REST 응답 경로는 **WS 로 받은 이벤트에 다시 upsert** 해도 값이 같다.
- 실패하면 `false` 를 돌려주고 `debugPrint('[updateEvent error] $e')` 남긴다.
  (`deleteEvent` / `rsvpEvent` 와 같은 규칙)

**해결 — C 쪽 (화면 계층)**

1. `lib/screens/schedule/schedule_screen.dart`
   - `_buildEventCard()` 의 카드를 `InkWell`(또는 `InkWell` + `Material`) 로 감싸서
     **카드 전체를 눌러 상세 시트가 뜨게** 한다.
   - 단, 카드 안의 RSVP 칩과 삭제 버튼은 **그대로 동작**해야 한다
     (칩/버튼을 누를 때 카드 탭이 같이 발동하지 않게 한다).
   - 생성자 여부(`ev.createdBy == myId`)를 상세 시트에 넘긴다.
2. **신규 파일** `lib/screens/schedule/event_detail_sheet.dart`
   (`showModalBottomSheet` — 키보드가 올라와도 composer 를 가리지 않도록 스크롤 가능하게)
   - 제목 · 날짜/시간(하루 종일 여부) · 장소 · **설명 전체** · **참석자 목록**(이름 + RSVP 상태)
     · 작성자 · 연결된 채널 을 보여준다.
   - **생성자(또는 워크스페이스 관리자)에게만** "수정" · "삭제" 버튼을 보여준다.
   - "삭제" 는 기존의 확인 다이얼로그(`'${ev.title}' 일정을 삭제하시겠습니까?`)를 재사용하고,
     실패하면 `showAppSnackBar(context, '일정을 삭제하지 못했습니다')`.
3. **편집 UI**: `lib/screens/schedule/event_dialog.dart` 를 **편집 모드로 재사용**한다.
   - `EventDialog` 에 `ScheduleEvent? editing` 파라미터를 추가한다.
     있으면 제목이 "일정 수정" 이 되고, 기존 값으로 필드를 초기화하고,
     등록 버튼이 "수정" 이 되고, `_submit()` 이 `state.updateEvent(...)` 를 호출한다.
     없으면 지금과 같이 생성 동작.
   - 실패하면 **다이얼로그를 닫지 않고** 입력값을 유지한 채
     `showAppSnackBar(context, '일정 수정 실패: $e')` 로 알린다.
4. 모바일에서 날짜/시간을 고르는 UX 는 이미 `EventDialog` 에 구현되어 있으니 재사용한다.
   (붙잡기/드래그 등 새 입력 방식은 이번 라운드 범위 밖)

**주의 (공용 헬퍼 규칙)**

- 모달 안에서 나는 스낵바는 **반드시 `showAppSnackBar`** 를 쓴다
  (`lib/widgets/app_snack_bar.dart`, C 소유). `ScaffoldMessenger.of(context).showSnackBar` 를
  직접 쓰면 다이얼로그/시트 뒤에 숨어서 안 보인다 (§9-17).
- `lib/screens/schedule/` 는 **C 영역**이다. A 는 `lib/services/` 와 `lib/providers/` 만 건드린다.

**테스트**

- A: `updateEvent` 실패 시 `false` 를 돌려주고 목록이 바뀌지 않는지.
- C: 일정 카드를 탭하면 상세 시트가 뜨고, 상세 시트에서 참석자/설명 전체가 보이는지
  (위젯 테스트).

---

### 9-24. 요청/할 일의 제목·설명을 수정할 수 없다 (담당 A + C)

**실기 확인 (2026-11-09)**

프로젝트 탭 → "전체 시스템 개발" → 요청 카드(요청 탭의 "정산 대시보드 화면")를 탭하면
`TaskDetailSheet` 가 열린다. 이 시트에서 가능한 일은 **세 가지**뿐이다.

- 상태 변경 (`PopupMenuButton` — `task_detail_sheet.dart:354`)
- 삭제 (`IconButton` — `:145`)
- 의견(코멘트) 작성 (하단 입력창)

**제목과 설명은 읽기 전용**이다. 제목을 잘못 쓰거나(예: "정산 대시보드 화면" 이라고 쓰고
뒤에 "v2" 를 붙여야 했다) 설명을 수정하고 싶어도 **수정할 수단이 없다.**

**왜 이게 큰 문제인가**

할 일/요청에는 **의견(코멘트) 스레드**가 붙는다. 실수로 제목이나 설명을 잘못 쓰면
고치는 방법은 **삭제 후 다시 만드는 것**뿐인데,

- 같이 달린 **의견이 전부 사라진다** (이번 라운드 테스트에서 "r8comment" 의견이 붙은 요청을
  보면 이 손실이 얼마나 큰지 알 수 있다)
- **담당자·마일스톤·로드맵 연결·마감일**을 다시 손으로 맞춰야 한다
- 진행 이력/알림도 남는다

**백엔드와 통신 계층은 이미 준비되어 있다**

- `PATCH /api/v1/tasks/{task_id}` (`TaskUpdate`: title / description / status / assignee_id /
  roadmap_id / milestone_id / start_at / due_at / position)
- `mobile/lib/services/api_service.dart` 의 `updateTask()` 도 **이미 title/description 을 받는다**
  (`api_service.dart:512`)

→ **화면 진입 경로만 없다.** 서버를 바꿀 필요도, 통신 계층을 새로 만들 필요도 없다.

**해결 — A 쪽 (상태 계층)**

`lib/providers/app_state_workspace.dart` 에 추가:

```dart
Future<bool> updateTask({
  required String taskId,
  String? title,
  String? description,
  String? assigneeId,
  DateTime? dueAt,
  String? roadmapId,      // 2026-11-09 추가 (편집 다이얼로그에 로드맵 드롭다운이 있음)
}) async;
```

- `api.updateTask(...)` 를 호출하고, 성공하면 **할 일 목록을 id 기준 upsert** 로 갱신하고
  `_notify()` 후 `true`, 실패하면 `debugPrint('[updateTask error] $e')` 후 `false`.
  (§9-1 규칙: 백엔드가 PATCH 직후 WS `task.updated` 를 먼저 보내므로,
  REST 응답 경로는 WS 로 받은 태스크에 다시 upsert 해도 값이 같다.
  목록 갱신은 `lib/providers/list_upsert.dart` 의 `upsertById` 사용.)
- **기존 `updateTaskStatus(Task, TaskStatus)` 는 그대로 둔다.** (시그니처가 다르고, 쓰고 있는 곳이 있다.)
- null 인자는 "변경 안 함".

**해결 — C 쪽 (화면 계층)** — *이 회차에서는 C 에이전트가 `lib/screens/schedule/` 만 작업 중이라,
화면 계층 구현은 **B 에이전트에게 배정**했다 (`lib/screens/projects/` 2개 파일 + 테스트 1개).
B 는 화면 계층만, A 는 상태 계층만 건드린다. (2026-11-09)*

1. `lib/screens/projects/task_detail_sheet.dart`
   - 헤더에 **"수정" 버튼**(`IconButton(Icons.edit_outlined)`)을 추가한다.
     삭제/닫기 버튼 옆에 두고, **44dp 터치 영역**을 확보한다 (§9-7).
   - 누르면 편집 다이얼로그를 연다.
2. `lib/screens/projects/task_dialog.dart` 를 **편집 모드로 재사용**한다.
   - `TaskDialog` 에 `final Task? editing` 파라미터를 추가한다.
     있으면 제목 "할 일 수정", 기존 값으로 필드(제목/설명/상태/담당자/마감일/로드맵) 초기화,
     버튼 라벨 "수정", `_submit()` 이 `state.updateTask(...)` 를 호출.
     없으면 지금과 같이 생성 동작.
   - 실패하면 **다이얼로그를 닫지 않고** 입력값을 유지한 채
     `showAppSnackBar(context, '할 일 수정 실패: $e')` 로 알린다.
3. 시트를 닫지 않고 위에서 편집하면 **시트가 열린 채로** 제목이 갱신되어야 한다.
   (`TaskDetailSheet` 는 이미 `state.activeProjectTasks` 에서 최신 태스크를 다시 찾는다 —
   `:110`. 이 경로를 그대로 쓰면 된다.)

**주의 (공용 헬퍼 규칙)**

- 모달 안에서 나는 스낵바는 **반드시 `showAppSnackBar`** 를 쓴다
  (`lib/widgets/app_snack_bar.dart`, C 소유). §9-17.
- `lib/screens/projects/` 는 **C 영역**, `lib/providers/` · `lib/services/` 는 **A 영역**이다.

**테스트**

- A: `updateTask` 실패 시 `false` 를 돌려주고 목록이 바뀌지 않는지.
- C: 상세 시트에서 "수정" 을 누르면 편집 다이얼로그가 기존 값으로 열리고,
  수정하면 시트의 제목이 갱신되는지 (위젯 테스트).

---

### 9-25. [MAJOR] 일정의 시간이 **9시간씩 밀린다** — 만들 때도, 고칠 때도 (담당 A + C)

**실기 확인 (2026-11-09)** — §9-23 일정 상세 시트를 붙이면서 발견했다.

#### 증상 1. 저장할 때마다 시간이 9시간 뒤로 밀린다

`lib/screens/schedule/event_dialog.dart` 는 시작/종료 시각을 **로컬** `DateTime` 으로 만든다
(`DateTime(_startDate.year, ..., _startTime.hour, _startTime.minute)`).
`lib/services/api_service.dart` 가 이를 `startsAt.toIso8601String()` 로 직렬화해서 보낸다.

그런데 **로컬 `DateTime` 의 `toIso8601String()` 에는 타임존이 없다.**
`2026-11-09 10:00 (KST)` → `"2026-11-09T10:00:00"` (끝에 `Z` 가 없다).

백엔드의 `UTCDateTime` 컬럼은 **타임존 없는 값을 UTC 라고 간주**한다
(`backend/app/models/base.py:30-35` → `value.replace(tzinfo=UTC)`).
즉 **사용자가 고른 10:00(KST) 이 10:00 UTC(= 19:00 KST) 로 저장**된다.
앱은 값을 `toLocal()` 로 읽어 19:00(KST) 로 보여준다.

**편집하면 더 심해진다.** 편집 다이얼로그는 `editing.startsAt.toLocal()`
(`event_dialog.dart:47`) 로 값을 미리 채우므로 19:00 이 들어가 있고,
다시 저장할 때 또 9시간 밀린다. → **저장(편집)할 때마다 +9시간씩 밀린다.**

실기 증거 — "r8event" 를 10:00 에 만들었다가 한 번 편집한 결과:

| 단계 | DB 원본 | 앱에 보이는 시간 |
|---|---|---|
| 생성 (10:00 선택) | `2026-11-09 10:00:00` | 19:00 (KST) |
| 1차 편집 (그대로 저장) | `2026-11-09 19:00:00` | 다음날 04:00 (KST) |

API 응답도 `starts_at: "2026-11-09T19:00:00Z"` (= 11월 10일 04:00 KST) 였다.

#### 증상 2. 같은 일정이 두 날짜에 동시에 보인다

- 카드 목록의 날짜 필터는 `schedule_screen.dart:51-53` 의 `_isSameDay(a, b)` 로
  **원시 UTC** 인 `e.startsAt` 와 **로컬** 인 `selectedDate` 를 비교한다 (사용처 `:100-102`).
- 상세 시트는 `event.startsAt.toLocal()` 로 **로컬** 로 표시한다 (`event_detail_sheet.dart:249-250`).

→ 실기에서 카드는 **"11월 9일"** 쪽에 그려지고, 시트는 **"2026년 11월 10일 (화) · 04:00"** 이라고 한다.
한글이 두 날짜에 동시에 있다. (달력 점도 같은 버그 — `:305`)

#### 증상 3. (잠재) 조회 범위도 9시간 밀린다

`getEvents` 의 `from`/`to` (`api_service.dart:373`) 도 타임존 없는 로컬 문자열이라
백엔드가 UTC 로 해석한다. 데스크톱은 `from.toISOString()` 로 진짜 UTC 인스턴스를 보낸다
(`desktop/src/store/useStore.ts:864-867`).
지금은 모바일이 범위 없이 전체를 부르고 있어서 (§9-25 시점 `app_state_workspace.dart:13`) 아직 드러나지 않는다.

#### 데스크톱(참조 구현) 규약

| | 쓰기 | 읽기 / 날짜 묶기 |
|---|---|---|
| 데스크톱 | `fromDateTimeInput()` → `new Date(y,m-1,d,h,min).toISOString()` = **진짜 UTC 인스턴트** (`desktop/src/lib/calendar.ts:86-90`) | `dayOf(iso)` → `dateKey(new Date(iso))` = **로컬 날짜** (`calendar.ts:64-66`) |
| 모바일 (현재) | `toIso8601String()` = **타임존 없는 로컬 벽시계** ✗ | 카드=UTC, 시트=로컬 ✗ |

**규약: 보낼 때는 진짜 UTC 인스턴트, 보여줄 때는 로컬.**
이렇게 해야 데스크톱에서 만든 일정과 모바일에서 만든 일정이 **같은 시각**이 된다.

#### 해결 — A 쪽 (통신 계층)

`lib/services/api_service.dart` 에서 **나가는 모든 날짜·시간을 `toUtc().toIso8601String()` 로 통일**한다.
백엔드는 UTC 인스턴스를 받아 UTC 로 정규화해 저장하고(`process_bind_param` → `astimezone(UTC)`),
되읽을 때도 UTC 로 태깅하므로 **로컬 10:00(KST) → "2026-11-09T01:00:00Z" → DB '2026-11-09 01:00:00'
→ 되읽으면 10:00(KST)** 로 왕복이 맞는다.

- `getEvents` 의 `from`/`to` (`:373`)
- `createEvent` 의 `starts_at`/`ends_at` (`:398-399`)
- `updateEvent` 의 `starts_at`/`ends_at` (`:439-440`)
- `createTask` 의 `due_at` (`:504`), `updateTask` 의 `due_at` (`:518`)

**주의**: 이미 저장된 값은 고치지 않는다(백엔드 데이터 이전은 이번 범위 밖).
읽은 값은 UTC 인스턴스이므로 **화면에는 항상 `.toLocal()` 로 찍는다.**

#### 해결 — C 쪽 (화면 계층)

1. `lib/screens/schedule/schedule_screen.dart:51-53` `_isSameDay` 를 **양쪽 다 로컬** 로 비교한다.
   - 날짜 필터 (`:100-102`): `_isSameDay(e.startsAt.toLocal(), selectedDate)`,
     `_isSameDay(e.endsAt.toLocal(), selectedDate)`
   - 날짜를 가로지르는 판정: `e.startsAt.toLocal().isBefore(selectedDate) && e.endsAt.toLocal().isAfter(selectedDate)`
   - 달력 점 (`:305`) 도 같은 기준.
2. 마감일 표시/프리필도 로컬로 통일한다 (**B 담당**, `lib/screens/projects/`):
   - `projects_screen.dart:365` — `DateFormat('M.d').format(task.dueAt!.toLocal())`
   - `task_detail_sheet.dart:203` — `DateFormat('yyyy.MM.dd').format(task.dueAt!.toLocal())`
   - `task_dialog.dart:42` — `_dueDate = editing.dueAt?.toLocal()`
   - (A 가 `due_at` 을 UTC 인스턴스로 보내기 시작하므로, 그대로 찍으면 **하루 밀린다**.)

#### 테스트

- A: `createEvent`/`updateEvent` 요청 본문의 `starts_at`/`ends_at` 가 `Z` 로 끝나는지 (MockClient 로 본문 캡처).
- A: `due_at` 도 `Z` 로 끝나는지.
- C: UTC 로 저장된 이벤트를 **로컬 기준**으로 날짜 묶는지 (위젯 테스트).
- B: 마감일이 로컬로 표시되는지, 편집 다이얼로그 프리필이 로컬 날짜인지.

#### 관찰 (결함 아님 — 기록만)

시드 데이터의 시간은 **UTC 기준**으로 들어 있다 (`backend/scripts/seed.py:792` — `_now()` = `datetime.now(UTC)`).
"디자인 리뷰 14:00" 은 실제로는 14:00 UTC = 23:00 KST 이라 데스크톱에서도 23:00 으로 보인다.
데스크톱과 동일하므로 **모바일 고유 결함이 아니며**, 이번 범위에서 손대지 않는다.

---

### 9-27. [MINOR] 날짜·시간 선택기가 **영어 + 12시간제**로 나온다 (담당 C)

**실기 확인 (2026-11-09)** — §9-25 를 실기 검증하던 중 발견했다.

일정 생성/수정 다이얼로그의 "시작 시간" 을 누르면 Material `TimePicker` 가 뜨는데,
**앱 전체가 한국어인데 이 창만 영어**다.

| | 실제로 보이는 것 |
|---|---|
| 제목 | **"Select time"** (한국어야 함) |
| 버튼 | **"Cancel" / "OK"** |
| 시간 표기 | **10 : 00  AM / PM** (12시간제) |

그런데 앱이 그 일정을 **24시간제**로 보여준다 ("10:00 - 11:00").
→ **같은 시간이 화면마다 다른 형식으로 보인다.** 한국 사용자에게 "AM/PM" 은 낯선 표기다.
(날짜 선택기도 마찬가지로 영어("Select date", "Cancel"/"OK")이고, 키보드도 영어 키보드로 나온다.)

**원인**

`lib/main.dart:31-43` 의 `MaterialApp` 에

```dart
localizationsDelegates: const [ GlobalMaterialLocalizations.delegate, ... ],
supportedLocales: const [ Locale('ko', 'KR'), Locale('en', 'US') ],
```

까지는 있는데 **`locale:` 가 없다.**
`MaterialApp` 은 `locale` 이 없으면 **기기(=에뮬레이터)의 로케일**로 해석한다.
에뮬레이터는 en_US 라서 **Material 위젯 전부(en_US)** 가 english + 12시간제로 렌더된다.
(앱이 직접 그리는 텍스트는 하드코딩된 한국어라서 한국어로 보이는 것.)

**해결 — C 쪽 (화면 계층)**

`lib/main.dart` 의 `MaterialApp` 에 **`locale` 한 줄**을 추가한다.

```dart
locale: const Locale('ko', 'KR'),
```

- 앱은 한국어 제품이므로 Material 위젯도 한국어로 고정한다.
  (기기가 영어로 되어 있어도 날짜/시간 선택기 = 한국어 + 24시간제)
- 부수 효과: 키보드도 한국어 IME 으로 뜬다(플러터가 `Localizations.localeOf(context)` 를
  텍스트 입력에 넘기기 때문).
- `supportedLocales` 는 그대로 둔다.

**소유권 예외 (이번 회차 한 번만)**

`lib/main.dart` 은 §0 규약상 "공통(수정 금지)" 이지만,
이 절은 **C 에이전트에게 `lib/main.dart` 한 파일에 대한 일회성 예외 권한**을 부여한다.
C 는 **`MaterialApp` 의 `locale:` 한 줄만** 추가하고, 그 파일의 다른 코드는 건드리지 않는다.
(A·B 는 `lib/main.dart` 을 계속 건드리지 않는다.)

**테스트**

- 위젯 테스트: `MaterialApp` (또는 앱 루트) 를 pump 하고 `Locale('ko','KR')` 가 적용되는지.
  (`Localizations.localeOf(context)` 로 확인)
- 회귀: 기존 90개 테스트가 그대로 통과하는지.

---

### 9-28. 8차 라운드 실기 검증 결과 (2026-11-09, 에뮬레이터 Pixel_7_API_36)

§9-22 ~ §9-25, §9-27 을 적용한 APK 를 기기에 설치해서 손으로 확인한 결과다.

| 확인 항목 | 결과 |
|---|---|
| **§9-22 태스크 코멘트 중복** | **해결 확인.** "정산 대시보드 화면" 시트에 의견 "r9dup" 작성 → **"의견 (1)"** 로 뜨고 **"r9dup" 가 1줄만** 나온다. 서버도 `GET /api/v1/projects/{pid}/tasks` → 해당 태스크 `comments` **1건**. (스크린샷 `/tmp/v41.png`) |
| **§9-23 일정 상세 시트** | **해결 확인.** 일정 카드(제목·시간·장소·설명)를 **탭하면 상세 시트가 열린다.** 시간·장소·작성자·설명·**참석자(3명) 과 RSVP 배지** 가 모두 보인다. (`/tmp/v36.png`) |
| **§9-24 할 일 제목/설명 수정** | **해결 확인.** 태스크 상세 시트에 **연필(수정) 버튼**이 있고, 누르면 **"할 일 수정"** 다이얼로그가 **제목·설명이 미리 채워진 상태**로 열린다. (`/tmp/v38.png`, `/tmp/v39.png`) |
| **§9-25 일정 시간 9시간 밀림 (생성)** | **해결 확인.** 10:00 로 만든 일정의 API 요청이 `starts_at: "2026-11-10T01:00:00Z"` (= 10:00 KST) 이고, 카드에도 **"10:00 - 11:00"** 으로 보인다. |
| **§9-25 일정 시간 9시간 밀림 (수정)** | **해결 확인.** 시간을 바꾸지 않고 "수정" → "수정" 해도 API 값이 **`2026-11-09T19:00:00Z` 로 그대로**이고 카드도 **"04:00 - 05:00"** 으로 안 밀린다. |
| **§9-25 날짜 묶기** | **해결 확인.** 카드가 **선택한(로컬) 날짜** 쪽에 그려지고, **달력 점도 같은 기준**으로 움직인다. |
| **§9-27 날짜·시간 선택기** | **해결 확인.** 시간 선택기 제목 **"시간 선택"**, 버튼 **"취소" / "확인"**, 표기는 **"오전 10:00"** (영어 "Select time"/"Cancel"/"OK"·"AM/PM" 아님). 날짜 선택기도 **"날짜 선택" / "2026년 11월" / "일 월 화 수 목 금 토" / "취소"·"확인"** 로 한국어. (`/tmp/v28.png`, `/tmp/v29.png`) |
| **정적 검사** | `flutter analyze` → **No issues found**. `flutter test` → **92/92 통과**. |
| **위젯 트리 에러** | **없음.** logcat 에 `EXCEPTION CAUGHT` / `Unhandled exception` 0건. |

**테스트 데이터 정리 (실기 뒤)**

- 코멘트 "r9dup" (`tc_01M6Y6NQRGA17ZHENFWKV5S1EE`) → `DELETE /api/v1/task-comments/{id}` 로 **삭제**.
  → DB 에 남는 코멘트는 **0건**.
- 일정 3건(`round8check` · `tzprobe` · `r8event`), DM 채널 2건은 앞 회차에서 이미 삭제했고,
  태스크 제목은 **"정산 대시보드 화면"** 으로 되돌렸다.
  → 남는 데이터는 **시드 일정 5건 + 시드 태스크 5건** 뿐이다.

**환경 메모 (앱 결함 아님)**

- 앱을 `adb install -r` 로 덮어쓴 직후에는 엔진이 **`Could not prepare isolate` / `Could not create root isolate`**
  로 죽어서 **네이티브 스플래시에서 멈췄다**(logcat 확인). 앱 코드가 아니라 **설치가 깨진 상태**였다.
  → `adb uninstall` 후 재설치하니 정상 기동했다. 앞으로 APK 를 갈아끼울 때는 **언제나 재설치**한다.

---

### 9-29. [MAJOR] 종일 일정이 **이틀에 걸쳐** 보인다 (11월 13일에도 "분기 계획" 이 뜬다) (담당 C)

**실기 확인 (2026-11-09)** — 8차 라운드 검증 중, 11월 12일과 13일을 오가며 보다가 발견했다.

#### 증상

시드 일정 "분기 계획" 은 **`all_day = true`**, `starts_at = 2026-11-12T00:00:00Z`, `ends_at = 2026-11-13T00:00:00Z`
(= **12일 09:00 ~ 13일 09:00 KST**, 백엔드 규약상 **다음 날 자정 직전(= exclusive)**).

그런데 모바일은 이 일정을 **11월 12일에도, 11월 13일에도** 보여준다.

| 화면 | 11월 12일(금) | 11월 13일(토) |
|---|---|---|
| 달력 점 | ● 있음 | **점 없음** |
| 일정 목록 | "분기 계획 / 하루 종일" | **"분기 계획 / 하루 종일"** ← **버그** |

즉 **한 화면 안에서 달력과 목록이 서로 모순**된다(13일에는 점이 없는데 목록에 일정이 있다).
스크린샷 `/tmp/v44.png` (12일) · `/tmp/v45.png` (13일).

#### 원인

`lib/screens/schedule/schedule_screen.dart:104-108` 의 날짜 필터가 **세 가지 조건을 OR** 로 붙인다.

```dart
final onDay = _isSameDay(e.startsAt.toLocal(), selectedDate) ||
    (_isSameDay(e.endsAt.toLocal(), selectedDate) && e.allDay) ||   // ← ①
    (e.startsAt.toLocal().isBefore(selectedDate) && e.endsAt.toLocal().isAfter(selectedDate)); // ← ②
```

- **①** 종일 일정의 `ends_at` 은 **다음 날 자정**(exclusive)이라, 로컬로 바꾸면 **다음 날 09:00** 이 된다.
  → 그 "다음 날" 에도 종일 일정이라고 붙어 버린다.
- **②** "날짜를 가로지르는 일정" 판정도 `startsAt < selectedDate < endsAt` 이므로
  13일 00:00 에 대해 **true** 가 된다.

근데 **달력 점**(`:311`)은 `_isSameDay(e.startsAt.toLocal(), date)` — **시작 날짜만** 본다.
그래서 필터(①②)와 달력 점이 **서로 다른 기준**을 쓰면서 화면이 어긋난다.

#### 데스크톱(참조 구현) 규약

데스크톱은 **시작 날짜로만** 묶는다. 종료일 쪽에 붙이는 로직이 아예 없다.

```ts
// desktop/src/components/ScheduleView.tsx:98-107
const key = dayOf(event.starts_at);   // ← 시작 날짜(로컬)만
```

`dayOf(iso)` = `dateKey(new Date(iso))` = **로컬 날짜** (`desktop/src/lib/calendar.ts:64-66`).
달력 점(`marks`)도 **같은 `byDay` 맵**에서 나오므로 데스크톱에서는 **목록과 점이 절대 어긋나지 않는다.**

#### 해결 (담당 C — `lib/screens/schedule/schedule_screen.dart`)

**날짜 필터를 "시작 날짜" 하나로 통일한다.** (데스크톱과 같게)

- `:104-108` 의 세 조건 OR → `_isSameDay(e.startsAt.toLocal(), selectedDate)` **하나만** 남긴다.
  ①② 를 지우면 목록과 달력 점(`:311`)이 **같은 기준**이 되어 모순이 사라진다.
- `allDay` 여부는 **표시**(카드의 "하루 종일" 문구, `:363`)에만 쓴다 — 날짜 묶기에는 쓰지 않는다.

**주의**

- 종일 일정의 `ends_at` 은 **exclusive(다음 날 자정)** 라는 백엔드 규약은 그대로 둔다.
  (§9-25 의 UTC 규약과 무관 — 이건 "종일" 의 끝을 나타내는 서버 규약이다.)
- **다중 날짜 일정**(예: 12일 09:00 → 15일 18:00) 도 **데스크톱처럼 시작 날짜에만** 표시된다.
  종료 날짜에도 뜨게 하려면 달력 점도 같이 바꿔야 하는데, 그러면 데스크톱과 달라진다.
  → **데스크톱과 같게 시작 날짜만** 하는 것이 규약이다.

#### 테스트

- 위젯 테스트: `starts_at = 2026-11-12T00:00:00Z`, `ends_at = 2026-11-13T00:00:00Z`, `allDay = true` 인 일정이
  - **로컬 11월 12일** 에는 보인다.
  - **로컬 11월 13일** 에는 **보이지 않는다.**
- 위젯 테스트: 달력 점과 목록이 **같은 날짜 집합**을 쓴다(선택 날짜가 11월 13일인데 점이 하나도 없으면 안 된다).
- 회귀: §9-25 의 "UTC 로 저장된 일정은 로컬 날짜 기준으로 카드에 뜬다" 테스트가 **계속 통과**해야 한다.

---

### 9-30. [MINOR] 콜드 스타트 동안 **"Llack 연결 중..." 이 화면에 뜨지 않는다** (담당 C)

**실기 확인 (2026-11-09)** — 앱을 완전히 종료한 뒤 다시 켜면 **네이티브 스플래시(로고 아이콘)** 만
6~8초 떠 있다가 그제야 로그인/메인 화면이 나온다. 그동안 **"연결 중" 진행 표시가 하나도 없다.**

#### 원인

`lib/main.dart:11-24`

```dart
final appState = AppState();
await appState.boot();     // ← 네트워크가 끝날 때까지 여기서 멈춘다
runApp(...);                // ← 그래서 Flutter 프레임이 아예 안 그려진다
```

`boot()` 안에서 `getMe` → `getWorkspaces` → `bootstrap` → `events` → `projects` → `org` 를 **순차로** 부른다
(`lib/providers/app_state.dart:47-79`). 그동안 **첫 프레임이 안 나오니까** 안드로이드 12+ 스플래시
(로고 아이콘)만 보인다.

그런데 `main.dart:49-77` 에 **이미 `state.isBooting` 일 때 "Llack 연결 중..." 스피너 + 문구를 그리는
위젯이 있다.** → `isBooting` 은 `boot()` 이 끝나야 false 가 되는데,
**`runApp` 이 `boot()` 뒤에 호출되므로 이 위젯은 절대로 화면에 나타나지 않는다.** (죽은 코드)

#### 해결 (담당 C — `lib/main.dart`)

**`runApp` 을 먼저 하고, `boot()` 은 그 뒤에 시작한다.**

```dart
final appState = AppState();
runApp(ChangeNotifierProvider.value(value: appState, child: const LlackMobileApp()));
// 부팅은 첫 프레임 이후에 시작한다 → "Llack 연결 중..." 이 바로 보인다
appState.boot();
```

- `_isBooting` 의 초기값이 이미 `true` (`app_state_core.dart:20`) 라므로,
  첫 프레임부터 **"Llack 연결 중..."** 이 보이고 `boot()` 이 끝나면 자동으로 로그인/메인으로 넘어간다.
- `boot()` 내부에서 `_isBooting = true` 로 다시 설정하고 `finally` 에서 false 로 돌리는 구조는 **그대로** 쓴다.

#### 소유권 예외 (이번 회차 한 번만)

`lib/main.dart` 은 §0 규약상 "공통(수정 금지)" 이지만,
이 절은 **C 에이전트에게 `lib/main.dart` 한 파일에 대한 일회성 예외 권한**을 부여한다.
C 는 **`main()` 안에서 `runApp` 과 `boot()` 의 순서만** 바꿔야 하고, 그 파일의 다른 코드는 건드리지 않는다.
(A·B 는 `lib/main.dart` 을 계속 건드리지 않는다.)

#### 테스트

- 위젯 테스트: `AppState` 의 `boot()` 이 끝나기 전 상태로 앱 루트를 pump 하고
  **"Llack 연결 중..."** 이 화면에 보이는지.
- 회귀: `isBooting` 이 끝난 뒤에는 로그인 화면 / 메인 화면으로 넘어가는지.
- 회귀: 기존 92개 테스트가 그대로 통과하는지.

---

### 9-31. 9차 라운드 실기 검증 결과 (2026-11-09, 에뮬레이터 Pixel_7_API_36)

§9-29 · §9-30 을 **실기에서 확인**했다. 디버그 APK → 프록시/프로파일 APK 순으로 검증했다.

#### §9-29 [종일 일정이 이틀에 걸쳐 보인다] — ✅ 해결 확인

| 조작 | 기대 | 실기 결과 | 판정 |
|---|---|---|---|
| 일정 탭 → **11월 12일** | 종일 일정 "분기 계획" 이 보인다 | 카드 1개, "하루 종일" 뱃지 표시 | ✅ |
| 일정 탭 → **11월 13일** | 목록에 **없다** | "11월 13일 금요일 · **0개의 일정**" + "등록된 일정이 없습니다" | ✅ |
| 달력 점 | 12일 ● , 13일 점 없음 | 12일 ● / 13일 없음 → **목록과 점이 같은 기준** | ✅ |

- 수정 전에는 13일에도 "분기 계획" 이 떴고(종료 날짜에 걸림), 달력 점은 12일에만 있었다 → **점이 없는 날에 일정이 뜨는 모순**.
- 수정 후에는 **목록 필터와 달력 점이 같은 술어**(시작 날짜 기준)를 쓴다.
- **profile APK 로도 재확인**했다(디버그와 동일 결과).

#### §9-30 [콜드 스타트 진행 표시가 안 뜬다] — ✅ 해결 확인

| 조작 | 기대 | 실기 결과 | 판정 |
|---|---|---|---|
| 앱 완전 종료(`am force-stop`) → 재시작 | 첫 프레임에 **"Llack 연결 중..."** + 스피너 | **화면에 표시됨** | ✅ |

- 캡처 방법(중요): `adb exec-out screencap` 은 한 장에 0.4~1초가 걸려서 1초 이하 전이 화면은 **절대 못 잡는다**.
  → **백엔드 앞에 3초 지연 TCP 프록시**를 끼워서 콜드 스타트를 늘린 뒤 캡처했다.
  (실제 백엔드를 8001 로 옮기고 8000 에 relay 프록시 → 캡처 후 원복. 반드시 원복할 것.)
- 위젯 테스트는 `main()` 의 **순서**를 검증하지 못한다(`LlackMobileApp` 를 직접 pump).
  → **"화면에 실제로 뜨는가"는 실기로만 확인 가능**하다. 위 표가 그 증거다.

#### 콜드 스타트 시간 측정 (logcat `ActivityTaskManager: Displayed`)

| 빌드 | 첫 프레임까지 | 비고 |
|---|---|---|
| debug | **+6s141ms** | JIT. 매우 느림 |
| profile | **+3s560ms** | AOT. 이것이 현실적인 수치 |

- 그 시간 동안은 **안드로이드 12+ 네이티브 스플래시(로고 아이콘)** 가 보인다.
  Flutter 레벨 "Llack 연결 중..." 화면은 **첫 프레임 이후부터**만 나타난다(구조적으로 inevitable).
- → **네이티브 스플래시 자체는 흰 배경 + 로고로 Flutter 화면과 이어져서 시각적 단절은 없다.** 별도 수정 대상 아님.
- (후보) 실제 기기에서의 콜드 스타트는 1~1.5초로 예상되므로 **추가 최적화는 다음 라운드 후보로 미룬다.**

#### 정적 검사

- `flutter analyze` → **No issues found!**
- `flutter test` → **95/95 All tests passed!** (92 + §9-29 위젯 테스트 1 + §9-30 위젯 테스트 2)

#### 테스트 데이터 정리

- 실기에서 만든 태스크 코멘트 1건은 **삭제 완료**(DB 코멘트 0건).
- 남은 데이터 = **시드 일정 5개 + 시드 태스크 5개**뿐(변조 없음).

#### 환경 메모 (다시 한 번 강조)

- APK 교체는 **항상 `adb uninstall` 후 재설치**. `adb install -r` 로 덮어쓰면 엔진이 안 뜬다.
- 비밀번호 입력: `input text` 는 **키보드가 뜨면서 레이아웃이 밀려** 두 번째 필드 좌표가 틀어진다.
  → **이메일 칸에 다 입력된 뒤 탭이 빗나가면**, 그 자리에서 `keyevent 123`(MOVE_END) → N× `keyevent 67`(DEL) 로 비우고,
  **`keyevent 61`(TAB)** 으로 다음 필드로 넘어가면 좌표 계산이 필요 없다. 이게 가장 안전하다.

---

## 10. 6차 라운드 (2026-11-09, 에뮬레이터 Pixel_7_API_36 실기 — profile APK)

### 9-32. 10차 라운드 실기 발견 요약

이번 라운드에서 손으로 조작하며 확인한 표면:
채널 목록 · 채널 화면(메시지 + 작성 + 키보드) · 스레드 · 일정(세로/가로) · 프로젝트 · 조직도 ·
빠른 검색 · 워크스페이스 전환 · 설정 시트 · 오프라인(백엔드 정지) 상태의 전송 실패 경로.

확인 결과:

| 표면 | 판정 |
|---|---|
| 빠른 검색 ("random" 입력) | ✅ 채널 1건 정확히 일치 ("random" / 잡담과 수다) |
| 오프라인 전송 실패 | ✅ "전송에 실패했습니다. 다시 시도해주세요." + 작성 중인 글자 유지 |
| 연결 복구 | ✅ 백엔드 복귀 후 ~12초 뒤 배너 자동 해제 |
| 일정 상세 시트 버튼 | ✅ 작성자만 수정/삭제 보임 (버튼 잘림 아님 — 오탐) |
| 일정 달력/목록 기준 일치 | ✅ §9-29 재확인 |

아래 3건은 **실제로 결함**이라 판단했다.

### 9-33. [MINOR] 실시간 연결 끊김 배너가 **채널 화면(대화방)에서 보이지 않는다** (담당 C)

#### 증상

백엔드를 정지시킨 뒤:

- 채널 목록(셸)에는 "실시간 연결이 끊어졌습니다: ..." 배너가 보인다. ✅
- 그런데 **채널을 열면 배너가 사라진다**. ❌
  대화방이 실시간 상태를 가장 중요하게 여기는 화면인데, 정작 거기서는 사용자가 오프라인인 줄 모른다.
- 스레드 화면도 마찬가지로 push 된 라우트라서 배너가 가려진다.

#### 원인

- `ConnectionBanner` 는 `MainShell` 의 `body` Column 안에 있다(`lib/screens/main_shell.dart:372`).
- 그런데 채널 화면은 `Navigator.of(context, rootNavigator: true)` 로 **루트** 네비게이터에 push 된다
  (`lib/screens/chat/chat_navigator.dart:24`).
  → 셸은 루트 네비게이터 **아래 계층**이라, push 된 라우트가 셸을 통째로 덮어쓴다. 배너도 같이 가려진다.
- `thread_screen.dart` 도 `Navigator.push` 로 push 되므로 같은 문제다.

#### 요구사항

1. **배너를 공용 위젯으로 분리**한다 → `lib/widgets/connection_banner.dart` (신규 파일, C 소유).
   - `ConnectionBanner` — 현재 동작 그대로(상태바 inset 패딩 포함). 셸에서 사용.
   - `ConnectionBannerStrip` — **상태바 inset 패딩이 없는** 얇은 스트립. 앱바 `bottom` 에 얹는 용도.
   - 두 변형은 "한 번이라도 연결된 적이 있는지" 로직을 **공유**해야 한다.
     두 인스턴스가 따로 들면 "아직 연결 안 됨" vs "연결 끊김" 판정이 서로 달라질 수 있다.
     → 배너 파일 안에서 `private` 한 `ValueNotifier<bool>` 로 관리하고 두 변형이 같이 본다.
2. `lib/screens/main_shell.dart` — `ConnectionBanner` 를 새 파일에서 import 하도록 바꾸되 **동작은 그대로**.
3. `lib/screens/chat/chat_screen.dart` — 앱바 `bottom` 에 `const ConnectionBannerStrip()` 을 넣는다.
   - 앱바는 2곳: "선택된 대화방이 없습니다" 상태(236행 부근), 본 앱바(264행 부근).
   - `lib/screens/chat/thread_screen.dart` 에도 앱바가 있으면 똑같이 넣는다.
4. 스트립은 **앱바 아래**에 붙는다(앱바를 덮지 않는다).
   뒤로 가기 버튼·제목·아바타를 **가리지 않아야 한다**.
5. 문구는 기존 것을 그대로 쓴다.
   - 사유 있음: "실시간 연결이 끊어졌습니다: $reason"
   - 사유 없음: "실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다."

#### 소유권 예외 (이번 회차 한 번만)

`lib/screens/chat/chat_screen.dart` 와 `lib/screens/chat/thread_screen.dart` 는 §0 규약상 **B 소유**다.
이 절은 **C 에이전트에게 이 두 파일에 대한 일회성 예외 권한**을 부여한다.
B 는 이번 회차에 이 파일들을 건드리지 않는다.

#### 테스트

- 위젯 테스트: 채널 화면을 pump 하고, `AppState.connectionError` 를 준 뒤
  **"실시간 연결이 끊어졌습니다" 가 화면에 보이는지** 확인.
- 회귀: 연결 중(오류 없음, 아직 연결된 적 없음)에는 스트립이 **보이지 않아야** 한다.

### 9-34. [MINOR] 가로모드에서 일정 달력 칸이 **너무 커서** 하루 목록이 화면 밖으로 밀린다 (담당 C)

#### 증상

에뮬레이터를 가로모드(2400×1080 px = 914×411 dp)로 돌리면:

- 일정 탭의 달력 한 칸이 약 113dp × 91dp → 6줄 = **545dp**.
- 화면 높이가 411dp 라서 **달력만 가득** 차지하고, 그 아래 "N개의 일정" + 일정 카드 목록은
  **몇 화면 아래로** 밀린다. 한 달을 다 보려면 스크롤이 매우 많이 필요하다.
- 세로모드(411dp 폭)에서는 문제가 없다.

#### 원인

`lib/screens/schedule/schedule_screen.dart:297-300`

```dart
gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
  crossAxisCount: 7,
  childAspectRatio: 1.25,   // ← 폭에 따라 높이가 같이 커진다
),
```

가로모드에서는 폰도 `FormFactor.isPad`(폭 ≥ 650dp)가 되어 **태블릿 레이아웃**(좌측 레일 72dp + 일정 화면)을 쓴다.
일정 화면 폭이 약 840dp 가 되면서 칸 폭이 커지고, `childAspectRatio` 탓에 **높이도 같이** 커진다.

#### 요구사항

1. **칸 높이를 고정**한다. `childAspectRatio` 를 버리고 `mainAxisExtent: 44`(dp) 를 쓴다.
   - 세로모드에서 지금 높이는 (411 − 32 − 16) ÷ 7 ≈ 52dp 폭 ÷ 1.25 ≈ **41.6dp** 이므로,
     44dp 로 바꿔도 **시각적으로 거의 동일**하다(리그레션 없음).
   - 가로모드에서도 6줄 = **264dp 로 고정**되어 화면을 넘지 않는다.
2. 가로모드(= `MediaQuery.sizeOf(context).width >= 650`)에서는 **달력과 하루 목록을 2단**으로 배치한다.
   - 왼쪽: 월 카드 (폭 고정 360dp)
   - 오른쪽: 선택 날짜 제목 + "N개의 일정" + 일정 카드 목록 (`Expanded`)
   - 양쪽은 각각 세로 스크롤된다.
3. 세로모드 레이아웃은 **지금과 동일**하게 둔다.
4. FAB("새 일정") 와 "내 일정만" 필터, 탭 제목/표시는 그대로 동작해야 한다.

#### 테스트

- 위젯 테스트: 폭 900dp 로 pump 했을 때 달력 칸 높이가 **44dp 로 제한**되는지(= 달력 전체 높이가 6×44 + 헤더 이하인지).
- 회귀: 폭 411dp(세로)에서 달력 1줄 높이가 이전과 같은 수준(40~46dp)인지.

### 9-35. [MINOR] 참석자 목록의 "나" 라벨이 **의미 불명**이다 (담당 C)

#### 증상

일정 상세 시트의 참석자 목록에서 자기 자신 옆에 초록색 `나` 라벨이 **떠 있는 텍스트**로 붙는다.
RSVP 배지(참석/미정/불참)와 나란히 놓여서, 이것이 무엇을 뜻하는지 알 수 없다.
("내가 참석 상태를 바꾸었다"는 뜻인지, "이 사람이 나"라는 뜻인지 헷갈린다.)

#### 요구사항

`lib/screens/schedule/event_detail_sheet.dart:175-178` 의 `Text('나')` 를 **작은 pill 배지**로 바꾼다.

- **조직도 화면의 '나' 배지(`lib/screens/org/org_screen.dart:233-245`)와 완전히 같은 스타일**로 만든다.
  (앱 안에서 두 곳의 '나' 표시가 달라지면 안 된다. 조직도에 이미 있는 형태가 정답이다.)
  ```dart
  Container(
    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
    decoration: BoxDecoration(
      color: LlackColors.accentSoft,
      borderRadius: BorderRadius.circular(4),
    ),
    child: Text(
      '나',
      style: theme.textTheme.labelSmall?.copyWith(
        color: LlackColors.accentDeep,
        fontWeight: FontWeight.w700,
      ),
    ),
  )
  ```
  여기에 `Tooltip(message: '나 (본인)')` 을 감싼다.
- **위치**: 이름 **옆**(바로 뒤)에 둔다. 즉 `김현진 [나]  ............  [참석]`.
  - 구현 시 주의: 이름을 `Flexible` 로 감싸고 배지를 **바깥 형제**로 두면,
    배지가 이름이 아니라 **행의 가운데**에 뜰 수 있다(Flexible 슬롯이 넓게 잡히므로).
    → 이름과 배지를 **같은 Row 안에 묶고**(그 Row 만 `Flexible`),
    RSVP 배지는 `Spacer` 뒤로 보내는 편이 안전하다.
  RSVP 배지는 오른쪽 끝에 그대로 둔다. 지금처럼 오른쪽 끝에 나란히 붙이면 또 헷갈린다.
- RSVP 배지(`_ResponseBadge`) 는 그대로 둔다.

#### 테스트

- 위젯 테스트: 자기 자신이 참석자로 포함된 일정 상세 시트를 pump 하고
  "나" 라벨이 **이름 뒤쪽**에 있는지(= 이름 Text 와 배지의 순서) 확인.

### 9-36. [MAJOR] 화면을 **회전하면 달력의 달과 선택된 날짜가 어긋난다** (담당 C)

#### 증상 (실기 확인, 2026-11-09)

에뮬레이터를 세로 → 가로 → 세로로 돌리는 동안 다음 상태가 그대로 남는다.

| 항목 | 화면에 보이는 값 |
|---|---|
| 달력 제목 | **2026년 11월** |
| 달력에서 선택된 칸 | **없음** (어느 칸도 초록으로 강조되지 않는다) |
| 목록 제목 | **12월 1일 화요일 · 0개의 일정** |

즉 **"11월 달력" 아래에 "12월 1일" 목록이 나온다.**
달력과 목록이 서로 다른 달을 가리키는, §9-29 와 같은 종류의 모순이다.

#### 재현 순서

1. 일정 탭에서 **다음 달(>)** 을 눌러 12월로 이동한다 → 목록은 "12월 1일", 달력은 "2026년 12월".
2. 기기를 **회전**한다(가로모드).
3. 다시 **세로모드**로 돌아온다.
4. → 달력은 "2026년 11월"(=현재 월)로 되돌아가 있지만, 목록은 여전히 "12월 1일".

#### 원인

- `_viewMonth` 은 `ScheduleScreen` 의 **로컬 위젯 상태**(`schedule_screen.dart:23`)이고,
  선택 날짜는 **AppState 의 전역 상태**(`app_state_core.dart:81`)다. **둘이 따로 관리된다.**
- 가로모드(폰 가로 = 폭 914dp ≥ 650dp)에서는 `FormFactor.isPad` 가 되어
  `main_shell.dart` 의 **태블릿 레이아웃**으로 바뀐다. 그때 일정 화면이
  `ScheduleScreen(showCommonActions: false)` 로 **새 위젯**이 되고, 기존 element 가 교체되면서
  **State 가 새로 만들어진다** → `initState()` 에서 `_viewMonth = DateTime(now.year, now.month, 1)`
  로 **현재 월(11월)** 로 초기화된다.
- 그런데 `state.selectedDate` 는 AppState 에 남아서 **12월 1일** 이 유지된다.
  → 달력(11월)과 목록(12월 1일)이 어긋난다.

#### 요구사항

**선택 날짜가 달력의 달을 단일 소스로 삼게 한다.**

1. `_viewMonth` 로컬 상태를 **삭제**하고, 표시할 달을
   `DateTime(state.selectedDate.year, state.selectedDate.month, 1)` 로 **파생**한다.
   - `setSelectedDate` 의 호출처는 `schedule_screen.dart` 의 두 곳뿐
     (`_shiftMonth` 과 날짜 칸 탭)이라 **동작 변화가 없다**.
     - `_shiftMonth(+1)` → `selectedDate` = 다음 달 1일 → 달력도 다음 달 ✓
     - 날짜 칸 탭 → `selectedDate` = 그 날짜 → 달력도 그 달 ✓
   - 회전/레이아웃 변경으로 State 가 재생성되어도 **항상 일치**한다(버그 자체가 사라진다).
2. `_shiftMonth` 은 `state.setSelectedDate(next)` 만 호출한다(두 값을 따로 관리하지 않는다).
3. **회귀 테스트**: `selectedDate` 가 다른 달인 상태에서 화면을 다시 만들었을 때
   달력 제목이 `selectedDate` 의 달과 같고, 그 달의 선택된 칸이 강조되는지 확인.

#### 부수 확인 (같은 회차에 함께 볼 것)

- 회전 후에도 **"오늘" 강조**는 현재 월 기준으로 정상인가? (달력 칸 강조 = `isToday` ✓)
- 회전 후에도 **목록/달력 점 기준**(시작 날짜, §9-29)이 유지되는가? ✓ (같은 술어 사용)

### 9-37. 10차 라운드(계속) — 추가로 손으로 확인한 표면

| 조작 | 기대 | 실기 결과 | 판정 |
|---|---|---|---|
| **가로모드 → 설정 시트** | 항목 잘림/overflow 없음 | 프로필·상태 칩·서버 주소·로그아웃 모두 보임, 잘림 없음 | ✅ |
| **프로젝트 탭 → 프로젝트 드롭다운** | 다른 프로젝트로 전환 | 3개 목록(결제 시스템 개편 / 디자인 시스템 v2 / 사내 공동 라이브러리) 정상 표시 | ✅ |
| **프로젝트 탭 → 태스크 카드 탭** | 상세 시트 열림 | 상태 드롭다운·제목·담당자·의견 입력창 정상, 키보드 올라올 때 입력창이 키보드 위로 밀림 | ✅ |
| **채널 화면 → 메시지 길게 누르기** | 액션 시트 | 반응 이모지 6종 + 스레드 답글 + 인라인 답글 + 고정 + 복사 | ✅ (내 메시지는 수정/삭제 추가됨) |
| **스레드 화면** | 루트 메시지 + 답글 + 입력창 | 정상 | ✅ |
| **조직도 탭** | 부서 트리 + 멤버 목록 | 5명 전원 표시, DM 버튼 정상, **자기 자신은 '나' 배지(pill)** 표시 | ✅ |
| **검색 "random"** | 채널 1건 | "random / 잡담과 수다" 정확히 1건 | ✅ |

- 여기서 나온 **'나' 배지가 조직도에는 이미 pill 형태(accentSoft 배경 + accentDeep 글자)로 구현되어 있다**는 것을 확인했다.
  → §9-35 는 이벤트 상세 시트의 `Text('나')` 를 **이 pill 과 똑같은 모양**으로 바꾸라는 요구로 확정한다.
  (같은 의미의 표시가 앱 안에서 두 가지 모양으로 보이면 안 된다.)

### 9-38. [MINOR] 기기를 **회전하면 프로젝트 상태 필터 탭이 초기화**된다 (담당 C)

#### 증상 (실기 확인, 2026-11-09)

1. 프로젝트 탭 → 상태 필터 **"진행 중 (2)"** 선택 → 태스크 2개 표시 ✓
2. 기기를 **회전**(가로 → 세로)한다.
3. → 필터가 **"요청 (1)"** 로 되돌아가고, 목록도 "요청" 태스크로 바뀐다.

사용자가 골라둔 필터가 회전 한 번으로 사라진다.

#### 원인

- 상태 필터 탭은 `_ProjectsScreenState` 의 **로컬 `TabController`**(`projects_screen.dart:25`)가 들고 있다.
- 회전하면 폰↔태블릿 레이아웃이 전환되며 `ProjectsScreen` element 가 교체 → **State 재생성** →
  `initState` 에서 `TabController(length: 4)` 로 새로 만들어 **인덱스 0** 부터 시작한다.
- 반면 **선택한 프로젝트**(`state.activeProject`)와 **로드맵 필터**(`state.selectedRoadmapId`)는
  AppState 에 있어 **유지된다** → 필터만 초기화되어 부분적으로 리셋된다.

(§9-36 과 같은 원인: **로컬 위젯 상태 vs 전역 상태**의 분리.)

#### 요구사항

1. 상태 필터 인덱스를 **화면 State 밖**에 보관해 회전에도 살아남게 한다.
   - 권장: `projects_screen.dart` 안에 파일 레벨 `ValueNotifier<int>` 하나 두고 공유한다.
     (`connection_banner.dart` 의 `_hasEverConnected` 와 같은 방식. 다른 에이전트 파일을 건드리지 않는다.)
   - `initState` 에서 `TabController(length: 4, initialIndex: <저장된 값>)` 로 만들고,
     탭이 바뀔 때 저장된 값을 갱신한다.
   - **AppState(`lib/providers/*`) 는 건드리지 않는다.** (A 소유 파일)
2. 프로젝트 전환/로드맵 필터와 **여전히 함께 동작**해야 한다
   (프로젝트를 바꾸면 상태 필터는 유지되는지 확인 — 데스크톱 동작에 맞춰 정한다).
3. 앱을 **완전 종료 후 재시작**하면 필터가 0(요청)으로 시작하는 것은 지금과 같아도 된다.

#### 테스트

- 위젯 테스트: 상태 필터를 "진행 중" 으로 바꾼 뒤 **화면을 다시 만들어도**(새 State) 같은 탭이 선택되어 있는가.

---

### 9-39. 11차 라운드 실기 검증 결과 (2026-11-09, profile APK · 에뮬레이터 Pixel_7_API_36)

대상 APK: `build/app/outputs/flutter-apk/app-profile.apk` (104.1MB) — `adb uninstall` 후 재설치.
계정: hyunjin@hanbit.co.kr (김현진). 백엔드: `127.0.0.1:8000` (uvicorn, 앱 기준 `http://10.0.2.2:8000`).

| # | 항목 | 손으로 한 조작 | 기대 | 실기 결과 | 판정 |
|---|---|---|---|---|---|
| §9-33 | 실시간 연결 끊김 배너가 채널 화면에서 안 보임 | `# general` 채널을 **루트 네비게이터로 push** 한 상태에서 백엔드(pid) 종료 | 대화방 앱바 **아래**에 스트립이 뜨고, 뒤로가기/제목/채널 주제를 가리지 않는다 | `☁ 실시간 연결이 끊어졌습니다: 서버에 연결할 수 없습니다.` 가 앱바 바로 아래 한 줄 스트립으로 표시됨. 뒤로가기 버튼·`# general` 제목·`팀 전체 공지와 일상적인 이야기` 주제가 모두 그대로 보임 | ✅ |
| §9-33 | (동일 화면) 스레드 화면 | `답글 2개` 를 눌러 스레드로 이동 | 스레드 앱바 아래에도 같은 스트립 | 스레드 앱바(`스레드 답글 / 박지민님의 메시지`) 아래에 동일 스트립 표시 | ✅ |
| §9-33 | (복구) 배너 사라짐 | 백엔드 재기동 후 대기 | 스트립이 사라지고 빈 여백도 남지 않는다 | 재기동 후 스트립 자동 소멸, 앱바 아래 빈 공간 없이 원래 레이아웃으로 복귀 (스크롤 영역이 그대로 이어짐) | ✅ |
| §9-34 | 가로모드에서 달력 칸이 너무 큼 | 가로모드 전환 | 달력 칸 높이가 폭과 무관하게 고정되고, 화면이 2단(달력 \| 일정 목록)으로 나뉜다 | 가로모드에서 **왼쪽 360dp 달력 카드 + 오른쪽 날짜 목록** 2단 배치로 전환됨. 칸 높이 = 44dp 로 고정(줄 간격 실측 116px @2.63x = 44dp) | ✅ |
| §9-35 | 참석자 목록의 "나" 라벨 | `주간 스탠드업`(참석자 5명, 내가 포함) 상세 시트 | 이름 **바로 뒤**에 pill 이 붙고, RSVP 배지는 오른쪽 끝 | `김현진 [나] .......... 참석` — pill 이 이름에 붙어 있고 RSVP 배지는 `Spacer` 로 오른쪽에 밀려 있음. 다른 참석자(박지민/이채원/최수아/정우진)에는 pill 이 없음 | ✅ |
| §9-36 | 회전하면 달력의 달과 선택 날짜가 어긋남 | 11월 → `>` 로 12월 이동 → **가로모드** → **세로모드 복귀** | 달력 제목·선택 칸·목록이 모두 12월로 유지 | 세로→가로→세로 왕복 후에도 달력 제목 `2026년 12월`, 1일 칸 강조, 목록 `12월 1일 화요일` 로 **모두 일치**. (수정 전에는 달력 11월 / 목록 12월 1일 로 어긋남) | ✅ |
| §9-38 | 회전하면 프로젝트 상태 필터 탭이 초기화 | 프로젝트 탭 → `진행 중 (2)` 선택 → **가로모드** → **세로모드 복귀** | 필터가 유지된다 | 복귀 후에도 `진행 중 (2)` 탭이 선택되어 있고, 목록 2건(`결제 도메인 모델 초안`, `PG사 샌드박스 연동`)이 그대로 보임 | ✅ |

#### 검증 중 함께 확인한 회귀 없음

- 일정 화면 세로모드: 달력 칸 높이 44dp 는 기존(≈41.6dp)과 시각 차가 거의 없고, `8/9/11/12/15` 일의 일정 점과 선택 강조가 그대로 유지됨.
- 가로모드 2단 배치에서 달력 카드와 날짜 목록이 **각각 독립 스크롤**됨(달력 카드 폭 360dp 고정).
- 프로젝트 탭 필터 유지와 함께, **프로젝트 전환 드롭다운**(결제 시스템 개편 / 디자인 시스템 v2 / 사내 공동 라이브러리)도 정상 동작.
- 로그인 → 메시지 → 일정 → 프로젝트 → 조직도 전 탭 왕복 중 크래시·오버플로우 없음.

#### 재현 방법 (다음 라운드 재현용)

```bash
# 백엔드만 죽여서 "연결 끊김" 을 만든다 (앱은 살아 있다)
kill $(lsof -ti tcp:8000)
# → # general 채널을 열어둔 채 캡처 → 배너 스트립 확인
# 되돌리기
cd backend && .venv/bin/python .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
```

- 회전은 `adb shell settings put system accelerometer_rotation 0` 후 `user_rotation 1`(가로)/`0`(세로).
  **작업이 끝나면 `accelerometer_rotation 1` 로 복원**한다.

### 9-40. [MINOR] 이름 옆 "나" 배지가 있는 행에서만 **오른쪽 배지 열이 어긋난다** (담당 C)

#### 증상 (실기 확인, 2026-11-09 · profile APK)

**일정 상세 시트 → 참석자 목록** (`주간 스탠드업`, 참석자 5명):

```
김현진 [나]              참석      ← 배지가 오른쪽으로 밀려 있다
박지민              미정
이채원              불참
최수아              참석
정우진              미정
```

- RSVP 배지가 **모두 같은 x 에 정렬되어 있지 않다.** "나" pill 이 있는 김현진 행의 배지만
  pill 폭만큼(~16dp) 오른쪽으로 밀려 있다.
- 게다가 배지가 **행의 오른쪽 끝에 붙지 않는다.** 시트 내용 영역의 오른쪽 끝까지
  **약 112dp 의 빈 공간**이 남아 있다(배지가 화면 가운데쯤에 떠 있다).

**조직도 → 전체 구성원** 에도 같은 문제가 있다.

```
김현진 [나]                  소유자
박지민              멤버
이채원              멤버
최수아              멤버
```

- "소유자"/"멤버" 라벨이 오른쪽 끝에 붙지 않고, "나" pill 이 있는 행만 위치가 다르다.

#### 원인

두 화면 모두 한 줄을 이렇게 짜고 있다.

```dart
Row(
  children: [
    Flexible(child: Text(name, overflow: TextOverflow.ellipsis)),  // ← flex: 1 (기본값)
    if (isMe) ...[ SizedBox(width: 6), 나 pill ],
    const Spacer(),                                               // ← flex: 1
    <오른쪽에 붙일 배지>,
  ],
)
```

- `Flexible` 의 **기본 flex 는 1** 이고 `Spacer` 도 flex 1 이다.
- Flutter 의 `RenderFlex` 는 남은 공간을 **flex 비율로 나눠 가진다** → 남은 공간의
  **절반씩** `Flexible(이름)` 과 `Spacer` 에 준다.
- `Flexible(fit: loose)` 이므로 이름 `Text` 는 자기 크기만큼만 차지하고(할당된 상한만 큼),
  **`Spacer` 가 "오른쪽 끝으로 밀어줄" 공간을 절반밖에 못 받는다.**
  → 오른쪽 배지가 오른쪽 끝이 아니라 **가운데쯤**에 붙는다.
- "나" pill 이 있는 행은 pill 이 추가로 공간을 먹으므로 그만큼 더 밀린다 →
  **행마다 배지 열이 어긋난다.**

> 같은 패턴이 `projects_screen.dart:396` 에도 있다(`Spacer` + `Flexible(로드맵 칩)`).
> 현재는 로드맵 이름이 붙은 태스크가 없어 **눈에 보지 않지만** 같은 잠재 결함이다.

#### 요구사항

1. **오른쪽 배지는 행의 오른쪽 끝에 붙어야 하고, 모든 행이 같은 열에 정렬되어야 한다.**
   (이름 옆 "나" pill 이 있는 행도 예외가 아니다.)
2. "나" pill 은 **이름 바로 뒤**에 그대로 붙어 있어야 한다(§9-35 유지).
3. 이름이 길면 **말줄임**되되, 오른쪽 배지가 화면 밖으로 밀려 **overflow 가 나면 안 된다.**
   (지금처럼 `Flexible` + `Spacer` 를 나란히 두면 이름이 길 때 배지가 밀릴 수 있다.)
4. `lib/providers/*`, `lib/main.dart`, `lib/screens/chat/*` 는 건드리지 않는다. (A/B 소유 파일)
5. 가능하면 **세 군데(`event_detail_sheet.dart`, `org_screen.dart`, `projects_screen.dart`)를 같은 방식으로** 고친다.
   - `projects_screen.dart` 의 로드맵 칩은 **오른쪽 끝**에 붙도록 한다.

#### 권장 구현

이름+pill 묶음을 하나의 `Expanded` 안에 넣고, 오른쪽 배지는 그 밖으로 뺀다.

```dart
Row(
  children: [
    Expanded(
      child: Row(
        mainAxisSize: MainAxisSize.min,      // 이름 + pill 묶음은 자기 크기만큼
        children: [
          Flexible(child: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis)),
          if (isMe) ...[ const SizedBox(width: 6), 나 pill ],
        ],
      ),
    ),
    오른쪽 배지,   // Expanded 밖이므로 항상 오른쪽 끝에 붙는다
  ],
)
```

- 안쪽 `Row(mainAxisSize: min)` 안에서 `Flexible(Text)` 이 남은 폭의 상한을 받으므로
  **긴 이름은 말줄임**되고, pill 은 이름 바로 뒤에 붙는다.
- 바깥 `Expanded` 가 남는 폭을 모두 가져가므로 **오른쪽 배지는 항상 오른쪽 끝**에 붙는다.

#### 테스트

- 위젯 테스트: 참석자 목록에서 **모든 행의 RSVP 배지 오른쪽 x 좌표가 같다**가 아니라
  **행의 오른쪽 끝(폭 - padding)에 정렬**되어 있고, **"나" 행도 다른 행과 같은 열**인지 확인.
- 위젯 테스트: 이름이 아주 긴 멤버가 있어도 **overflow 가 나지 않고** 배지가 화면 안에 있는가.

---

## 12차 라운드 실기 검증 결과 (2026-11-09 · profile APK · 에뮬레이터 Pixel_7_API_36)

### §9-40 검증 — 오른쪽 배지 열 정렬

| 대상 | 확인 방법 | 결과 | 판정 |
|---|---|---|---|
| 일정 상세 시트 · 참석자 목록 | `1:1 (김현진 ↔ 최수아)` 시트 → `김현진 [나] ␣ 참석` / `최수아 ␣ 불참` 두 행 | 두 배지의 오른쪽 끝이 **모두 x=842(표시 좌표)** 로 동일. "나" pill 은 이름 바로 뒤 | ✅ |
| 일정 상세 시트 · 긴 이름 | 동일 시트 (참석자 2명) | 말줄임·오버플로 없음, 배지 화면 안 | ✅ |
| 조직도 · 전체 구성원 | `김현진 [나] ␣ 소유자` / `박지민 ␣ 멤버` / `이채원 ␣ 멤버` / `최수아 ␣ 멤버` | "소유자"와 "멤버" 라벨의 오른쪽 끝이 **모두 x=672** 로 동일 | ✅ |
| 프로젝트 · 태스크 카드 (로드맵 칩) | 로드맵 2개를 만들어 붙인 뒤 카드 2장 비교 | 두 카드의 칩 오른쪽 끝이 **모두 x=842** 로 동일. 이름이 길어지면 칩이 **왼쪽으로** 늘어나 오른쪽 끝을 유지 | ✅ |
| 프로젝트 · 로드맵 필터 칩 | `모든 카드 / 1분기 목표 / 2분기 목표` | 가로 스크롤로 정상 동작 | ✅ |

> 로드맵 데이터가 시드 DB 에 없어, 검증용으로 `roadmaps` 테이블에 직접 2개를 넣고
> `tasks.roadmap_id` 를 채워 확인했다(검증 후 정리).

#### 함께 확인한 회귀 없음

- 일정 탭 · 조직도 탭 · 프로젝트 탭 왕복 중 크래시 없음.
- 일정 달력의 `내 일정`(초록)/`팀 일정`(회색) 점 구분 정상 (1:1 은 초록).
- 가로모드(914dp)에서도 태스크 카드의 로드맵 칩이 같은 열에 정렬됨.

### §9-40 구현 메모 (담당 C 가 보고한 내용, 채택)

- 세 곳 모두 `Row[ Expanded(Row(min)[ Flexible(이름), 나 pill ]), 오른쪽 배지 ]` 로 통일.
- **추가 발견**: 조직도에서 자기 자신 행은 `trailing`(DM 버튼)이 없어 `ListTile` 제목 폭이
  다른 행보다 넓어 → 역할 라벨 열이 어긋나던 것이 진짜 원인이었다.
  `Spacer` 제거만으로는 해결되지 않아 `trailing` 자릿수까지 48dp 로 맞췄다.
- 회귀 테스트 `test/row_badge_alignment_test.dart` 2건 추가(배지 우측 x 동일 + 우측 끝 정렬,
  긴 이름에서 예외 없음). 되돌리면 `Expected: 269.5 / Actual: 283.25` 로 실패함을 역검증.
- `flutter analyze` → No issues found / `flutter test` → **106 passed**.

### 그 밖에 확인한 것

- **메시지 삭제 → "실행 취소"(undo) 는 정상 동작한다.** (이전 라운드에서 실패로 보인 것은
  스낵바가 이미 자동 소멸한 뒤 탭이 도착한 것이었다.)
  백엔드 로그로 `DELETE /api/v1/messages/{id} 204` → `POST /api/v1/messages/{id}/restore 200 OK`
  를 확인했고, 기기에서도 삭제 직후 스낵바의 "실행 취소" 를 누르니 메시지가 되살아났다.
  다만 이 과정에서 **되돌릴 수 없는 삭제가 감지된 시점부터 5초 만에 취소창이 사라진다**는
  불편을 그대로 느꼈다 → §9-42.

---

### 9-41. [MAJOR] 긴 로드맵 이름이 있으면 **태스크 카드가 깨진다** (담당 C)

#### 증상 (실기 확인, 2026-11-09 · profile APK)

프로젝트 탭 → `진행 중 (2)` → 로드맵 이름이 긴 카드가 있는 경우:

```
┌──────────────────────────────────────────┐
│ PG사 샌드박스 연동                       │
│ 이니시스 테스트 가이드로 붙여 봅니다.      │
│ ████████████████████████████████████████ │  ← 로드맵 칩이 카드 밖까지 뻗는다
│ (이채원 · 11.14 · 댓글수 가 사라짐)      │
└──────────────────────────────────────────┘
```

- 로드맵 칩이 **카드의 오른쪽 경계를 넘어 화면 끝까지** 그려진다(카드 밖으로 넘침).
  카드 테두리가 칩 뒤로 숨겨진다.
- 더 중요한 것은 **왼쪽 정보가 통째로 사라진다**는 것이다.
  아바타·담당자 이름·마감일·댓글수가 **한 개도 보이지 않는다.**
- 세로모드/가로모드 **둘 다** 재현한다.

#### 원인

`lib/screens/projects/projects_screen.dart` 의 태스크 카드 메타 `Row`:

```dart
Row(
  children: [
    Expanded(child: Row(mainAxisSize: min, children: [ ...담당자·마감일·댓글수... ])),
    if (task.roadmapName != null)
      Container(                       // ← 이 칩이 flex 가 아니다
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(color: LlackColors.surfaceWell, borderRadius: ...),
        child: Text(task.roadmapName!, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
  ],
)
```

- Flutter 의 `RenderFlex` 는 **flex 가 아닌 자식**을 배치할 때 주축(가로) 제약을
  `maxWidth: infinity` 로 준다 → 칩이 **자기 크기(고유 길이) 그대로** 잡힌다.
- 그러면 `Expanded` 로 왼쪽 정보를 넣은 자식에는 **남는 폭이 0** 이 배정되어
  담당자·마감일·댓글수가 전부 사라진다.
- `Card` 는 기본적으로 자식을 잘라내지 않으므로, 넘친 칩이 **카드 밖으로 그려진다.**
- `Text` 에 `overflow: ellipsis` 가 있어도 **폭 제한이 없으면** 줄바꿈 대신 그냥 그려진다.
  (ellipsis 는 제약이 있을 때에만 동작한다)

> **§9-40 의 회귀가 아니다.** 이전 `Spacer` + `Flexible(칩)` 구조에서도 칩이 flex 가 아니었다.
> 다만 §9-40 이후에도 남아 있던 **잠재 결함**이며, 로드맵 데이터가 시드 DB 에 없어
> 아무도 눈치채지 못한 상태였다.

#### 참고: 상세 시트는 안전하다

`lib/screens/projects/task_detail_sheet.dart:206` 은 이미 칩을 `Flexible` 로 감싸고 있어
길이 제한 안에서 말줄임된다. **카드(`projects_screen.dart`)만 안전하지 않다.**

#### 요구사항

1. 로드맵 이름이 아무리 길어도 **카드 밖으로 넘치면 안 된다.**
2. **담당자 아바타·이름·마감일·댓글수는 항상 보여야 한다**(길이 때문에 사라지면 안 된다).
3. 칩은 **여전히 행의 오른쪽 끝에 붙어 있어야 한다**(§9-40 유지).
4. 칩의 글자가 길면 **말줄임**(ellipsis) 처리되어야 한다.
5. `lib/providers/*`, `lib/main.dart`, `lib/screens/chat/*` 는 건드리지 않는다.
6. `task_detail_sheet.dart` 는 이미 안전하므로 건드릴 필요 없다(선택).

#### 권장 구현

칩이 flex 자식이 아니라는 점이 문제이므로, **칩의 폭에 상한을 걸어서** 오른쪽 끝을 유지한다.

```dart
LayoutBuilder(
  builder: (context, c) => Row(
    children: [
      Expanded(child: Row(mainAxisSize: MainAxisSize.min, children: [ ...왼쪽 정보... ])),
      if (task.roadmapName != null)
        ConstrainedBox(
          constraints: BoxConstraints(maxWidth: c.maxWidth * 0.4),   // 행 폭의 40% 이내
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: LlackColors.surfaceWell, borderRadius: BorderRadius.circular(4)),
            child: Text(task.roadmapName!, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ),
    ],
  ),
),
```

- `LayoutBuilder` 로 **행의 실제 폭**을 알아야 백분율 제한이 정확히 먹는다.
- (고정 dp 로 자르는 방법도 가능하지만, 태블릿(가로모드)에서는 쓸데없이 좁아진다.)
- `ConstrainedBox` 안에서는 폭이 제한되므로 `Text` 의 `ellipsis` 가 실제로 동작한다.

#### 테스트

- 위젯 테스트: 로드맵 이름이 **아주 긴** 태스크 카드가 렌더될 때
  ① 예외가 나지 않는다(`tester.takeException()` 이 null),
  ② **담당자 이름이 여전히 보인다**,
  ③ 칩의 오른쪽 끝이 카드 내용 영역의 오른쪽 끝에 정렬되어 있다.
- 위젯 테스트: 로드맵 칩이 있는 카드와 없는 카드의 **왼쪽 정보 시작 x 가 같다**.

---

### 9-42. [MINOR] 메시지 삭제 "실행 취소" 스낵바가 **5초 만에 사라진다** (담당 B)

#### 증상 (실기 확인, 2026-11-09 · profile APK)

DM 에서 메시지를 길게 누르고 `메시지 삭제` → 스낵바 `메시지를 삭제했습니다 / 실행 취소` 가 뜨지만,
**5초 후 사라진다.**

- 실기 테스트 중 "실행 취소" 를 누르려 했는데 이미 사라져 있었고, 삭제 자체는 되돌릴 수 없어졌다.
- 되돌리는 기능 자체는 정상이다(§12차 검증 참고: `restore` API 200 OK, 기기에서도 복구 확인).
  문제는 **되돌릴 수 있는 시간이 너무 짧다**는 것이다.
- 파괴적인 작업(메시지 삭제)의 취소 창을 5초만 주는 것은 사람이 "아, 실수다" 하고
  눈을 돌리는 시간에 비해 너무 짧다.

#### 원인

`lib/screens/chat/message_actions.dart` 의 `buildDeleteSnackBar`:

```dart
SnackBar(
  content: const Text('메시지를 삭제했습니다'),
  duration: const Duration(seconds: 5),   // ← 5초
  persist: false,
  action: SnackBarAction(label: '실행 취소', onPressed: onUndo),
)
```

Material Design 가이드라인은 **액션이 붙은 스낵바를 10초** 띄우라고 한다.

#### 요구사항

1. 삭제 스낵바의 유지 시간을 **10초**로 늘린다.
2. `persist: false` 는 유지(스낵바가 화면을 막고 있으면 안 된다).
3. `lib/providers/*`, `lib/main.dart`, `lib/screens/chat/*` 밖은 건드리지 않는다.
4. 복구 실패 시 "메시지를 복구하지 못했습니다" 스낵바도 같은 방식으로 동작하는지 확인.

#### 테스트

- 위젯 테스트: `buildDeleteSnackBar` 의 `duration` 이 **10초 이상**인지 확인.
- (가능하면) 스낵바가 10초 뒤까지 살아 있고, 그 전에 `onUndo` 를 누르면 동작하는지 확인.

---

## 13차 라운드 실기 검증 결과 (2026-11-09 · profile APK · 에뮬레이터 Pixel_7_API_36)

두 항목(§9-41 · §9-42)을 한 번의 프로필 APK 빌드로 묶어서 실기 검증했다.

- 빌드: `flutter build apk --profile` → `build/app/outputs/flutter-apk/app-profile.apk` (104.2MB)
- 설치: `adb install -r` (로그인 세션 유지) → `am start -n com.hanbit.llack.llack_mobile/.MainActivity`
  - 참고: `monkey -p … -c android.intent.category.LAUNCHER 1` 은 이 기기에서 `VM exiting with result code -5`
    (액티비티 없음)로 앱을 띄우지 못했다. `am start -n <pkg>/.MainActivity` 로 띄우면 된다.
- 계정: hyunjin@hanbit.co.kr · 백엔드 `127.0.0.1:8000` (앱은 `http://10.0.2.2:8000`)

### §9-41 검증 — 긴 로드맵 이름이 카드 안에서 말줄임된다

DB 에 테스트 로드맵 2개를 직접 심었다(실기에서 이 경로가 원래는 비어 있었음).

| 로드맵 id | 이름 |
|---|---|
| `rdm_01M6WWTESTAAA001` | `1분기 목표` |
| `rdm_01M6WWTESTAAA002` | `2분기 목표 아주나아주나주나…` (80자 → DB 컬럼 `VARCHAR(120)`) |

할 일 5개에 `tasks.roadmap_id` 를 붙여서 진행 중 탭에 긴 이름이 걸린 카드를 만들었다.

**세로모드 (411dp)** — 진행 중 탭 `PG사 샌드박스 연동` 카드:

| 항목 | 결과 |
|---|---|
| 칩 | `2분기 목표 아주나아주나주…` — **카드 안에서 말줄임**, 카드 밖으로 넘치지 않음 |
| 담당자 | `이채원` **보임** |
| 마감일 | `11.14` **보임** |
| 칩 정렬 | 카드 내부 오른쪽 끝에 붙음 (짧은 `1분기 목표` 칩과 오른쪽 끝 x 동일) |
| 렌더 오버플로 | 없음 (카드를 벗어나 그려진 부분 없음) |

**가로모드 (태블릿 레이아웃)** — 40% 상한이 과도하게 좁아 보이지 않는지 확인:

- 행 폭이 넓어지므로 40% 상한도 같이 넓어진다. 칩에 **더 많은 글자가 보이고**(`2분기 목표 아주나아주나주나주…`)
  여전히 말줄임 + 오른쪽 끝 정렬이 유지된다.
- 담당자/마감일도 그대로 보인다.

→ §9-41 해결 확인. (수정 전에는 칩이 카드 밖(화면 가장자리)까지 칠해져서
담당자·마감일·댓글수가 **전부 사라졌다** — 지금은 정보가 유지된다.)

### §9-42 검증 — "실행 취소" 스낵바가 10초 동안 산다

#general 채널에서 메시지를 직접 보내고(길게 누르기 → `메시지 삭제`) 스낵바 수명을 측정했다.

| 시점 | 화면 | 비고 |
|---|---|---|
| +1.3초 | 스낵바 보임 (`메시지를 삭제했습니다` / `실행 취소`) | 정상 |
| +6.5초 | **스낵바 아직 보임** | ← 5초였으면 이 시점엔 이미 사라짐 |
| +10.7초 | 스낵바 사라짐 | 10초 후 자동 닫힘 (persist:false 유지) |

**되돌리기 동작 확인 (6초 지연 후 탭)** — 삭제를 하고 **6초 뒤에** `실행 취소` 를 눌렀다.

- 백엔드 로그: `POST /api/v1/messages/msg_01M6YAXBC5QC329HBKQMEVBCSD/restore` → **200 OK**
- 화면: `restore check 2` 메시지가 다시 초록 말풍선 + `04:42` 타임스탬프로 복원됨

→ §9-42 해결 확인. 이제 "실수한 걸 발견하고 눈을 돌렸다가 되돌리기" 를 10초 안에 할 수 있다.

#### 실기 팁 (다음 라운드에)

- **스낵바를 확인한 뒤 탭하려면, 탭까지 한 셸 커맨드 안에서 이어서 실행해야 한다.**
  스크린샷을 찍고 스크린샷을 "보는" 시점까지 왕복하면 실제 시간으로 **10~20초** 가 흐른다.
  10초짜리 스낵바는 그 사이에 이미 사라져 버린다. (이번에도 한 번 헛발질했다.)
  ```
  adb shell input tap <삭제>; sleep 6; adb exec-out screencap -p > /tmp/a.png; adb shell input tap <실행취소>
  ```
- `adb shell input text` 는 **한글을 넣으면 NullPointerException** 이 난다. 영문/숫자로 입력한다.
- `adb shell input swipe x y x y 900` (= 길게 누르기) 는 Flutter 의 스크롤 뷰에서는 스크롤이 안 되고
  롱프레스만 된다. 스크롤이 필요하면 `adb shell input motionevent DOWN/MOVE/UP` 시퀀스를 쓴다.
- 앱이 안 뜰 때 `monkey` 말고 `am start -n <pkg>/.MainActivity` 를 쓴다.

### 테스트 데이터 정리

- `backend/llack.db` 에 심었던 `rdm_01M6WWTESTAAA001` / `rdm_01M6WWTESTAAA002` 삭제
- `tasks.roadmap_id` → `NULL` 로 복구 (남은 로드맵 연결 0건)
- 실기에서 만든 테스트 메시지(`delete undo test` / `undo tap check` / `restore check 2`) 삭제
- 앱 재시작 후 프로젝트 탭 확인 → 로드맵 필터 칩이 사라지고 카드에도 칩이 없음 (정상 복구)

### 함께 확인한 회귀 없음

- §9-40 (오른쪽 배지 열 정렬) — 조직도/일정 상세/프로젝트 세 화면 모두 그대로 정렬 유지
- §9-41 을 적용하면서 §9-40 의 정렬이 깨지지 않았는지 진행 중 탭의 `1분기 목표` 칩과
  `2분기 목표 …` 칩의 오른쪽 끝 x 좌표가 같은 것으로 확인

---

## 14차 라운드 (2026-11-09 · 에뮬레이터 Pixel_7_API_36 실기 — profile APK)

### 9-43. [MAJOR] 메시지 검색 결과를 눌러도 **찾은 메시지로 이동하지 않는다** (담당 A + B)

#### 증상 (실기 확인, 2026-11-09 · profile APK)

`#engineering` 채널에서 `heartbeat` 를 검색 → 검색 결과(메시지) 중
**2026-11-07 20:20 "그럼 서버 heartbeat는 20초 주기로 하면 될 것 같아요."** 를 탭했다.

- 채널은 **열리긴 했다** — **하지만 화면에는 11-08 10:24~13:34 의 최신 메시지만 보인다.**
- 찾은 메시지는 화면 어디에도 없다. 스크롤바 위치로 보아도 **10시간 이상 과거**다.
- "얼마나를 스크롤해야 하지" 라는 안내도, "여기야" 라는 표시도 없다.
  → 사용자는 "검색 결과가 잘못된 것인가?" 하고 좌절한다.

#### 원인

`lib/screens/search/search_dialog.dart` 의 메시지 검색 결과 `onTap` 이 **채널 id 만** 넘긴다.

```dart
onTap: () {
  final appState = context.read<AppState>();
  final navigator = Navigator.of(context, rootNavigator: true);
  final compact = FormFactor(context).isCompact;
  Navigator.pop(context, SearchSelection(channelId: r.channel.id));
  ChatNavigator.openChannel(
    state: appState,
    navigator: navigator,
    channelId: r.channel.id,     // ← 메시지 id 를 버린다
    push: compact,
  );
},
```

- `ChatNavigator.openChannel` → `state.selectChannel(channelId)` → `loadMessages(channelId)`
  → `GET /channels/{id}/messages` **기본값은 "최신 40개"** 다.
  → 열림 직무로 화면의 맨 아래(최신)에 붙는다. **찾은 메시지는 어디에도 없다.**
- `SearchSelection` 에는 `channelId` / `userId` / `projectId` 만 있고 **메시지 id 필드가 없다.**
- 채팅 화면에 **"특정 메시지로 스크롤" 또는 "메시지 강조" 기능이 아예 없다.**
  (`ChatScreen` 에는 `_scrollController` 와 `_loadOlder()` 뿐, 특정 메시지로 가는 길이 없다.)

**데스크톱 앱도 똑같다.** `desktop/src/components/Dialogs.tsx` 의 검색 결과 클릭도
`void enterChannel(result.channel.id)` 뿐이다. → 데스크톱만 고치는 게 아니라 **제품 공백**이며,
모바일은 좁은 화면 + 스크롤만으로 과거를 더듬어야 하므로 체감 피해가 더 크다.

#### 요구사항

1. 메시지 검색 결과를 탭하면 **그 메시지가 화면에 보이도록** 이동한다.
2. 도착한 메시지는 **눈에 띄게 강조**한다(배경/테두리).
3. 점프한 뒤에도 대화방이 **양방향으로 계속 탐색 가능**해야 한다.
   - 위로 스크롤 → 과거 메시지 더 로드 (기존 `before` 페이지네이션 그대로)
   - 아래로 스크롤 → **최신 메시지까지** 갈 수 있어야 한다 (점프 후 "막다른 길" 금지)
4. 실패하면(메시지가 삭제됨 / 권한 없음 / 네트워크 오류) **한국어로 이유를 알리고**,
   대화방은 정상적으로(최신 위치로) 열린다. 성공한 척 최신 메시지만 보여주면 안 된다.
5. **회귀 금지**: 채널 목록에서 평소대로 채널을 열면 여전히 최신 메시지에 있어야 한다.
   채널별 스크롤 위치 기억(`ChatScrollMemory`) 동작도 그대로여야 한다.

#### 백엔드 계약 (담당 A)

`GET /api/v1/channels/{channel_id}/messages` 에 커서를 2개 추가한다.

| 파라미터 | 의미 |
|---|---|
| `around` | 기준(anchor) 메시지 id. **그 메시지를 가운데 둔 창(window)** 을 돌려준다. |
| `after` | 기준 메시지 id. **`before` 의 반대 방향** — 기준보다 **새로운** 메시지를 oldest-first 로 돌려준다. |

- `before` / `after` 는 **exclusive** (기준 메시지는 포함하지 않는다).
- `before` 와 `after` 는 동시에 못 쓴다. `around` 는 둘 다와 같이 못 쓴다.
- `around` 응답 구성: 기준 메시지 **본인** + 기준보다 오래된 메시지 최대 `limit//2` 개
  + 기준보다 새로운 메시지 나머지. 전체는 `limit` 개 이하, **oldest-first**.
- `has_more` = **반환된 가장 오래된 메시지보다 더 과거의 메시지가 있다** (기존 의미 유지).
- `has_more_after` = **반환된 가장 새로운 메시지보다 더 새로운 메시지가 있다** (신규 필드).
- 기준 메시지가 없거나 다른 채널이면 **404** (`not_found("message not found")`).
- `MessagePage` 스키마에 `has_more_after: bool = False` 를 **추가**한다.
  (붙이는 필드라 데스크톱 앱 영향 없음 — 데스크톱은 `has_more` 만 쓴다.)

#### 모바일 코어 계약 (담당 A) — B 가 이 시그니처를 그대로 쓴다

```dart
// lib/services/api_service.dart
/// (messages, hasMore, hasMoreAfter)
Future<(List<Message>, bool, bool)> getMessages(
  String channelId, {
  int limit = 50,
  String? before,
  String? after,
  String? around,
});

/// 앱 상태
/// [messageId] 주변 메시지를 불러오고 화면에 노출한다.
/// 성공하면 true, 찾지 못하면 false.
Future<bool> loadMessagesAround(String channelId, String messageId);

/// 아직 스크롤/강조가 처리되지 않은 대상 메시지 id. (B 가 읽고 clear 한다)
String? get pendingFocusMessageId;
void clearPendingFocusMessageId();

/// 점프 실패 사유(한국어). B 가 스낵바로 보여주고 clear 한다.
String? get focusErrorMessage;
void clearFocusErrorMessage();

/// 활성 채널의 "아직 더 최신 메시지가 있다" 여부. (B 가 아래로 스크롤할 때 쓴다)
bool get hasMoreNewerMessages;

/// 최신 방향으로 더 불러온다. (B 가 목록 아래쪽에 닿을 때 부른다)
Future<void> loadNewerMessages(String channelId);

/// 채널을 연다. [focusMessageId] 가 있으면 그 메시지로 점프한다.
void selectChannel(String channelId, {String? focusMessageId});
```

- `selectChannel(channelId, focusMessageId: id)` 는 **같은 채널이어도 early-return 하지 않는다.**
  (이미 그 채널에 있어도 과거 메시지로 점프할 수 있어야 한다)
- `focusMessageId` 가 있으면 `loadMessages(channelId)`(최신 40개) 대신
  `loadMessagesAround(channelId, id)` 를 호출한다. → 목록이 **기준 주변 창**으로 바뀐다.
  이때 `_hasMore[channelId]`(과거 방향) 와 `hasMoreNewer`(최신 방향) 를
  백엔드가 준 값 그대로 저장한다.
- `loadMessagesAround` 이 실패하면 `focusErrorMessage` 에 한국어 사유를 넣고
  `pendingFocusMessageId` 를 null 로 만든다. **이때 대화방은 최신 위치로 열린다** (요구사항 4).

#### 채팅 UI 계약 (담당 B)

1. `lib/screens/search/search_dialog.dart`
   - `SearchSelection` 에 `messageId` 필드를 추가한다.
   - 메시지 결과 `onTap` → `ChatNavigator.openChannel(..., messageId: r.message.id)`.
2. `lib/screens/chat/chat_navigator.dart`
   - `openChannel({... required String channelId, bool push = true, String? messageId})`
   - `messageId` 가 있으면 `state.selectChannel(channelId, focusMessageId: messageId)`,
     없으면 기존처럼 `state.selectChannel(channelId)`.
3. `lib/screens/chat/chat_screen.dart`
   - `state.pendingFocusMessageId` 가 non-null 이고 그 메시지가 `state.activeMessages` 에 있으면
     → **그 메시지로 스크롤**하고 **강조**한 뒤 `state.clearPendingFocusMessageId()`.
   - **임의 인덱스로 스크롤하는 방법** (`ListView.builder` 는 lazy 라 대상이 아직 빌드되지 않았을 수 있다):
     - 메시지마다 `GlobalKey`(`Map<String, GlobalKey>`) 를 붙이고
       `Scrollable.ensureVisible(key.currentContext!, alignment: 0.35, duration: 300ms)` 를 쓴다.
     - **대상이 빌드되어 있어야 한다.** 점프가 대기 중인 동안 `ListView` 의 `cacheExtent` 를
       크게(=100000) 올려서 창 안의 모든 항목이 빌드되게 하고, 점프가 끝나면 원래 값으로 되돌린다.
       (대안으로, 점프 대기 중에는 창을 `ListView(children: [...])` 로 바꾸어도 된다.)
     - 점프 대기 중에는 `_followBottom`(최신 따라가기)가 켜지지 않게 한다.
   - 강조: `ChatScreen` State 에 `_highlightedMessageId` 를 두고
     `MessageBubble(highlight: msg.id == _highlightedMessageId)` 로 넘긴다.
     강조는 **사용자가 수동 스크롤하거나 / 채널을 바꾸거나 / 새 메시지를 보내면 해제**한다.
     (수동 스크롤 판별은 `NotificationListener<UserScrollNotification>` 의 direction != idle.)
   - `state.focusErrorMessage` 가 non-null 이면 스낵바로 보여주고 clear 한다.
     (기존 `showAppSnackBar` 헬퍼 또는 `ScaffoldMessenger` — §9-17 규칙 참고:
      **모달 안에서 띄운 스낵바는 안 보인다**.)
   - 목록 아래쪽에 닿으면(`position.pixels >= position.maxScrollExtent - 80`)
     `state.hasMoreNewerMessages` 가 true 일 때 `state.loadNewerMessages(channelId)` 를 부른다.
     (기존 `_loadOlder()` 와 대칭. 추가되는 메시지는 목록 **아래**에 붙으므로 스크롤 위치 보정은 필요 없다.)
4. `lib/widgets/message_bubble.dart`
   - `bool highlight = false` 옵션을 추가한다.
   - true 면 말풍선 주변에 **주황/앰버 계열 하이라이트**(배경 + 좌측 3dp 테두리 + 살짝 넓은 패딩)를 그린다.
     (`LlackColors.accentSoft` 계열을 쓸지, 별도 색을 쓸지는 C 의 `theme/*` 를 건드리지 말고
     `message_bubble.dart` 안에서 상수로 정의한다. — C 소유 파일이라 건드리지 않는다.)

#### 테스트

- **백엔드**: `around` 로 창이 올바른지(기준 메시지 포함, 앞뒤 개수, oldest-first),
  `after` 로 새 메시지만 오는지, 잘못된 id 면 404 인지.
- **모바일(단위/위젯)**: `getMessages` 가 `around`/`after` 를 쿼리에 넣는지,
  `selectChannel(focusMessageId:)` 가 `pendingFocusMessageId` 를 세팅하는지.
- **실기(내가 한다)**: 검색 → 오래된 결과 탭 → **그 메시지가 화면 가운데에 강조되어 보이나**,
  위로 스크롤하면 과거가 이어지고, 아래로 스크롤하면 최신까지 갈 수 있나.

---

## 15차 라운드 실기 검증 결과 (2026-11-09 · profile APK · 에뮬레이터 Pixel_7_API_36)

§9-43 (검색 결과 → 해당 메시지로 점프) 을 프로필 APK 로 빌드해서 **실기**로 확인했다.

- 빌드: `flutter build apk --profile` → `build/app/outputs/flutter-apk/app-profile.apk` (104.2MB, 05:39)
- 설치: `adb install -r` (로그인 세션 유지) → `am start -n com.hanbit.llack.llack_mobile/.MainActivity`
- 백엔드: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (**`--reload` 없음** → 코드 변경 후 **명시적 재시작** 필요)
- 계정: hyunjin@hanbit.co.kr (김현진) · 앱은 `http://10.0.2.2:8000` 로 붙는다
- 자동 검사: `flutter analyze` → **No issues found** · `flutter test` → **118 passed** ·
  백엔드 `pytest -q` → **156 passed**

### §9-43 검증 — 검색 결과를 탭하면 그 메시지로 이동하고 강조된다

재현용으로 `#general` 에 `zzjumpmarker` 라는 메시지를 심고, 그 **뒤로** `fillerbatch 1…55` 를
넣었다(즉 `zzjumpmarker` 는 최신 기준 **56번째 전**). 검색 결과에서 이 메시지를 탭하면
"과거가 56-message 만큼 뒤로 간 상태"에서 시작해야 한다.

**수정 전(before)** — 검색 결과 탭 → `#general` 이 **맨 아래(최신)** 에 붙었다.
`fillerbatch 55` 가 마지막에 보이고 `zzjumpmarker` 는 화면 어디에도 없었다(스크롤 56회 필요).

**수정 후(after)** — 같은 탭 동작을 다시 했을 때:

| 항목 | 결과 |
|---|---|
| 도착 위치 | `zzjumpmarker` 가 **화면 위쪽~중간**(`alignment: 0.35`)에 보인다 |
| 강조 | **앰버 배경(`#FFF3D6`) + 좌측 3dp 주황 테두리(`#E8A33D`)** 적용됨 |
| 다른 메시지 | 강조 없음 (대상만 강조) |
| 백엔드 요청 | `GET /api/v1/channels/{id}/messages?limit=40&around=msg_01M6YDBBWY615GRB57JDG5X5YM` → **200 OK** |
| 창 구성 | 40개, **기준 메시지가 20번 인덱스**(정중앙), oldest-first, `has_more=true`, `has_more_after=true` |

**양방향 탐색 (요구사항 3)** — 점프 후에도 막다른 길이 없다:

| 방향 | 조작 | 결과 |
|---|---|---|
| 과거(위) | 위로 스크롤 | `before=` 요청 → 더 과거 메시지 로드, 계속 이어짐 |
| 최신(아래) | 아래로 스크롤 | `after=` 요청 → `fillerbatch 34 → 43` … 결국 **최신(`fillerbatch 55`)까지 도달** |
| 최신(최하단) | 목록 끝에 닿음 | `has_more_after=false` 가 되면 추가 요청 없음 (무한 요청 X) |
| 강조 해제 | 수동 스크롤 | 강조가 **해제**됨 (수동 스크롤 판별이 제대로 동작) |

**실패 경로 (요구사항 4)** — 대상 메시지를 DB 에서 하드 삭제한 뒤(검색 결과는 이미 렌더된 상태)
같은 결과를 탭했다:

| 항목 | 결과 |
|---|---|
| 백엔드 | `GET …/messages?limit=40&around=msg_01M6YDBBWY615GRB57JDG5X5YM` → **404 Not Found** |
| 코어 폴백 | 이어서 `GET …/messages?limit=40` → **200 OK** (최신 위치로 폴백) |
| 화면 | **한국어 스낵바**: `해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.` |
| 대화방 | 정상적으로 열리고 **최신 메시지**(`fillerbatch 46…54`)가 보임 |
| 루프 | 실패 처리 후 같은 대상으로 **재시도하지 않음** (무한 프레임 스핀 없음) |

> "성공한 척 최신만 보여주기" 가 아니라 **실패 이유를 한국어로 알리고** 그 다음 최신으로 폴백했다.

**회귀 없음 (요구사항 5)** — 같은 APK 에서 평소 경로도 확인했다:

| 항목 | 결과 |
|---|---|
| 채널 목록에서 `#engineering` 열기 | **최신 메시지(13:34)** 에 붙음. 강조 없음, 점프 없음 |
| `ChatScrollMemory` | `#engineering` 에서 위로 스크롤 → 뒤로가기 → 다시 열기 → **같은 오프셋으로 복원** |
| 기존 메시지 목록 | `fillerbatch` 시딩 메시지를 지운 뒤 `#general` 은 **28개**로 정상 복구 |

#### 실기 팁 (다음 라운드에)

- **DB 를 직접 건드릴 때 경로는 반드시 절대경로로.**
  `sqlite3 backend/llack.db …` 를 `mobile/` 에서 실행하면 `Error: unable to open database file` 로
  **조용히 실패**한다. 삭제가 안 된 걸 모르고 "수정 후" 테스트를 다시 하면
  그냥 같은 메시지로 또 점프할 뿐이라 **원인을 못 찾는다.**
  ```
  sqlite3 /Volumes/samsung/2026/projects/llack/backend/llack.db \
    "delete from messages where id='…'; select 'rows deleted: '||changes();"
  ```
  `rows deleted: 0` 이면 삭제가 안 된 것이다.
- **검색 결과는 "이미 렌더된 상태"로 두면 삭제를 재현할 수 있다.**
  검색 결과를 먼저 띄워 두고 → DB 삭제 → 그 결과를 탭하면 404 경로가 정확히 재현된다.
  (검색을 다시 하면 결과 목록에서 사라져서 재현이 안 된다.)
- **점프 후 "최신까지 갈 수 있는가" 는 `has_more_after` 로 확인한다.**
  화면만 보면 "맨 아래처럼 보이지만 못 내려가는" 케이스를 놓친다.
  백엔드 로그의 `after=` 요청과 실제 도착 메시지를 함께 봐야 한다.
- `adb shell input swipe` 는 Flutter 스크롤 뷰에서 안 굴린다 →
  `adb shell input motionevent DOWN/MOVE/UP` 시퀀스.

### 테스트 데이터 정리

- `backend/llack.db` 에 심었던 `zzjumpmarker` 1건 삭제 (실패 경로 재현용)
- `backend/llack.db` 의 `fillerbatch 1…55` 55건 삭제
- 남은 테스트 잔여물 확인: `fillerbatch%` / `%zzjumpmarker%` / `%undotest%` → **0건**
- `#general` 메시지 수 원복: **28개**
- 앱 재시작 후 `#general` 진입 → 과거 메시지가 정상적으로 이어지는 것 확인

### 함께 확인한 회귀 없음

- §9-42 (삭제 "실행 취소" 스낵바 10초) — 메시지 삭제/복구 흐름 정상
- §9-41 (긴 로드맵 이름 말줄임) / §9-40 (오른쪽 배지 열 정렬) — 변경 없음
- 채널 진입 일반 경로(최신 위치) · `ChatScrollMemory` 스크롤 위치 복원 모두 정상


---

## 16차 라운드 (2026-11-09 · 에뮬레이터 Pixel_7_API_36 실기 — profile APK)

### 9-44. [MAJOR] 스레드에 답글을 **한 번만 보내도 화면에 2개로 보인다** (담당 A)

#### 증상 (실기 확인, 2026-11-09 · profile APK · 계정 hyunjin@hanbit.co.kr)

`#release` 채널에서 **내 메시지**(`네. 앱 버전만 되돌리면 되게 설계했어요.`)를 롱프레스 →
`스레드로 답글 달기` → 스레드 화면에서 `thread test reply` 한 줄을 보내고 전송 버튼을 **한 번** 눌렀다.

- 전송 직후 스레드 화면 헤더가 **`답글 2개`** 로 뜬다.
- 본문도 **똑같은 메시지가 2개** 연속으로 보인다 (`thread test reply` / `thread test reply`, 둘 다 `05:47`).
- 그런데 **DB 에는 1건만** 있다.
  ```
  $ sqlite3 backend/llack.db "select id, body from messages where body like 'thread test reply%';"
  msg_01M6YENB7T0BM9RTMGQRD4QT59|thread test reply
  ```
- 백엔드 로그에도 **POST 는 1회**뿐이다.
  ```
  POST /api/v1/channels/chl_01M6WWCMA3YWVH8AXA5D8PS15Y/messages HTTP/1.1" 200 OK   ← 1회
  ```
- 스레드를 **닫았다가 다시 열면** `답글 1개`, 메시지도 1개로 **정확하게** 보인다.
  → **서버가 중복을 만든 게 아니라, 앱 상태(메모리)에만 중복이 생겼다.**

사용자 체감: "한 번 보냈는데 2개로 떴어? 내 보낸 메시지를 두 번 보낸 건가?" →
스레드를 다시 열면 1개로 사라진다. **자기 화면에서 숫자가 바뀌는 기이한 버그**이고,
"이거 두 번 보낸 건가" 싶은 사람이라면 그대로 두 번 보내게 된다.

#### 원인 (경합 조건)

스레드 답글은 **두 경로**로 같은 메시지가 앱에 들어온다.

1. **HTTP 응답** — `AppState.sendReply()` 가 `POST /messages` 의 응답 본문(`reply`)을 받아서
   `_threadReplies.add(reply)` 로 **무조건 추가**한다.
   (`lib/providers/app_state_messages.dart:186-195`)
2. **WebSocket 브로드캐스트** — 서버가 저장 직후 WS 로 `message.created` 를 뿌린다.
   `lib/providers/app_state_realtime.dart:39-47` 의 WS 핸들러가
   `if (!_threadReplies.any((r) => r.id == msg.id))` 로 **id 기준 중복 검사**를 하고 추가한다.

**WS 이벤트가 HTTP 응답보다 먼저 도착하면**,
① WS 핸들러가 먼저 `_threadReplies` 에 넣고 → ② `sendReply()` 가 같은 id 를 또 넣는다.
→ **같은 메시지가 2개.**

`sendReply()` 쪽에 **id 중복 검사가 없다**가 문제의 핵심이다.

대조: 같은 파일의 일반 채널 전송(`sendMessage`) 은 `_upsertMessage(cid, msg)` 를 쓰기 때문에
id 기준으로 덮어써서 **중복이 생기지 않는다**. → **스레드 답글만 방어 빠져 있다.**

`sendReply()` 안의 주석도 이 긴장을 이미 아는데, **replyCount 에만** 적용되어 있다.
```dart
// replyCount 는 서버가 WS 로 알려준다 (로컬에서 더하면 2씩 증가한다).
```
`replyCount` 는 손대지 않았고, **리스트 자체**의 중복은 막지 않았다.

#### 요구사항

1. 스레드에 답글을 **한 번 보내면 화면에 1개만** 보여야 한다.
   (WS 도착 순서에 따라 결과가 달라져서는 안 된다 — **순서 무관**해야 한다.)
2. 답글을 여러 번 보내면 그만큼 정확히 N개가 보여야 한다.
3. **회귀 금지**: 일반 채널 메시지 전송, 인라인 답글, 반응, 편집, 삭제 동작이 그대로여야 한다.

#### 모바일 코어 계약 (담당 A)

- `lib/providers/app_state_messages.dart` 의 `sendReply()`:
  HTTP 응답으로 받은 `reply` 를 `_threadReplies` 에 넣을 때
  **같은 id 가 이미 있으면 넣지 않는다** (WS 핸들러와 **동일한 기준**).
  ```dart
  // WS 'message.created' 가 먼저 도착할 수 있다. id 로 중복을 막는다.
  if (!_threadReplies.any((r) => r.id == reply.id)) {
    _threadReplies.add(reply);
  }
  ```
- 같은 기준(`id`)으로 **양쪽 경로가 동일하게** 동작해야 한다.
  (`app_state_realtime.dart` 의 WS 핸들러와 대칭.)
- **하드코딩으로 id 를 비교하지 말고**, 이미 있는 공용 헬퍼
  (`lib/providers/list_upsert.dart` 에 id 기준 upsert 헬퍼가 있으면 그걸 쓴다) 를 재사용한다.
  → 나중에 다른 경로가 또 생겨도 같은 함수를 쓰게 된다.
- `replyCount` 를 로컬에서 더하지 않는 기존 규칙은 **유지**한다.

#### 테스트

- **단위 테스트 (권장)**: `sendReply()` 를 호출한 뒤, WS `message.created` 가
  **먼저** 도착한 상황과 **나중에** 도착한 상황을 모두 재현해서
  `_threadReplies` 길이가 **항상 1** 임을 확인한다.
  - WS 먼저: WS 로 1개 추가 → `sendReply()` 응답이 와도 **추가되지 않음** → 1개
  - HTTP 먼저: `sendReply()` 로 1개 추가 → WS 로 와도 **추가되지 않음** → 1개
- **실기(내가 한다)**: 스레드에 답글 1개 보내기 → **답글 1개**로 뜨고 메시지도 1개만 보인다.
  다시 열어도 1개로 유지된다.

### 9-45. [MAJOR] **보고 있는 채널**에 도착한 메시지가 **안읽음 배지로 남는다** (담당 A + B)

#### 증상 (실기 확인, 2026-11-09 · profile APK · 계정 hyunjin@hanbit.co.kr)

1. 최수아 DM(`chl_01M6WWCMCB4H8S0J0P57YRW1XH`)을 **열어 둔다**.
   → 채널 목록에서 최수아 배지는 0이다. (열자마자 읽음 처리되므로 정상)
2. 같은 화면을 보고 있는 사이에 최수아 계정으로 메시지가 도착한다.
   ```bash
   $ curl -X POST http://127.0.0.1:8000/api/v1/channels/chl_01M6WWCMCB4H8S0J0P57YRW1XH/messages \
       -H "Authorization: Bearer $(cat /tmp/sua_token)" \
       -d '{"body":"visible while open 4321"}'
   ```
3. **메시지가 대화창에 온전히 보인다.** (`visible while open 4321` · 05:54 · 최수아 · 본문까지 화면에 있음)
   → **사용자는 이미 읽었다.**
4. 뒤로 가서 채널 목록으로 나온다.
   → **최수아 항목에 배지 `1`** 이 떠 있다.

같은 일이 `#general` 에서도 그대로 재현된다
(`readwhileopen check 9999` 도착 → 대화창에 보임 → 뒤로 가면 `#general` 배지 `1`).

사용자 체감: "**내가 보고 있던 화면에 이미 나온 메시지가 안읽음으로 세어진다.**
나중에 들어가서 또 읽어야 하는데, 읽은 것 같아서 그냥 넘겼다."
→ 받은 편지함에 "안 읽은 메일" 이 쌓이는 것과 같은 심리적 거슬림.
WhatsApp/Slack 처럼 **열어 두고 본 채널은 배지가 살아 있으면 안 된다.**

#### 원인 (읽음 신호가 "채널에 들어온 순간" 에만 간다)

읽음 처리(`read`) 신호는 **채널에 들어갈 때 한 번만** 보낸다.

```dart
// lib/providers/app_state_messages.dart:331-349  (selectChannel)
void selectChannel(String channelId, {String? focusMessageId}) {
  ...
  // Mark channel read
  ws.sendRead(channelId);          // ← 유일한 호출 지점 (채널 "진입" 시점)
  ...
}
```

```
$ grep -rn "sendRead" lib/
lib/services/ws_service.dart:168:  void sendRead(String channelId, {String? messageId}) {
lib/providers/app_state_messages.dart:344:    ws.sendRead(channelId);
```
→ **`sendRead` 는 채널에 들어갈 때만 불린다.**
**채널을 열어 둔 채로** 새 메시지가 도착해도 **읽음 신호가 전혀 가지 않는다.**

서버 쪽은 이렇게 움직인다.

1. `POST /messages` → 메시지 저장 → `emit_message_created()` 가 WS 로 `message.created` 를 뿌리고
   (`backend/app/realtime/events.py:29-41`)
2. 이어서 `emit_unread_counts()` 가 **절대값** 배지 숫자를 같은 사람에게 다시 보낸다.
   (`backend/app/realtime/events.py:260-266`)
   ```python
   {"type": "unread", "channel_id": channel.id, "count": counts.get(channel.id, 0)}
   ```
3. 서버의 `unread_counts()` 는 "앵커(읽음 기준)보다 나중이고, 내가 쓴 messages 가 아니면 안읽음" 으로 센다.
   (`backend/app/services/messages.py:464+`)
   → **앵커가 전진하지 않았으므로** 방금 화면에 보인 메시지가 **안읽음 1건** 으로 계산된다.

클라이언트는 두 갈래로 fight 하지만 둘 다 실패한다.

```dart
// lib/providers/app_state_realtime.dart:59-68  (message.created)
// 로컬 증가분은 활성 채널이면 막는다 → 이건 맞다.
if (_activeChannelId != msg.channelId && msg.userId != _currentUser?.id) { ... +1 ... }

// lib/providers/app_state_realtime.dart:168-178  (unread)
// 그런데 서버가 보내는 "절대값" 이 로컬 값을 그대로 덮어쓴다.
_channels[idx] = _channels[idx].copyWith(unreadCount: count ?? 0);   // ← 1 이 들어온다
```

→ **로컬에서 막아도 서버 숫자가 다시 1 로 되돌린다.**
그리고 서버 앵커가 전진하지 않았으므로 **앱을 껐다 켜도** 배지가 그대로 살아 있다.

> 참고: 서버와 WS 모두 **이미** `message_id` 를 받는 읽음 신호를 지원한다.
> `lib/services/ws_service.dart:168` (`sendRead(channelId, {messageId})`),
> `backend/app/api/v1/realtime.py:124-142` (`_handle_read` → `mark_read(..., message_id)`).
> **백엔드는 바꿀 필요가 없다.** 모바일이 신호를 안 보내는 것이 문제다.

#### 요구사항

1. **지금 보고 있는 채널**에 도착한 메시지는 **읽은 것으로** 처리되어야 한다.
   - 채널 목록의 배지가 **0** 이 유지되어야 한다.
   - **앱을 껐다 켜도** 배지가 살아나면 안 된다. (서버 앵커까지 전진해야 한다)
2. **화면에서 볼 수 없는** 상태(위쪽을 스크롤해 두는 중)라면 그 메시지는 **안읽음으로 남아야 한다.**
   - "읽었다고 해 놓고 못 본 메시지" 가 되어서도 안 된다.
   - → **"보고 있다" 의 판정은 화면(스크롤 위치)이 알고, 코어는 그것을 물어본다.**
3. **회귀 금지**: 다른 채널의 안읽음 배지, 채팅 목록 순서, 메시지 실시간 도착,
   알림/읽음 수신 잘못 뜨지 않기, 채널 진입 시 읽음 처리는 그대로여야 한다.

#### 모바일 코어 계약 (담당 A)

**A-1. 화면에 보이는지 물어보는 훅을 코어에 둔다.**

`lib/providers/app_state_core.dart` 에 다음을 둔다.

```dart
/// 현재 열려 있는 대화창에서 "새 메시지가 화면에 보이는가" 를 물어보는 훅.
///
/// 담당 B(chat_screen.dart) 가 **대화창이 열려 있는 동안에만** 값을 채운다.
/// - 대화창이 열려 있지 않으면 **null**
///   (= 사용자가 그 채널의 메시지를 보고 있지 않다)
/// - 열려 있으면 "최신 메시지가 화면에 보이는가" 를 반환
///   - true  : 최신 구간에 붙어 있음 → 도착한 메시지는 화면에 보임 → 읽음 처리 가능
///   - false : 위로 스크롤해 있음 → 도착한 메시지는 화면에 안 보임 → 읽음 처리하면 안 됨
bool Function(String channelId)? isNewestMessageVisible;
```

> **왜 "활성 채널" 로는 판단이 안 되는가** (실기에서 확인한 사실)
>
> 대화창은 목록 화면 위에 **push 되는 라우트**다. (`lib/screens/chat/chat_tab.dart:20-30`)
> - 사용자가 대화방에서 **뒤로 가면** route 가 pop 되지만 `_activeChannelId` 는 **그대로 남는다.**
> - **콜드 스타트**에서도 목록 화면인데 `_activeChannelId` 가 채워진다
>   (`lib/providers/app_state.dart:95-98` — `selectChannel` 를 거치지 않으므로 읽음 신호도 안 간다)
>
> → **"활성 채널" ≠ "사용자가 그 채널의 메시지를 보고 있다".**
> "보고 있다" 의 판정은 **대화창이 떠 있는지**(훅의 null 여부)로 해야 한다.

**A-2. `message.created` (활성 채널) → 읽음 신호를 보낸다.**

`lib/providers/app_state_realtime.dart` 의 `message.created` 핸들러에서,
`msg.channelId == _activeChannelId` 이면:

```dart
// 내가 보고 있는 채널. 화면에 보이면 읽은 것으로 처리한다.
if (_activeChannelId == msg.channelId) {
  final hook = isNewestMessageVisible;
  // 훅이 null = 대화창이 열려 있지 않다 = 사용자가 보고 있지 않다
  final visible = hook != null && hook(msg.channelId);
  if (visible) {
    // 서버 앵커를 이 메시지까지 전진시킨다.
    // (앱을 껐다 켜도 배지가 살아나지 않게 하는 핵심)
    ws.sendRead(msg.channelId, messageId: msg.id);
    // 배지는 0 유지
    _setUnreadCount(msg.channelId, 0);
  } else {
    // 볼 수 없는 곳에 도착 → 안읽음으로 남긴다.
    _setUnreadCount(msg.channelId, _unreadOf(msg.channelId) + 1);
  }
}
```

- "화면에 보인다" 의 판정은 **담당 B** 가 `_isNearBottom()` 로 채운다.
- 코어는 **판정 결과만** 쓴다. (스크롤 값을 코어가 들고 가지 않는다)
- 화면에 보이는 경우에는 **가장 최근 메시지 id** 로 앵커를 전진시킨다.
  → 사용자가 화면에 볼 수 있는 것은 "최신 구간" 뿐이므로, 최신으로 앵커를 옮겨도 과하지 않다.
- **기본값은 "안 읽음" 이다.** (훅이 null 이면 `visible == false`)
  열지 않은 채널이 읽음 처리돼서 배지가 죽는 쪽이
  "왜 이 메시지 안 왔지?" 하는 사용자 체감상 더 나쁘다.

**A-2-1. 읽음 처리를 하는 공개 메서드를 하나 둔다.** (담당 B 도 이게 필요하다)

```dart
/// 채널을 읽음으로 표시한다. (서버 앵커 전진 + 로컬 배지 0)
/// 담당 B 가 사용자가 위로 스크롤해 있다가 **다시 최신 구간으로 내려왔을 때** 호출한다.
void markChannelRead(String channelId, {String? messageId});
```

- `messageId` 가 있으면 그 메시지까지, 없으면 서버가 채널의 최신으로 앵커를 옮긴다.
- `ws.sendRead` 는 `lib/services/ws_service.dart` 의 기존 걸 그대로 쓴다. (`messageId` 인자를 이미 받는다)
- `selectChannel` 의 기존 동작은 **바꾸지 않는다.** (회귀 금지)

**A-3. 서버의 "절대값" 배지가 이미 읽은 메시지를 되살리지 않게 한다.**

`unread` 이벤트는 **서버가 계산한 절대값** 이므로, 클라이언트가 방금 읽음 신호를 보낸 직후에도
**"신호보다 먼저 계산된 숫자"** 가 먼저 도착한다. (서버는 `message.created` → `unread` 순으로 뿌린다.
`backend/app/realtime/events.py:29-41`)

→ **읽음 신호를 보냈지만 아직 서버의 확인이 오지 않은 동안**은 서버 숫자를 **무시**해야 한다.

```dart
/// 채널별로 "읽음 신호를 보냈고 서버 확인을 아직 못 받은" 상태.
final Set<String> _readAckPending = {};
```

- `unread` 이벤트가 왔을 때:
  - 해당 채널이 `_readAckPending` 에 있으면 → **배지를 건드리지 않는다.**
    (확인용 숫자 `count == 0` 이 오면 플래그를 정리하고 0 을 확정한다)
  - 활성 채널이 아니면 → 기존처럼 서버 숫자를 그대로 쓴다.
- 플래그는 아래에서 **반드시 정리**한다 (안 정리하면 그 채널의 배지가 영영 고 sticks):
  - 서버 확인(`count == 0`) 도착 시
  - 같은 채널에 새 `message.created` 가 도착할 때 (다시 armed)
  - `selectChannel` 로 다른 채널로 옮길 때
  - **WS 재연결 시** (연결이 끊기면 확인이 안 올 수 있으므로 전부 비운다)

**A-4. 회귀 방지**

- `selectChannel` 의 기존 읽음 처리(`ws.sendRead(channelId)` + 로컬 배지 0)는 **그대로 둔다.**
- 다른 채널의 안읽음 증가(local +1)도 **그대로 둔다.**
- `unread` 이벤트가 **다른 채널**에 적용되는 경로는 **그대로 둔다.**

#### 화면 계약 (담당 B)

`lib/screens/chat/chat_screen.dart` 는 "지금 최신 구간을 보고 있는가" 를 이미 알고 있다.

```dart
/// 사용자가 최신 구간에 붙어 있는지
bool _isNearBottom() {
  if (!_scrollController.hasClients) return true;
  final p = _scrollController.position;
  return p.maxScrollExtent - p.pixels <= 120;
}
```

- `initState` 에서 코어에 알려주고, `dispose` 에서 **해제**한다.
  ```dart
  state.isNewestMessageVisible = (cid) => _isNearBottom();
  // dispose 에서는
  state.isNewestMessageVisible = null;
  ```
- 대화방이 **열려 있는 동안**만 값을 갖는다. (닫으면 null → 코어는 "안 읽음" 으로 처리)
- 스크롤 위치 판정은 **기존 `_isNearBottom()`** 을 그대로 쓴다. (새 로직 금지)
- **추가**: 사용자가 위로 스크롤해 있다가 **다시 최신 구간으로 내려왔을 때**
  (즉 안읽음이 남은 메시지를 화면에서 다시 보게 된 때) → `state.markChannelRead(channelId)` 를 호출한다.
  → 그래야 "안읽음으로 남아 있던 배지"가 실제로 읽은 뒤에 사라진다. (배지가 고 sticks 하면 안 된다)
  - `_onScroll` 는 아주 자주 불리므로 **"최신 구간에 붙었다" 는 상태가 바뀔 때만** 호출하도록 막아라.
    (예: 직전 판정이 false 였고 지금 true 가 된 순간에만. 또는 디바운스.)

#### 테스트

- **단위 테스트 (담당 A)**: 가짜 WS 로
  - 활성 채널에 `message.created` 도착 + `isNewestMessageVisible` 가 `true`
    → **읽음 신호가 그 메시지 id 로 나가야 한다** / 배지는 0
  - 활성 채널에 `message.created` 도착 + `isNewestMessageVisible` 가 `false`
    → **읽음 신호가 **안** 나가야 한다** / 배지는 1
  - 활성 채널에 `message.created` 도착 + 훅이 **`null`** (대화창이 닫혀 있음)
    → **읽음 신호가 **안** 나가야 한다** / 배지는 1  ← (기본값이 "안 읽음" 인지 확인)
  - 위(1번) 상태에서 서버가 `unread` 로 **1** 을 보내도 (읽음 신호 보낸 직후의 낡은 값)
    → **배지가 1 로 되살아나면 안 된다**
  - 다른 채널의 `unread` 는 **그대로 적용**되어야 한다 (회귀 방지)
- **실기(내가 한다)**:
  1. DM 을 열어 둔 채 메시지 도착 → **뒤로 가도 배지 0**
  2. 앱을 **완전히 종료했다가 다시 켜도** 배지 0 (서버 앵커가 전진했는지 확인)
  3. 대화창을 **위로 스크롤해 둔 상태**에서 메시지 도착 → 배지 1 (안 읽은 것으로 남아야 함)
  4. **목록 화면(대화창을 닫은 상태)**에서 메시지 도착 → 배지 1 (열지도 않았는데 읽음 처리되면 안 됨)
  5. **콜드 스타트 직후**(목록 화면) → 도착한 메시지가 배지 1 로 떠야 한다 (읽음 처리되면 안 됨)

### 9-46. [MAJOR] **놓친 실시간 이벤트가 영영 복구되지 않는다** — 대화방을 다시 열어도 새 메시지가 안 보인다 (담당 A)

#### 증상 (실기 확인, 2026-11-09 06:01~06:03 · profile APK · 계정 hyunjin@hanbit.co.kr)

`#general` 에 최수아 계정으로 메시지 2개를 보냈다 (앱의 WS 가 연결되지 않은 상태였다).
DB 에는 **정상적으로 들어 있다**.

```
$ sqlite3 backend/llack.db "select id, created_at, body from messages where channel_id='chl_01M6WWCM9YDMB322Y86TDGAQJT' order by created_at desc limit 3;"
msg_01M6YFEZBJA1SEEC3FDZ46VY61|2026-11-08 21:01:38.547965|reconnect miss check 8888
msg_01M6YFBQWT4GCQGZKX9SM26RWA|2026-11-08 20:59:52.602603|boot unread check 7777
```

그런데 앱에서는:

| 순서 | 조작 | 화면에 보이는 것 |
|---|---|---|
| 1 | 콜드 스타트 | `#general` 배지 **1** (서버 실제 값은 2) |
| 2 | `#general` 열기 | `boot unread check 7777` 만 보임. **`reconnect miss check 8888` 없음** |
| 3 | 뒤로 가기 → **당겨서 새로고침** | 배지는 **2** 로 갱신 ✓ (bootstrap 이 배지는 고쳐준다) |
| 4 | 다시 `#general` 열기 | **여전히 `reconnect miss check 8888` 없음** ✗ |

→ **안읽음 숫자는 당겨서 새로고침하면 따라오는데, 메시지 목록은 영영 따라오지 않는다.**
→ 사용자는 "메시지가 안 온다"고 생각하고, 실제로 그 메시지를 **볼 방법이 없다.**
(앱을 완전히 껐다 켜야만 보인다.)

사용자 체감: "**내 톡이 왜 안 갔지?** 다른 사람 말인데 안 보이네." → **놓친 메시지를 조용히 삼킨다.**

#### 원인 (4 가지가 겹친다)

**1) 새 메시지를 알게 되는 경로가 WS 이벤트 하나뿐이다.**
폴링도, 재검증(revalidate)도 없다. 서버는 `message.created` 를 **현재 연결된 소켓에**만 보낸다.
→ 그 소켓이 어떤 이유로 그 이벤트를 놓치면(재연결, 앱이 백그라운드로 있다가 OS 가 소켓을 정리,
네트워크 변경 등) **클라이언트는 영영 그 사실을 모른다.**

**2) WS 재연결 시 서버가 아무 상태도 안 준다.**
```python
# backend/app/api/v1/realtime.py:62-68
await hub.send(connection, {
    "type": "hello",
    "user": UserOut.model_validate(current).model_dump(mode="json"),
})
```
→ `hello` 에는 **나(내 정보)만** 들어 있다. 채널 목록도, 안읽음 숫자도, 메시지도 없다.

**3) 클라이언트가 재연결해도 아무것도 다시 맞추지 않는다.**
```dart
// mobile/lib/providers/app_state.dart:25-29
ws.onStatusChanged = (connected, error) {
  _isConnected = connected;
  _connectionError = error;
  _notify();          // ← 상태만 바꾼다. bootstrap 도, 메시지도 다시 안 불러온다
};
```

**4) 대화방을 다시 열어도 메시지를 다시 불러오지 않는다.** ← **가장 직접적인 원인**
```dart
// mobile/lib/providers/app_state_messages.dart:358-360
// WS 로 먼저 도착한 메시지만 있는 채널도 히스토리를 반드시 불러온다.
if (!hasLoadedHistory(channelId)) {
  loadMessages(channelId);
}
```
`hasLoadedHistory` 가 true 인 채널(한 번이라도 열어 본 채널)은 **다시 열어도 아무것도 안 불러온다.**
→ 놓친 메시지가 영영 목록에 들어오지 않는다.

**5) 당겨서 새로고침은 채널 목록(배지)만 고친다.**
```dart
// mobile/lib/providers/app_state_core.dart:243-259  refreshWorkspace()
// bootstrap 을 다시 부른다 → 채널 목록 + 안읽음 배지는 갱신
// 하지만 _messages 는 건드리지 않는다 → 메시지 목록은 그대로 stale
```

#### 요구사항

1. **대화방을 열 때(재진입 포함) 최신 메시지를 반드시 다시 가져와야 한다.**
   - 사용자가 놓친 메시지가 **화면에 나타나야 한다.**
   - (1번 요구사항만으로는 배지만 고쳐지고 메시지는 여전히 안 보인다 → **이게 핵심**)
2. **이미 불러온 과거 메시지는 사라지면 안 된다.**
   - 목록을 통째로 교체하면 사용자가 스크롤해 올린 과거 메시지가 사라지고,
     스크롤 위치도 튄다. → **병합(upsert) 으로 갱신**해야 한다.
3. **WS 재연결 시 채널 목록과 안읽음 배지를 다시 맞춰야 한다.**
   - (지금은 배지조차 재연결 후엔 옛 값에 머문다)
4. **회귀 금지**: 검색 점프(`around`), 위/아래로 더 불러오기(`before`/`after`),
   스레드 화면, 채널별 스크롤 위치 복원(`ChatScrollMemory`), 당겨서 새로고침.

#### 모바일 코어 계약 (담당 A)

**A-1. "최신 메시지 병합 갱신" 메서드를 하나 만든다.**

`lib/providers/app_state_messages.dart` 에:

```dart
/// [channelId] 의 **최신 메시지**를 다시 가져와 기존 목록에 병합한다.
///
/// (놓친 WS 이벤트를 복구하는 것이 목적)
/// - 목록을 통째로 바꾸지 않는다 → 이미 불러온 과거 메시지와 스크롤 위치가 유지된다
/// - id 로 upsert 한다 → `lib/providers/list_upsert.dart` 의 `upsertById` 를 재사용
Future<void> refreshNewestMessages(String channelId) async { ... }
```

구현 요령:
- `api.getMessages(channelId, limit: 40)` (서버는 최신 40개를 준다)
- 기존 목록에 `upsertById` 로 병합 → 서버 정렬 기준(`created_at`, id) 으로 다시 정렬
  (이미 있는 `_compareMessages` 를 쓴다)
- `_newerCursor` 는 **가져온 목록의 마지막 id** 로 갱신
- `_hasMoreNewer` 는 "가져온 최신 메시지가 기존 목록의 마지막보다 더 신기한가" 로 다시 계산
- `_hasMore`(과거 더 보기) 는 **유지**한다 (병합이지 교체 아니다)
- `_isLoadingMessages[channelId]` 가 true 면 **건너뛴다** (다른 로딩과 겹치지 않게)

**A-2. `selectChannel` 에서 병합 갱신을 쓴다.**

```dart
if (!hasLoadedHistory(channelId)) {
  loadMessages(channelId);          // 처음 열 때: 그대로
} else {
  refreshNewestMessages(channelId); // 다시 열 때: 최신만 병합 (과거·스크롤 유지)
}
```
- `focusMessageId` 가 있는 경로(검색 점프)는 **그대로** (`loadMessagesAround`).
  병합 갱신이 점프 창을 덮어쓰면 안 된다.
- `selectChannel` 의 다른 동작(읽음 처리, 배지 0, `_readAckPending` 정리)은 **그대로.**

**A-3. WS 재연결 시(`hello`) 상태를 다시 맞춘다.**

`lib/providers/app_state_realtime.dart` 의 `case 'hello':` 에서:
- `_readAckPending.clear()` (이미 되어 있다) **뒤에**,
- 워크스페이스를 다시 맞춘다:
  ```dart
  // 재연결하면 그 사이에 놓친 이벤트가 있을 수 있다.
  // 채널 목록과 안읽음 배지부터 서버와 다시 맞춘다.
  unawaited(refreshWorkspace());
  ```
- `refreshWorkspace()` 는 `lib/providers/app_state_core.dart` 의 기존 걸 쓴다
  (bootstrap → 채널 목록 + 안읽음 배지).
- **활성 채널의 메시지도** 같이 맞추고 싶으면 `refreshNewestMessages(_activeChannelId)` 를 추가로 부른다.
  (A-2 의 병합 갱신이라 과거 메시지는 유지된다 → 안전)
- 재연결 직후 배지가 옛 값으로 돌아가는 **깜빡임**이 있으면 안 된다.
  (§9-45 의 `_readAckPending` 규칙과 양립해야 한다. `_readAckPending` 은 `hello` 에서 이미 비운다.)

**A-4. 회귀 방지**
- `loadMessages(more: true)` (과거 더 불러오기) 경로는 **그대로.**
- `loadMessagesAround` (검색 점프) 경로는 **그대로.**
- `loadNewerMessages` (최신 더 불러오기) 경로는 **그대로.**
- `ChatScrollMemory` 기반 스크롤 복원은 **그대로.** (병합 갱신은 목록 뒤쪽만 늘리므로 위치가 유지된다)

#### 테스트

- **단위 테스트 (담당 A)**: 가짜 API 로
  - 이미 히스토리를 불러온 채널을 다시 열면 → **최신 메시지가 목록에 들어와야 한다** (놓친 메시지 복구)
  - 병합 갱신 후 **기존에 불러온 과거 메시지가 사라지면 안 된다**
  - 병합 갱신 후 **순서가 유지**된다 (created_at, id)
  - `focusMessageId` 로 점프할 때는 병합 갱신이 **안** 돌아간다 (점프 창이 덮어써지지 않음)
  - WS `hello`(재연결) → **bootstrap 을 다시 부른다** (채널 목록·배지 갱신)
- **실기(내가 한다)**:
  1. 놓친 메시지가 있는 상태에서 대화방을 **다시 열면** 그 메시지가 보인다
  2. 당겨서 새로고침 후에도 대화방 목록이 깨지지 않는다 (과거 메시지 유지)
  3. 위쪽으로 스크롤해 올린 상태로 대화방을 닫았다 다시 열면 **스크롤 위치가 유지**된다
  4. 검색 결과로 점프했을 때 **점프 창이 유지**된다


---

## 17차 라운드 실기 검증 결과 (2026-11-09 · profile APK · 에뮬레이터 Pixel_7_API_36)

§9-44 (스레드 답글 중복) 과 §9-45 (보고 있는 채널의 배지 오작동) 을 프로필 APK 로 빌드해서 **실기**로 확인했다.

- 빌드: `flutter build apk --profile` → `build/app/outputs/flutter-apk/app-profile.apk` (**104.3MB**, 06:07)
- 설치: `adb install -r` (로그인 세션 유지) → `adb shell am start -n com.hanbit.llack.llack_mobile/.MainActivity`
  (`monkey` 로 띄우면 Flutter 액티비티가 안 뜬다)
- 백엔드: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (PID **51532**, **`--reload` 없음**)
- 별도 미러 프로세스: `uvicorn app.main:app --host 127.0.0.1 --port 8001` (PID **70113**, **같은 `llack.db`** 를 쓰되
  **WS 허브는 별도 프로세스** → 앱의 WS 가 못 듣는 이벤트를 만드는 용도. §9-46 실기에 쓴다.)
- 계정: hyunjin@hanbit.co.kr (김현진) · 앱은 `http://10.0.2.2:8000` 로 붙는다
- 자동 검사: `flutter analyze` → **No issues found** · `flutter test` → **132 passed** ·
  백엔드 `pytest -q` → **156 passed**
- 테스트 계정: 최수아(`sua@hanbit.co.kr`, 기획자) 토큰 `/tmp/sua_token` 로 API 발신

### §9-44 검증 — 스레드에 답글을 한 번만 보내도 2개로 보이나

`#engineering` 에서 정우진(데브옵스) 의 `로그stash 인덱스가 또 커졌네요. 일주일치만 롤링할까요?`
(12:39) 를 **길게 누르면** 액션 시트가 열린다 → `스레드로 답글 달기`.

| 순서 | 조작 | 화면에 보이는 것 |
|---|---|---|
| 1 | 길게 누르기 → `스레드로 답글 달기` | 스레드 화면 열림 |
| 2 | (열린 직후) | `답글 0개` + `아직 답글이 없습니다. 첫 답글을 남겨보세요.` |
| 3 | `threadreply1` 입력 → 전송 | **`답글 1개`** + 말풍선 **1개** (`threadreply1`, 06:11) |
| 4 | 뒤로 가기 → `#engineering` | 원본 메시지 아래 **`답글 1개 ›`** 링크 |
| 5 | `답글 1개 ›` 다시 탭 | **`답글 1개`** + 말풍선 **1개** — **여전히 1개** ✓ |

**DB 크로스체크** — 중복이 아니라 "화면에만 2개로 보이는" 문제였는지 확인:

```
$ sqlite3 backend/llack.db "select id, body, reply_count from messages where reply_count>0 …"
msg_01M6WWCMAMNYWDZ4DB7DH9AYY7 | 로그stash 인덱스가 또 커졌네요. … | reply_count= 1
$ sqlite3 backend/llack.db "select id, body from messages where parent_id is not null …"
msg_01M6YG1A86EJHDG51WZEMJE9ZQ | threadreply1
```

→ 부모 메시지의 `reply_count = 1`, 자식 행도 **정확히 1개**.
`sendReply` 의 HTTP 응답과 WS `message.created` 가 **같은 id 로 upsert** 되므로(id 기준 `upsertById`),
HTTP 를 먼저 받고 WS 를 나중에 받아도 **행이 하나만 남는다.**

### §9-45 검증 — 보고 있는 채널에 도착한 메시지가 안읽음 배지로 남는다

#### (1) 대화창이 열려 있고 최신 구간에 있을 때

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | 최수아(DM) 대화창을 **열어둔 상태**에서 최수아 계정으로 `read while open 5555` 발신 | 메시지가 **화면에 보인다** |
| 2 | 뒤로 가기 → DM 목록 | **배지 없음(0)** ✓ — 읽고 있는 채널에 온 건 배지로 남지 않는다 |
| 3 | DB 확인 | `read_states.last_read_message_id` = `msg_01M6YFTAZP7C2MJ3T9K3Z9SM0M` (`read while open 5555`) — **서버 앵커가 그 메시지까지 전진** ✓ |
| 4 | 앱 완전 재시작(콜드 스타트) → DM 목록 | **배지 없음(0)** ✓ — 서버에 앵커가 남았으므로 재시작해도 살아나지 않는다 |

#### (2) 대화창이 **닫혀 있을 때** (과잉 적용 회귀 확인)

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | 최수아(DM) 대화창을 **닫은 상태**에서 `closed conv check 6666` 발신 | — |
| 2 | DM 목록 | **배지 1** ✓ — 닫혀 있으면 당연히 안읽음으로 남아야 한다 |

#### (3) **위로 스크롤해 둔 상태**에서 메시지가 도착하는 경우 (이번 라운드의 핵심 케이스)

`#general` 을 열어 **최신 구간보다 위로 스크롤**한 상태(12:19 박지민 메시지가 보이는 지점)에서
최수아 계정으로 `scrolled up check 9999` 를 발신했다.

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | `#general` 열기 → 위로 스크롤 (최신 구간 아님) | 화면이 12:19 구간에 정지 ✓ |
| 2 | `scrolled up check 9999` 발신 (다른 계정) | **뷰가 최신 구간으로 튀지 않는다.** 새 메시지는 화면에 안 보임 |
| 3 | 뒤로 가기 → 채널 목록 | `#general` **배지 3** |
| 4 | DB 확인 | 서버의 실제 안읽음 개수도 **3** (`boot unread check 7777`, `reconnect miss check 8888`, `scrolled up check 9999` 가 앵커 이후 3건) — **배지 = 서버 값 정확히 일치, 이중 계상 없음** ✓ |
| 5 | `#general` 다시 열기 → **최신 구간까지 아래로 스크롤** | 최신 메시지 `scrolled up check 9999` (06:09) 가 최하단에 보임 |
| 6 | 뒤로 가기 → 채널 목록 | `#general` **배지 없음(0)** ✓ — 최신 구간으로 돌아오면 배지가 사라진다 |
| 7 | DB 확인 | 서버 앵커가 `msg_01M6YFXTNKXKQCBQESTKA3ECYH` (`scrolled up check 9999`) 로 **전진** ✓ |

> 3번과 4번이 핵심이다. **안 읽은 것으로 남아야 하는 경우(스크롤 중)에는 배지가 살아 있고**,
> 서버 숫자와 **정확히 같으며**(이중 계상 없음), **최신 구간으로 돌아오면 0 으로 사라지고 서버 앵커까지 전진**한다.

#### (4) 함께 확인한 회귀 없음

| 항목 | 결과 |
|---|---|
| 닫힌 대화방에 도착한 메시지 | **배지 1** (과잉 적용 안 함) |
| 열려 있는 대화방(최신 구간)에 도착한 메시지 | **배지 0** (누락 안 함) |
| 재시작 후 배지 | 서버 앵커가 유지되므로 **0** (부활 안 함) |
| 앱을 껐다 켜자마자 | 부활하지 않음 ✓ (콜드 부팅이 `selectChannel` 를 거치지 않는 경로도 무방) |
| 채널 목록 배지 숫자 | 서버 값과 **항상 일치** (로컬 증가 + 서버 절대값 덮어쓰기가 경합하지 않음) |

#### 실기 팁 (다음 라운드에)

- **Flutter 스크롤은 `adb shell input swipe` 로 굴지 않는다.**
  → `adb shell input motionevent DOWN 540 500` → `MOVE` 여러 번 → `UP` 시퀀스로 그린다.
- **스크롤 방향을 반대로 하면 아무 일도 안 일어난다(오해를 부르는 함정).**
  - *이전(오래된) 메시지* 보기 → 손가락을 **아래로** 드래그 (`DOWN y=500` → `UP y=1200`)
  - *최신 메시지* 보기 → 손가락을 **위로** 드래그 (`DOWN y=1200` → `UP y=400`)
  - 반대 방향으로 드래그하면 이미 최하단이라 **아무 변화가 없고**, "스크롤이 안 먹는다" 하고 잘못 판단한다.
- **드래그가 너무 빠르면 플링으로 튀어 원위치로 돌아온다.**
  `MOVE` 사이에 `sleep 0.05` 를 넣어 천천히 그릴 것.
- `adb shell input text` 는 **공백에서 잘리고 한글에서 죽는다** → 스페이스 없는 영문만 쓴다.
  (`threadreply1` 처럼)
- 키보드만 닫으려면 `adb shell input keyevent 4` (한 번만). 두 번 누르면 라우트까지 닫힌다.
- **배지 숫자는 "클라이언트 값"과 "서버 값"을 둘 다 봐야 한다.**
  화면의 배지가 맞아도 서버 앵커가 안 전진했으면 **재시작하면 부활**한다.
  → `read_states.last_read_message_id` 를 DB 에서 직접 확인하는 습관.



### §9-46 검증 — 놓친 실시간 이벤트가 대화방을 다시 열어도 복구되지 않는다

**재현 장치**: WS 허브가 **별도 프로세스**인 백엔드(포트 8001, PID 70113)를 하나 더 띄워 둔다.
두 프로세스는 **같은 `llack.db`** 를 쓰지만 WS 허브는 따로라, 8001 로 들어온 메시지는
앱(8000 에 붙어 있음)의 WS 에는 `message.created` 가 **전달되지 않는다.**
→ "앱이 놓친 이벤트" 를 정확히 재현할 수 있다.

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | 앱 콜드 스타트 → `#general` 열기 | 히스토리 로드됨 (최신 = `scrolled up check 9999`, 06:09) |
| 2 | **8001** 로 `missed via 8001 #1`, `missed via 8001 #2` 생성 | DB 에는 정상 저장 (06:16) |
| 3 | 앱 화면 확인 | **두 메시지가 보이지 않는다** ← 놓친 상태(재현 성공) |
| 4 | 뒤로 가기 → `#general` **다시 열기** | **두 메시지가 나타난다** ✓ (`merge` 로 기존 목록 뒤에 붙음) |
| 5 | 목록 확인 | 과거 메시지(`boot unread check 7777` 등)는 **그대로 살아 있다** ✓ (교체가 아니라 병합) |
| 6 | 뒤로 가기 → 배지 | `#general` **배지 없음(0)** ✓ |
| 7 | DB 확인 | 서버 앵커가 `missed via 8001 #2` 로 **전진** ✓ |

> 3행과 4행이 핵심이다. **수정 전에는 4행에서 두 메시지가 계속 안 보였다.**
> (배지만 당겨서 새로고침하면 따라오고 메시지는 영영 stale — plan §9-46 증상 표 3·4행)

**스크롤 위치 유지 (요구사항 2)**

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | `#general` 열기 → **위로 스크롤** (23:29 구간) | 오래된 구간에 정지 |
| 2 | 뒤로 가기 → 다시 열기 | **같은 위치**(23:29 구간)를 유지 ✓ (최신으로 튀지 않는다) |

**검색 점프 창 유지 (요구사항 4)**

| 순서 | 조작 | 결과 |
|---|---|---|
| 1 | 검색에 `reconnect` 입력 → 결과 탭 | `reconnect miss check 8888` 로 **점프 + 앰버 강조** ✓ |
| 2 | 뒤로 가기 → 다시 열기 | **점프 창이 유지**되고, 병합으로 최신 메시지(`missed via 8001 #1/#2`)도 목록 아래에 같이 보인다 ✓ |

**부수 발견 → §9-48**
병합 갱신 후 최하단으로 스크롤하면 백엔드 로그에 **0건짜리 `after=` 요청** 이 찍혔다.
```
GET …/messages?limit=40&after=msg_01M6YGAANVQDTEMK01HHHM1KF2  200 OK   ← after 가 최신 id
```
`_hasMoreNewer` 의 의미가 `loadMessages` 와 `refreshNewestMessages` 에서 달라서 생긴 문제다. → **§9-48** 로 분리.

**부수 발견 → §9-47 (중대)**
§9-46 실기 중 **백엔드를 재시작**했을 때, 앱의 WS 가 **1초마다 영원히 재접속**하기 시작했다
(`[WS] disconnected` 가 1.01초 간격, 서버 로그에 초당 1회 `connection open`).
원인은 백엔드가 아니라 **클라이언트**였다 — 액세스 토큰(TTL 30분) 이 만료되었는데
`WsService` 가 토큰을 `connect()` 에서 복사해 두고 **갱신된 토큰을 모른다.**
→ **§9-47** 로 분리.

#### 실기 팁 (이번 라운드 추가)

- **WS 를 "놓친 이벤트" 를 재현하려면 WS 허브가 분리된 프로세스가 필요하다.**
  같은 프로세스 안에서 메시지를 만들면 WS 로 곧바로 전달되므로 재현이 안 된다.
  → 같은 DB 를 쓰는 uvicorn 을 포트 하나 더 띄우면 된다. (`--reload` 없이)
- **앱이 WS 를 못 쓰는 상태를 만들려면 백엔드를 재시작하면 된다.**
  (`svc wifi disable` 은 QEMU 브리지(10.0.2.2)에 영향이 없어 소켓이 끊기지 않는다)
- **서버 로그에서 `connection open` 의 개수**로 재접속 루프의 빈도를 바로 알 수 있다.

---

## 18차 라운드 (2026-11-09 · 에뮬레이터 Pixel_7_API_36 실기 — profile APK)

### 9-47. [MAJOR] **액세스 토큰이 만료되면 실시간 연결이 영영 돌아오지 않는다** — 1초마다 재접속 무한 루프 (담당 A)

#### 증상 (실기 확인, 2026-11-09 06:16~06:22 · profile APK · 계정 hyunjin@hanbit.co.kr)

앱을 켜고 **30분쯤** 쓰고 있었다가(액세스 토큰 TTL = 30분) 갑자기 실시간이 죽었다.

| 순서 | 관찰 | 내용 |
|---|---|---|
| 1 | 앱 화면 | 빨간 배너: `실시간 연결이 끊어졌습니다: 연결이 끊어졌습니다.` ← **문구 중복** |
| 2 | 백엔드 로그 | `WebSocket /api/v1/ws?token=...` → `connection open` 이 **초당 1회** 계속 찍힘 |
| 3 | logcat | `[WS] disconnected` 가 **1.01초 간격**으로 무한 반복 |
| 4 | **REST 는 멀쩡함** | `GET …/messages` → 401 → `POST /auth/refresh` 200 → 재시도 200 (자동 갱신이 동작함) |
| 5 | 서버 로그(토큰 만료 토큰으로 직접 연결) | `received 4401 (private use); then sent 4401` — **만료된 토큰이면 4401 로 닫는다** |

→ **핵심 모순: REST 는 새 토큰으로 살아 있는데, WS 는 죽은 토큰으로 붙고 있다.**
→ 사용자는 "앱이 얼었다", "새 메시지가 안 와" 라고 느낀다.
→ 실시간(새 메시지·읽음·typing·presence)이 **전부 죽어 있는데 아무도 모른다.**
→ 동시에 서버는 초당 1회 WS 연결 시도를 맞는다.

#### 원인 (4 가지가 겹친다)

**1) WS 는 토큰을 "한 번만" 받아서 계속 쓴다.**
```dart
// mobile/lib/services/ws_service.dart:44-53
void connect({required String baseUrl, required String token}) {
  _baseUrl = baseUrl;
  _token = token;        // ← 이 값이 평생 고정된다
  ...
}
```
`_open()` 은 `_token` 으로 URI 를 만든다. **토큰이 갱신돼도 WS 는 옛 토큰으로 붙는다.**

**2) REST 는 알아서 토큰을 갱신한다. (WS 와의 불일치)**
```dart
// mobile/lib/services/api_service.dart:119-124, 155-172
if (res.statusCode == 401 && retry && _refreshToken != null) {
  final renewed = await _refreshAccessToken();   // ← 새 토큰을 저장한다
  ...
}
```
→ `api.accessToken` 은 갱신되지만 **`ws` 는 그 사실을 모른다.**

**3) 서버는 만료된 토큰의 WS 를 `4401` 로 닫고, 클라이언트는 그 코드를 구분하지 않는다.**
```python
# backend/app/api/v1/realtime.py:36-40
if user is None:
    await websocket.accept()
    await websocket.close(code=AUTH_FAILED)   # 4401
    return
```
클라이언트 쪽 `onDone` 은 "그냥 끊겼다" 로만 처리한다. (4401 인지 모른다)

**4) 백오프가 리셋되어 1초 무한 루프가 된다.**
```dart
// mobile/lib/services/ws_service.dart:72-76
channel.ready.then((_) {
  if (_closed || _channel != channel) return;
  _attempt = 0;      // ← 붙었다가 1초 만에 죽어도 attempt 가 0 으로 돌아간다
```
`ready` 는 "TCP 연결 + WS 핸드셰이크 성공" 이다. **연결이 즉시 죽어도 attempt = 0** 이 되고,
`_scheduleReconnect` 의 delay = `1 << _attempt` = **1초**.
→ **초당 1회로 영원히 재접속.** (서버 부담 + 배터리 + 로그 범람)

#### 요구사항

1. **WS 는 매번 현재 유효한 토큰으로 붙어야 한다.**
   - 토큰을 `connect()` 에서 복사해서 들고 있지 말고, **연결 시점에 조회**해야 한다.
2. **4401(인증 실패)을 구분해야 한다.**
   - 4401 이면 토큰을 갱신(또는 재로그인)한 뒤 **한 번만** 다시 시도한다.
   - 그래도 실패하면 "세션이 만료되었습니다" 를 **정확한 한국어로** 알리고 무한 재시도하지 않는다.
3. **재접속 루프를 멈춰야 한다.**
   - 백오프를 **연결이 실제로 살아 있을 때만** 리셋한다. (즉시 죽으면 attempt 를 줄이지 않는다)
   - 연속 실패 시 최소 재접속 간격을 둔다.
4. **UI 가 정직해야 한다.**
   - 배너 문구 중복(`실시간 연결이 끊어졌습니다: 연결이 끊어졌습니다.`)을 없앤다.
   - "인증 만료" 와 "일시적 단절" 을 구분해서 보여준다.
5. **회귀 금지**: 정상 연결/재연결, §9-45 읽음 배지, §9-46 재동기화(`hello` → bootstrap/최신 병합),
   로그아웃, typing, presence, 읽음 확인.

#### 모바일 코어 계약 (담당 A)

**A-1. `lib/services/ws_service.dart` — 토큰을 연결 시점에 조회한다.**
```dart
/// 토큰을 "복사"하지 말고, 연결할 때마다 최신 토큰을 물어본다.
typedef WsTokenProvider = String? Function();

void connect({required String baseUrl, required WsTokenProvider tokenProvider});
```
- `_open()` 안에서 `final token = _tokenProvider?.call();` 로 **그 시점의** 토큰을 받는다.
- 토큰이 null 이면 붙지 않는다(로그인 상태가 아님).
- `AppState` 는 `tokenProvider: () => api.accessToken` 로 넘긴다.
- (기존 `token:` 파라미터는 **제거**하거나 호환을 유지하되, 주 경로는 provider 다.)

**A-2. `lib/services/ws_service.dart` — 4401 을 구분한다.**
- `onDone` 에서 종료 코드(`channel.closeCode` / `sink.closeReason`) 를 확인한다.
- `closeCode == 4401` 이면:
  - **토큰 갱신을 한 번** 시도한다. (ApiService 에 "토큰을 갱신해 달라" 는 콜백을 준다)
  - 갱신 성공 → 그 토큰으로 **즉시** 다시 연결(1회).
  - 갱신 실패(리프레시 토큰도 만료) → **재시도를 멈추고**
    "세션이 만료되었습니다. 다시 로그인해주세요." 상태로 바꾼다.
- 4401 이 아닌 일반 단절은 기존처럼 백오프 재접속.

**A-3. `lib/services/ws_service.dart` — 백오프가 즉시 죽어도 리셋되지 않는다.**
- `_attempt = 0` 은 "연결이 **일정 시간 이상 유지**되었을 때" 만 한다. (예: 10초)
- 그 전에는 attempt 를 되돌리지 않는다 → 1초 → 2초 → 4초 → 8초 → 16초 → 30초 로 늘어난다.
- **최소 재접속 간격**을 둔다. (예: 5초)
- 목표: 장애 30초 안에 **연결 시도 5회 이하.**

**A-4. `lib/services/api_service.dart` — 토큰 갱신 알림.**
- `setTokens()` 이 성공하면 `onTokensChanged` 같은 콜백을 호출한다.
- `AppState` 는 여기서 WS 를 새 토큰으로 다시 연결한다. (A-1 과의 이중 안전망)

**A-5. `lib/providers/app_state.dart` — 상태를 구분한다.**
- `_connectionError` 가 "일시적 단절" 과 "인증 만료(4401)" 를 구분할 수 있게 한다.
- 인증 만료면 "세션이 만료되었습니다. 다시 로그인해주세요." (그리고 로그인 화면으로 유도)

**A-6. `lib/widgets/connection_banner.dart` — 문구 중복 제거.**
> **소유권 추가**: 이 파일은 어느 에이전트 소유권에도 없었으므로, **담당 A** 로 명시한다.
- `'실시간 연결이 끊어졌습니다: $error'` 에서 error 가 이미 "연결이 끊어졌습니다." 라서
  `실시간 연결이 끊어졌습니다: 연결이 끊어졌습니다.` 가 된다.
- 한 문장으로 정리한다. (suffix 가 겹치면 "실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다." 형태)

#### 테스트

**단위 (담당 A)**
- 토큰이 갱신되면 **다음 연결이 새 토큰**으로 간다 (옛 토큰 아님)
- `closeCode 4401` → 토큰 갱신 요청이 **한 번** 일어나고, 새 토큰으로 재연결한다
- 토큰 갱신까지 실패 → **재시도하지 않는다** + "세션 만료" 상태가 된다
- 즉시 죽는 연결(ready 직후 onDone)이면 **백오프가 커진다** (1초 → 2초 → 4초 …)
- 정상적으로 오래 유지된 연결은 **다음 장애 때 백오프를 리셋**한다
- `hello` 수신 시 §9-46 재동기화가 **한 번만** 일어난다 (루프 때문에 여러 번 아님)

**실기 (내가 한다)**
1. 토큰 만료 후에도 실시간이 복구된다 (새 메시지가 뜬다)
2. 재접속 시도가 초당 1회가 아니다 (서버 로그로 확인)
3. 배너 문구가 중복되지 않는다
4. 로그아웃 / 재로그인이 정상이다


### 9-48. [MINOR] **재진입 병합 갱신 후 "최신 더 불러오기" 가 쓸데없이 한 번 더 요청된다** (담당 A)

#### 증상 (실기 확인, 2026-11-09 06:17 · profile APK)

§9-46 병합 갱신(`refreshNewestMessages`) 으로 대화방을 다시 연 뒤, 목록 최하단으로 스크롤하면
백엔드 로그에 **불필요한 요청** 이 찍힌다.

```
GET /api/v1/channels/chl_01M6WWCM9YDMB322Y86TDGAQJT/messages?limit=40&after=msg_01M6YGAANVQDTEMK01HHHM1KF2  200 OK
```
`after=` 는 **가장 최신 메시지 id** 다. → 서버가 돌려줄 메시지가 **0건**인 요청이다.

#### 원인

`_hasMoreNewer` 의 의미가 두 경로에서 다르다.

```dart
// mobile/lib/providers/app_state_messages.dart:8-28  loadMessages (평상시 로드)
_hasMoreNewer[channelId] = false;          // "최신 위치이므로 더 최신 메시지는 없다"
```
```dart
// mobile/lib/providers/app_state_messages.dart:43-78  refreshNewestMessages (병합 갱신)
_hasMoreNewer[channelId] = oldNewest == null || _compareMessages(newNewest, oldNewest) > 0;
// → "새로 발견한 최신 메시지가 있다" 라는 **다른 의미**의 값이 들어간다
```
병합 갱신은 **서버의 최신 40개** 를 받아온 것이므로, 그 시점에는 **더 최신 메시지가 없다.**
→ 값은 `false` 여야 한다. (`true` 가 되면 스크롤이 최하단에서 `loadNewerMessages` 를 한 번 더 호출한다)

#### 요구사항

1. `refreshNewestMessages` 가 끝나면 `_hasMoreNewer[channelId] = false` (서버의 최신 40개를 받은 것이므로).
2. `_newerCursor` 는 **뒤로 물러나지 않게** 갱신한다.
   (기존 커서보다 오래된 id 로 낮아지지 않아야 한다)
3. 회귀 금지: 검색 점프(around) 후 `loadNewerMessages` 경로, 과거 더 보기(`before`).

#### 테스트 (단위, 담당 A)

- 병합 갱신 후 `_hasMoreNewer` 가 `false` 다 (새 메시지를 새로 발견했더라도)
- 병합 갱신 후 `_newerCursor` 가 최신 id 다
- 병합 갱신 후 최하단 스크롤에서 `after=` 요청이 **나가지 않는다**

---

## 19차 라운드 실기 검증 결과 (2026-11-09 · profile APK · 에뮬레이터 Pixel_7_API_36)

§9-47 (액세스 토큰 만료 → 실시간 영영 복구 불가 · 1초 무한 재접속) 과
§9-48 (재진입 병합 갱신 후 불필요한 `after=` 요청) 을 프로필 APK 로 빌드해서 **실기**로 확인했다.

- 빌드: `flutter build apk --profile` → `build/app/outputs/flutter-apk/app-profile.apk` (**104.3MB**, 06:29)
- 설치: `adb install -r` → `adb shell am start -n com.hanbit.llack.llack_mobile/.MainActivity`
- 백엔드: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (`--reload` 없음) · 로그 `/tmp/backend.log`
- 자동 검사: `flutter analyze` → **No issues found** · `flutter test` → **146 passed** (기존 137 + 신규 9)
  · 백엔드 `pytest -q` → **156 passed** (백엔드 무변경)
- 계정: hyunjin@hanbit.co.kr (김현진) · 앱은 `http://10.0.2.2:8000`

### 재현을 위해 만든 환경 (토큰 TTL 을 90초로)

원래 액세스 토큰 TTL 은 30분이라 "30분 동안 기다리기" 가 필요하다.
그래서 백엔드를 **`ACCESS_TOKEN_TTL_SECONDS=90`** 으로 잠깐 띄워서
"토큰이 빨리 만료되는 situations" 을 바로 만들어 냈다.

```bash
# backend/
ACCESS_TOKEN_TTL_SECONDS=90 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

→ 로그인 토큰이 `iat 06:31:49 / exp 06:33:19` (90초) 로 발급되는 것을 확인했다.
(테스트가 끝나면 **기본값(1800초) 으로 되돌린 서버**로 교체했다. )

### §9-47 검증 — 액세스 토큰이 만료돼도 실시간이 복구된다

#### (1) 4401 을 받고 토큰을 갱신한 뒤 **다시 붙는다**

| 시각 | 주체 | 로그 |
|---|---|---|
| 06:31:49 | 앱 | 로그인 → `POST /auth/login 200` → `WebSocket … [accepted]` / `connection open` |
| 06:33:09 | 서버 | 앱이 들고 있는 액세스 토큰 **만료** (`exp 06:33:19`) |
| 06:33:26 | 백엔드 | 재시작 → 소켓 끊김 |
| 06:33:26.210 | 앱 logcat | `[WS] disconnected (code=1012)` |
| 06:33:31.253 | 앱 logcat | **[WS] disconnected (code=4401)** ← 만료 토큰으로 붙었다가 인증 실패로 닫힘 |

**백엔드 로그 (그 구간 그대로):**

```
INFO:     WebSocket /api/v1/ws?token=… [accepted]      ← 만료 토큰
INFO:     connection open
INFO:     POST /api/v1/auth/refresh HTTP/1.1" 200 OK    ← ★ 토큰 갱신 1회
INFO:     WebSocket /api/v1/ws?token=… [accepted]      ← ★ 새 토큰으로 즉시 재연결
INFO:     connection open
INFO:     GET  …/bootstrap  200 OK                     ← hello 재동기화 (§9-46)
INFO:     GET  …/messages?limit=40  200 OK
```

- 4401 을 **구분해서** 잡고, 토큰 갱신을 **한 번만** 시도하고, 성공하면 **즉시** 새 토큰으로 붙었다. ✓
- 새 토큰: `iat 06:33:31 / exp 07:03:31` (30분) — 옛 토큰이 아니다. ✓

#### (2) **초당 1회 무한 루프가 사라졌다** (제일 중요)

| 항목 | 이전(§9-47 증상) | 이번 실기 |
|---|---|---|
| 장애 뒤 연결 시도 | **1.01초 간격 무한 반복** | **총 2회** (4401 1회 + 성공 1회) |
| 백엔드 `connection open` | 매초 찍힘 | 1회 |
| logcat `[WS] disconnected` | 매초 찍힘 | 1012 1회 + 4401 1회 |

→ 5초 뒤 1회 재접속(백오프 하한), 4401 은 백오프 없이 즉시 복구.
→ **서버를 초당 1회씩 때리지 않는다.** ✓

#### (3) 실시간이 실제로 살아 있다

복구 직후 최수아 계정으로 `#general` 에 `realtime recovery check 7777` 을 API 발신 →
**앱 화면에 배지 1 로 즉시 도착.** (WS 가 살아 있다) ✓

#### (4) 배너 문구가 중복되지 않는다 (A-6)

```
이전: 실시간 연결이 끊어졌습니다: 연결이 끊어졌습니다.
지금: 실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다.
```

백엔드를 죽인 직후(연결 끊김) 스크린샷으로 확인 → **중복 없음** ✓
(세션 만료 문구는 `세션이 만료되었습니다. 다시 로그인해주세요.` 로 한 문장.)

#### (5) 로그아웃 / 재로그인

설정 시트 → 로그아웃 → 로그인 화면으로 전환 ✓ → 다시 로그인 → WS 재연결 + 데이터 정상 로드 ✓

### §9-48 검증 — 재진입 병합 갱신 후 `after=` 요청이 없다

1. `#general` 대화방을 **나갔다가 다시 들어간다** (병합 갱신 `refreshNewestMessages` 경로)
2. 목록을 위로 올렸다가 **다시 최하단으로** 스크롤
3. 백엔드 로그 확인

```
$ tail -n +<MARK> /tmp/backend.log | grep messages
(아무것도 없음)
```

→ 이전에는 최하단 스크롤 때 `GET …/messages?limit=40&after=<최신 id>` (0건짜리) 가 찍혔는데,
**지금은 아예 요청이 없다.** ✓
(스크롤이 실제로 동작했는지는 화면 캡처로 확인 — 오래된 메시지 구간 → 최하단 이동 완료)

### 함께 확인한 회귀 없음

| 항목 | 결과 |
|---|---|
| §9-43 검색 점프 | `check` 검색 → 결과 탭 → `GET …/messages?limit=40&around=…` → **해당 메시지가 노란 테두리로 강조**되고 화면에 보임 ✓ |
| §9-45 읽음 배지 | 메시지 도착 시 배지 1 → 대화방 열면 **0** , `read_states.last_read_message_id` = 그 메시지 id 로 전진 ✓ |
| §9-46 재동기화 | `hello` 수신 후 재진입 병합이 **한 번만** 일어나 최신 메시지가 목록 끝에 붙음 ✓ |
| 메시지 전송 | `ws send check 8888` 전송 → 말풍선 **1개** (중복 없음) + DB 1행 ✓ |
| presence | 내가 온라인이면 초록 점, 다른 계정은 회색 점 ✓ |

### 테스트 데이터 정리

- 실기에 쓴 메시지 3건 삭제: `realtime recovery check 7777`, `ws send check 8888`,
  이전 라운드에서 남긴 긴 단어 테스트(`ThisIsAVeryLongMessage…`)
- `#general` `read_states` 앵커를 **남아 있는 최신 메시지**로 다시 pointing
  (`msg_01M6WWCMB1W9H4PY9F9V0ZC5Z9`)
- 검증: `#general` 메시지 수 **28개** (원래 값), 잔여 테스트 메시지 **0건**

### 남은 관찰 (수정하지 않음)

- 콜드 스타트 때 `bootstrap` 이 **2번** 불린다. (`_bootstrapWorkspaces` + `hello` → `_resyncAfterReconnect`)
  무해하지만 요청이 1회 늘어난다. (담당 A 보고 사항 — 다음 라운드에서 다룰지 판단)

---

## 19차 라운드 실기 검증 결과 — 2부: 세션 만료(만료 후 로그인 화면 복귀) 경로

같은 환경(profile APK · Pixel_7_API_36)에서 **리프레시 토큰까지 만료된** 경우를 추가로 만들었다.
(§9-47 앞부분은 액세스 토큰만 만료돼서 "토큰 갱신 후 재연결" 으로 복구되는 경로였다.
이번에는 **갱신까지 실패하는** 분기를 봤다.)

### 재현을 위해 만든 환경

```bash
ACCESS_TOKEN_TTL_SECONDS=60 REFRESH_TOKEN_TTL_SECONDS=5 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

→ 액세스 토큰 60초, 리프레시 토큰 5초. (설정값은 `app/core/config.py` 의 pydantic-settings 항목이라
환경변수로 덮어쓸 수 있다. 기본값은 1800초 / 30일.)

### 진행 순서

| 시각 | 동작 | 관찰 |
|---|---|---|
| 06:39:36 | 기기에서 로그인 (`hyunjin@hanbit.co.kr`) | `POST /api/v1/auth/login` 200, 토큰 `iat 06:39:36 / exp 06:40:36` (60초) |
| 06:39:37 | 소켓 연결 | `WebSocket /api/v1/ws?token=…` accepted → connection open |
| 06:40:47 | 백엔드 kill | 소켓 끊김 → 앱이 5초 뒤 재접속 예약 |
| 06:40:50 | 백엔드 재기동 (같은 짧은 TTL) | — |
| 06:40:52 | 앱이 **만료된** 액세스 토큰으로 재접속 | 서버가 4401 로 닫음 |
| 06:40:52 | 앱이 토큰 갱신 시도 | `POST /api/v1/auth/refresh` → **401 Unauthorized** |
| 06:40:52 | `clearTokens()` → `isAuthenticated == false` | 앱이 로그인 화면으로 전환 |

### 백엔드 로그 (재기동 이후 구간)

```
INFO:     Started server process [2061]
2026-11-09 06:40:51,255 INFO llack llack backend ready (database=sqlite+aiosqlite:///./llack.db)
INFO:     127.0.0.1:60870 - "WebSocket /api/v1/ws?token=eyJ…exp…MTU2…fQ.CuCbRnvy…" [accepted]
INFO:     connection open
INFO:     127.0.0.1:60871 - "POST /api/v1/auth/refresh HTTP/1.1" 401 Unauthorized
```

재기동 이후 **WebSocket 재접속 시도 1회, refresh 1회**뿐이었다. (60초 뒤 다시 확인해도 그대로였다.)

```
$ sed -n '863,$p' /tmp/backend.log | grep -c "WebSocket /api/v1/ws"   # → 1
$ sed -n '863,$p' /tmp/backend.log | grep -c "auth/refresh"            # → 1
```

→ **무한 재연결 루프 없음.** ✓ (A-2 / §9-47 계약 충족)

### 앱 화면 (06:41:08 캡처)

로그인 폼으로 정확히 복귀했다. ✓ (A-5 "로그인 화면으로 유도" 충족)
그런데 **화면에 아무 안내가 없었다.**

- 오류 박스 없음 (`state.authError` 는 로그인 실패 때만 채워진다 → 여기선 `null`)
- 세션 만료 문구 없음 (`WsService.sessionExpiredMessage` 는 WS 배너용이고, 배너는 `MainShell` 안에 있어서
  로그인 화면으로 전환되면 **보이지 않는다**)
- 이메일 칸이 비어 있어 사용자가 처음부터 다시 입력해야 했다.

→ **A-5 의 "메시지를 보여주고 로그인 화면으로 유도" 중 앞부분이 실제로는 전달되지 않는다.**
(상태 플래그 `AppState.isSessionExpired` 는 이미 만들어져 있었고 값도 `true` 였다. **UI 가 이를 쓰지 않았다.**)

---

## 20차 라운드에서 고칠 것 (19차 라운드에서 새로 발견한 결함)

| ID | 증상 (실기에서 본 것) | 원인 | 담당 | 수정 파일 |
|---|---|---|---|---|
| **F-1** | 세션 만료로 튕겨 로그인 화면에 왔는데 **왜 튕겼는지 안내가 전혀 없다**. 사용자는 비밀번호를 다시 맞게 눌러보다 실패하고 "계정이 잠겼다"고 오해한다. | `AppState.isSessionExpired` 는 `true` 로 세팅되지만, 이를 화면에 보여주는 코드가 없다. 배너는 `MainShell` 안에 있어 로그인 화면으로 전환되면 사라진다. | **C** | `lib/screens/auth_screen.dart` |
| **F-2** | 세션 만료(401)를 **"이메일 또는 비밀번호가 맞지 않습니다"** 로 말한다. 로그인 화면이 이미 떠 있는 상황이라 사용자를 완전히 잘못 안내한다. | `ApiService._request()` 가 **모든** 401 의 메시지를 "비밀번호가 틀렸다"로 고정. | **A** | `lib/services/api_service.dart` |
| **F-3** | 세션 만료 후 로그인 화면에서 **이메일을 다시 손으로 쳐야 한다.** | 만료 직전 사용자 이메일이 이미 `AppState.currentUser` 에 있다. | **C** | `lib/screens/auth_screen.dart` |
| **F-4** | 콜드 스타트 때 `bootstrap` 이 **2번**, `projects`/`events`/`org`/`tasks`/`roadmaps`/`milestones` 도 **각 2번** 불린다. (19차 라운드 "남은 관찰" 항목을 승격) | **최초** 연결의 `hello` 도 `_resyncAfterReconnect()` 를 태워 전체 워크스페이스를 다시 받아온다. | **A** | `lib/providers/app_state*.dart`, `lib/services/ws_service.dart` |

**배정 근거**

- F-1 / F-3 은 화면 쪽이라 **C 소유**(`auth_screen.dart`). `AppState` 에 이미 `isSessionExpired` / `currentUser` 가
  공개되어 있으므로 **A 소유 파일을 건드리지 않고** C 단독으로 해결된다. (에이전트 간 계약 충돌 없음)
- F-2 / F-4 는 데이터/상태 쪽이라 **A 소유**. `api_service.dart` 와 `app_state*.dart` 는 서로 겹치지 않는다.

**F-4 가 위험한 이유 (주의)**

재동기화를 통째로 없애면 안 된다. 소켓이 실제로 끊겼다가 다시 붙었을 때 놓친 실시간 이벤트를 복구하는 장치이기 때문이다.
따라서 "**세션의 첫 `hello` 에만** 건너뛰고, 재연결 후의 `hello` 에서는 그대로 재동기화" 로 제한해야 한다.
로그아웃 → 재로그인 후에도 "첫 `hello` = 재동기화 없음" 으로 되돌아와야 한다.

### 테스트 데이터 정리 (19차 라운드 추가분)

- 기기에서 로그아웃 → 재로그인 (06:42:22). 서버는 **기본 TTL** 로 되돌려 재기동했고, 로그인 API 200 확인.
- 검증 중 지운 테스트 메시지(`realtime recovery check 7777`, `ws send check 8888`) 는 DB 에서 사라져 있고,
  앱 화면에만 남아 있던 캐시 사본은 다음 진입에서 갱신된다. (`messages` 테이블에 `body like '%check%'` 0건 확인)
- `#design` 채널이 목록에 안 보이는 것은 **버그가 아니다.** `design` 은 private 이고 김현진이 멤버가 아니다.
  (멤버: 박지민 · 이채원 · 최수아. `#release` 는 김현진이 멤버라 자물쇠와 함께 보인다.)

---

## 20차 라운드 — 실기에서 발견한 결함 수정 및 검증 (2026-11-09)

19차 라운드에서 만든 "세션 만료" 재현 환경을 그대로 써서, 20차 라운드에서 고친 것들을 기기에서 다시 검증했다.

### 구현 내역 (Pi · minimax/MiniMax-M3.1-Flash)

| ID | 내용 | 담당 | 수정 파일 |
|---|---|---|---|
| F-1 | 세션 만료 안내 박스를 로그인 화면에 표시 | C | `lib/screens/auth_screen.dart` |
| F-2 | 401 을 "비밀번호가 틀렸다" 로 말하지 않음 | A | `lib/services/api_service.dart` |
| F-3 | 세션 만료로 튕기면 이메일을 자동 채움 | C | `lib/screens/auth_screen.dart` |
| F-4 | 콜드 스타트 `bootstrap` 중복 제거 (2회 → 1회) | A | `lib/providers/app_state*.dart` |
| F-5 | 콜드 스타트 일정/프로젝트/조직도 중복 요청 제거 | A(플래그) + C(화면) | `lib/providers/app_state*.dart`, `lib/screens/{schedule,projects,org}/*.dart` |

### F-1 / F-3 실기 검증 (profile APK · Pixel_7_API_36)

재현: `ACCESS_TOKEN_TTL_SECONDS=60 REFRESH_TOKEN_TTL_SECONDS=5` 로 백엔드 재기동 → 기기에서 로그인
→ 65초 뒤 백엔드 kill/재기동 → 소켓 끊김 → 만료된 토큰으로 재접속 → 4401 → refresh 401.

백엔드 로그:

```
INFO:     127.0.0.1:64189 - "WebSocket /api/v1/ws?token=eyJ…exp…NTU2…fQ.HjqOR52Q…" [accepted]
INFO:     connection open
INFO:     127.0.0.1:64190 - "POST /api/v1/auth/refresh HTTP/1.1" 401 Unauthorized
```

재접속 **1회**, refresh **1회**뿐 (무한 루프 없음 — §9-47 유지 ✓)

**화면 (06:49 캡처):**

```
┌────────────────────────────────────────────┐
│ ⓘ  세션이 만료되었습니다. 다시 로그인해주세요. │
│    보안 정책상 연결이 끊겨 로그인 화면으로     │
│    돌아왔습니다. 같은 계정으로 다시           │
│    로그인해주세요.                            │
└────────────────────────────────────────────┘
이메일    hyunjin@hanbit.co.kr     ← 자동 채움 ✓
비밀번호  (비어 있음)                        ← 자동 채우지 않음 ✓
```

→ 19차 라운드에서 "안내가 전혀 없다"던 문제가 해결됐다. ✓
→ 빨간 오류 박스(비밀번호 오류)와 구분되는 **중립색(accent)** 박스라 오해하지 않는다. ✓
→ 수동 로그아웃(06:47 캡처)에서는 이 박스가 **떠지 않는다**. (노이즈 없음 ✓)

### F-4 실기 검증 (콜드 스타트)

새 APK 설치 후 콜드 스타트 → 백엔드 로그:

```
"GET /api/v1/workspaces/wsp_.../bootstrap" 200 OK   ← 1회 (전에는 2회)
```

→ 19차 라운드 "남은 관찰" 이었던 bootstrap 중복이 사라졌다. ✓
(원인: 최초 연결의 `hello` 가 `_resyncAfterReconnect()` 를 태우던 것.
`AppState._hasSeenHello` 플래그로 "세션의 첫 hello = 재연결 아님" 을 구분하고,
`logout()` / `login()` / `signup()` 에서 초기화한다. **재연결 후의 `hello` 에서는 재동기화가 그대로 돈다.**)

### F-5 실기 검증 (콜드 스타트)

**원인:** `MainShell` 의 `IndexedStack` 이 탭 화면 4개를 앱 시작과 동시에 모두 만들어,
`initState` 의 `postFrameCallback` 로더가 Core 의 `_loadWorkspaceData()` 로더와 **겹쳐** 요청이 2회씩 나던 것.

**수정:** A 가 Core 에 "로더가 성공했는지" 신호 3종을 추가하고, C 가 세 화면의 `initState` 를 그 신호로 가드했다.

```dart
// lib/providers/app_state_core.dart
bool get hasLoadedEvents   => _hasLoadedEvents;    // loadEvents() 성공 시 true
bool get hasLoadedProjects => _hasLoadedProjects;  // loadProjects() 성공 시 true
bool get hasLoadedOrg      => _hasLoadedOrg;       // loadOrg() 성공 시 true
```

```dart
// lib/screens/schedule/schedule_screen.dart
if (!state.hasLoadedEvents) state.loadEvents();
// lib/screens/projects/projects_screen.dart
if (!state.hasLoadedProjects) state.loadProjects();
// lib/screens/org/org_screen.dart
if (!state.hasLoadedOrg) state.loadOrg();
```

- 판정 기준은 **목록이 비었는지**가 아니라 **로더가 성공했는지**다.
  빈 워크스페이스에서는 `hasLoaded* == true` 가 되므로 중복 요청이 사라진다.
- `refreshWorkspace()` · `logout()` · 워크스페이스 전환 시 플래그를 초기화해 다음 진입 때 다시 불러온다.
- 당겨서 고침(pull-to-refresh)은 플래그와 무관하게 **항상** 로더를 직접 호출한다 (기존 동작 유지).

**콜드 스타트 실측** (F-5 반영 APK 재설치 → 기기 강제 종료 → 재기동, 백엔드 로그):

```
"GET /api/v1/me"                                            200   ← 1회
"GET /api/v1/workspaces"                                    200   ← 1회
"GET /api/v1/workspaces/wsp_.../bootstrap"                  200   ← 1회
"GET /api/v1/workspaces/wsp_.../events"                     200   ← 1회
"GET /api/v1/channels/chl_.../messages?limit=40"            200   ← 1회
"GET /api/v1/workspaces/wsp_.../projects"                   200   ← 1회
"GET /api/v1/projects/prj_.../roadmaps"                     200   ← 1회
"GET /api/v1/projects/prj_.../tasks"                        200   ← 1회
"GET /api/v1/projects/prj_.../milestones"                   200   ← 1회
"GET /api/v1/workspaces/wsp_.../org"                        200   ← 1회
"WebSocket /api/v1/ws?token=…"                              [accepted] ← 1회
```

→ 수정 전에는 `events / projects / roadmaps / milestones / tasks / org` 가 **각 2회**씩 나갔다.
이제 **전부 각 1회**다. ✓

### F-2 실기 결과

`api_service.dart` 의 401 분기는 경로로 구분한다.

- `POST /auth/login` · `POST /auth/signup` → "이메일 또는 비밀번호가 맞지 않습니다."
- 그 밖의 경로 → "세션이 만료되었습니다. 다시 로그인해주세요." (서버 메시지에 만료/토큰/세션 키워드가 있으면 서버 문구를 그대로 쓴다)

기기에서 재현되는 표면은 좁다. refresh 가 실패하면 `clearTokens()` 가 먼저 일어나
`isAuthenticated == false` → **앱이 로그인 화면으로 튕겨나가므로**, 401 문구 자체가 렌더링되기 전에
F-1 의 세션 만료 안내 박스로 사용자에게 설명이 도착한다. 즉 F-1 이 1차 설명, F-2 가 2차 안전망이다.
F-2 는 실제 `HttpServer` 를 세운 6개 단위 테스트로 검증했다. (`mobile/test/auth_401_message_test.dart`)

### 회귀 없음

| 항목 | 결과 |
|---|---|
| `flutter analyze` | No issues found! |
| `flutter test` | **172 tests, All tests passed!** (기존 149 + 신규 23) |
| `backend pytest` | 156 passed (백엔드 무변경) |
| 수정 금지 파일 | `lib/main.dart`, `lib/screens/chat/**`, `lib/widgets/message_*`, `android/**`, `pubspec.yaml` 무수정 |

### 신규 테스트 파일 (20차 라운드)

| 파일 | 담당 | 케이스 |
|---|---|---|
| `test/auth_session_expired_test.dart` | C | 4 — 안내 박스 표시/미표시, 이메일 자동 채움, 비밀번호 자동 채우지 않음, 사용자가 지운 이메일 재채우지 않음 |
| `test/auth_401_message_test.dart` | A | 6 — 실제 `HttpServer` 로 401 분기 검증 |
| `test/hello_resync_test.dart` | A | 3 — 첫 hello 재동기화 없음 / 재연결 hello 재동기화 / 로그아웃→로그인→첫 hello |
| `test/section_loaded_flags_test.dart` | A | 6 — 로더 플래그 성공/실패/빈 목록/워크스페이스 전환/로그아웃/새로고침 |
| `test/tab_duplicate_load_test.dart` | C | 7 — 세 화면의 중복 요청 0회/1회 + 새로고침은 항상 1회 |
| `test/reconnect_resync_test.dart` | A | 갱신 — `hello` 2회 emit 후 재연결 시 bootstrap +1, 병합 메시지 1회 |

### 환경 복구

검증 후 백엔드를 **기본 TTL** 로 되돌려 재기동했다 (`ACCESS_TOKEN_TTL_SECONDS=60 REFRESH_TOKEN_TTL_SECONDS=5` 해제).
앱은 정상 로그인 상태로 두었다.

---

## 21차 라운드 — 실기 탐색에서 발견한 결함 (2026-11-09)

20차 라운드(F-1~F-5) 반영분을 profile APK 로 다시 빌드해 기기에 설치하고,
손으로 한 바퀴 돌면서 새로 발견한 결함 3건이다. **전부 에뮬레이터 Pixel_7_API_36 실기에서 재현**했고,
백엔드 로그로 교차 확인했다.

### F-6. [MAJOR] 프로젝트 탭에 당겨서 고침(새로고침)이 없다 — 담당 C

**재현 (같은 제스처로 탭을 돌려봄)**

| 탭 | 당겨서 고침 | 백엔드 로그 |
|---|---|---|
| 일정 | 동작 ✓ | `GET /workspaces/wsp_.../events` **1회** |
| 조직도 | 동작 ✓ | `GET /workspaces/wsp_.../org` **1회** |
| 메시지 | 동작 ✓ | `RefreshIndicator` 있음 |
| **프로젝트** | **동작하지 않음 ✗** | **요청 0회** |

**원인** — `lib/screens/projects/projects_screen.dart` 에 `RefreshIndicator` 가 없다.
같은 역할의 다른 화면은 모두 있다.
- `lib/screens/schedule/schedule_screen.dart:248` → `onRefresh: () => state.loadEvents()`
- `lib/screens/org/org_screen.dart:94` → `onRefresh: () => state.loadOrg()`
- `lib/screens/chat/chat_tab.dart:40` → `onRefresh: () => state.refreshWorkspace()`

**사용자 영향** — 다른 탭에서는 당기면 갱신되는데 프로젝트 탭에서는 아무 일도 일어나지 않는다.
모바일에서 데이터가 오래됐을 때 새로고침할 수단이 사라진다.

### F-7. [MAJOR] 삭제된 메시지가 실제 메시지와 구분되지 않는다 — 담당 B

**재현** — `#general` 에 삭제된 메시지가 쌓여 있었을 때, 대화방이 "(삭제된 메시지)" 만 가득한 벽이 됐다.
내 메시지 9개 + 타인 메시지 2개가 전부 삭제 상태였는데, 각각이 실제 메시지와 **똑같은 크기·무게감**으로
아바타/작성자 이름/직함/타임스탬프/말풍선을 그대로 차지하고 있었다.
"삭제된 줄 하나"와 "진짜 메시지 하나"의 차이가 거의 없어 화면 절반 이상이 회색 줄로 채워진다.

**원인** — `lib/widgets/message_bubble.dart`
- 타인 메시지 삭제: line 298~305 — 아바타 + `_buildHeader()`(이름·직함·타임스탬프) + 이탤릭 "(삭제된 메시지)"
- 내 메시지 삭제: line 222~224 — 오른쪽 정렬 말풍선 안에 "(삭제된 메시지)"

**원칙** — 삭제된 메시지는 조용한 **한 줄**이어야 한다. 아바타도 이름도 타임스탬프도 말풍선도 없이.
연속된 삭제 메시지는 한 줄로 합친다.

### F-8. [MAJOR] "나 일정만" 필터가 달력 점에는 적용되지 않는다 — 담당 C

**재현 (07:01 캡처)**

- 일정 탭 상단 "나 일정만" 칩을 켜면(✓) 그 아래 **하루 목록**은 내 일정만 보여준다.
- 그런데 **같은 화면의 달력은 필터를 무시한다.**
  - 필터 ON + 11월 9일 선택 → 목록은 "0개의 일정 / 등록된 일정이 없습니다"
  - 그런데 달력의 **9일에는 회색 점(팀 일정)이 그대로 남아 있다**
    (9일 일정은 남이 만든 것이고 나는 참석자가 아니다)
  - 11월 15일 선택 → 목록에 "1:1 (김현진 ↔ 최수아)" 정상 표시 (내 일정이라 초록 점)
- 즉 **"점을 보라니 일정 있다" 고 눌렀더니 목록은 비어 있다** — 달력과 목록이 서로 모순한다.

**원인** — `lib/screens/schedule/schedule_screen.dart`

```dart
// _buildMonthGrid() — 필터를 전혀 안 본다
final dayEvs = state.events.where((e) => _isSameDay(e.startsAt.toLocal(), date)).toList();
final hasMyEvent = dayEvs.any((e) => e.createdBy == myId || e.attendees.any((a) => a.user.id == myId));
final hasTeamEvent = dayEvs.isNotEmpty;

// 하루 목록 — 필터를 적용한다 (line 109~121)
if (onlyMyEvents) {
  final isMine = e.createdBy == myId || e.attendees.any((a) => a.user.id == myId);
  return isMine;
}
```

**수정 방향** — "내 일정" 판정을 헬퍼 하나로 모으고 **목록과 달력이 같은 판정** 을 쓴다.
필터 ON 이면 그날 일정이 전부 남의 것이면 **점을 아예 그리지 않는다**(회색 점도).
필터 OFF 의 기존 동작(내 일정=초록, 팀만=회색)은 유지하고, 범례의 "팀 일정" 도 필터에 맞춰 숨긴다.

### 함께 확인한 정상 동작 (수정 대상 아님)

- WS 단절 시 배너 "실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다." 노출 → 백엔드 복구 후 배너 자동 소멸 ✓
- 재연결 시 `bootstrap` + `messages?limit=40` 1회씩 수행하고 데이터가 정상 복구됨 ✓
- 채널 정보 시트의 "참여 중인 멤버 (5)" 는 스크롤하면 5명 모두 보인다 (DB `channel_memberships` 5건과 일치) ✓
- 검색 → 결과 탭 → 해당 메시지로 점프 + 강조 표시 ✓
- 긴 누르기 액션 시트(답글/인라인/핀/복사/수정/삭제) 동작 ✓

### 테스트 데이터 정리 (21차 라운드)

- 이전 라운드의 삭제 테스트로 남은 **소프트 삭제 메시지 17건** 을 하드 삭제
  (연결된 `message_attachments` 1건도 함께 삭제, `reactions`·답글·핀 참조는 0건)
- 그중 3건이 `read_states` 앵커를 가리키고 있어서, 해당 채널의 **최신 생존 메시지** 로 앵커를 다시 pointing
- 실기에서 만든 테스트 메시지 `ux-test-round21` 1건은 앱 안에서 삭제(액션 시트 → 메시지 삭제 → `DELETE /api/v1/messages/... 204`)
- 검증: `#general` 메시지 **14건**(원래 시드 데이터만 남음), 소프트 삭제 잔여 **0건**

### 배정

| ID | 내용 | 담당 | 수정 파일 |
|---|---|---|---|
| F-6 | 프로젝트 탭 당겨서 고침 추가 | C | `lib/screens/projects/projects_screen.dart` |
| F-7 | 삭제된 메시지를 컴팩트 한 줄로 | B | `lib/widgets/message_bubble.dart` |
| F-8 | "나 일정만" 필터를 달력 점에도 적용 | C | `lib/screens/schedule/schedule_screen.dart` |

### 구현 내역 (Pi · minimax/MiniMax-M3.1-Flash)

| ID | 구현 |
|---|---|
| F-6 | `projects_screen.dart` 의 빈 목록 화면과 카드 목록(`TabBarView`) 양쪽에 `RefreshIndicator` 추가. 카드 목록 쪽은 `notificationPredicate: (n) => n.depth <= 1 && n.metrics.axis == Axis.vertical` 로 **depth 1 알림**까지 받는다. `onRefresh: () => state.loadProjects()` |
| F-7 | `message_bubble.dart` 에 `MessageDeletedMarker` 위젯 추가 — 2dp×12dp 옅은 세로선 + `LlackColors.muted` 한 줄. 아바타·작성자·직함·타임스탬프·말풍선 없음. `deletedCount` 로 연속 삭제 구간을 "삭제된 메시지 N개" 로 합침(`chat_screen.dart` 에서 연속 삭제 병합). 빠른 반응/복사 액션도 삭제 메시지에서는 숨김 |
| F-8 | `schedule_screen.dart` 에 순수 함수 3개 추가 — `isMyScheduleEvent()` / `visibleScheduleEvents()` / `calendarDotForDay()`. **하루 목록과 달력 점이 같은 판정**(`visibleScheduleEvents`)을 공유. 필터 ON 이면 그날 일정이 전부 남의 것이면 점을 아예 그리지 않고, "팀 일정" 범례도 숨김 |

### F-6 실기 검증 (profile APK · Pixel_7_API_36)

프로젝트 탭에서 아래로 당긴 뒤 백엔드 로그를 확인했다.

```
$ adb shell input swipe 540 500 540 1500 800
$ tail -n +$((MARK+1)) /tmp/backend.log | grep -oE '"GET [^"]+ HTTP/1.1" [0-9]+' | sort | uniq -c
   1 "GET /api/v1/projects/prj_01M6WWCMCV62QPX8JB9R7FG3GH/milestones HTTP/1.1" 200
   1 "GET /api/v1/projects/prj_01M6WWCMCV62QPX8JB9R7FG3GH/roadmaps HTTP/1.1" 200
   1 "GET /api/v1/projects/prj_01M6WWCMCV62QPX8JB9R7FG3GH/tasks HTTP/1.1" 200
   1 "GET /api/v1/workspaces/wsp_01M6WWCM9WY7YTSHNQ89V7WKKQ/projects HTTP/1.1" 200
```

| | 수정 전 | 수정 후 |
|---|---|---|
| 프로젝트 탭 당겨서 고침 | **요청 0회** ✗ | **요청 4회** ✓ (projects/roadmaps/milestones/tasks 각 1회) |

**함정 기록 — `RefreshIndicator` 의 알림 깊이.**
`TabBarView` 안에 있는 `ListView` 의 스크롤 알림은 **depth 1** 로 올라온다.
`RefreshIndicator` 의 기본 `notificationPredicate` 는 depth 0 만 받으므로,
`TabBarView` 안에서는 당겨도 **조용히 아무 일도 일어나지 않는다**.
→ depth 0 만 받아서 되는 화면(일정·조직도)과 달리, 중첩 스크롤이 있는 화면은
`notificationPredicate: (n) => n.depth <= 1 && n.metrics.axis == Axis.vertical` 가 필요하다.

### F-7 실기 검증 (profile APK · Pixel_7_API_36)

`#general` 에 테스트 메시지 3개를 만들고 API 로 소프트 삭제한 뒤 대화방을 열었다.

**수정 전** — 3줄이 각각 아바타 + 이름 + 직함 + 타임스탬프 + 말풍선을 차지했다
("(삭제된 메시지)" 벽).

**수정 후** — 통째로 **한 줄**:

```
│ 삭제된 메시지 3개
```

아바타·작성자·직함·타임스탬프·말풍선이 없고, 옅은 세로선 하나와 작은 글씨만 있다.
연속 삭제 구간이 **1줄로 합쳐지는 것**까지 함께 확인했다.

### F-8 실기 검증 (profile APK · Pixel_7_API_36)

기준 데이터(DB 확인): 11월 9일의 "디자인 리뷰" 는 **박지민이 만든 일정**이고 참석자는
박지민·이채원·최수아. 로그인한 사용자(김현진)는 **작성자도 참석자도 아니다** → 팀 일정.

**필터 OFF** — 9일에 **회색 점(팀 일정)** 이 있고, 8·11·12·15일에는 초록 점(내 일정).
범례에 "내 일정" 과 "팀 일정" 이 둘 다 보인다. (DB 와 정확히 일치 ✓)

**필터 ON ("내 일정만" 체크)** — 9일의 회색 점이 **아예 사라진다**.
11·12·15일의 초록 점은 그대로 남고, "팀 일정" 범례도 숨겨진다.
9일을 선택하면 목록은 "0개의 일정 / 등록된 일정이 없습니다" 로,
**점과 목록이 이제 모순되지 않는다.**

| | 수정 전 | 수정 후 |
|---|---|---|
| 필터 ON + 9일 | 회색 점 있음 + 목록 0건 (모순) | **점 없음** + 목록 0건 (일치) ✓ |
| 필터 ON 범례 | "내 일정" + "팀 일정" | "내 일정" 만 ✓ |
| 필터 OFF | 회색/초록 구분 유지 | **그대로 유지** ✓ |

### 회귀 없음

- `flutter analyze` → No issues found
- `flutter test` → **193 passed** (신규 3개 파일: `deleted_message_bubble_test.dart` 7 · `projects_refresh_test.dart` 4 · `schedule_only_my_filter_test.dart` 10)
- `backend pytest` → **156 passed** (변경 없음)

### 테스트 데이터 정리 (21차 라운드 · 추가분)

- F-7 실기 검증용으로 만든 소프트 삭제 메시지 3건(`f7-tombstone-1/2/3`) 을 **하드 삭제**
- 그중 1건이 `read_states` 앵커를 가리키고 있어서 `#general` 의 최신 생존 메시지
  (`msg_01M6WWCMB1W9H4PY9F9V0ZC5Z9`) 로 앵커를 다시 pointing
- 검증: `#general` 메시지 **14건**, 소프트 삭제 잔여 **0건**
