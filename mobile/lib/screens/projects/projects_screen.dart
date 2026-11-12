import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/llack_avatar.dart';
import '../main_shell.dart';
import 'task_detail_sheet.dart';
import 'task_dialog.dart';
import '../../widgets/app_snack_bar.dart';

class ProjectsScreen extends StatefulWidget {
  /// 태블릿에서는 좌측 레일에 검색/아바타가 있어 앱바 공통 액션을 숨긴다.
  final bool showCommonActions;

  const ProjectsScreen({super.key, this.showCommonActions = true});

  @override
  State<ProjectsScreen> createState() => _ProjectsScreenState();
}

/// 상태 필터(요청/할 일/진행 중/완료) 인덱스.
///
/// 로컬 TabController 에만 두면 기기 회전(폰↔태블릿 레이아웃 전환)으로 State 가 재생성될 때
/// 필터가 0(요청)으로 초기화된다 (§9-38).
/// 화면 State 밖(파일 레벨)에 보관해 회전해도 유지되게 한다.
final ValueNotifier<int> _taskStatusFilterIndex = ValueNotifier<int>(0);

class _ProjectsScreenState extends State<ProjectsScreen> with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  late TabController _tabController;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // 저장된 필터 인덱스로 시작한다 (회전 후에도 같은 탭이 선택되어 있어야 한다)
    _tabController = TabController(length: 4, initialIndex: _taskStatusFilterIndex.value, vsync: this);
    _tabController.addListener(_syncStatusFilterIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      // Core 가 이미 프로젝트를 불러왔다면 다시 부르지 않는다 (F-5 중복 요청 방지).
      // 목록이 비었는지로는 판단하지 않는다 — 로더가 성공했는지만 본다.
      if (!state.hasLoadedProjects) state.loadProjects();
    });
  }

  @override
  void dispose() {
    _tabController
      ..removeListener(_syncStatusFilterIndex)
      ..dispose();
    super.dispose();
  }

  /// 탭이 바뀌면 저장된 인덱스를 갱신한다
  void _syncStatusFilterIndex() {
    if (_taskStatusFilterIndex.value != _tabController.index) {
      _taskStatusFilterIndex.value = _tabController.index;
    }
  }

  void _showNewProjectDialog(BuildContext context) {
    // 컨트롤러를 대화상자가 직접 소유하도록 위젯으로 분리했다 (9-10a)
    showDialog<void>(
      context: context,
      builder: (_) => const _NewProjectDialog(),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    final projects = state.projects;
    final activeProject = state.activeProject;
    final roadmaps = state.activeRoadmaps;
    final selectedRoadmapId = state.selectedRoadmapId;

    // 목록이 비면 (불러오기 실패로 목록이 비었을 때 포함) 빈 상태 화면을 보여준다.
    // (선택값만 남아 있는 상태로 드롭다운을 그리면 비어 보이기만 한다)
    if (projects.isEmpty) {
      return Scaffold(
        backgroundColor: LlackColors.paper,
        appBar: LlackAppBar(
          tabTitle: '프로젝트',
          showCommonActions: widget.showCommonActions,
          actions: [
            IconButton(
              icon: const Icon(Icons.add_rounded, size: 22),
              tooltip: '새 프로젝트',
              onPressed: () => _showNewProjectDialog(context),
            ),
          ],
        ),
        body: RefreshIndicator(
          onRefresh: () => state.loadProjects(),
          color: LlackColors.accent,
          // 목록이 비어도 당겨서 고침할 수 있게 스크롤 가능하게 만든다.
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // 실패와 "프로젝트 없음" 을 구분해서 보여준다 (§1-A-13)
                        if (state.projectsError != null) ...[
                          SectionErrorBanner(
                            message: state.projectsError!,
                            onRetry: () => state.retryProjects(),
                          ),
                          const SizedBox(height: 16),
                        ],
                        Text(
                          '프로젝트가 없습니다',
                          style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        ElevatedButton.icon(
                          icon: const Icon(Icons.add, size: 18),
                          label: const Text('새 프로젝트 만들기'),
                          onPressed: () => _showNewProjectDialog(context),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    final allTasks = state.activeProjectTasks;
    // Filter tasks by selected roadmap if any
    final filteredTasks = selectedRoadmapId == null
        ? allTasks
        : allTasks.where((t) => t.roadmapId == selectedRoadmapId).toList();

    final requestTasks = filteredTasks.where((t) => t.status == TaskStatus.request).toList();
    final todoTasks = filteredTasks.where((t) => t.status == TaskStatus.todo).toList();
    final inProgressTasks = filteredTasks.where((t) => t.status == TaskStatus.inProgress).toList();
    final doneTasks = filteredTasks.where((t) => t.status == TaskStatus.done).toList();

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: LlackAppBar(
        tabTitle: '프로젝트',
        showCommonActions: widget.showCommonActions,
        // 프로젝트 선택 드롭다운이 앱바 제목을 대신한다 (§3-C-6: isExpanded + ellipsis)
        titleWidget: DropdownButtonHideUnderline(
          child: DropdownButton<String>(
            // 프로젝트 "id" 를 값으로 쓴다.
            // (객체 자체를 값으로 쓰면 목록을 다시 불러올 때 인스턴스가 달라져
            //  "선택값이 목록에 없다" 는 assertion 으로 화면이 죽는다)
            value: _selectedProjectId(projects, activeProject),
            isDense: true,
            isExpanded: true,
            icon: const Icon(Icons.keyboard_arrow_down, color: LlackColors.ink),
            // 목록에 선택 항목이 없으면(재로드 직후 등) 제목을 빈칸으로 두지 않는다
            hint: Text(
              '프로젝트 선택',
              style: theme.textTheme.titleLarge?.copyWith(fontSize: 17, color: LlackColors.muted),
            ),
            selectedItemBuilder: (context) => projects
                .map(
                  (p) => Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      p.name,
                      style: theme.textTheme.titleLarge?.copyWith(fontSize: 17),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                )
                .toList(),
            items: projects.map((p) {
              return DropdownMenuItem(
                value: p.id,
                child: Text(
                  p.name,
                  style: theme.textTheme.titleLarge?.copyWith(fontSize: 17),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              );
            }).toList(),
            onChanged: (id) {
              if (id == null) return;
              // 같은 이름의 프로젝트가 있을 수 있으므로 id 로 찾는다.
              for (final p in projects) {
                if (p.id == id) {
                  state.selectProject(p);
                  return;
                }
              }
            },
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_rounded, size: 22),
            tooltip: '새 프로젝트',
            onPressed: () => _showNewProjectDialog(context),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: Size.fromHeight(roadmaps.isNotEmpty ? 88 : 48),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Roadmap filter chips
              if (roadmaps.isNotEmpty)
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    children: [
                      FilterChip(
                        label: const Text('모든 카드'),
                        selected: selectedRoadmapId == null,
                        selectedColor: LlackColors.accentSoft,
                        checkmarkColor: LlackColors.accent,
                        onSelected: (_) => state.filterRoadmap(null),
                      ),
                      ...roadmaps.map((r) {
                        final isSel = selectedRoadmapId == r.id;
                        return Padding(
                          padding: const EdgeInsets.only(left: 6),
                          child: FilterChip(
                            label: Text(r.name),
                            selected: isSel,
                            selectedColor: LlackColors.accentSoft,
                            checkmarkColor: LlackColors.accent,
                            onSelected: (_) => state.filterRoadmap(r.id),
                          ),
                        );
                      }),
                    ],
                  ),
                ),

              // TabBar for columns
              TabBar(
                controller: _tabController,
                indicatorColor: LlackColors.accent,
                labelColor: LlackColors.accentDeep,
                unselectedLabelColor: LlackColors.muted,
                labelStyle: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w700),
                unselectedLabelStyle: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w500),
                tabs: [
                  Tab(text: '요청 (${requestTasks.length})'),
                  Tab(text: '할 일 (${todoTasks.length})'),
                  Tab(text: '진행 중 (${inProgressTasks.length})'),
                  Tab(text: '완료 (${doneTasks.length})'),
                ],
              ),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: LlackColors.accent,
        foregroundColor: LlackColors.accentInk,
        elevation: 2,
        onPressed: () {
          final currentStatus = TaskStatus.values[_tabController.index];
          showDialog(
            context: context,
            builder: (_) => TaskDialog(initialStatus: currentStatus),
          );
        },
        tooltip: '새 할 일',
        child: const Icon(Icons.add_rounded),
      ),
      body: Column(
        children: [
          // 프로젝트 목록을 불러오지 못한 경우에도 카드 화면을 가리지 않고 위에 배너로 알린다
          if (state.projectsError != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
              child: SectionErrorBanner(
                message: state.projectsError!,
                onRetry: () => state.retryProjects(),
              ),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => state.loadProjects(),
              color: LlackColors.accent,
              // TabBarView 안의 카드 목록은 스크롤 알림이 depth 1 로 올라온다.
              // (기본 필터는 depth 0 만 받으므로 당겨서 고침이 동작하지 않는다)
              notificationPredicate: (n) => n.depth <= 1 && n.metrics.axis == Axis.vertical,
              child: TabBarView(
                controller: _tabController,
                children: [
                  _buildTaskList(requestTasks),
                  _buildTaskList(todoTasks),
                  _buildTaskList(inProgressTasks),
                  _buildTaskList(doneTasks),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 현재 선택된 프로젝트의 id.
  ///
  /// 목록을 다시 불러오면 같은 프로젝트라도 인스턴스가 새로 만들어진다.
  /// 그래서 **목록에 있는 새 인스턴스와 id 로 비교**해서 찾고,
  /// 목록에 없으면 null 을 돌려준다 (드롭다운 assertion 으로 죽지 않도록).
  String? _selectedProjectId(List<Project> projects, Project? activeProject) {
    if (activeProject == null) return null;
    for (final p in projects) {
      if (p.id == activeProject.id) return p.id;
    }
    return null;
  }

  Widget _buildTaskList(List<Task> tasks) {
    final theme = Theme.of(context);

    if (tasks.isEmpty) {
      // 카드가 하나도 없어도 당겨서 고침이 가능해야 한다.
      // (빈 목록이라 스크롤이 안 되면 새로고침 경로가 사라진다)
      return LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Text(
                '카드가 없습니다',
                style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
              ),
            ),
          ),
        ),
      );
    }

    return ListView.builder(
      // 하단 FAB 가 마지막 카드를 가리지 않도록 여백을 둔다
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
      itemCount: tasks.length,
      itemBuilder: (ctx, i) {
        final task = tasks[i];
        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          child: InkWell(
            onTap: () {
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (_) => TaskDetailSheet(task: task),
              );
            },
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
                  if (task.description.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      task.description,
                      style: theme.textTheme.labelMedium?.copyWith(color: LlackColors.ink2),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 10),
                  LayoutBuilder(
                    builder: (context, constraints) => Row(
                      children: [
                        // 왼쪽 정보(담당자·마감일·댓글수)는 남는 폭을 가져가고,
                        // 로드맵 칩은 Expanded 밖이라 항상 행의 오른쪽 끝에 붙는다 (§9-40)
                        Expanded(
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (task.assignee != null) ...[
                                LlackAvatar(name: task.assignee!.name, size: 22, fontSize: 10),
                                const SizedBox(width: 6),
                                // 이름이 길면 Row 가 넘치지 않도록 Flexible + ellipsis (§3-C-5)
                                Flexible(
                                  child: Text(
                                    task.assignee!.name,
                                    style: theme.textTheme.labelSmall,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                const SizedBox(width: 12),
                              ],
                              if (task.dueAt != null) ...[
                                const Icon(Icons.schedule, size: 13, color: LlackColors.muted),
                                const SizedBox(width: 4),
                                Text(
                                  DateFormat('M.d').format(task.dueAt!.toLocal()),
                                  style: theme.textTheme.labelSmall,
                                ),
                                const SizedBox(width: 12),
                              ],
                              if (task.comments.isNotEmpty || task.commentCount > 0) ...[
                                const Icon(Icons.mode_comment_outlined, size: 13, color: LlackColors.muted),
                                const SizedBox(width: 4),
                                Text(
                                  '${task.comments.isNotEmpty ? task.comments.length : task.commentCount}',
                                  style: theme.textTheme.labelSmall,
                                ),
                              ],
                            ],
                          ),
                        ),
                        if (task.roadmapName != null)
                          // 칩은 flex 자식이 아니면 고유 길이 그대로 잡혀 카드 밖으로 넘친다 (§9-41).
                          // 행 폭의 40% 로 상한을 걸면 오른쪽 끝을 유지하면서 말줄임도 동작한다.
                          ConstrainedBox(
                            constraints: BoxConstraints(maxWidth: constraints.maxWidth * 0.4),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: LlackColors.surfaceWell,
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                task.roadmapName!,
                                style: theme.textTheme.labelSmall,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// 새 프로젝트 다이얼로그.
///
/// 컨트롤러를 이 위젯이 직접 소유해 dispose 로 정리한다 (9-10a).
/// 생성 중에는 버튼을 잠가 연타 중복 생성을 막고 (9-4),
/// 실패하면 이유를 스낵바로 알려준다.
class _NewProjectDialog extends StatefulWidget {
  const _NewProjectDialog();

  @override
  State<_NewProjectDialog> createState() => _NewProjectDialogState();
}

class _NewProjectDialogState extends State<_NewProjectDialog> {
  final _nameCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  bool _isSubmitting = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty || _isSubmitting) return;

    setState(() => _isSubmitting = true);
    final state = context.read<AppState>();
    try {
      await state.createProject(name: name, description: _descCtrl.text.trim());
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      // 실패 이유를 알려야 "버튼이 죽었다" 고 느끼지 않는다
      setState(() => _isSubmitting = false);
      showAppSnackBar(context, '프로젝트 생성에 실패했습니다: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AlertDialog(
      title: Text('새 프로젝트', style: theme.textTheme.titleLarge),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _nameCtrl,
            autofocus: true,
            decoration: const InputDecoration(labelText: '프로젝트 이름', hintText: '예: 2026 하반기 리뉴얼'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _descCtrl,
            decoration: const InputDecoration(labelText: '설명', hintText: '프로젝트 목적 및 개요'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _isSubmitting ? null : () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: _isSubmitting ? null : _create,
          child: _isSubmitting
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('생성'),
        ),
      ],
    );
  }
}
