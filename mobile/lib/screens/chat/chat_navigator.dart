import 'package:flutter/material.dart';
import '../../providers/app_state.dart';
import '../../services/api_service.dart';
import 'chat_screen.dart';

/// 대화창을 여는 공통 헬퍼.
///
/// 검색 / 신규 DM / 채널 목록 등 여러 곳에서 "대화를 연다" 동작을 한다.
/// 예전에는 각자 `await` 이후에 `context.mounted` 를 확인했는데,
/// 다이얼로그를 닫은 뒤에는 그 context 가 사라져 대화창이 열리지 않았다.
/// 그래서 state 와 navigator 를 **먼저 캡처** 해 두고 열도록 모았다.
class ChatNavigator {
  ChatNavigator._();

  /// 채널 대화창을 연다. (태블릿 등 이미 대화창이 보이는 화면에서는 push 하지 않는다)
  ///
  /// [messageId] 가 있으면 **그 메시지 주변으로 점프**한다. (검색 결과 탭)
  static void openChannel({
    required AppState state,
    required NavigatorState navigator,
    required String channelId,
    bool push = true,
    String? messageId,
  }) {
    if (messageId != null) {
      state.selectChannel(channelId, focusMessageId: messageId);
    } else {
      state.selectChannel(channelId);
    }
    if (!push) return;
    navigator.push(
      MaterialPageRoute(
        builder: (_) => const ChatScreen(showBackButton: true),
      ),
    );
  }

  /// 1:1 대화를 만들고(기존 대화가면 그대로) 대화창을 연다.
  static Future<void> openDm({
    required AppState state,
    required NavigatorState navigator,
    required String userId,
    bool push = true,
  }) async {
    await state.openDm(userId);
    if (!push) return;
    navigator.push(
      MaterialPageRoute(
        builder: (_) => const ChatScreen(showBackButton: true),
      ),
    );
  }

  /// DM 을 열지 못했을 때 원인을 한국어로 설명한다.
  /// "대화를 열지 못했습니다" 같은 막연한 문구 대신 이유를 알려야 사용자가 다음 행동을 정할 수 있다.
  static String describeDmError(Object error) {
    if (error is ApiException) {
      switch (error.status) {
        case 422:
          return '자신과의 1:1 대화는 만들 수 없습니다.';
        case 403:
          return '이 사람은 이 워크스페이스의 멤버가 아닙니다.';
        case 404:
          return '사용자를 찾을 수 없습니다.';
        case 409:
          return '이미 대화가 있습니다.';
      }
      if (error.code == 'timeout') {
        return '네트워크 응답이 없습니다. 잠시 후 다시 시도해주세요.';
      }
      if (error.code == 'network') {
        return '서버에 연결할 수 없습니다. 연결 상태를 확인해주세요.';
      }
      return '대화를 열지 못했습니다 (오류 ${error.status}). 잠시 후 다시 시도해주세요.';
    }
    return '대화를 열지 못했습니다. 잠시 후 다시 시도해주세요.';
  }
}
