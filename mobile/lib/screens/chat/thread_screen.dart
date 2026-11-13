import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/message_bubble.dart';
import '../../widgets/message_composer.dart';
import 'message_actions.dart';
import '../../widgets/connection_banner.dart';

class ThreadScreen extends StatefulWidget {
  final Message rootMessage;

  const ThreadScreen({super.key, required this.rootMessage});

  @override
  State<ThreadScreen> createState() => _ThreadScreenState();
}

class _ThreadScreenState extends State<ThreadScreen> {
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    // 스레드를 반복해서 열면 회수되지 않은 ScrollController 가 쌓인다.
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final myId = state.currentUser?.id;
    final replies = state.threadReplies;
    final isLoading = state.isLoadingReplies;

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
             Text('스레드 답글', style: LlackTypography.title),
            Text(
              '${widget.rootMessage.author.name}님의 메시지',
              style: LlackTypography.caption,
            ),
          ],
        ),
        // 실시간 연결이 끊어졌을 때도 알린다 (셸의 배너는 push 된 라우트에 가려진다)
        bottom: connectionBannerBottom(state),
      ),
      body: ScaffoldMessenger(
        // 채팅 화면과 마찬가지로 화면 전용 messenger 를 둔다.
        // SnackBar 가 답글 입력창(composer)을 덮지 않도록 메시지 영역에만 그린다.
        child: Column(
          children: [
            Expanded(
              child: Builder(
                // Builder 로 안쪽 context 를 잡아 가장 가까운(중첩) messenger 를 쓰게 한다.
                builder: (innerCtx) => Scaffold(
                  backgroundColor: Colors.transparent,
                  resizeToAvoidBottomInset: false,
                  body: ListView(
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    children: [
                      // Root message container
                      Container(
                        margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        decoration: BoxDecoration(
                          color: LlackColors.surfaceWell.withValues(alpha: 0.6),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: MessageBubble(
                          message: widget.rootMessage,
                          isMine: widget.rootMessage.userId == myId,
                          fileUrlResolver: state.api.absoluteFileUrl,
                          onToggleReaction: (emoji) => state.toggleReaction(widget.rootMessage, emoji),
                          onTogglePin: () => state.togglePin(widget.rootMessage),
                          // 루트 메시지의 삭제 메뉴가 조용히 아무 일도 하지 않지 않도록 연결한다.
                          onDelete: () => MessageActions.deleteMessage(
                            innerCtx,
                            widget.rootMessage,
                            widget.rootMessage.channelId,
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          children: [
                            const Expanded(child: Divider()),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Text(
                                '답글 ${replies.length}개',
                                style: LlackTypography.caption.copyWith(fontWeight: FontWeight.w600),
                              ),
                            ),
                            const Expanded(child: Divider()),
                          ],
                        ),
                      ),
                      if (isLoading)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(16),
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      else if (replies.isEmpty)
                        Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Text(
                              '아직 답글이 없습니다. 첫 답글을 남겨보세요.',
                              style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                            ),
                          ),
                        )
                      else
                        ...replies.map((reply) {
                          return MessageBubble(
                            message: reply,
                            isMine: reply.userId == myId,
                            fileUrlResolver: state.api.absoluteFileUrl,
                            onToggleReaction: (emoji) => state.toggleReaction(reply, emoji),
                            onTogglePin: () => state.togglePin(reply),
                            onEdit: (newBody) => state.editMessage(reply.id, newBody),
                            onDelete: () =>
                                MessageActions.deleteMessage(innerCtx, reply, reply.channelId),
                          );
                        }),
                    ],
                  ),
                ),
              ),
            ),
            MessageComposer(
              hintText: '답글 입력...',
              onSend: (text) async {
                // sendReply 의 반환값을 그대로 돌려준다.
                // false 면(스레드가 이미 닫혔거나 서버 오류) 컴포저가 글자를 되살리고
                // "전송에 실패했습니다. 다시 시도해주세요." 스낵바를 띄운다.
                final ok = await state.sendReply(text);
                if (!ok) return false;
                await Future.delayed(const Duration(milliseconds: 100));
                if (_scrollController.hasClients) {
                  _scrollController.animateTo(
                    _scrollController.position.maxScrollExtent,
                    duration: const Duration(milliseconds: 250),
                    curve: Curves.easeOut,
                  );
                }
                return true;
              },
            ),
          ],
        ),
      ),
    );
  }
}
