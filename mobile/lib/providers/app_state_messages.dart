part of 'app_state.dart';

/// 메시지(대화) 와 채널/DM 관리 부분.
abstract class _AppStateMessages extends _AppStateRealtime {
  _AppStateMessages({super.api, super.ws});
  // ── Messages & Realtime Chat ─────────────────────────────────

  Future<void> loadMessages(String channelId, {bool more = false}) async {
    if (_isLoadingMessages[channelId] == true) return;
    _isLoadingMessages[channelId] = true;
    _notify();

    try {
      final currentList = _messages[channelId] ?? [];
      final beforeId = more && currentList.isNotEmpty ? currentList.first.id : null;
      final (fetched, hasMore, _) = await api.getMessages(channelId, limit: 40, before: beforeId);

      if (more) {
        _messages[channelId] = [...fetched, ...currentList];
      } else {
        _messages[channelId] = fetched;
        // 최신 위치이므로 더 최신 메시지는 없다.
        _hasMoreNewer[channelId] = false;
        _newerCursor[channelId] = fetched.isNotEmpty ? fetched.last.id : '';
      }
      _hasMore[channelId] = hasMore;
      _historyLoaded.add(channelId);
      _messagesError = null;
    } catch (e) {
      debugPrint('[loadMessages error] $e');
      _messagesError = '메시지를 불러오지 못했습니다. 다시 시도해주세요.';
    } finally {
      _isLoadingMessages[channelId] = false;
      _notify();
    }
  }

  /// [channelId] 의 **최신 메시지**를 다시 가져와 기존 목록에 병합한다.
  ///
  /// (놓친 WS 이벤트를 복구하는 것이 목적)
  /// - 목록을 통째로 바꾸지 않는다 → 이미 불러온 과거 메시지와 스크롤 위치가 유지된다
  /// - id 로 upsert 한다 → `lib/providers/list_upsert.dart` 의 `upsertById` 를 재사용
  Future<void> refreshNewestMessages(String channelId) async {
    if (_isLoadingMessages[channelId] == true) return;
    _isLoadingMessages[channelId] = true;
    _notify();

    try {
      final (fetched, _, _) = await api.getMessages(channelId, limit: 40);
      final current = _messages[channelId] ?? [];
      if (fetched.isNotEmpty) {
        final newNewest = fetched.last;

        // 병합 (교체 아님) → 기존에 불러온 과거 메시지는 그대로 남는다.
        var merged = current;
        for (final msg in fetched) {
          merged = upsertById(merged, msg, (m) => m.id);
        }
        // 서버 정렬 기준(created_at, id) 으로 다시 정렬한다.
        merged.sort(_compareMessages);
        _messages[channelId] = merged;

        // 최신 커서는 서버에서 받은 마지막 메시지.
        // (뒤로 물러나지 않게: 기존 커서보다 오래된 값으로는 낮추지 않는다)
        final cursor = _newerCursor[channelId];
        var keepCursor = false;
        if (cursor != null && cursor.isNotEmpty) {
          final idx = merged.indexWhere((m) => m.id == cursor);
          if (idx != -1) {
            keepCursor = _compareMessages(newNewest, merged[idx]) < 0;
          }
        }
        _newerCursor[channelId] = keepCursor ? cursor! : newNewest.id;
        // 병합 갱신은 **서버의 최신 40개** 를 받아온 것이므로,
        // 그 시점에는 더 최신 메시지가 없다.
        _hasMoreNewer[channelId] = false;
      }
      // 과거 더 보기(_hasMore)는 병합이지 교체아니므로 그대로 둔다.
      // 히스토리를 이미 불렀다는 뜻으로 _historyLoaded 에는 넣지 않는다.
    } catch (e) {
      debugPrint('[refreshNewestMessages error] $e');
    } finally {
      _isLoadingMessages[channelId] = false;
      _notify();
    }
  }

  /// [messageId] 주변 메시지를 불러와 화면에 노출한다.
  /// 성공하면 true, 찾지 못하면 false.
  ///
  /// 목록은 기준 메시지를 가운데 둔 "창"으로 바뀐다.
  /// 실패하면 [focusErrorMessage] 에 한국어 사유를 남기고,
  /// 대화방은 실패를 성공인 척 하지 않고 최신 위치로 열린다.
  Future<bool> loadMessagesAround(String channelId, String messageId) async {
    final ok = await _loadMessagesAroundWindow(channelId, messageId);
    if (!ok) {
      await loadMessages(channelId);
    }
    return ok;
  }

