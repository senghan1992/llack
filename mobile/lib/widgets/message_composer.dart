import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_theme.dart';
import '../theme/llack_typography.dart';
import 'message_markdown.dart';

class MessageComposer extends StatefulWidget {
  /// 메시지를 보내고 성공 여부를 돌려준다. (false 면 전송 실패)
  ///
  /// [onSendWithAttachments] 가 있으면 그쪽이 우선 쓰인다.
  /// (둘 다 없으면 보낼 수 없다)
  final Future<bool> Function(String body)? onSend;

  /// 파일을 골라 업로드하고, (이름, 파일 id) 목록을 돌려준다. 취소하면 null.
  final Future<List<(String, String)>?> Function()? onUploadAttachments;

  /// 첨부 id 를 붙여 메시지를 보낸다. (onSendWithAttachments 가 있으면 그것을 우선 쓴다)
  final Future<bool> Function(String body, List<String>? attachmentIds)? onSendWithAttachments;

  /// 입력창 글자가 바뀔 때마다 호출된다. (초기값으로도 한 번 호출된다)
  final ValueChanged<String>? onChanged;

  /// 입력창의 처음 글자. (채널별 임시저장 글을 되돌릴 때 쓴다)
  final String initialText;

  final ValueChanged<bool>? onTyping;
  final Message? replyTo;
  final VoidCallback? onCancelReply;
  final String hintText;

  const MessageComposer({
    super.key,
    this.onSend,
    this.onUploadAttachments,
    this.onSendWithAttachments,
    this.onChanged,
    this.initialText = '',
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

  /// 아직 보내지 않은 첨부 파일. ((이름, 파일 id) 목록)
  final List<(String, String)> _attachments = [];

  /// 이모티콘 그리드를 펼쳐 놓았는지
  bool _showEmojiGrid = false;

  /// 파일을 올리는 중인지
  bool _uploading = false;

  /// 업로드가 끝날 때까지 기다리는 Future. (보내기를 기다릴 때 쓴다)
  Future<void>? _uploadFuture;

  bool _canSend = false;
  bool _isSending = false;
  Timer? _typingTimer;

  /// 마지막으로 알린 글자. (선택이 움직일 때는 알리지 않는다)
  String _lastText = '';

  @override
  void initState() {
    super.initState();
    // 채널을 옮겼다가 돌아왔을 때 쓰던 글을 되돌린다.
    if (widget.initialText.isNotEmpty) {
      _controller.text = widget.initialText;
      _controller.selection = TextSelection.collapsed(offset: widget.initialText.length);
      _lastText = widget.initialText;
      _canSend = true;
    }
    _controller.addListener(_handleTextChanged);

    // 초기값으로도 한 번 알려준다.
    // (부모가 build 중에 setState 하지 않도록 프레임이 끝난 뒤에 부른다)
    final onChanged = widget.onChanged;
    if (onChanged != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        onChanged(_controller.text);
      });
    }
  }

  void _handleTextChanged() {
    final text = _controller.text;
    if (text != _lastText) {
      _lastText = text;
      widget.onChanged?.call(text);
    }
    _updateCanSend();
    if (widget.onTyping != null) {
      widget.onTyping!(true);
      _typingTimer?.cancel();
      _typingTimer = Timer(const Duration(seconds: 3), () {
        widget.onTyping?.call(false);
      });
    }
  }

  /// 본문이 비어도 첨부가 있으면 보낼 수 있다.
  void _updateCanSend() {
    final canSend = _controller.text.trim().isNotEmpty || _attachments.isNotEmpty;
    if (canSend != _canSend) {
      setState(() => _canSend = canSend);
    }
  }

  Future<void> _handleSend() async {
    if (_isSending) return;
    if (_controller.text.trim().isEmpty && _attachments.isEmpty) return;

    // 업로드가 진행 중이면 끝날 때까지 기다린다. (첨부가 함께 붙는다)
    final pending = _uploadFuture;
    if (pending != null) {
      await pending;
      if (!mounted) return;
    }

    final text = _controller.text.trim();
    final ids = _attachments.map((file) => file.$2).toList();
    if (text.isEmpty && ids.isEmpty) return;

    // 연타로 같은 메시지가 중복 전송되지 않도록 전송 중 상태로 잠근다.
    setState(() => _isSending = true);
    bool ok = false;
    try {
      final sender = widget.onSendWithAttachments;
      if (sender != null) {
        ok = await sender(text, ids.isEmpty ? null : ids);
      } else {
        final legacy = widget.onSend;
        if (legacy != null) {
          ok = await legacy(text);
        }
      }
    } catch (_) {
      ok = false;
    }
    if (!mounted) return;

    if (ok) {
      _controller.clear();
      setState(() {
        _attachments.clear();
        _showEmojiGrid = false;
      });
      _typingTimer?.cancel();
      widget.onTyping?.call(false);
    } else {
      // 전송에 실패하면 지운 글은 되살리고 사용자에게 알린다.
      _controller.text = text;
      _controller.selection = TextSelection.collapsed(offset: text.length);
      _showError('전송에 실패했습니다. 다시 시도해주세요.');
    }
    setState(() => _isSending = false);
  }

  /// 파일을 골라 올리고 첨부 칩으로 보여준다.
  Future<void> _pickAttachments() async {
    final uploader = widget.onUploadAttachments;
    // 업로드 중에는 다시 들어올 수 없다.
    if (uploader == null || _uploading) return;

    setState(() => _uploading = true);
    final future = _upload(uploader);
    _uploadFuture = future;
    await future;
  }

