import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import '../models/models.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_typography.dart';
import 'llack_avatar.dart';
import 'message_attachments.dart';

class MessageBubble extends StatelessWidget {
  final Message message;
  final bool isMine;
  final VoidCallback? onOpenThread;
  final VoidCallback? onReplyInline;
  final void Function(String emoji)? onToggleReaction;
  final VoidCallback? onTogglePin;
  final void Function(String newBody)? onEdit;
  final VoidCallback? onDelete;

  /// 첨부 파일의 상대경로를 실제 이미지 URL 로 바꿔주는 함수.
  /// (서버가 상대경로를 주기 때문에 절대 URL 로 바꿔야 Image.network 가 동작한다)
  final String Function(String url)? fileUrlResolver;

  /// 검색 결과로 점프해 온 메시지를 잠깐 강조한다.
  final bool highlight;

  /// 연속으로 삭제된 메시지 묶음의 개수.
  /// (1 이면 "삭제된 메시지" 한 줄, 2 이상이면 "삭제된 메시지 N개" 로 합쳐 그린다)
  final int deletedCount;

  const MessageBubble({
    super.key,
    required this.message,
    required this.isMine,
    this.onOpenThread,
    this.onReplyInline,
    this.onToggleReaction,
    this.onTogglePin,
    this.onEdit,
    this.onDelete,
    this.fileUrlResolver,
    this.highlight = false,
    this.deletedCount = 1,
  });

  /// 최소 터치 타깃 (Material 접근성 권장 최소 크기)
  static const double _minTapSize = 44;

  /// 검색 결과로 점프한 메시지의 강조 색.
  /// (theme/* 는 다른 에이전트 소유라 여기에서 직접 정의한다)
  static const Color _highlightBackground = Color(0xFFFFF3D6);
  static const Color _highlightBorder = Color(0xFFE8A33D);

  /// 강조 테두리를 그린다. (강조가 아니면 원래 레이아웃 그대로)
  Widget _wrapHighlight(Widget child) {
    if (!highlight) return child;
    return Container(
      padding: const EdgeInsets.fromLTRB(6, 4, 6, 4),
      decoration: BoxDecoration(
        color: _highlightBackground,
        borderRadius: BorderRadius.circular(14),
        border: const Border(left: BorderSide(color: _highlightBorder, width: 3)),
      ),
      child: child,
    );
  }

  String _formatTimestamp(DateTime dt) {
    return DateFormat('HH:mm').format(dt.toLocal());
  }

