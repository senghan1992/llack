part of 'app_state.dart';

/// 서버 WebSocket 이벤트를 상태에 반영하는 부분.
///
/// (메시지 목록과 채널 목록은 _AppStateMessages 가 이어서 관리한다)
abstract class _AppStateRealtime extends _AppStateCore {
  _AppStateRealtime({super.api, super.ws});
  // ── WebSocket Handler ────────────────────────────────────────

  void _handleWsEvent(Map<String, dynamic> event) {
    final type = event['type'] as String?;
    if (type == null) return;

    switch (type) {
      case 'hello':
        // (재)연결된 순간이다. 확인이 안 올 수도 있는 읽음 확인 플래그를 전부 비운다.
        _readAckPending.clear();
        // **첫 연결**의 hello 는 "재연결" 이 아니다.
        // (최초 부트스트랩으로 이미 최신 상태를 받아왔는데 다시 받으면 bootstrap 이 두 번씩 나간다)
        final isReconnect = _hasSeenHello;
        _hasSeenHello = true;
        if (isReconnect) {
          // 재연결하면 그 사이에 놓친 이벤트가 있을 수 있다.
          // 서버와 다시 맞춰 놓는다.
          _resyncAfterReconnect();
        }
        if (event['user'] != null) {
          final u = User.fromJson(event['user'] as Map<String, dynamic>);
          _presence[u.id] = u.presence;
          if (_currentUser?.id == u.id) {
            _currentUser = u;
          }
          _notify();
        }
        break;

      case 'presence':
        final userId = event['user_id'] as String?;
        final presVal = event['presence'] as String?;
        if (userId != null && presVal != null) {
          final p = Presence.fromString(presVal);
          _presence[userId] = p;
          if (_currentUser?.id == userId) {
            _currentUser = _currentUser!.copyWith(presence: p);
          }
          _notify();
        }
        break;

      case 'message.created':
        if (event['message'] != null) {
          final msg = Message.fromJson(event['message'] as Map<String, dynamic>);
          if (msg.parentId != null) {
            if (_threadRoot?.id == msg.parentId) {
              // id 로 중복을 막는다 (sendReply 의 HTTP 응답과 같은 기준).
              _threadReplies = upsertById(_threadReplies, msg, (r) => r.id);
            }
            final list = _messages[msg.channelId] ?? [];
            final pidx = list.indexWhere((m) => m.id == msg.parentId);
            if (pidx != -1) {
              final parent = list[pidx];
              list[pidx] = parent.copyWith(
                replyCount: parent.replyCount + 1,
                lastReplyAt: msg.createdAt,
              );
            }
            if (msg.inline) {
              _upsertMessage(msg.channelId, msg);
            }
          } else {
            _upsertMessage(msg.channelId, msg);
            if (_activeChannelId != msg.channelId && msg.userId != _currentUser?.id) {
              final cidx = _channels.indexWhere((c) => c.id == msg.channelId);
              if (cidx != -1) {
                _channels[cidx] = _channels[cidx].copyWith(
                  unreadCount: _channels[cidx].unreadCount + 1,
                );
              }
            }
          }
          // 내가 보고 있는 채널에 도착한 메시지 → 읽음 처리.
          if (_activeChannelId == msg.channelId) {
            _handleMessageInActiveChannel(msg);
          }
          _notify();
        }
        break;

      case 'message.updated':
      case 'reaction.updated':
        if (event['message'] != null) {
          final msg = Message.fromJson(event['message'] as Map<String, dynamic>);
          _replaceMessageInAll(msg);
          _notify();
        }
        break;

      case 'message.deleted':
        final mid = event['message_id'] as String?;
        final cid = event['channel_id'] as String?;
        if (mid != null && cid != null) {
          final list = _messages[cid] ?? [];
          final idx = list.indexWhere((m) => m.id == mid);
          if (idx != -1) {
            // 되돌리기를 위해 원본을 보관한다.
            // (삭제 전에 저장한 원본을 덮어쓰면 "실행 취소" 가 원문 없이 되돌린다)
            _deletedMessages.putIfAbsent(mid, () => list[idx]);
            list[idx] = list[idx].copyWith(deletedAt: DateTime.now(), body: '');
            _messages[cid] = List.from(list);
          }
          final ridx = _threadReplies.indexWhere((r) => r.id == mid);
          if (ridx != -1) {
            _threadReplies[ridx] = _threadReplies[ridx].copyWith(deletedAt: DateTime.now(), body: '');
          }
          _notify();
        }
        break;

      case 'typing':
        final cid = event['channel_id'] as String?;
        final uid = event['user_id'] as String?;
        final name = event['name'] as String?;
        final on = event['on'] as bool? ?? false;
        if (cid != null && uid != null && uid != _currentUser?.id) {
          final users = _typing.putIfAbsent(cid, () => {});
          if (on && name != null) {
            // 시각을 함께 저장해 5초가 지나면 자동으로 만료된다.
            users[name] = DateTime.now();
          } else if (name != null) {
            users.remove(name);
          }
          _notify();
        }
        break;

      case 'channel.created':
        if (event['channel'] != null) {
          final ch = Channel.fromJson(event['channel'] as Map<String, dynamic>);
          // REST 응답 경로와 같은 규칙을 쓴다 (둘 중 하나가 먼저 와도 1개).
          _channels = upsertById(_channels, ch, (c) => c.id, prepend: true);
          _notify();
        }
        break;

      case 'event.created':
      case 'event.updated':
        if (event['event'] != null) {
          final ev = ScheduleEvent.fromJson(event['event'] as Map<String, dynamic>);
          // REST 응답 경로와 같은 규칙을 쓴다 (둘 중 하나가 먼저 와도 1개).
          _events = upsertById(_events, ev, (e) => e.id);
          _notify();
        }
        break;

      case 'event.deleted':
        final eid = event['event_id'] as String?;
        if (eid != null) {
          _events.removeWhere((e) => e.id == eid);
          _notify();
        }
        break;

      case 'task.created':
      case 'task.updated':
        if (event['task'] != null) {
          final t = Task.fromJson(event['task'] as Map<String, dynamic>);
          final list = _projectTasks[t.projectId] ?? [];
          // REST 응답 경로와 같은 규칙을 쓴다 (둘 중 하나가 먼저 와도 1개).
          _projectTasks[t.projectId] = upsertById(list, t, (x) => x.id);
          _notify();
        }
        break;

      case 'task.deleted':
        final tid = event['task_id'] as String?;
        if (tid != null && _activeProject != null) {
          final list = _projectTasks[_activeProject!.id] ?? [];
          _projectTasks[_activeProject!.id] = list.where((x) => x.id != tid).toList();
          _notify();
        }
        break;

      // 서버 payload: {"type":"unread","channel_id":"...","count":3}
      case 'unread':
        final cid = event['channel_id'] as String?;
        final count = event['count'] as int?;
        if (cid != null) {
          if (_readAckPending.contains(cid)) {
            // 읽음 신호를 보냈고 아직 서버 확인이 없다.
            // (신호보다 먼저 계산된 낡은 숫자다) → 배지를 건드리지 않는다.
            if (count == 0) {
              _readAckPending.remove(cid);
              _setUnreadCount(cid, 0);
              _notify();
            }
          } else {
            final idx = _channels.indexWhere((c) => c.id == cid);
            if (idx != -1) {
              _channels[idx] = _channels[idx].copyWith(unreadCount: count ?? 0);
              _notify();
            }
          }
        }
        break;
    }
  }