  Future<void> _upload(Future<List<(String, String)>?> Function() uploader) async {
    List<(String, String)>? uploaded;
    Object? error;
    try {
      uploaded = await uploader();
    } catch (e) {
      error = e;
    }
    if (!mounted) return;

    _uploadFuture = null;
    setState(() => _uploading = false);

    if (error != null) {
      // 실패하면 칩은 추가하지 않고 이유를 알려준다.
      _showError('첨부를 올리지 못했습니다: ${_errorText(error)}');
      return;
    }
    // 취소하면(null) 아무것도 하지 않는다.
    if (uploaded == null) return;
    final files = uploaded;

    setState(() => _attachments.addAll(files));
    _updateCanSend();
  }

  /// 아직 보내지 않은 첨부에서 하나를 뺀다.
  void _removeAttachment(String id) {
    setState(() => _attachments.removeWhere((file) => file.$2 == id));
    _updateCanSend();
  }

  /// 이모티콘을 현재 커서 위치에 넣는다. (선택 영역이 있으면 대체한다)
  void _insertEmoji(String emoji) {
    final text = _controller.text;
    final selection = _controller.selection;
    final start = selection.isValid ? selection.start : text.length;
    final end = selection.isValid ? selection.end : text.length;
    final safeStart = start.clamp(0, text.length);
    final safeEnd = end.clamp(safeStart, text.length);

    final next = text.replaceRange(safeStart, safeEnd, emoji);
    _controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: safeStart + emoji.length),
    );
    _focusNode.requestFocus();
  }

  void _showError(String text) {
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(SnackBar(content: Text(text)));
  }

  /// 오류에서 사람이 읽을 수 있는 이유를 뽑는다.
  String _errorText(Object error) {
    final text = error.toString();
    if (text.startsWith('Exception: ')) return text.substring('Exception: '.length);
    return text;
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
    // 보낼 방법이 하나도 없으면 전송할 수 없다.
    final canSendAtAll = widget.onSend != null || widget.onSendWithAttachments != null;
    final sendEnabled = _canSend && !_isSending && canSendAtAll;

    return Container(
      decoration: BoxDecoration(
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
            if (_uploading) _buildUploadingBanner(),
            if (_attachments.isNotEmpty) _buildAttachmentChips(),
            if (_showEmojiGrid) _buildEmojiGrid(),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  // 파일 첨부 버튼 (_CALLBACK 이 있을 때만 그린다)
                  if (widget.onUploadAttachments != null) _buildAttachButton(),
                  _buildEmojiButton(),
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
                          ?  SizedBox(
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

  /// 파일 첨부 버튼. (업로드 중에는 눌리지 않는다)
  Widget _buildAttachButton() {
    return IconButton(
      onPressed: _uploading ? null : _pickAttachments,
      icon: _uploading
          ?  SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: LlackColors.muted),
            )
          : Icon(Icons.attach_file, size: 20, color: LlackColors.muted),
      tooltip: '파일 첨부',
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
    );
  }

  /// 이모티콘 버튼. (누르면 아래로 그리드가 펼쳐진다)
  Widget _buildEmojiButton() {
    return IconButton(
      onPressed: () => setState(() => _showEmojiGrid = !_showEmojiGrid),
      icon: Icon(Icons.sentiment_satisfied, size: 20, color: LlackColors.muted),
      tooltip: '이모티콘',
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
    );
  }

  /// 업로드 중 표시.
  Widget _buildUploadingBanner() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
      child: Row(
        children: [
           SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(strokeWidth: 2, color: LlackColors.accent),
          ),
          const SizedBox(width: 8),
          Text('업로드 중', style: LlackTypography.caption.copyWith(color: LlackColors.accentDeep)),
        ],
      ),
    );
  }

  /// 붙일 파일 칩. (이름 + 삭제)
  Widget _buildAttachmentChips() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: _attachments.map((file) {
          final name = file.$1;
          final id = file.$2;
          return Container(
            padding: const EdgeInsets.fromLTRB(8, 4, 2, 4),
            decoration: BoxDecoration(
              color: LlackColors.surfaceRaise,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: LlackColors.rule),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.insert_drive_file_outlined, size: 14, color: LlackColors.accent),
                const SizedBox(width: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 160),
                  child: Text(
                    name,
                    style: LlackTypography.caption.copyWith(color: LlackColors.ink),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  onPressed: () => _removeAttachment(id),
                  icon: Icon(Icons.close, size: 14, color: LlackColors.muted),
                  tooltip: '첨부 제거',
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  /// 빠른 이모티콘 그리드. (누르면 커서 위치에 넣는다)
  Widget _buildEmojiGrid() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      color: LlackColors.surfaceWell,
      child: Wrap(
        spacing: 4,
        runSpacing: 4,
        children: quickReactions.map((emoji) {
          return InkWell(
            onTap: () => _insertEmoji(emoji),
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              width: 40,
              height: 40,
              child: Center(child: Text(emoji, style: const TextStyle(fontSize: 20))),
            ),
          );
        }).toList(),
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
           Icon(Icons.reply_rounded, size: 16, color: LlackColors.accent),
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
                    style: TextStyle(fontWeight: FontWeight.w600, color: LlackColors.accent),
                  ),
                  TextSpan(
                    text: target.deletedAt != null ? '삭제된 메시지' : target.body,
                    style: TextStyle(color: LlackColors.ink2),
                  ),
                ],
              ),
            ),
          ),
          // 답글 취소 버튼도 최소 44dp 터치 타깃
          IconButton(
            onPressed: widget.onCancelReply,
            icon: Icon(Icons.close, size: 18, color: LlackColors.muted),
            tooltip: '답글 취소',
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          ),
        ],
      ),
    );
  }
}
