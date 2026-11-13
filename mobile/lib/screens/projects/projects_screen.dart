import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/llack_avatar.dart';
import '../main_shell.dart';
import 'milestone_sheet.dart';
import 'my_tasks_screen.dart';
import 'project_settings_sheet.dart';
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

/// 보드 전체 탭 인덱스 (마일스톤 · 내 할 일 탭까지).
///
/// 상태 필터와 같은 이유로 파일 레벨에 둔다 (§9-38).
final ValueNotifier<int> _boardTabIndex = ValueNotifier<int>(0);

/// 프로젝트 거르기 (전체 / 내 프로젝트).
enum _ProjectScope { all, mine }

/// 프로젝트 거르기 상태. 회전해도 유지되게 파일 레벨에 둔다.
final ValueNotifier<_ProjectScope> _projectScope = ValueNotifier<_ProjectScope>(_ProjectScope.all);

class _ProjectsScreenState extends State<ProjectsScreen> with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  late TabController _tabController;

  /// 상태 탭(요청/할 일/진행 중/완료) 의 개수.
  static const int _statusTabCount = 4;

  /// "내 할 일" 탭 인덱스.
  static const int _myTasksTabIndex = 5;

  /// 셸 탭에서 프로젝트 탭의 위치. (셸의 네 탭 중 셋째)
  static const int _projectsShellTabIndex = 2;

  /// 셸의 탭 인덱스.
  ///
  /// dispose() 에서 context 를 읽으면 "비활성화된 위젯의 조상" 이 된다.
  /// 그래서 여기에 먼저 기억해 둔다.
  ValueNotifier<int>? _shellTabIndex;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // 저장된 탭 인덱스로 시작한다 (회전 후에도 같은 탭이 선택되어 있어야 한다)
    _tabController = TabController(length: 7, initialIndex: _boardTabIndex.value, vsync: this);
    _tabController.addListener(_syncTabIndex);
    // 셸에서 프로젝트 탭으로 다시 돌아오면 "내 할 일" 목록을 새로 불러온다.
    _shellTabIndex = context.read<AppState>().tabIndex;
    _shellTabIndex!.addListener(_onShellTabChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      // Core 가 이미 프로젝트를 불러왔다면 다시 부르지 않는다 (F-5 중복 요청 방지).
      // 목록이 비었는지로는 판단하지 않는다 — 로더가 성공했는지만 본다.
      if (!state.hasLoadedProjects) state.loadProjects();
      // "내 할 일" 탭으로 시작한 경우 목록을 불러온다.
      if (_tabController.index == _myTasksTabIndex) state.loadMyTasks();
    });
  }

  @override
  void dispose() {
    _tabController
      ..removeListener(_syncTabIndex)
      ..dispose();
    _shellTabIndex?.removeListener(_onShellTabChanged);
    super.dispose();
  }

  /// 셸 탭이 바뀌면 (프로젝트 탭으로 다시 왔을 때) "내 할 일" 목록을 갱신한다.
  void _onShellTabChanged() {
    if (!mounted) return;
    if (_shellTabIndex?.value != _projectsShellTabIndex) return;
    context.read<AppState>().loadMyTasks();
  }

  /// 탭이 바뀌면 저장된 인덱스를 갱신한다
  void _syncTabIndex() {
    final index = _tabController.index;
    if (index == _boardTabIndex.value) return;
    _boardTabIndex.value = index;
    // 상태 필터 인덱스는 상태 탭 안에서만 움직인다.
    if (index < _statusTabCount && _taskStatusFilterIndex.value != index) {
      _taskStatusFilterIndex.value = index;
    }
    // "내 할 일" 탭에 들어갈 때 목록을 불러온다. (들어올 때마다 새것을 보여준다)
    if (index == _myTasksTabIndex) {
      context.read<AppState>().loadMyTasks();
    }
    // 탭마다 FAB 이 달라지므로 화면을 다시 그린다.
    if (mounted) setState(() {});
  }

  /// 새 프로젝트 만들기와 프로젝트 설정을 연다.
  ///
  /// 만드는 것과 고치는 것이 같은 시트다. ([project] 가 null 이면 새로 만든다)
  void _openProjectSettings(BuildContext context, {Project? project}) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ProjectSettingsSheet(project: project),
    );
  }

  /// 프로젝트를 거르는 기준을 바꾼다.
  ///
  /// 지금 보고 있는 프로젝트가 걸러지면 그쪽으로 옮긴다.
  void _setScope(_ProjectScope scope) {
    if (_projectScope.value == scope) return;
    _projectScope.value = scope;
    final state = context.read<AppState>();
    final visible = _visibleProjects(state.projects);
    final active = state.activeProject;
    if (active == null || !visible.any((p) => p.id == active.id)) {
      if (visible.isNotEmpty) state.selectProject(visible.first);
    }
    setState(() {});
  }

  /// 기준에 맞는 프로젝트 목록.
  List<Project> _visibleProjects(List<Project> projects) {
    if (_projectScope.value == _ProjectScope.mine) {
      return projects.where((p) => p.isMember).toList();
    }
    return projects;
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
    final visibleProjects = _visibleProjects(projects);

    // 목록이 비면 (불러오기 실패로 목록이 비었을 때 포함) 빈 상태 화면을 보여준다.
    // (선택값만 남아 있는 상태로 드롭다운을 그리면 비어 보이기만 한다)
    if (visibleProjects.isEmpty) {
      final onlyMine = _projectScope.value == _ProjectScope.mine;
      return Scaffold(
        backgroundColor: LlackColors.paper,
        appBar: LlackAppBar(
          tabTitle: '프로젝트',
          showCommonActions: widget.showCommonActions,
          actions: [
            IconButton(
              icon: const Icon(Icons.add_rounded, size: 22),
              tooltip: '새 프로젝트',
              onPressed: () => _openProjectSettings(context),
            ),
          ],
        ),
        body: Column(
          children: [
            _buildScopeFilter(context, projects),
            Expanded(
              child: RefreshIndicator(
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
                                onlyMine ? '내 프로젝트가 없습니다' : '프로젝트가 없습니다',
                                style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 12),
                              ElevatedButton.icon(
                                icon: const Icon(Icons.add, size: 18),
                                label: const Text('새 프로젝트 만들기'),
                                onPressed: () => _openProjectSettings(context),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
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
    final myTasks = state.myTasks;

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
            value: _selectedProjectId(visibleProjects, activeProject),
            isDense: true,
            isExpanded: true,
            icon: Icon(Icons.keyboard_arrow_down, color: LlackColors.ink),
            // 목록에 선택 항목이 없으면(재로드 직후 등) 제목을 빈칸으로 두지 않는다
            hint: Text(
              '프로젝트 선택',
              style: theme.textTheme.titleLarge?.copyWith(fontSize: 17, color: LlackColors.muted),
            ),
            selectedItemBuilder: (context) => visibleProjects
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
            items: visibleProjects.map((p) {
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
              for (final p in visibleProjects) {
                if (p.id == id) {
                  state.selectProject(p);
                  return;
                }
              }
            },
          ),
        ),
        actions: [
          // 프로젝트 헤더 메뉴 — 프로젝트 설정을 연다.
          if (activeProject != null)
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, size: 22),
              tooltip: '프로젝트 메뉴',
              onSelected: (value) {
                if (value == 'settings') _openProjectSettings(context, project: activeProject);
              },
              itemBuilder: (context) => const [
                PopupMenuItem<String>(value: 'settings', child: Text('프로젝트 설정')),
              ],
            ),
          IconButton(
            icon: const Icon(Icons.add_rounded, size: 22),
            tooltip: '새 프로젝트',
            onPressed: () => _openProjectSettings(context),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: Size.fromHeight(
            _scopeRowHeight + (roadmaps.isNotEmpty ? _roadmapRowHeight : 0) + _tabBarHeight,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 프로젝트 거르기 (전체 / 내 프로젝트)
              _buildScopeFilter(context, projects),

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
                            // 로드맵은 칩에서 바로 지운다. (만들기는 없다)
                            onDeleted: () => _confirmDeleteRoadmap(context, r),
                            deleteIcon: const Icon(Icons.close, size: 14),
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
                // 탭이 여섯 개라 화면에 다 들어가지 않는다. 옆으로 밀어 본다.
                isScrollable: true,
                tabAlignment: TabAlignment.start,
                labelPadding: const EdgeInsets.symmetric(horizontal: 8),
                tabs: [
                  Tab(text: '요청 (${requestTasks.length})'),
                  Tab(text: '할 일 (${todoTasks.length})'),
                  Tab(text: '진행 중 (${inProgressTasks.length})'),
                  Tab(text: '완료 (${doneTasks.length})'),
                  const Tab(text: '마일스톤'),
                  Tab(text: '내 할 일 (${myTasks.length})'),
                  const Tab(text: '타임라인'),
                ],
              ),
            ],
          ),
        ),
      ),
      // 새 할 일은 상태 탭에서만 만든다. (마일스톤·내 할 일 탭은 보드가 아니다)
      floatingActionButton: _tabController.index < _statusTabCount
          ? FloatingActionButton(
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
            )
          : null,
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
                  const MilestonePanel(),
                  const MyTasksScreen(),
                  const TimelinePanel(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 프로젝트 거르기 줄. (전체 / 내 프로젝트)
  Widget _buildScopeFilter(BuildContext context, List<Project> projects) {
    final mineCount = projects.where((p) => p.isMember).length;
    final scope = _projectScope.value;
    return SizedBox(
      height: _scopeRowHeight,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Row(
          children: [
            FilterChip(
              label: Text('전체 (${projects.length})'),
              selected: scope == _ProjectScope.all,
              selectedColor: LlackColors.accentSoft,
              checkmarkColor: LlackColors.accent,
              onSelected: (_) => _setScope(_ProjectScope.all),
            ),
            const SizedBox(width: 6),
            FilterChip(
              label: Text('내 프로젝트 ($mineCount)'),
              selected: scope == _ProjectScope.mine,
              selectedColor: LlackColors.accentSoft,
              checkmarkColor: LlackColors.accent,
              onSelected: (_) => _setScope(_ProjectScope.mine),
            ),
          ],
        ),
      ),
    );
  }

  /// 로드맵을 지운다. (확인 한 뒤에)
  Future<void> _confirmDeleteRoadmap(BuildContext context, Roadmap roadmap) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('로드맵 삭제'),
        content: Text('\'${roadmap.name}\' 로드맵을 삭제할까요?\n이 안의 할 일은 그대로 남습니다.'),
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
    if (confirmed != true || !context.mounted) return;

    final state = context.read<AppState>();
    final ok = await state.deleteRoadmap(roadmap.id);
    if (!context.mounted) return;
    if (!ok) showAppSnackBar(context, '로드맵을 삭제하지 못했습니다');
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
                  // 마일스톤 배지 (색 + 이름)
                  if (task.milestoneName != null) ...[
                    const SizedBox(height: 8),
                    _MilestoneBadge(name: task.milestoneName!, color: task.milestoneColor),
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
                                 Icon(Icons.schedule, size: 13, color: LlackColors.muted),
                                const SizedBox(width: 4),
                                Text(
                                  DateFormat('M.d').format(task.dueAt!.toLocal()),
                                  style: theme.textTheme.labelSmall,
                                ),
                                const SizedBox(width: 12),
                              ],
                              if (task.comments.isNotEmpty || task.commentCount > 0) ...[
                                 Icon(Icons.mode_comment_outlined, size: 13, color: LlackColors.muted),
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

/// 프로젝트 거르기 줄 높이.
const double _scopeRowHeight = 40;

/// 로드맵 칩 줄 높이.
const double _roadmapRowHeight = 40;

/// 탭 바 높이.
const double _tabBarHeight = 48;

/// 할 일 카드의 마일스톤 배지. (색 + 이름)
class _MilestoneBadge extends StatelessWidget {
  final String name;
  final String? color;

  const _MilestoneBadge({required this.name, this.color});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final c = milestoneColor(color);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: c, shape: BoxShape.circle),
          ),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              name,
              style: theme.textTheme.labelSmall?.copyWith(color: c, fontWeight: FontWeight.w700),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
