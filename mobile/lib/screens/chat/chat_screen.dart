import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:file_picker/file_picker.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/message_composer.dart';
import '../../widgets/presence_badge.dart';
import 'channel_info_dialog.dart';
import 'chat_message_item.dart';
import 'chat_messages_error_state.dart';
import 'chat_scroll_memory.dart';
import 'message_actions.dart';
import 'thread_screen.dart';
import '../../widgets/connection_banner.dart';

class ChatScreen extends StatefulWidget {
  final bool showBackButton;

  const ChatScreen({super.key, this.showBackButton = false});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final ScrollController _scrollController = ScrollController();

  /// 중첩 ScaffoldMessenger 의 키.
  /// (스낵바가 메시지 영역에만 그려져 composer 를 가리지 않게 한다)
  final GlobalKey<ScaffoldMessengerState> _messengerKey =
      GlobalKey<ScaffoldMessengerState>();

  /// 점프 대상 항목에 붙이는 키.
  ///
  /// 점프는 **한 번에 하나의 메시지**로만 하므로 키도 하나만 쓴다.
  /// (메시지마다 키를 만들면 과거를 많이 불러올 때마다 맵이 무한히 커지고,
  ///  같은 id 의 메시지가 다시 등장했을 때 GlobalKey 중복 위험이 생긴다)
  final GlobalKey _jumpKey = GlobalKey(debugLabel: 'jump-target');

  /// 검색 결과로 점프해 강조한 메시지 id
  String? _highlightedMessageId;

  /// 점프(스크롤 + 강조) 진행 중인지
  bool _isJumping = false;

  /// 점프 대기 중 재시도 횟수 (무한 대기 방지)
  int _jumpRetryCount = 0;

  /// 점프에 실패한 대상 id.
  /// (코어가 pending 을 지우지 않아도 같은 대상을 계속 시도하지 않도록 막는다)
  String? _failedJumpTarget;

  /// 점프 재시도 상한
  static const int _maxJumpRetries = 10;

  /// 최신 방향으로 더 불러오는 중인지
  bool _loadingNewer = false;

  /// ListView 의 기본 cache extent.
  /// 점프할 때는 대상 항목이 아직 빌드되지 않았을 수 있어 크게 늘린다.
  static const double _defaultCacheExtent = 250;
  static const double _jumpCacheExtent = 100000;

  /// 지금 보고 있는 채널 id
  String? _channelId;

  /// 코어(AppState) 참조.
  /// (dispose 에서 context 를 쓰지 않고 훅을 해제하기 위해 필드에 보관한다)
  late final AppState _state;

  /// 코어에 등록한 "최신 구간인가" 훅 (자기 소유 확인용)
  bool Function(String channelId)? _visibilityHook;

  /// 직전 스크롤에서 최신 구간에 붙어 있었는지.
  /// (위로 스크롤해 있다가 다시 최신 구간으로 내려왔을 때 읽음 처리하기 위해)
  bool _wasAtBottom = true;

  /// 새 메시지 도착을 감지하기 위한 이전 메시지 수
  int _lastMessageCount = 0;

  /// 과거 메시지를 불러오는 중인지 (이때는 자동 스크롤하지 않는다)
  bool _loadingOlder = false;

  /// 채널 전환 후 복원할 "최신으로부터의 거리". null 이면 복원할 위치 없음.
  double? _pendingRestoreDistance;

  /// 새 메시지 때문에 최신 구간으로 따라가야 하는 상태
  bool _followBottom = false;

  double _lastKeyboardInset = 0;

  /// 채널별 임시저장 글.
  ///
  /// (코어에도 같은 내용을 `state.setDraft` 로 기록한다.
  ///  코어에 남는 이유는 대화창이 새로 만들어져도(모바일은 채널마다 새 화면을 push 한다)
  ///  작성 중인 글이 사라지지 않아야 하기 때문이다)
  final Map<String, String> _drafts = {};

  /// composer 를 다시 만들기 위한 값. (채널이 바뀌면 증가한다)
  int _composerGeneration = 0;