  Future<bool> _loadMessagesAroundWindow(String channelId, String messageId) async {
    // 같은 채널의 로딩이 끝날 때까지 기다린다.
    // (겹치면 "창"이 최신 목록으로 덮어써져 점프가 사라진다)
    for (var i = 0; i < 100 && _isLoadingMessages[channelId] == true; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 30));
    }
    _isLoadingMessages[channelId] = true;
    _notify();

    try {
      final (fetched, hasMore, hasMoreAfter) =
          await api.getMessages(channelId, limit: 40, around: messageId);
      _messages[channelId] = fetched;
      _hasMore[channelId] = hasMore;
      _hasMoreNewer[channelId] = hasMoreAfter;
      _newerCursor[channelId] = fetched.isNotEmpty ? fetched.last.id : '';
      _historyLoaded.add(channelId);
      _messagesError = null;
      _focusErrorMessage = null;
      _pendingFocusMessageId = messageId;
      return true;
    } catch (e) {
      debugPrint('[loadMessagesAround error] $e');
      _focusErrorMessage = _focusErrorText(e);
      _pendingFocusMessageId = null;
      return false;
    } finally {
      _isLoadingMessages[channelId] = false;
      _notify();
    }
  }

  /// 채널을 읽음으로 표시한다. (서버 앵커 전진 + 로컬 배지 0)
  ///
  /// [messageId] 가 있으면 그 메시지까지, 없으면 서버가 채널의 최신으로 앵커를 옮긴다.
  /// (담당 B 가 사용자가 위로 스크롤해 있다가 **다시 최신 구간으로 내려왔을 때** 부른다)
  void markChannelRead(String channelId, {String? messageId}) {
    ws.sendRead(channelId, messageId: messageId);
    _setUnreadCount(channelId, 0);
    // 서버 확인(0)이 올 때까지는 서버 숫자를 믿지 않는다.
    _readAckPending.add(channelId);
    _notify();
  }

  /// 재연결('hello') 했을 때 상태를 서버와 다시 맞춘다.
  ///
  /// 놓친 실시간 이벤트를 복구하기 위한 것이 목적이다.
  /// - 채널 목록과 안읽음 배지를 서버와 다시 맞춘다 (bootstrap)
  /// - 활성 채널이 있으면 최신 메시지도 병합해서 복구한다
  @override
  void _resyncAfterReconnect() {
    unawaited(refreshWorkspace());
    final cid = _activeChannelId;
    if (cid != null) {
      unawaited(refreshNewestMessages(cid));
    }
  }

  /// 점프 실패 사유를 한국어로 바꾼다.
  String _focusErrorText(Object error) {
    if (error is ApiException) {
      if (error.status == 404) return '해당 메시지를 찾을 수 없습니다. 이미 삭제되었을 수 있어요.';
      if (error.status == 403) return '이 메시지를 볼 권한이 없습니다.';
      if (error.code == 'timeout') return '네트워크 응답이 없습니다. 잠시 후 다시 시도해주세요.';
      if (error.code == 'network') return '서버에 연결할 수 없습니다. 서버 주소를 확인해주세요.';
    }
    return '메시지를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.';
  }

  /// 아직 처리되지 않은 점프 대상을 없앤다.
  void clearPendingFocusMessageId() {
    if (_pendingFocusMessageId == null) return;
    _pendingFocusMessageId = null;
    _notify();
  }

  /// 점프 실패 사유를 없앤다.
  void clearFocusErrorMessage() {
    if (_focusErrorMessage == null) return;
    _focusErrorMessage = null;
    _notify();
  }

  /// 최신 방향으로 더 불러온다. (목록 아래쪽에 닿을 때 부른다)
  Future<void> loadNewerMessages(String channelId) async {
    if (_isLoadingMessages[channelId] == true) return;
    final currentList = _messages[channelId] ?? [];
    // 기준은 "서버에서 마지막으로 받은 메시지"다.
    // (WS 로 들어온 메시지가 목록 끝에 있어도 그 뒤를 건너뛰면 안 된다)
    final cursor = _newerCursor[channelId];
    final anchor = (cursor != null && cursor.isNotEmpty)
        ? cursor
        : (currentList.isNotEmpty ? currentList.last.id : null);
    if (anchor == null) return;
    _isLoadingMessages[channelId] = true;
    _notify();

    try {
      final (fetched, _, hasMoreAfter) =
          await api.getMessages(channelId, limit: 40, after: anchor);
      if (fetched.isNotEmpty) {
        // 목록(오래된 → 최신) 뒤에 붙인다.
        var merged = currentList;
        for (final msg in fetched) {
          merged = upsertById(merged, msg, (m) => m.id);
        }
        // 서버가 보내는 순서(created_at, id) 로 다시 정렬한다.
        merged.sort(_compareMessages);
        _messages[channelId] = merged;
        _newerCursor[channelId] = fetched.last.id;
      }
      _hasMoreNewer[channelId] = hasMoreAfter;
    } catch (e) {
      debugPrint('[loadNewerMessages error] $e');
    } finally {
      _isLoadingMessages[channelId] = false;
      _notify();
    }
  }

  /// 서버가 메시지를 정렬하는 기준(created_at, id) 과 같은 순서 비교.
  int _compareMessages(Message a, Message b) {
    final byTime = a.createdAt.compareTo(b.createdAt);
    if (byTime != 0) return byTime;
    return a.id.compareTo(b.id);
  }

  /// 메시지를 보낸다. 실패하면 `false` 를 돌려준다 (호출부가 입력값을 되살린다).
  ///
  /// [attachmentIds] 는 먼저 업로드된 파일의 id 다. (없으면 첨부 없이 보낸다)
  Future<bool> sendMessage(String body, {List<String>? attachmentIds}) async {
    final cid = _activeChannelId;
    if (cid == null || (body.trim().isEmpty && (attachmentIds == null || attachmentIds.isEmpty))) {
      return false;
    }
    final replyTo = _replyToMessage;
    _replyToMessage = null;
    _notify();

    try {
      final msg = await api.sendMessage(
        channelId: cid,
        body: body.trim(),
        replyToId: replyTo?.id,
        inline: replyTo != null,
        attachmentIds: attachmentIds,
      );
      _upsertMessage(cid, msg);
      _notify();
      return true;
    } catch (e) {
      debugPrint('[sendMessage error] $e');
      // 실패하면 답글 컨텍스트도 되돌린다 (사용자가 그대로 다시 시도할 수 있게).
      _replyToMessage = replyTo;
      _notify();
      return false;
    }
  }

  /// 파일을 워크스페이스에 올린다. (먼저 올리고, 그 id 를 메시지에 붙인다)
  Future<FileRef> uploadFile(String filePath, {String? fileName}) async {
    final wsId = _activeWorkspace?.id;
    if (wsId == null) {
      throw ApiException(0, 'error', '워크스페이스가 없습니다.');
    }
    return api.uploadFile(
      workspaceId: wsId,
      filePath: filePath,
      fileName: fileName,
    );
  }

  /// 스레드에 답글을 보낸다. 실패하면 false 를 돌려준다.
  /// (호출부가 글자를 되살리고 스낵바를 띄운다)
  Future<bool> sendReply(String body) async {
    final root = _threadRoot;
    if (root == null || body.trim().isEmpty) return false;
    try {
      final reply = await api.sendMessage(
        channelId: root.channelId,
        body: body.trim(),
        parentId: root.id,
      );
      // 기다리는 사이에 다른 스레드로 바뀌었으면 여기서 버린다.
      if (_threadRoot?.id != root.id) return false;
      // WS 'message.created' 가 먼저 도착할 수 있다.
      // id 로 중복을 막아야 어느 쪽이 먼저 오든 답글이 1개로 보인다.
      _threadReplies = upsertById(_threadReplies, reply, (r) => r.id);
      // replyCount 는 서버가 WS 로 알려준다 (로컬에서 더하면 2씩 증가한다).
      _notify();
      return true;
    } catch (e) {
      debugPrint('[sendReply error] $e');
      return false;
    }
  }

  Future<void> editMessage(String messageId, String newBody) async {
    final updated = await api.editMessage(messageId, newBody);
    _replaceMessageInAll(updated);
    _notify();
  }

  Future<void> deleteMessage(String messageId, String channelId) async {
    await api.deleteMessage(messageId);
    final list = _messages[channelId] ?? [];
    final idx = list.indexWhere((m) => m.id == messageId);
    if (idx != -1) {
      // 되돌리기를 위해 원본을 보관한다.
      // (WS 'message.deleted' 가 먼저 도착할 수 있어, 첫 번째로 저장한 원본을 지킨다)
      _deletedMessages.putIfAbsent(messageId, () => list[idx]);
      list[idx] = list[idx].copyWith(deletedAt: DateTime.now(), body: '');
      _messages[channelId] = List.from(list);
    }
    if (_threadRoot?.id == messageId) {
      _threadRoot = _threadRoot!.copyWith(deletedAt: DateTime.now(), body: '');
    }
    _notify();
  }

  /// 삭제 직후 "실행 취소" 를 눌렀을 때 메시지를 복구한다.
  /// 서버에서 실제로 되돌린 뒤(다른 기기에서도 바로 보인다), 그 결과로 로컬 상태를 교체한다.
  Future<bool> undoDeleteMessage(String messageId, String channelId) async {
    try {
      final restored = await api.restoreMessage(messageId);
      _deletedMessages.remove(messageId);

      final cid = restored.channelId.isEmpty ? channelId : restored.channelId;
      final list = _messages[cid];
      if (list != null) {
        final idx = list.indexWhere((m) => m.id == messageId);
        if (idx != -1) {
          list[idx] = restored;
          _messages[cid] = List.from(list);
        }
      }
      final ridx = _threadReplies.indexWhere((r) => r.id == messageId);
      if (ridx != -1) {
        _threadReplies[ridx] = restored;
      }
      if (_threadRoot?.id == messageId) {
        _threadRoot = restored;
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[undoDeleteMessage error] $e');
      return false;
    }
  }

  Future<void> toggleReaction(Message message, String emoji) async {
    final existing = message.reactions.firstWhere(
      (r) => r.emoji == emoji,
      orElse: () => Reaction(emoji: emoji, count: 0, userIds: [], me: false),
    );
    final updated = await api.toggleReaction(message.id, emoji, existing.me);
    _replaceMessageInAll(updated);
    _notify();
  }

  Future<void> togglePin(Message message) async {
    final updated = await api.togglePin(message.id, message.pinned);
    _replaceMessageInAll(updated);
    _notify();
  }

  void openThread(Message message) async {
    final myRoot = message;
    _threadRoot = myRoot;
    _threadReplies = [];
    _isLoadingReplies = true;
    _notify();

    try {
      final replies = await api.getReplies(myRoot.id);
      // 그 사이에 다른 스레드를 열었으면 이 응답은 버린다.
      if (_threadRoot?.id != myRoot.id) return;
      _threadReplies = replies;
    } catch (e) {
      debugPrint('[getReplies error] $e');
    } finally {
      // 다른 스레드가 열려 있으면 그쪽의 로딩 상태를 건드리지 않는다.
      if (_threadRoot?.id == myRoot.id) {
        _isLoadingReplies = false;
        _notify();
      }
    }
  }

  void closeThread() {
    _threadRoot = null;
    _threadReplies = [];
    _isLoadingReplies = false;
    _notify();
  }

  void setReplyTo(Message? message) {
    _replyToMessage = message;
    _notify();
  }

  void clearReplyTo() {
    _replyToMessage = null;
    _notify();
  }

  /// 입력 중 표시. 반드시 "어느 채널에" 보내는지 명시한다.
  /// (다른 채널로 옮긴 뒤 `off` 가 엉뚱한 채널로 나가면 상대 화면에 "입력 중" 이 남는다)
  void sendTyping(bool on, String channelId) {
    final previous = _typingChannelId;
    if (previous != null && previous != channelId) {
      ws.sendTyping(previous, on: false);
    }
    _typingChannelId = channelId;
    ws.sendTyping(channelId, on: on);
  }

  // ── Channels & DMs Management ────────────────────────────────

  /// 채널을 옮긴다. (메시지를 여는 위치라 메시지 쪽 클래스에 둔다)
  ///
  /// [focusMessageId] 가 있으면 그 메시지로 점프한다 (같은 채널이어도 early-return 하지 않는다).
  void selectChannel(String channelId, {String? focusMessageId}) {
    final sameChannel = _activeChannelId == channelId;
    if (sameChannel && focusMessageId == null) {
      // 같은 채널을 다시 연다 (목록에서 다시 탭, 알림에서 점프 등).
      // - 놓친 실시간 이벤트를 복구하려고 **최신만 병합**해서 가져온다
      //   (이미 불러온 과거 메시지와 스크롤 위치는 그대로다)
      // - 다시 읽음 처리한다 (화면에 올라왔으니 배지도 0)
      unawaited(refreshNewestMessages(channelId));
      ws.sendRead(channelId);
      _setUnreadCount(channelId, 0);
      _notify();
      return;
    }
    if (!sameChannel) {
      // 다른 채널로 옮기면 확인이 안 올 수도 있는 읽음 확인 플래그를 정리한다.
      _readAckPending.clear();
    }
    _activeChannelId = channelId;
    _replyToMessage = null;
    _threadRoot = null;
    _threadReplies = [];
    _pendingFocusMessageId = focusMessageId;
    if (focusMessageId == null) {
      _focusErrorMessage = null;
    }
    _notify();

    // Mark channel read
    ws.sendRead(channelId);
    final idx = _channels.indexWhere((c) => c.id == channelId);
    if (idx != -1 && _channels[idx].unreadCount > 0) {
      _channels[idx] = _channels[idx].copyWith(unreadCount: 0);
      _notify();
    }

    if (focusMessageId != null) {
      // 점프: 기준 주변 창을 연다. (실패하면 최신 위치로 열린다)
      unawaited(loadMessagesAround(channelId, focusMessageId));
      return;
    }

    // WS 로 먼저 도착한 메시지만 있는 채널도 히스토리를 반드시 불러온다.
    if (!hasLoadedHistory(channelId)) {
      unawaited(loadMessages(channelId));
    } else {
      // 다시 열 때: 최신만 병합해서 가져온다.
      // (놓친 WS 이벤트를 복구하고, 이미 불러온 과거 메시지는 남긴다)
      unawaited(refreshNewestMessages(channelId));
    }
  }

  Future<Channel> createChannel({
    required String name,
    String? topic,
    bool isPrivate = false,
    List<String>? memberIds,
  }) async {
    if (_activeWorkspace == null) throw Exception('활성 워크스페이스가 없습니다');
    final ch = await api.createChannel(
      workspaceId: _activeWorkspace!.id,
      name: name,
      topic: topic,
      isPrivate: isPrivate,
      memberIds: memberIds,
    );
    // WS 로 이미 들어왔을 수 있다. id 로 upsert 해서 항상 1개만 남긴다.
    _channels = upsertById(_channels, ch, (c) => c.id, prepend: true);
    selectChannel(ch.id);
    _notify();
    return ch;
  }

  Future<Channel> openDm(String targetUserId) async {
    if (_activeWorkspace == null) throw Exception('활성 워크스페이스가 없습니다');
    final ch = await api.openDm(_activeWorkspace!.id, targetUserId);
    final idx = _channels.indexWhere((c) => c.id == ch.id);
    if (idx == -1) {
      _channels.insert(0, ch);
    }
    selectChannel(ch.id);
    _notify();
    return ch;
  }

  Future<void> leaveChannel(String channelId) async {
    await api.leaveChannel(channelId);
    _channels.removeWhere((c) => c.id == channelId);
    _messages.remove(channelId);
    _historyLoaded.remove(channelId);
    if (_activeChannelId == channelId) {
      _afterActiveChannelRemoved();
    }
    _notify();
  }

  /// 채널 이름·주제를 고친다. (이름·주제·목적)
  Future<bool> updateChannel({
    required String channelId,
    String? name,
    String? topic,
    String? purpose,
  }) async {
    try {
      final updated = await api.updateChannel(
        channelId,
        name: name,
        topic: topic,
        purpose: purpose,
      );
      _channels = upsertById(_channels, updated, (c) => c.id);
      _notify();
      return true;
    } catch (e) {
      debugPrint('[updateChannel error] $e');
      return false;
    }
  }

  /// 공개 채널에 들어간다. (아직 속하지 않은 채널)
  Future<Channel> joinChannel(String channelId) async {
    final joined = await api.joinChannel(channelId);
    _channels = upsertById(_channels, joined, (c) => c.id, prepend: true);
    _notify();
    return joined;
  }

  /// 채널을 삭제한다. (주최자만 가능)
  Future<bool> deleteChannel(String channelId) async {
    try {
      await api.deleteChannel(channelId);
      _channels.removeWhere((c) => c.id == channelId);
      _messages.remove(channelId);
      _historyLoaded.remove(channelId);
      if (_activeChannelId == channelId) {
        _afterActiveChannelRemoved();
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[deleteChannel error] $e');
      return false;
    }
  }

  /// 채널에 사람을 넣는다.
  Future<bool> addChannelMember(String channelId, String userId) async {
    try {
      await api.addChannelMember(channelId, userId);
      // 멤버 목록을 다시 읽는다 (누가 들어왔는지 화면이 바로 보여야 한다)
      _channelMembers.remove(channelId);
      _notify();
      return true;
    } catch (e) {
      debugPrint('[addChannelMember error] $e');
      return false;
    }
  }

  Future<void> deleteDm(String channelId) async {
    await api.deleteDm(channelId);
    _channels.removeWhere((c) => c.id == channelId);
    _messages.remove(channelId);
    _historyLoaded.remove(channelId);
    if (_activeChannelId == channelId) {
      _afterActiveChannelRemoved();
    }
    _notify();
  }

  /// 떠난 채널이 활성 채널이었을 때 남은 채널로 이동한다 (빈 대화창 방지).
  void _afterActiveChannelRemoved() {
    if (_channels.isEmpty) {
      _activeChannelId = null;
      _notify();
      return;
    }
    selectChannel(_channels.first.id);
  }
}