  void _showContextMenu(BuildContext context) {
    // 롱프레스 동작을 눈으로 확인할 수 있게 햅틱을 준다.
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      backgroundColor: LlackColors.surfaceRaise,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Quick Emoji Reactions
              // (삭제된 메시지에는 리액션도 무의미하다)
              if (message.deletedAt == null) ...[
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: ['👍', '❤️', '🔥', '🎉', '👀', '😂'].map((emoji) {
                      return InkWell(
                        onTap: () {
                          Navigator.pop(ctx);
                          HapticFeedback.selectionClick();
                          onToggleReaction?.call(emoji);
                        },
                        borderRadius: BorderRadius.circular(22),
                        child: Container(
                          // 터치 타깃 44dp 확보
                          width: _minTapSize,
                          height: _minTapSize,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: LlackColors.surfaceWell,
                            shape: BoxShape.circle,
                          ),
                          child: Text(emoji, style: const TextStyle(fontSize: 22)),
                        ),
                      );
                    }).toList(),
                  ),
                ),
                const Divider(height: 1),
              ],
              ListTile(
                leading: const Icon(Icons.forum_outlined, size: 20, color: LlackColors.ink),
                title: const Text('스레드로 답글 달기', style: LlackTypography.body),
                onTap: () {
                  Navigator.pop(ctx);
                  HapticFeedback.selectionClick();
                  onOpenThread?.call();
                },
              ),
              ListTile(
                leading: const Icon(Icons.reply_rounded, size: 20, color: LlackColors.ink),
                title: const Text('인라인 답글', style: LlackTypography.body),
                onTap: () {
                  Navigator.pop(ctx);
                  HapticFeedback.selectionClick();
                  onReplyInline?.call();
                },
              ),
              ListTile(
                leading: Icon(
                  message.pinned ? Icons.push_pin : Icons.push_pin_outlined,
                  size: 20,
                  color: LlackColors.ink,
                ),
                title: Text(message.pinned ? '핀 고정 해제' : '핀으로 고정', style: LlackTypography.body),
                onTap: () {
                  Navigator.pop(ctx);
                  HapticFeedback.selectionClick();
                  onTogglePin?.call();
                },
              ),
              // (삭제된 메시지는 본문이 없으니 복사 항목도 숨긴다)
              if (message.deletedAt == null)
                ListTile(
                  leading: const Icon(Icons.copy_rounded, size: 20, color: LlackColors.ink),
                  title: const Text('메시지 복사', style: LlackTypography.body),
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: message.body));
                    Navigator.pop(ctx);
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('복사되었습니다'), duration: Duration(seconds: 1)),
                    );
                  },
                ),
              if (isMine && message.deletedAt == null) ...[
                ListTile(
                  leading: const Icon(Icons.edit_outlined, size: 20, color: LlackColors.ink),
                  title: const Text('메시지 수정', style: LlackTypography.body),
                  onTap: () {
                    Navigator.pop(ctx);
                    _showEditDialog(context);
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.delete_outline_rounded, size: 20, color: LlackColors.presenceBusy),
                  title: const Text('메시지 삭제', style: TextStyle(color: LlackColors.presenceBusy)),
                  onTap: () {
                    Navigator.pop(ctx);
                    onDelete?.call();
                  },
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  void _showEditDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => _EditMessageDialog(
        initialBody: message.body,
        onSave: (newBody) {
          if (newBody.isNotEmpty && newBody != message.body) {
            onEdit?.call(newBody);
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final maxBubbleWidth = MediaQuery.sizeOf(context).width * 0.78;

    // 삭제된 메시지는 아바타·작성자·직함·타임스탬프·말풍선 없이
    // 아주 조용한 한 줄로 그린다. (같은 크기의 말풍선이 벽을 만든 문제)
    if (message.deletedAt != null) {
      return GestureDetector(
        onLongPress: () => _showContextMenu(context),
        child: MessageDeletedMarker(count: deletedCount),
      );
    }

    if (isMine) {
      return GestureDetector(
        onLongPress: () => _showContextMenu(context),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 3),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (message.pinned) _buildPinnedBadge(),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxBubbleWidth),
                child: _wrapHighlight(Container(
                  decoration: BoxDecoration(
                    color: message.deletedAt != null
                        ? LlackColors.surfaceWell
                        : LlackColors.bubbleMine,
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(14),
                      topRight: Radius.circular(14),
                      bottomLeft: Radius.circular(14),
                      bottomRight: Radius.circular(4),
                    ),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      _buildReplyQuote(isMine: true),
                      Text(
                        message.body,
                        style: LlackTypography.body.copyWith(
                          color: LlackColors.bubbleMineInk,
                        ),
                      ),
                      MessageAttachments(
                        attachments: message.attachments,
                        isMine: true,
                        fileUrlResolver: fileUrlResolver,
                      ),
                      const SizedBox(height: 4),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (message.editedAt != null)
                            Padding(
                              padding: const EdgeInsets.only(right: 4),
                              child: Text(
                                '(수정됨)',
                                style: LlackTypography.caption.copyWith(
                                  color: LlackColors.bubbleMineDim,
                                  fontSize: 10,
                                ),
                              ),
                            ),
                          Text(
                            _formatTimestamp(message.createdAt),
                            style: LlackTypography.monoTimestampOnMine,
                          ),
                        ],
                      ),
                    ],
                  )),
                ),
              ),
              _buildReactionsRow(isMine: true),
              _buildThreadButton(isMine: true),
            ],
          ),
        ),
      );
    }

    // Others' message
    return GestureDetector(
      onLongPress: () => _showContextMenu(context),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LlackAvatar(
              name: message.author.name,
              avatarUrl: message.author.avatarUrl,
              avatarColor: message.author.avatarColor,
              size: 36,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildHeader(),
                  const SizedBox(height: 3),
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: maxBubbleWidth),
                    child: _wrapHighlight(Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: LlackColors.surfaceRaise,
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(4),
                          topRight: Radius.circular(14),
                          bottomLeft: Radius.circular(14),
                          bottomRight: Radius.circular(14),
                        ),
                        border: Border.all(color: LlackColors.rule, width: 1),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildReplyQuote(isMine: false),
                          Text(
                            message.body,
                            style: LlackTypography.body,
                          ),
                          MessageAttachments(
                            attachments: message.attachments,
                            isMine: false,
                            fileUrlResolver: fileUrlResolver,
                          ),
                        ],
                      ),
                    )),
                  ),
                  _buildReactionsRow(isMine: false),
                  _buildThreadButton(isMine: false),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 작성자 / 직함 / 시간 헤더.
  /// 이름과 직함이 길어도 줄무늬 오버플로가 나지 않도록 한 줄로 ellipsis 처리한다.
  Widget _buildHeader() {
    final author = message.author;
    return Row(
      children: [
        Expanded(
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: author.name, style: LlackTypography.authorName),
                if (author.title != null && author.title!.isNotEmpty)
                  TextSpan(
                    text: '  ${author.title}',
                    style: LlackTypography.caption,
                  ),
              ],
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 8),
        Text(
          _formatTimestamp(message.createdAt),
          style: LlackTypography.monoTimestamp,
        ),
        if (message.pinned) ...[
          const SizedBox(width: 6),
          const Icon(Icons.push_pin, size: 12, color: LlackColors.accent),
        ],
      ],
    );
  }

  /// 인라인 답글 인용 라인 ("← 이름: 원문 한 줄")
  Widget _buildReplyQuote({required bool isMine}) {
    final replyTo = message.replyTo;
    if (replyTo == null) return const SizedBox.shrink();

    final nameColor = isMine ? LlackColors.accentInk : LlackColors.accentDeep;
    final bodyColor = isMine ? LlackColors.bubbleMineInk : LlackColors.ink2;

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.only(left: 8),
      decoration: BoxDecoration(
        border: Border(
          left: BorderSide(color: isMine ? LlackColors.accentInk : LlackColors.accent, width: 3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            replyTo.authorName.isEmpty ? '답글' : replyTo.authorName,
            style: LlackTypography.caption.copyWith(
              fontWeight: FontWeight.w700,
              color: nameColor,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Text(
            replyTo.deleted ? '삭제된 메시지' : replyTo.body,
            style: LlackTypography.caption.copyWith(color: bodyColor),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  Widget _buildPinnedBadge() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.push_pin, size: 12, color: LlackColors.accent),
          const SizedBox(width: 4),
          Text(
            '고정됨',
            style: LlackTypography.caption.copyWith(color: LlackColors.accent, fontSize: 10),
          ),
        ],
      ),
    );
  }

  Widget _buildReactionsRow({required bool isMine}) {
    if (message.reactions.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Wrap(
        spacing: 4,
        runSpacing: 4,
        alignment: isMine ? WrapAlignment.end : WrapAlignment.start,
        children: message.reactions.map((r) {
          final isSelected = r.me;
          return InkWell(
            onTap: () {
              HapticFeedback.selectionClick();
              onToggleReaction?.call(r.emoji);
            },
            borderRadius: BorderRadius.circular(12),
            // 터치 타깃 44dp 확보 (시각적 칩은 그대로 둔다)
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: _minTapSize),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: isSelected ? LlackColors.accentSoft : LlackColors.surfaceWell,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isSelected ? LlackColors.accent : LlackColors.rule,
                      width: 1,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(r.emoji, style: const TextStyle(fontSize: 13)),
                      const SizedBox(width: 4),
                      Text(
                        '${r.count}',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                          color: isSelected ? LlackColors.accentDeep : LlackColors.ink2,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildThreadButton({required bool isMine}) {
    if (message.replyCount <= 0) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: InkWell(
        onTap: onOpenThread,
        borderRadius: BorderRadius.circular(8),
        // 터치 타깃 44dp 확보
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: _minTapSize),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.forum_outlined, size: 14, color: LlackColors.accent),
              const SizedBox(width: 5),
              Text(
                '답글 ${message.replyCount}개',
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: LlackColors.accent,
                ),
              ),
              const Icon(Icons.chevron_right, size: 14, color: LlackColors.accent),
            ],
          ),
        ),
      ),
    );
  }
}

