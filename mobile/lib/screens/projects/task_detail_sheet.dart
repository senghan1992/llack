import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';
import 'task_dialog.dart';
import '../../widgets/app_snack_bar.dart';

class TaskDetailSheet extends StatefulWidget {
  final Task task;

  const TaskDetailSheet({super.key, required this.task});

  @override
  State<TaskDetailSheet> createState() => _TaskDetailSheetState();
}

class _TaskDetailSheetState extends State<TaskDetailSheet> {
  final _commentCtrl = TextEditingController();

  /// 전송 중인 댓글(낙관적 표시).
  /// 서버에 저장되어 상태의 댓글로 확정되면 제거된다.
  final List<String> _pendingComments = [];
  bool _isSubmittingComment = false;

  @override
  void dispose() {
    _commentCtrl.dispose();
    super.dispose();
  }

  /// 댓글을 보낸다.
  ///
  /// await 동안 시트가 닫힐 수 있으므로 글자는 await 전에 떼어 두고,
  /// await 이후에는 컨트롤러를 만지지 않는다. (dispose 된 컨트롤러를 쓰면 빨간 화면)
  /// 전송 중에는 곧바로 목록에 보여주고(낙관적 업데이트), 서버 응답으로 확정한다.
  Future<void> _sendComment() async {
    final text = _commentCtrl.text.trim();
    if (text.isEmpty || _isSubmittingComment) return;

    setState(() {
      _isSubmittingComment = true;
      _pendingComments.add(text);
    });
    // 낙관적 처리: 입력창은 바로 비운다 (보냈다는 인상을 즉시 준다)
    _commentCtrl.clear();

    final state = context.read<AppState>();
    try {
      await state.addTaskComment(widget.task.id, text);
      if (!mounted) return;
      // 서버가 확정했으면(=상태에 댓글이 생겼으면) 임시 표시를 지운다
      final confirmed = state.activeProjectTasks
          .where((t) => t.id == widget.task.id)
          .expand((t) => t.comments)
          .any((c) => c.body == text);
      setState(() {
        if (confirmed) _pendingComments.remove(text);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pendingComments.remove(text);
        _isSubmittingComment = false;
      });
      // 실패하면 다시 고칠 수 있게 글자를 되돌려 놓는다
      _commentCtrl.text = text;
      showAppSnackBar(context, '댓글 작성에 실패했습니다: $e');
    }
    if (mounted) setState(() => _isSubmittingComment = false);
  }

  /// 할 일 편집 다이얼로그를 연다.
  ///
  /// 이 시트는 빌드할 때마다 상태에서 최신 태스크를 다시 찾으므로
  /// (state.activeProjectTasks) 편집이 끝나면 **시트를 닫지 않아도** 제목이 갱신된다.
  void _openEditDialog(BuildContext context, Task task) {
    showDialog(
      context: context,
      builder: (_) => TaskDialog(editing: task),
    );
  }

