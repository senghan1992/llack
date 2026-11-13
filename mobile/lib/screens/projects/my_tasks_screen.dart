import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import 'task_detail_sheet.dart';

/// "내 할 일" 목록.
///
/// 프로젝트 보드의 탭으로 쓰인다.
/// 항목마다 프로젝트 이름 · 상태 · 마감일을 보여주고, 누르면 그 할 일의 상세가 열린다.
class MyTasksScreen extends StatelessWidget {
  const MyTasksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final tasks = state.myTasks;
    final theme = Theme.of(context);

    if (tasks.isEmpty) {
      // 카드가 하나도 없어도 당겨서 고침이 가능해야 한다.
      return LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Text(
                '내게 맡은 할 일이 없습니다',
                style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
              ),
            ),
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
      itemCount: tasks.length,
      itemBuilder: (context, i) {
        final task = tasks[i];
        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          child: InkWell(
            onTap: () => _openTask(context, task),
            borderRadius: BorderRadius.circular(14),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    task.title,
                    style: theme.textTheme.titleMedium,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      // 프로젝트 이름이 길어도 화면을 넘지 않도록 Flexible (§3-C-5)
                      Flexible(
                        child: Text(
                          _projectName(state, task.projectId),
                          style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 10),
                      _StatusBadge(status: task.status),
                      if (task.dueAt != null) ...[
                        const SizedBox(width: 10),
                         Icon(Icons.schedule, size: 13, color: LlackColors.muted),
                        const SizedBox(width: 4),
                        Text(
                          DateFormat('M.d').format(task.dueAt!.toLocal()),
                          style: theme.textTheme.labelSmall,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// 그 할 일이 있는 프로젝트 이름을 찾는다.
  String _projectName(AppState state, String projectId) {
    for (final project in state.projects) {
      if (project.id == projectId) return project.name;
    }
    return '프로젝트';
  }

  /// 할 일 상세를 연다.
  ///
  /// 카드가 다른 프로젝트의 것이면 그 프로젝트 보드를 먼저 연다.
  /// (상태 API 는 "선택된 프로젝트" 의 할 일만 고치기 때문이다)
  Future<void> _openTask(BuildContext context, Task task) async {
    final state = context.read<AppState>();
    if (state.activeProject?.id != task.projectId) {
      Project? target;
      for (final project in state.projects) {
        if (project.id == task.projectId) {
          target = project;
          break;
        }
      }
      if (target != null) await state.selectProject(target);
      if (!context.mounted) return;
    }
    if (!context.mounted) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => TaskDetailSheet(task: task),
    );
  }
}

/// 할 일 상태 배지.
class _StatusBadge extends StatelessWidget {
  final TaskStatus status;

  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: _colorForStatus(status).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        status.label,
        style: LlackTypography.caption.copyWith(
          color: _colorForStatus(status),
          fontWeight: FontWeight.w700,
        ),
      ),
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
