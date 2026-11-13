import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';

/// 메시지 삭제 + 되돌리기(실행 취소) 를 한곳에서 처리한다.
///
/// 1차 라운드에서는 채팅 화면에만 되돌리기가 있어서 스레드 화면의 답글은
/// 지워진 뒤 되돌릴 수 없었다. 두 화면이 같은 UX 를 갖도록 공통 헬퍼로 모았다.
class MessageActions {
  MessageActions._();

  /// 삭제 안내 SnackBar.
  ///
  /// Flutter 의 SnackBar 생성자는 `persist = persist ?? action != null` 이라
  /// **액션이 있으면 자동 닫힘이 꺼지고 `duration` 이 무시된다.**
  /// ("실행 취소" SnackBar 가 화면에 계속 남아 composer 를 덮던 버그의 원인)
  /// 그래서 `persist: false` 를 명시해 정한 시간 뒤에 닫히게 한다.
  ///
  /// 유지 시간은 **10초**다.
  /// 5초였을 때는 "아, 실수다" 하고 취소 버튼을 누르기 전에 이미 사라져
  /// 되돌릴 수 없는 경우를 실기에서 확인했다.
  /// (Material Design 가이드라인도 액션이 붙은 스낵바는 10초를 권장한다)
  @visibleForTesting
  static SnackBar buildDeleteSnackBar({required VoidCallback onUndo}) {
    return SnackBar(
      content: const Text('메시지를 삭제했습니다'),
      duration: const Duration(seconds: 10),
      persist: false,
      action: SnackBarAction(
        label: '실행 취소',
        onPressed: onUndo,
      ),
    );
  }

  /// 메시지를 삭제하고 "실행 취소" SnackBar 를 띄운다.
  ///
  /// [context] 는 **SnackBar 를 그릴 ScaffoldMessenger 의 안쪽**에서 가져와야 한다.
  /// (가장 가까운 messenger 를 잡기 때문에, ChatScreen 안에 중첩 messenger 를 두면
  ///  SnackBar 가 메시지 영역에만 그려져 composer 를 가리지 않는다.)
  static Future<void> deleteMessage(
    BuildContext context,
    Message message,
    String channelId,
  ) async {
    final state = context.read<AppState>();
    final messenger = ScaffoldMessenger.of(context);

    try {
      await state.deleteMessage(message.id, channelId);
    } catch (_) {
      _show(messenger, '메시지를 삭제하지 못했습니다');
      return;
    }

    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      buildDeleteSnackBar(
        onUndo: () => _restore(messenger, state, message.id, channelId),
      ),
    );
  }

  /// 삭제를 되돌린다. 서버 복구에 실패하면 이유를 알려준다.
  static Future<void> _restore(
    ScaffoldMessengerState messenger,
    AppState state,
    String messageId,
    String channelId,
  ) async {
    final ok = await state.undoDeleteMessage(messageId, channelId);
    // 복구되면 메시지가 원래대로 돌아오므로 별도 안내는 필요 없다.
    if (ok) return;
    _show(messenger, '메시지를 복구하지 못했습니다');
  }

  static void _show(ScaffoldMessengerState messenger, String text) {
    if (!messenger.mounted) return;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  /// 반응한 사람들을 바텀 시트로 보여준다.
  ///
  /// 데스크톱은 반응 이모티콘에 커서를 올리면 "누가 눌렀는지" 를 보여준다.
  /// 모바일은 반응 칩을 길게 누르면 이 시트가 열린다.
  ///
  /// 이름은 [AppState.members] 에서 찾는다. (못 찾으면 짧게 잘린 id 로 대신한다)
  static Future<void> showReactionParticipants(
    BuildContext context,
    Reaction reaction,
  ) {
    final names = _participantNames(context, reaction);

    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: LlackColors.surfaceRaise,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 10),
                child: Text(
                  names.isEmpty
                      ? '${reaction.emoji} 반응'
                      : '${reaction.emoji} 반응한 사람 ${names.length}명',
                  style: LlackTypography.title,
                ),
              ),
              if (names.isEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                  child: Text(
                    reaction.count > 0
                        ? '${reaction.count}명이 반응했습니다'
                        : '이름을 확인할 수 없습니다',
                    style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                  ),
                )
              else
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    children: names
                        .map(
                          (name) => ListTile(
                            leading: LlackAvatar(name: name, size: 32),
                            title: Text(name, style: LlackTypography.body),
                          ),
                        )
                        .toList(),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  /// 반응한 사람들의 이름. (멤버 목록에서 찾고, 못 찾으면 짧은 id 로 대신한다)
  static List<String> _participantNames(BuildContext context, Reaction reaction) {
    List<Member> members = const [];
    try {
      members = context.read<AppState>().members;
    } catch (_) {
      // AppState 가 없는 곳(테스트 등)에서는 id 로 대신한다.
      members = const [];
    }

    return reaction.userIds.map((id) {
      for (final member in members) {
        if (member.user.id == id) return member.user.name;
      }
      return _shortId(id);
    }).toList();
  }

  /// 이름을 모를 때 보여줄 짧은 id.
  static String _shortId(String id) {
    if (id.length <= 8) return id;
    return '${id.substring(0, 8)}…';
  }
}