  /// composer 를 찾기 위한 키. (입력창 컨트롤러를 얻는 데 쓴다)
  final GlobalKey _composerKey = GlobalKey(debugLabel: 'message-composer');

  /// 채널을 바꾼 순간의 임시저장 글.
  ///
  /// (composer 가 처음 알리는 "빈 글" 때문에 지워지지 않도록 미리 잡아 둔다)
  String _pendingDraft = '';

  /// 임시저장을 복원하는 중인지 (복원할 때 "입력 중" 신호를 보내지 않기 위해)
  bool _restoringDraft = false;

  /// "최신 메시지" 버튼을 보여줄지 (과거를 보고 있을 때만)
  bool _showJumpToLatest = false;

  /// 프로그램이 스크롤하는 중인지 (버튼이 깜빡이지 않도록)
  bool _autoScrolling = false;

  @override
  void initState() {
    super.initState();
    _state = context.read<AppState>();
    // 대화창이 열려 있는 동안에만 "최신 구간인가" 를 알려준다.
    // (닫으면 null = 사용자가 그 채널을 보고 있지 않다)
    _visibilityHook = (cid) => _isNearBottom();
    _state.isNewestMessageVisible = _visibilityHook;
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    // 대화창이 닫히면 코어가 "보고 있지 않다" 고 알 수 있게 훅을 해제한다.
    // (다른 대화창이 이미 자기 훅을 등록했다면 건드리지 않는다)
    if (identical(_state.isNewestMessageVisible, _visibilityHook)) {
      _state.isNewestMessageVisible = null;
    }
    _scrollController.dispose();
    super.dispose();
  }

  // ── 스크롤 ────────────────────────────────────────────────────

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;

    // 채널별 위치 기억 (최신 메시지로부터의 거리)
    final cid = _channelId;
    if (cid != null) {
      ChatScrollMemory.save(cid, position.maxScrollExtent - position.pixels);
    }

    // 위로 스크롤해 있다가 **다시 최신 구간으로 내려왔을 때** 읽음 처리한다.
    // (그동안 안읽음으로 남았던 메시지를 실제로 보게 된 순간)
    // _onScroll 은 아주 자주 불리므로 "최신 구간에 붙었다" 는 상태가 바뀔 때만 호출한다.
    final atBottom = _isNearBottom();
    if (atBottom && !_wasAtBottom) {
      _markReadIfUnread();
    }
    _wasAtBottom = atBottom;

    // 과거를 보고 있으면 "최신 메시지" 버튼을 띄운다.
    _updateJumpButton(atBottom);

    // 위쪽 끝에 가까우면 과거 메시지를 더 불러온다.
    if (position.pixels <= position.minScrollExtent + 80) {
      _loadOlder();
    }