/// 메시지 수정 다이얼로그.
///
/// [TextEditingController] 를 **이 위젯이 소유**한다.
/// (showDialog 로 띄운 로컬 컨트롤러는 자동으로 해제되지 않아
///  다이얼로그를 열 때마다 컨트롤러가 그대로 살아남았다)
class _EditMessageDialog extends StatefulWidget {
  final String initialBody;
  final ValueChanged<String> onSave;

  const _EditMessageDialog({
    required this.initialBody,
    required this.onSave,
  });

  @override
  State<_EditMessageDialog> createState() => _EditMessageDialogState();
}

class _EditMessageDialogState extends State<_EditMessageDialog> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.initialBody);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('메시지 수정', style: LlackTypography.title),
      content: TextField(
        controller: _controller,
        autofocus: true,
        maxLines: 4,
        style: LlackTypography.body,
        decoration: const InputDecoration(hintText: '수정할 내용을 입력하세요'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: () {
            // 컨트롤러 값을 먼저 읽고 → 그 다음 pop 한다.
            // (pop 이후에는 컨트롤러를 건드리지 않는다)
            final newText = _controller.text.trim();
            if (newText.isNotEmpty && newText != widget.initialBody) {
              widget.onSave(newText);
            }
            Navigator.pop(context);
          },
          child: const Text('수정'),
        ),
      ],
    );
  }
}

/// 삭제된 메시지를 그리는 조용한 한 줄.
///
/// 아바타·작성자·직함·타임스탬프·말풍선이 전부 없다.
/// (삭제된 메시지마다 실제 메시지만큼 자리를 차지해서 화면이 회색 벽이 되던 문제)
class MessageDeletedMarker extends StatelessWidget {
  /// 연속으로 삭제된 메시지의 개수 (1 이면 "삭제된 메시지")
  final int count;

  const MessageDeletedMarker({super.key, this.count = 1});

  @override
  Widget build(BuildContext context) {
    final label = count > 1 ? '삭제된 메시지 $count개' : '삭제된 메시지';
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 3),
      child: Row(
        children: [
          // 아주 옅은 세로선
          Container(width: 2, height: 12, color: LlackColors.rule),
          const SizedBox(width: 8),
          Text(label, style: LlackTypography.caption.copyWith(color: LlackColors.muted)),
        ],
      ),
    );
  }
}
