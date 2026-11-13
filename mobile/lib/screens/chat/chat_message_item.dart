import 'package:flutter/material.dart';
import '../../models/models.dart';
import '../../widgets/message_bubble.dart';
import 'message_date_header.dart';

/// 메시지 목록의 한 줄 (날짜 헤더 + 말풍선).
///
/// 목록을 그리는 코드가 화면 파일에 그대로 있으면 파일이 계속 길어지므로
/// 한 줄짜리 위젯으로 분리했다. (동작은 동일)
class ChatMessageItem extends StatelessWidget {
  final Message message;
  final bool isMine;

  /// 이 메시지 앞에 날짜 구분 헤더를 그릴지
  final bool showDateHeader;

  /// 연속으로 삭제된 메시지 묶음의 개수 (1 이면 "삭제된 메시지")
  final int deletedCount;

  /// 점프 대상 메시지에 붙이는 키 (그 외에는 null)
  final Key? jumpKey;

  /// 검색 결과로 점프해 강조하는지
  final bool highlight;

  final String Function(String url)? fileUrlResolver;
  final VoidCallback? onOpenThread;
  final VoidCallback? onReplyInline;
  final void Function(String emoji)? onToggleReaction;
  final VoidCallback? onTogglePin;
  final void Function(String newBody)? onEdit;
  final VoidCallback? onDelete;

  /// 반응 칩을 길게 눌렀을 때 (누가 그 반응을 눌렀는지) 보여줄 때 부른다.
  /// (없으면 말풍선이 기본 동작으로 직접 보여준다)
  final void Function(Reaction reaction)? onShowReactionParticipants;

  const ChatMessageItem({
    super.key,
    required this.message,
    required this.isMine,
    required this.showDateHeader,
    this.deletedCount = 1,
    this.jumpKey,
    this.highlight = false,
    this.fileUrlResolver,
    this.onOpenThread,
    this.onReplyInline,
    this.onToggleReaction,
    this.onTogglePin,
    this.onEdit,
    this.onDelete,
    this.onShowReactionParticipants,
  });

  @override
  Widget build(BuildContext context) {
    final bubble = MessageBubble(
      message: message,
      isMine: isMine,
      // 삭제된 메시지는 조용한 한 줄로 그린다 (연속 삭제는 하나로 합쳐진다)
      deletedCount: deletedCount,
      fileUrlResolver: fileUrlResolver,
      highlight: highlight,
      onOpenThread: onOpenThread,
      onReplyInline: onReplyInline,
      onToggleReaction: onToggleReaction,
      onTogglePin: onTogglePin,
      onEdit: onEdit,
      onDelete: onDelete,
      onShowReactionParticipants: onShowReactionParticipants,
    );

    return KeyedSubtree(
      key: jumpKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (showDateHeader) MessageDateHeader(date: message.createdAt),
          bubble,
        ],
      ),
    );
  }
}