  Future<void> _deleteTask() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('할 일 삭제'),
        content: Text('\'${widget.task.title}\' 할 일을 삭제하시겠습니까?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: LlackColors.presenceBusy),
            child: const Text('삭제'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    final state = context.read<AppState>();
    // 삭제 성공을 확인하고 나서 시트를 닫는다.
    // (먼저 닫으면 삭제가 조용히 실패해서 할 일이 그대로 남아 혼란스러워진다)
    final ok = await state.deleteTask(widget.task.id);
    if (!mounted) return;
    if (!ok) {
      showAppSnackBar(context, '할 일을 삭제하지 못했습니다');
      return;
    }
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    // find fresh task instance from state if updated
    final allTasks = state.activeProjectTasks;
    final task = allTasks.firstWhere((t) => t.id == widget.task.id, orElse: () => widget.task);

    return AnimatedPadding(
      // 키보드가 올라올 때 시트 높이가 튀지 않도록 애니메이션으로 맞춘다 (9-10c)
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Container(
        decoration: const BoxDecoration(
          color: LlackColors.surfaceRaise,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Drag handle
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.symmetric(vertical: 8),
                  decoration: BoxDecoration(color: LlackColors.rule, borderRadius: BorderRadius.circular(2)),
                ),
              ),

              // Header
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    _buildStatusDropdown(context, state, task),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 20),
                      tooltip: '할 일 수정',
                      // 최소 44dp 터치 타깃 (§9-7)
                      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                      onPressed: () => _openEditDialog(context, task),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 20, color: LlackColors.presenceBusy),
                      tooltip: '할 일 삭제',
                      onPressed: _deleteTask,
                    ),
                    IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => Navigator.pop(context)),
                  ],
                ),
              ),

              // Content
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(task.title, style: LlackTypography.title.copyWith(fontSize: 18)),
                      const SizedBox(height: 12),

                      // Metadata row — 이름/일정/로드맵이 길어져도 Row 가 넘치지 않도록 Flexible 사용 (§3-C-5)
                      Row(
                        children: [
                          if (task.assignee != null) ...[
                            LlackAvatar(name: task.assignee!.name, size: 24, fontSize: 10),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                task.assignee!.name,
                                style: LlackTypography.bodySmall,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 14),
                          ],
                          if (task.dueAt != null) ...[
                            const Icon(Icons.calendar_today_outlined, size: 14, color: LlackColors.muted),
                            const SizedBox(width: 4),
                            Text(DateFormat('yyyy.MM.dd').format(task.dueAt!.toLocal()), style: LlackTypography.monoTimestamp),
                            const SizedBox(width: 14),
                          ],
                          if (task.roadmapName != null)
                            Flexible(
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: LlackColors.surfaceWell,
                                  borderRadius: BorderRadius.circular(4),
                                  border: Border.all(color: LlackColors.rule),
                                ),
                                child: Text(
                                  task.roadmapName!,
                                  style: LlackTypography.caption,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ),
                        ],
                      ),

                      if (task.description.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        Text(task.description, style: LlackTypography.body),
                      ],

                      const SizedBox(height: 20),
                      const Divider(height: 1),
                      const SizedBox(height: 12),

                      // Comments section — 전송 중인 댓글(낙관적 표시)도 함께 보여준다
                      Text(
                        '의견 (${task.comments.length + _pendingComments.length})',
                        style: LlackTypography.subtitle.copyWith(fontSize: 14),
                      ),
                      const SizedBox(height: 8),

                      if (task.comments.isEmpty && _pendingComments.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Text('아직 작성된 의견이 없습니다.', style: LlackTypography.caption),
                        )
                      else
                        ListView.separated(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          itemCount: task.comments.length + _pendingComments.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 8),
                          itemBuilder: (ctx, i) {
                            // 앞쪽은 확정된 댓글, 뒤쪽은 전송 중인 댓글
                            if (i >= task.comments.length) {
                              return _buildPendingCommentRow(_pendingComments[i - task.comments.length]);
                            }
                            final c = task.comments[i];
                            return Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                LlackAvatar(name: c.author.name, size: 28, fontSize: 11),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: LlackColors.surfaceWell,
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Text(
                                              c.author.name,
                                              style: LlackTypography.caption.copyWith(fontWeight: FontWeight.w700),
                                            ),
                                            Text(
                                              DateFormat('MM.dd HH:mm').format(c.createdAt.toLocal()),
                                              style: LlackTypography.monoTimestamp,
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 4),
                                        Text(c.body, style: LlackTypography.bodySmall),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            );
                          },
                        ),
                    ],
                  ),
                ),
              ),

              // Comment input box
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: LlackColors.rule)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _commentCtrl,
                        decoration: const InputDecoration(
                          hintText: '의견 남기기...',
                          isDense: true,
                          contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      icon: _isSubmittingComment
                          ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.send_rounded, color: LlackColors.accent),
                      onPressed: _isSubmittingComment ? null : _sendComment,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 전송 중인 댓글 한 줄. (낙관적 업데이트 표시)
  Widget _buildPendingCommentRow(String body) {
    final me = context.read<AppState>().currentUser;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LlackAvatar(name: me?.name ?? '나', size: 28, fontSize: 11),
        const SizedBox(width: 8),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: LlackColors.surfaceWell,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(me?.name ?? '나', style: LlackTypography.caption.copyWith(fontWeight: FontWeight.w700)),
                    Text('전송 중', style: LlackTypography.monoTimestamp),
                  ],
                ),
                const SizedBox(height: 4),
                Text(body, style: LlackTypography.bodySmall),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStatusDropdown(BuildContext context, AppState state, Task task) {
    return PopupMenuButton<TaskStatus>(
      initialValue: task.status,
      onSelected: (newStatus) async {
        // 실패하면 상태가 바뀌지 않으므로 그대로 두고, 사유만 알려준다
        final ok = await state.updateTaskStatus(task, newStatus);
        if (!context.mounted || ok) return;
        showAppSnackBar(context, '상태를 바꾸지 못했습니다');
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: LlackColors.surfaceWell,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: LlackColors.rule),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: _colorForStatus(task.status), shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Text(task.status.label, style: LlackTypography.caption.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(width: 4),
            const Icon(Icons.arrow_drop_down, size: 16, color: LlackColors.muted),
          ],
        ),
      ),
      itemBuilder: (ctx) => TaskStatus.values.map((s) {
        return PopupMenuItem(
          value: s,
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: _colorForStatus(s), shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(s.label),
            ],
          ),
        );
      }).toList(),
    );
  }

  Color _colorForStatus(TaskStatus s) {
    switch (s) {
      case TaskStatus.request:
        return LlackColors.statusRequest;
      case TaskStatus.todo:
        return LlackColors.statusTodo;
      case TaskStatus.inProgress:
        return LlackColors.statusInProgress;
      case TaskStatus.done:
        return LlackColors.statusDone;
    }
  }
}
