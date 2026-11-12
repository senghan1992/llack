import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_theme.dart';
import '../theme/llack_typography.dart';

class MessageComposer extends StatefulWidget {
  /// 메시지를 보내고 성공 여부를 돌려준다. (false 면 전송 실패)
  final Future<bool> Function(String body) onSend;
  final ValueChanged<bool>? onTyping;
  final Message? replyTo;
  final VoidCallback? onCancelReply;
  final String hintText;

  const MessageComposer({
    super.key,
    required this.onSend,
    this.onTyping,
    this.replyTo,
    this.onCancelReply,
    this.hintText = '메시지 보내기...',
  });

  @override
  State<MessageComposer> createState() => _MessageComposerState();
}

class _MessageComposerState extends State<MessageComposer> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _canSend = false;
  bool _isSending = false;
  Timer? _typingTimer;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_handleTextChanged);
  }

  void _handleTextChanged() {
    final hasText = _controller.text.trim().isNotEmpty;
    if (hasText != _canSend) {
      setState(() => _canSend = hasText);
    }
    if (widget.onTyping != null) {
      widget.onTyping!(true);
      _typingTimer?.cancel();
      _typingTimer = Timer(const Duration(seconds: 3), () {
        widget.onTyping?.call(false);
      });
    }
  }

  Future<void> _handleSend() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isSending) return;

    // 연타로 같은 메시지가 중복 전송되지 않도록 전송 중 상태로 잠근다.
    setState(() => _isSending = true);
    bool ok = false;
    try {
      ok = await widget.onSend(text);
    } catch (_) {
      ok = false;
    }
    if (!mounted) return;

    if (ok) {
      _controller.clear();
      _typingTimer?.cancel();
      widget.onTyping?.call(false);
    } else {
      // 전송에 실패하면 지운 글은 되살리고 사용자에게 알린다.
      _controller.text = text;
      _controller.selection = TextSelection.collapsed(offset: text.length);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('전송에 실패했습니다. 다시 시도해주세요.')),
      );
    }
    setState(() => _isSending = false);
  }

  @override
  void dispose() {
    _typingTimer?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sendEnabled = _canSend && !_isSending;

    return Container(
      decoration: const BoxDecoration(
        color: LlackColors.paper,
        border: Border(
          top: BorderSide(color: LlackColors.rule, width: 1),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (widget.replyTo != null) _buildReplyBanner(),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                        color: LlackColors.surfaceWell,
                        borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                        border: Border.all(color: LlackColors.rule, width: 1),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      child: TextField(
                        controller: _controller,
                        focusNode: _focusNode,
                        maxLines: 5,
                        minLines: 1,
                        textInputAction: TextInputAction.newline,
                        style: LlackTypography.body,
                        decoration: InputDecoration(
                          hintText: widget.hintText,
                          hintStyle: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          isDense: true,
                          contentPadding: const EdgeInsets.symmetric(vertical: 8),
                          filled: false,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  // 전송 버튼: 최소 44dp 터치 타깃
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: sendEnabled ? LlackColors.accent : LlackColors.ruleSoft,
                      borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                    ),
                    child: IconButton(
                      icon: _isSending
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: LlackColors.muted),
                            )
                          : Icon(
                              Icons.arrow_upward_rounded,
                              color: sendEnabled ? LlackColors.accentInk : LlackColors.muted,
                              size: 20,
                            ),
                      onPressed: sendEnabled ? _handleSend : null,
                      padding: EdgeInsets.zero,
                      tooltip: '전송',
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildReplyBanner() {
    final target = widget.replyTo!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      color: LlackColors.accentSoft.withValues(alpha: 0.5),
      child: Row(
        children: [
          const Icon(Icons.reply_rounded, size: 16, color: LlackColors.accent),
          const SizedBox(width: 8),
          Expanded(
            child: RichText(
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              text: TextSpan(
                style: LlackTypography.caption.copyWith(color: LlackColors.ink),
                children: [
                  TextSpan(
                    text: '${target.author.name}님에게 답글: ',
                    style: const TextStyle(fontWeight: FontWeight.w600, color: LlackColors.accent),
                  ),
                  TextSpan(
                    text: target.deletedAt != null ? '삭제된 메시지' : target.body,
                    style: const TextStyle(color: LlackColors.ink2),
                  ),
                ],
              ),
            ),
          ),
          // 답글 취소 버튼도 최소 44dp 터치 타깃
          IconButton(
            onPressed: widget.onCancelReply,
            icon: const Icon(Icons.close, size: 18, color: LlackColors.muted),
            tooltip: '답글 취소',
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          ),
        ],
      ),
    );
  }
}