    // 아래쪽 끝에 가까우면 최신 메시지를 더 불러온다.
    // (점프 후에도 최신까지 갈 수 있어야 한다)
    if (position.pixels >= position.maxScrollExtent - 80) {
      _loadNewer();
    }
  }

  /// 안읽음이 남아 있는 채널이면 읽음 처리한다.
  ///
  /// 이미 읽음 처리된 채널은 서버에 갱신 요청을 보낼 이유가 없다.
  /// (읽음 신호가 폭탄으로 나가지 않도록 게이트한다)
  void _markReadIfUnread() {
    final cid = _channelId;
    if (cid == null) return;
    final channel = _state.activeChannel;
    if (channel == null || channel.unreadCount <= 0) return;
    _state.markChannelRead(cid);
  }


  /// 최신 방향으로 더 불러온다.
  /// 추가되는 메시지는 목록 **아래**에 붙으므로 스크롤 위치 보정은 필요 없다.
  Future<void> _loadNewer() async {
    if (_loadingNewer || _isJumping) return;
    final state = context.read<AppState>();
    final cid = state.activeChannelId;
    if (cid == null || !state.hasMoreNewerMessages) return;

    _loadingNewer = true;
    try {
      await state.loadNewerMessages(cid);
    } finally {
      _loadingNewer = false;
    }
  }

  /// 스레드 화면을 연다.
  void _openThread(BuildContext context, Message msg) {
    final state = context.read<AppState>();
    state.openThread(msg);
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ThreadScreen(rootMessage: msg),
      ),
    );
  }

  /// 검색 결과로 점프한 메시지로 이동한다.
  ///
  /// [ListView.builder] 는 lazy 라 대상 메시지가 아직 빌드되지 않았을 수 있다.
  /// 그래서 점프 대기 중에는 cache extent 를 크게 키워 **목록 전체가 빌드되게** 하고,
  /// 그 다음 `Scrollable.ensureVisible` 로 대상을 화면 가운데로 옮긴다.
  void _beginJump(String messageId) {
    _isJumping = true;
    _jumpRetryCount = 0;
    _highlightedMessageId = messageId;
    // 점프가 우선한다 (채널별 스크롤 위치 복원보다)
    _pendingRestoreDistance = null;
    _followBottom = false;
    WidgetsBinding.instance.addPostFrameCallback((_) => _performJump(messageId));
  }

  Future<void> _performJump(String messageId) async {
    if (!mounted) return;
    final target = _jumpKey.currentContext;
    if (target == null) {
      // 아직 빌드되지 않았다 → cache extent 를 크게 둔 상태에서 한 프레임 더 기다린다
      if (_jumpRetryCount++ > _maxJumpRetries) {
        _failJump(messageId);
        return;
      }
      WidgetsBinding.instance.addPostFrameCallback((_) => _performJump(messageId));
      return;
    }

    await Scrollable.ensureVisible(
      target,
      alignment: 0.35,
      duration: const Duration(milliseconds: 300),
    );
    if (!mounted) return;

    // 점프가 끝나면 cache extent 를 원래 값으로 되돌린다.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() => _isJumping = false);
    });
    context.read<AppState>().clearPendingFocusMessageId();
  }

  /// 점프에 실패했다 (대상 메시지를 찾지 못함).
  ///
  /// pending 을 **반드시** 지워야 한다.
  /// 지우지 않으면 build 가 매번 다시 점프를 시도해 무한 루프가 된다.
  void _failJump(String messageId) {
    // 같은 대상을 계속 시도하지 않도록 **즉시** 기록한다 (무한 루프 방지).
    // (build 중에 호출될 수 있으므로 상태 변경은 전부 다음 프레임으로 미룬다)
    _failedJumpTarget = messageId;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final state = context.read<AppState>();
      // 코어가 pending 을 지우도록 요청한다 (무한 루프의 근본 원인 제거)
      state.clearPendingFocusMessageId();
      setState(() {
        _isJumping = false;
        _highlightedMessageId = null;
      });

      final messenger = _messengerKey.currentState;
      messenger
        ?..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(
            content: Text('해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.'),
          ),
        );
    });
  }

  /// 사용자가 직접 스크롤하면 강조를 푼다.
  bool _handleUserScroll(UserScrollNotification notification) {
    // 점프 애니메이션 중의 스크롤은 무시한다 (강조가 바로 사라지면 안 된다)
    if (_isJumping) return false;
    if (notification.direction != ScrollDirection.idle &&
        _highlightedMessageId != null) {
      setState(() => _highlightedMessageId = null);
    }
    return false;
  }

  /// 사용자가 최신 구간에 붙어 있는지
  bool _isNearBottom() {
    if (!_scrollController.hasClients) return true;
    final p = _scrollController.position;
    return p.maxScrollExtent - p.pixels <= 120;
  }

  /// "최신 메시지" 버튼을 보여줄지 갱신한다.
  ///
  /// (최신 구간이 아니면 화면 아래에 버튼을 띄운다)
  void _updateJumpButton(bool atBottom) {
    if (!mounted) return;
    final show = !atBottom && !_autoScrolling;
    if (show == _showJumpToLatest) return;
    setState(() => _showJumpToLatest = show);
  }

  /// 화면이 그려진 뒤 스크롤 상태를 현재 데이터에 맞춘다.
  void _scheduleScrollSync() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _syncScroll();
    });
  }

  void _syncScroll() {
    if (!mounted || !_scrollController.hasClients) return;
    // 점프가 진행 중이면 위치 복원보다 점프를 우선한다
    if (_isJumping) return;
    final position = _scrollController.position;

    // 1) 채널이 바뀌었을 때: 저장된 위치(또는 최신)로 이동
    final pending = _pendingRestoreDistance;
    if (pending != null) {
      // 메시지가 아직 로드되지 않았으면 다음 빌드에서 다시 시도한다.
      if (context.read<AppState>().activeMessages.isEmpty) return;
      _pendingRestoreDistance = null;
      final target = (position.maxScrollExtent - pending)
          .clamp(position.minScrollExtent, position.maxScrollExtent)
          .toDouble();
      _scrollController.jumpTo(target);
      return;
    }

    // 2) 새 메시지가 도착했을 때: 최신 구간으로 따라간다.
    if (_followBottom) {
      _followBottom = false;
      _scrollToBottom(animate: true);
    }
  }

  /// 최신 메시지가 보이도록 스크롤한다.
  Future<void> _scrollToBottom({bool animate = false}) async {
    // 프로그램이 움직이는 동안에는 "최신 메시지" 버튼을 숨긴다. (깜빡임 방지)
    _autoScrolling = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted || !_scrollController.hasClients) {
        _autoScrolling = false;
        return;
      }
      final p = _scrollController.position;
      if (animate) {
        await _scrollController.animateTo(
          p.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      } else {
        _scrollController.jumpTo(p.maxScrollExtent);
      }
      if (!mounted || !_scrollController.hasClients) {
        _autoScrolling = false;
        return;
      }
      // 리스트가 늦게 레이아웃되면 최대 스크롤 범위가 더 커질 수 있다.
      // 그래도 최신 구간에 붙어 있도록 한 번 더 보정한다.
      final pos = _scrollController.position;
      if (pos.maxScrollExtent - pos.pixels > 8) {
        _scrollController.jumpTo(pos.maxScrollExtent);
      }
      _autoScrolling = false;
      _updateJumpButton(_isNearBottom());
    });
  }

  /// 과거 메시지를 불러온다.
  /// 목록 맨 위에 항목이 추가되므로 스크롤 오프셋을 그만큼 늘려야
  /// 사용자가 보고 있던 메시지가 화면에서 밀리지 않는다.
  Future<void> _loadOlder() async {
    // 점프 중에는 자동 로딩을 건드리지 않는다 (위치/강조가 흔들린다)
    if (_loadingOlder || _isJumping) return;
    final state = context.read<AppState>();
    final cid = state.activeChannelId;
    if (cid == null) return;
    if (!state.hasMoreActiveMessages || state.isLoadingActiveMessages) return;

    _loadingOlder = true;
    final position = _scrollController.position;
    final beforeOffset = position.pixels;
    final beforeMax = position.maxScrollExtent;

    await state.loadMessages(cid, more: true);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _loadingOlder = false;
      if (!_scrollController.hasClients) return;
      final p = _scrollController.position;
      final delta = p.maxScrollExtent - beforeMax;
      final target =
          (beforeOffset + delta).clamp(p.minScrollExtent, p.maxScrollExtent).toDouble();
      _scrollController.jumpTo(target);
    });
  }

  // ── 임시저장 (draft) ─────────────────────────────────────────

  /// 파일을 골라 워크스페이스에 올리고, (이름, 파일 id) 목록을 돌려준다.
  ///
  /// 취소하면 null, 업로드가 실패하면 사용자에게 알리고 null 을 돌려준다.
  Future<List<(String, String)>?> _uploadAttachments(
    BuildContext context,
    AppState state,
  ) async {
    List<PlatformFile> picked;
    try {
      picked = await FilePicker.pickFiles();
    } catch (_) {
      picked = const [];
    }
    if (picked.isEmpty) return null;

    final uploaded = <(String, String)>[];
    for (final file in picked) {
      final path = file.path;
      if (path == null) continue;
      try {
        final ref = await state.uploadFile(path, fileName: file.name);
        uploaded.add((file.name, ref.id));
      } catch (e) {
        if (!context.mounted) return null;
        showAppSnackBar(context, '파일을 올리지 못했습니다: $e');
        return null;
      }
    }
    return uploaded;
  }

  /// composer 안의 입력 컨트롤러를 찾는다.
  ///
  /// MessageComposer 는 입력창을 자기 안에서 만들어서 밖에서 줄 수 없다.
  /// (남의 파일을 고치지 않기 위해) 만들어진 입력창의 컨트롤러를 찾아 쓴다.
  TextEditingController? _composerInputController() {
    final ctx = _composerKey.currentContext;
    if (ctx == null) return null;
    return _findTextField(ctx)?.controller;
  }

  /// 하위 트리에서 첫 번째 [TextField] 를 찾는다.
  ///
  /// (composer 안에는 메시지 입력창 하나뿐이다)
  TextField? _findTextField(BuildContext ctx) {
    TextField? found;
    ctx.visitChildElements((element) {
      if (found != null) return;
      final widget = element.widget;
      if (widget is TextField) {
        found = widget;
        return;
      }
      found = _findTextField(element);
    });
    return found;
  }

  /// 입력창의 글자가 바뀔 때 채널별 임시저장으로 남긴다.
  void _handleDraftChanged(String channelId, String text) {
    _drafts[channelId] = text;
    _state.setDraft(channelId, text);
  }

  /// composer 가 만들어진 뒤에 저장해 둔 임시저장 글을 되돌린다.
  void _scheduleDraftRestore() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _restoreDraftIntoComposer();
    });
  }

  /// 저장해 둔 임시저장 글을 입력창에 다시 넣는다.
  ///
  /// 채널을 바꿨다가 돌아왔을 때 쓰던 글자가 그대로 있어야 한다.
  void _restoreDraftIntoComposer() {
    final draft = _pendingDraft;
    if (draft.isEmpty) return;

    final controller = _composerInputController();
    if (controller == null) return;
    if (controller.text == draft) return;

    // 복원하는 동안에는 "입력 중" 신호를 보내지 않는다.
    // (글자를 되돌린 것인데 상대방에게 "입력 중" 으로 뜨면 이상하다)
    _restoringDraft = true;
    controller.text = draft;
    controller.selection = TextSelection.collapsed(offset: draft.length);
    _restoringDraft = false;
  }

  // ── 메시지 삭제 / 되돌리기 ──────────────────────────────────────
  // (삭제 + "실행 취소" 는 스레드 화면과 공유하는 message_actions.dart 가 담당한다)

  // ── 헤더 ──────────────────────────────────────────────────────

  bool _isSameDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final channel = state.activeChannel;
    final myId = state.currentUser?.id;
    final channelId = state.activeChannelId;
    final messages = state.activeMessages;

    // 채널이 바뀌었으면 스크롤 위치를 리셋하고 저장된 위치(또는 최신)로 이동한다.
    if (channelId != _channelId) {
      _channelId = channelId;
      _failedJumpTarget = null;
      _highlightedMessageId = null;
      _pendingRestoreDistance =
          channelId == null ? null : ChatScrollMemory.load(channelId);
      _lastMessageCount = 0;
      // 되돌려 놓을 임시저장 글을 **지금** 잡아 둔다.
      // (composer 가 처음 알리는 "빈 글"에 지워지지 않도록 미리 빼 둔다)
      _pendingDraft = channelId == null
          ? ''
          : (_drafts[channelId] ?? _state.draftFor(channelId) ?? '');
      // 입력창을 새로 만들고(작성 중인 글은 임시저장에 남겨 둔다)
      // 저장해 둔 임시저장 글을 되돌린다.
      _composerGeneration++;
      _showJumpToLatest = false;
      _scheduleDraftRestore();
    }

    // 새 메시지가 도착했을 때, 사용자가 최신 구간에 있으면 따라간다.
    if (messages.length != _lastMessageCount) {
      final grew = messages.length > _lastMessageCount;
      _lastMessageCount = messages.length;
      if (grew &&
          !_loadingOlder &&
          !_isJumping &&
          _pendingRestoreDistance == null &&
          _isNearBottom()) {
        _followBottom = true;
      }
    }

    // 검색 결과로 점프할 대상이 목록에 있으면 스크롤 + 강조한다.
    // (코어가 주변 메시지를 불러오는 중이면 아직 목록에 없으니 다음 빌드에서 잡는다)
    final focusId = state.pendingFocusMessageId;
    if (focusId != null && !_isJumping && focusId != _failedJumpTarget) {
      if (messages.any((m) => m.id == focusId)) {
        _beginJump(focusId);
      } else if (!state.isLoadingActiveMessages) {
        // 로딩이 끝났는데 대상이 목록에 없다 → 찾을 수 없는 메시지
        _failJump(focusId);
      }
    }

    // 점프 실패 사유는 스낵바로 알린다.
    final focusError = state.focusErrorMessage;
    if (focusError != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final messenger = _messengerKey.currentState;
        messenger
          ?..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(focusError)));
        context.read<AppState>().clearFocusErrorMessage();
      });
    }

    // 키보드가 올라오면(입력 필드 포커스) 최신 메시지가 보이도록 스크롤한다.
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    if (keyboardInset > _lastKeyboardInset && _isNearBottom()) {
      _followBottom = true;
    }
    _lastKeyboardInset = keyboardInset;

    _scheduleScrollSync();

    if (channel == null) {
      return Scaffold(
        backgroundColor: LlackColors.paper,
        appBar: AppBar(
          title: const Text('대화'),
          // 실시간 연결이 끊어졌을 때도 알린다 (셸의 배너는 push 된 라우트에 가려진다)
          bottom: connectionBannerBottom(state),
        ),
        body: Center(
          child: Text(
            '선택된 대화방이 없습니다.\n채널이나 1:1 대화를 선택해주세요.',
            textAlign: TextAlign.center,
            style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
          ),
        ),
      );
    }

    final typingUsers = state.currentTypingUsers;
    final hasError = state.messagesError != null;

    // DM 상대방 presence
    Presence? dmPresence;
    if (channel.isDm) {
      final other = channel.dmUser ??
          ((channel.members != null && channel.members!.isNotEmpty)
              ? channel.members!.firstWhere((m) => m.id != myId, orElse: () => channel.members!.first)
              : null);
      if (other != null) {
        dmPresence = state.getPresence(other.id);
      }
    }

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: AppBar(
        automaticallyImplyLeading: widget.showBackButton,
        titleSpacing: widget.showBackButton ? 0 : 16,
        title: InkWell(
          onTap: () => showDialog(
            context: context,
            builder: (_) => ChannelInfoDialog(channel: channel),
          ),
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (channel.isDm) ...[
                  if (dmPresence != null) ...[
                    PresenceBadge(presence: dmPresence, size: 10),
                    const SizedBox(width: 8),
                  ],
                  // DM 이름이 길어도 앱바를 넘어가지 않도록 Flexible 로 감싼다.
                  Flexible(
                    child: Text(
                      channel.name,
                      style: LlackTypography.title,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ] else ...[
                  Icon(
                    channel.isPrivate ? Icons.lock_outline : Icons.tag,
                    size: 18,
                    color: LlackColors.accent,
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      channel.name,
                      style: LlackTypography.title,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline, size: 22),
            tooltip: '채널 정보',
            onPressed: () => showDialog(
              context: context,
              builder: (_) => ChannelInfoDialog(channel: channel),
            ),
          ),
        ],
        // 실시간 연결이 끊어졌을 때도 알린다 (셸의 배너는 push 된 라우트에 가려진다)
        bottom: connectionBannerBottom(state),
      ),
      body: ScaffoldMessenger(
        key: _messengerKey,
        // 이 화면 전용 messenger 를 둔다.
        // 루트(MaterialApp) messenger 는 ChatScreen 의 Scaffold 가 SnackBar 를
        // 화면 아래에 그려서 composer 를 덮는다. 중첩 messenger 를 두면
        // 메시지 영역의 Scaffold 만 SnackBar 를 그리기 때문에 composer 가 가려지지 않는다.
        child: Column(
          children: [
            if (channel.topic != null && channel.topic!.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                color: LlackColors.surfaceWell,
                child: Text(
                  channel.topic!,
                  style: LlackTypography.caption.copyWith(color: LlackColors.ink2),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),

            // 과거 메시지를 불러오는 중 표시
            if (state.isLoadingActiveMessages && messages.isNotEmpty)
               LinearProgressIndicator(
                minHeight: 2,
                color: LlackColors.accent,
                backgroundColor: LlackColors.surfaceWell,
              ),

            // Message list
            Expanded(
              child: Scaffold(
                // 메시지 영역 전용 Scaffold: SnackBar 가 이 영역 안에서만 그려진다.
                backgroundColor: Colors.transparent,
                // 키보드 처리는 바깥 Scaffold 가 이미 하므로 여기서는 중복으로 줄이지 않는다.
                resizeToAvoidBottomInset: false,
                body: state.isLoadingActiveMessages && messages.isEmpty
                    ? const Center(child: CircularProgressIndicator(strokeWidth: 2))
                    : hasError && messages.isEmpty
                        ? ChatMessagesErrorState(
                            message: state.messagesError ?? '메시지를 불러오지 못했습니다',
                            onRetry: state.retryMessages,
                          )
                        : messages.isEmpty
                            ? Center(
                                child: Text(
                                  '아직 메시지가 없습니다.\n첫 번째 메시지를 보내보세요!',
                                  textAlign: TextAlign.center,
                                  style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                                ),
                              )
                            : NotificationListener<UserScrollNotification>(
                                onNotification: _handleUserScroll,
                                // 메시지 목록 위에 "최신 메시지" 버튼을 띄운다.
                                child: Stack(
                                  fit: StackFit.expand,
                                  children: [
                                    ListView.builder(
                                      controller: _scrollController,
                                      // 점프 대기 중에는 목록 전체가 빌드되게 한다
                                      // (아직 빌드되지 않은 메시지로는 스크롤할 수 없다)
                                      scrollCacheExtent: ScrollCacheExtent.pixels(
                                        _isJumping ? _jumpCacheExtent : _defaultCacheExtent,
                                      ),
                                      padding: const EdgeInsets.symmetric(vertical: 8),
                                      itemCount: messages.length,
                                      itemBuilder: (ctx, i) {
                                        final msg = messages[i];
                                        final isMine = msg.userId == myId;

                                        final showDateHeader = i == 0 ||
                                            !_isSameDay(messages[i - 1].createdAt, msg.createdAt);

                                        // 삭제된 메시지는 조용한 한 줄로 그린다.
                                        // (연속으로 삭제된 메시지는 하나로 합친다)
                                        if (msg.deletedAt != null) {
                                          if (i > 0 && messages[i - 1].deletedAt != null) {
                                            // 앞 항목에 이미 합쳐서 그렸다
                                            return const SizedBox.shrink();
                                          }
                                          var run = 1;
                                          while (i + run < messages.length &&
                                              messages[i + run].deletedAt != null) {
                                            run++;
                                          }
                                          return ChatMessageItem(
                                            message: msg,
                                            isMine: isMine,
                                            showDateHeader: showDateHeader,
                                            deletedCount: run,
                                            fileUrlResolver: state.api.absoluteFileUrl,
                                            onOpenThread: () => _openThread(context, msg),
                                            onToggleReaction: (emoji) =>
                                                state.toggleReaction(msg, emoji),
                                            onTogglePin: () => state.togglePin(msg),
                                          );
                                        }

                                        return ChatMessageItem(
                                          message: msg,
                                          isMine: isMine,
                                          showDateHeader: showDateHeader,
                                          // 점프 대상에만 키를 붙인다
                                          jumpKey: msg.id == focusId ? _jumpKey : null,
                                          highlight: msg.id == _highlightedMessageId,
                                          fileUrlResolver: state.api.absoluteFileUrl,
                                          onOpenThread: () => _openThread(context, msg),
                                          onReplyInline: () => state.setReplyTo(msg),
                                          onToggleReaction: (emoji) =>
                                              state.toggleReaction(msg, emoji),
                                          onTogglePin: () => state.togglePin(msg),
                                          onEdit: (newBody) => state.editMessage(msg.id, newBody),
                                          // 메시지 목록 안의 context 를 넘겨야 가장 가까운
                                          // (중첩) messenger 를 잡아 스낵바가 composer 를 덮지 않는다.
                                          onDelete: () => MessageActions.deleteMessage(
                                            ctx,
                                            msg,
                                            channel.id,
                                          ),
                                        );
                                      },
                                    ),
                                    if (_showJumpToLatest)
                                      Positioned(
                                        right: 16,
                                        bottom: 12,
                                        child: _JumpToLatestButton(
                                          onPressed: () => _scrollToBottom(animate: true),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
              ),
            ),

            // Typing indicator
            if (typingUsers.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                child: Text(
                  '${typingUsers.join(', ')}님이 입력 중입니다...',
                  style: LlackTypography.caption.copyWith(
                    fontStyle: FontStyle.italic,
                    color: LlackColors.accent,
                  ),
                ),
              ),

            // Composer
            KeyedSubtree(
              // 입력창을 찾기 위한 키 (임시저장을 연결할 때 쓴다)
              key: _composerKey,
              child: MessageComposer(
                // 채널이 바뀌면 composer 를 새로 만들어서(입력창을 비우고)
                // 저장해 둔 임시저장 글을 되돌린다.
                key: ValueKey('composer-$channelId-$_composerGeneration'),
                // 채널마다 작성 중인 글을 따로 남긴다.
                initialText: _pendingDraft,
                replyTo: state.replyToMessage,
                onCancelReply: state.clearReplyTo,
                // 채널마다 작성 중인 글을 따로 남긴다.
                onChanged: (text) => _handleDraftChanged(channel.id, text),
                // 채널 id 를 함께 넘겨야 다른 채널에 "입력 중" 이 잘못 전송되지 않는다.
                onTyping: (typing) {
                  // 임시저장 글을 되돌린 경우에는 "입력 중" 을 보내지 않는다.
                  if (_restoringDraft) return;
                  state.sendTyping(typing, channel.id);
                },
                // 파일 첨부: 먼저 올리고, 그 id 를 메시지에 붙여 보낸다.
                onUploadAttachments: () => _uploadAttachments(context, state),
                onSendWithAttachments: (text, attachmentIds) async {
                  final ok = await state.sendMessage(text, attachmentIds: attachmentIds);
                  if (ok) {
                    // 보냈으면 임시저장을 지운다
                    state.setDraft(channel.id, '');
                    _drafts.remove(channel.id);
                    // 새 메시지를 보내면 강조를 푼다
                    if (_highlightedMessageId != null) {
                      setState(() => _highlightedMessageId = null);
                    }
                    _scrollToBottom(animate: true);
                  }
                  return ok;
                },
                onSend: (text) async {
                  final ok = await state.sendMessage(text);
                  if (ok) {
                    // 보냈으면 임시저장을 지운다
                    state.setDraft(channel.id, '');
                    _drafts.remove(channel.id);
                    // 새 메시지를 보내면 강조를 푼다
                    if (_highlightedMessageId != null) {
                      setState(() => _highlightedMessageId = null);
                    }
                    _scrollToBottom(animate: true);
                  }
                  return ok;
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "최신 메시지" 점프 버튼.
///
/// (과거를 보고 있을 때 화면 아래에 떠서 누르면 최신으로 간다)
class _JumpToLatestButton extends StatelessWidget {
  final VoidCallback onPressed;

  const _JumpToLatestButton({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: LlackColors.surfaceRaise,
      elevation: 2,
      shadowColor: Colors.black26,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(LlackTheme.radiusPill),
        side: BorderSide(color: LlackColors.rule),
      ),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(LlackTheme.radiusPill),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
               Icon(
                Icons.arrow_downward_rounded,
                size: 16,
                color: LlackColors.accent,
              ),
              const SizedBox(width: 6),
              Text(
                '최신 메시지',
                style: LlackTypography.caption.copyWith(
                  color: LlackColors.ink,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