  /// 재연결('hello') 했을 때 상태를 서버와 다시 맞춘다.
  /// (기본은 할 일 없음. 메시지 쪽 클래스가 필요한 작업을 덧붙인다)
  void _resyncAfterReconnect() {}

  /// 내가 보고 있는 채널에 도착한 메시지를 읽음으로 처리한다.
  ///
  /// **대화창이 화면에 떠 있어야** 읽음 처리한다.
  /// (훅이 null 이면 사용자가 그 채널을 보고 있지 않은 것이다)
  /// 화면에 보이면 읽음 신호를 보내서 **서버 앵커를 전진**시키고 배지를 0 으로 둔다.
  /// (앱을 껐다 켜도 배지가 살아나지 않게 하는 핵심)
  /// 보이지 않으면 안읽음으로 남긴다.
  void _handleMessageInActiveChannel(Message msg) {
    final hook = isNewestMessageVisible;
    final visible = hook != null && hook(msg.channelId);
    if (visible) {
      // 서버 앵커를 이 메시지까지 전진시킨다.
      ws.sendRead(msg.channelId, messageId: msg.id);
      _setUnreadCount(msg.channelId, 0);
      // 서버 확인(0)이 올 때까지는 서버 숫자를 믿지 않는다.
      _readAckPending.add(msg.channelId);
      return;
    }
    // 화면에서 보고 있지 않다 → 안읽음으로 남긴다.
    // (이전 읽음 확인은 무효가 되므로 플래그도 정리한다)
    _readAckPending.remove(msg.channelId);
    _setUnreadCount(msg.channelId, _unreadOf(msg.channelId) + 1);
  }

  void _upsertMessage(String channelId, Message message) {
    final list = _messages[channelId] ?? [];
    final idx = list.indexWhere((m) => m.id == message.id);
    if (idx != -1) {
      list[idx] = message;
    } else {
      list.add(message);
    }
    _messages[channelId] = List.from(list);
  }

  void _replaceMessageInAll(Message message) {
    final list = _messages[message.channelId] ?? [];
    final idx = list.indexWhere((m) => m.id == message.id);
    if (idx != -1) {
      list[idx] = message;
      _messages[message.channelId] = List.from(list);
    }
    final ridx = _threadReplies.indexWhere((r) => r.id == message.id);
    if (ridx != -1) {
      _threadReplies[ridx] = message;
    }
    if (_threadRoot?.id == message.id) {
      _threadRoot = message;
    }
  }
}
