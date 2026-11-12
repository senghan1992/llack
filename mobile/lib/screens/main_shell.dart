import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../responsive/screen_type.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_typography.dart';
import '../widgets/connection_banner.dart';
import '../widgets/llack_avatar.dart';
import 'chat/chat_screen.dart';
import 'chat/chat_tab.dart';
import 'org/org_screen.dart';
import 'projects/projects_screen.dart';
import 'schedule/schedule_screen.dart';
import 'search/search_dialog.dart';
import 'settings/settings_sheet.dart';

/// 모든 탭이 공유하는 앱바.
///
/// 앱바가 두 겹으로 쌓이던 문제(§3-C-1)를 없애기 위해 **화면마다 앱바는 정확히 1개**만 둔다.
/// 워크스페이스 전환 · 검색 · 아바타 같은 공통 진입점은 이 위젯 하나로 모은다.
class LlackAppBar extends StatelessWidget implements PreferredSizeWidget {
  /// 탭 이름(프로젝트 탭처럼 제목을 직접 그릴 때는 titleWidget 사용)
  final String tabTitle;
  final Widget? titleWidget;

  /// 탭 고유 액션 (예: 일정 탭의 "내 일정만" 필터)
  final List<Widget> actions;

  /// 탭 고유 하단 영역 (예: 프로젝트 탭의 TabBar)
  final PreferredSizeWidget? bottom;

  /// 태블릿에서는 좌측 레일에 검색/아바타가 있으므로 중복을 피한다.
  final bool showCommonActions;

  const LlackAppBar({
    super.key,
    required this.tabTitle,
    this.titleWidget,
    this.actions = const [],
    this.bottom,
    this.showCommonActions = true,
  });

  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + (bottom?.preferredSize.height ?? 0));

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final user = state.currentUser;
    final presence = user != null ? state.getPresence(user.id) : null;
    final theme = Theme.of(context);

    return AppBar(
      backgroundColor: LlackColors.paper,
      titleSpacing: 12,
      title: Row(
        children: [
          // 칩은 먼저 측정되도록 flex 를 주지 않는다 (제목이 남은 폭을 모두 쓰게 된다)
          _WorkspaceChip(name: state.activeWorkspace?.name ?? 'Llack'),
          const SizedBox(width: 10),
          Expanded(
            child: titleWidget ??
                Text(
                  tabTitle,
                  style: theme.textTheme.titleLarge?.copyWith(fontSize: 17),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
          ),
        ],
      ),
      actions: [
        ...actions,
        if (showCommonActions) ...[
          IconButton(
            icon: const Icon(Icons.search, size: 22),
            tooltip: '빠른 검색',
            onPressed: () => showDialog(
              context: context,
              builder: (_) => const SearchDialog(),
            ),
          ),
          if (user != null)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Tooltip(
                message: '내 프로필 · 설정',
                child: SizedBox(
                  // 터치 타깃 40dp 확보
                  width: 40,
                  height: 40,
                  child: Center(
                    child: InkWell(
                      onTap: () => showModalBottomSheet(
                        context: context,
                        isScrollControlled: true,
                        backgroundColor: Colors.transparent,
                        builder: (_) => const SettingsSheet(),
                      ),
                      borderRadius: BorderRadius.circular(16),
                      child: LlackAvatar(
                        name: user.name,
                        avatarUrl: user.avatarUrl,
                        avatarColor: user.avatarColor,
                        presence: presence,
                        size: 32,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ],
      bottom: bottom,
    );
  }
}

/// 워크스페이스 전환 칩. 앱바 왼쪽에 두어 모든 탭에서 같은 위치로 접근한다.
class _WorkspaceChip extends StatelessWidget {
  final String name;

  const _WorkspaceChip({required this.name});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      button: true,
      label: '워크스페이스 전환, 현재 $name',
      child: Tooltip(
        message: '워크스페이스 전환',
        child: InkWell(
          onTap: () => showWorkspaceSwitcher(context),
          borderRadius: BorderRadius.circular(8),
          child: Container(
            constraints: const BoxConstraints(maxWidth: 132),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: LlackColors.surfaceWell,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: LlackColors.rule),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.business_outlined, size: 13, color: LlackColors.muted),
                const SizedBox(width: 4),
                Flexible(
                  child: Text(
                    name,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: LlackColors.ink2,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const Icon(Icons.keyboard_arrow_down, size: 15, color: LlackColors.muted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 연결이 끊겼을 때 화면 위쪽에 붙는 얇은 배너 (§3-C-7)
/// 탭 화면 공통 오류 배너.
/// “빈 상태”와 구분되도록 오류 메시지와 함께 [다시 시도] 버튼을 보여준다.
class SectionErrorBanner extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const SectionErrorBanner({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      decoration: BoxDecoration(
        color: LlackColors.presenceBusy.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: LlackColors.presenceBusy.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, size: 18, color: LlackColors.presenceBusy),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.presenceBusy),
            ),
          ),
          TextButton(
            onPressed: onRetry,
            child: const Text('다시 시도'),
          ),
        ],
      ),
    );
  }
}

/// 워크스페이스 전환 시트를 열어준다. 앱바 칩에서 호출한다.
void showWorkspaceSwitcher(BuildContext context) {
  final state = context.read<AppState>();
  final workspaces = state.workspaces;
  final active = state.activeWorkspace;

  showModalBottomSheet(
    context: context,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text('워크스페이스 전환', style: LlackTypography.title.copyWith(fontSize: 16)),
          ),
          const Divider(height: 1),
          ...workspaces.map((ws) {
            final isSel = ws.id == active?.id;
            return ListTile(
              leading: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: isSel ? LlackColors.accent : LlackColors.surfaceWell,
                  borderRadius: BorderRadius.circular(8),
                ),
                alignment: Alignment.center,
                child: Text(
                  ws.name.isNotEmpty ? ws.name.substring(0, 1) : 'W',
                  style: TextStyle(
                    color: isSel ? Colors.white : LlackColors.ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              title: Text(
                ws.name,
                style: TextStyle(
                  fontWeight: isSel ? FontWeight.w700 : FontWeight.w500,
                  color: isSel ? LlackColors.accentDeep : LlackColors.ink,
                ),
              ),
              trailing: isSel ? const Icon(Icons.check, color: LlackColors.accent) : null,
              onTap: () {
                Navigator.pop(ctx);
                state.selectWorkspace(ws);
              },
            );
          }),
        ],
      ),
    ),
  );
}

/// 메시지 탭은 ChatTab 자체에 앱바가 없으므로 셸이 앱바 1개를 제공한다.
class _ChatTabHost extends StatelessWidget {
  const _ChatTabHost();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: LlackAppBar(tabTitle: '메시지'),
      body: ChatTab(),
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final formFactor = FormFactor(context);

    if (formFactor.isPad) {
      return _buildTabletLayout(context, state);
    }

    return _buildPhoneLayout(context, state);
  }

  // ── Phone Layout (Bottom Nav Bar) ────────────────────────────

  Widget _buildPhoneLayout(BuildContext context, AppState state) {
    // 탭 인덱스는 Core 의 ValueNotifier 를 단일 소스로 삼는다.
    // (검색/신규DM/조직도에서 다른 탭으로 이동할 때도 같은 값이 갱신된다.)
    return ValueListenableBuilder<int>(
      valueListenable: state.tabIndex,
      builder: (context, index, _) {
        return Scaffold(
          backgroundColor: LlackColors.paper,
          body: Column(
            children: [
              const ConnectionBanner(),
              Expanded(
                child: IndexedStack(
                  index: index,
                  // 각 탭은 자기 앱바를 하나씩만 가진다 (탭 전환 시 화면이 유지되도록 IndexedStack 사용).
                  children: const [
                    _ChatTabHost(),
                    ScheduleScreen(),
                    ProjectsScreen(),
                    OrgScreen(),
                  ],
                ),
              ),
            ],
          ),
          bottomNavigationBar: BottomNavigationBar(
            currentIndex: index,
            onTap: state.goToTab,
            items: const [
              BottomNavigationBarItem(
                icon: Icon(Icons.chat_bubble_outline),
                activeIcon: Icon(Icons.chat_bubble),
                label: '메시지',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.calendar_today_outlined),
                activeIcon: Icon(Icons.calendar_today),
                label: '일정',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.view_kanban_outlined),
                activeIcon: Icon(Icons.view_kanban),
                label: '프로젝트',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.corporate_fare_outlined),
                activeIcon: Icon(Icons.corporate_fare),
                label: '조직도',
              ),
            ],
          ),
        );
      },
    );
  }

  // ── Tablet / Pad Layout (Adaptive Split Panes) ──────────────

  Widget _buildTabletLayout(BuildContext context, AppState state) {
    return Scaffold(
      backgroundColor: LlackColors.paper,
      body: Column(
        children: [
          const ConnectionBanner(),
          Expanded(
            child: ValueListenableBuilder<int>(
              valueListenable: state.tabIndex,
              builder: (context, index, _) {
                return Row(
                  children: [
                    _buildLeftRail(context, state, index),
                    const VerticalDivider(width: 1, thickness: 1, color: LlackColors.rule),
                    if (index == 0) ...[
                      const SizedBox(width: 280, child: ChatTab()),
                      const VerticalDivider(width: 1, thickness: 1, color: LlackColors.rule),
                      const Expanded(child: ChatScreen(showBackButton: false)),
                    ] else
                      Expanded(
                        child: switch (index) {
                          1 => const ScheduleScreen(showCommonActions: false),
                          2 => const ProjectsScreen(showCommonActions: false),
                          _ => const OrgScreen(showCommonActions: false),
                        },
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLeftRail(BuildContext context, AppState state, int currentIndex) {
    final user = state.currentUser;
    final userPresence = user != null ? state.getPresence(user.id) : null;

    return Container(
      width: 72,
      color: LlackColors.surfaceRail,
      child: Column(
        children: [
          const SizedBox(height: 12),
          // Brand logo tile
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: LlackColors.accent,
              borderRadius: BorderRadius.circular(12),
            ),
            alignment: Alignment.center,
            child: const Text(
              'Ll',
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 18),
            ),
          ),
          const SizedBox(height: 20),

          // Nav icons
          _buildRailIcon(
            icon: Icons.chat_bubble_outline,
            activeIcon: Icons.chat_bubble,
            label: '대화',
            index: 0,
          ),
          _buildRailIcon(
            icon: Icons.calendar_today_outlined,
            activeIcon: Icons.calendar_today,
            label: '일정',
            index: 1,
          ),
          _buildRailIcon(
            icon: Icons.view_kanban_outlined,
            activeIcon: Icons.view_kanban,
            label: '프로젝트',
            index: 2,
          ),
          _buildRailIcon(
            icon: Icons.corporate_fare_outlined,
            activeIcon: Icons.corporate_fare,
            label: '조직도',
            index: 3,
          ),

          const Spacer(),

          // Search button
          IconButton(
            icon: const Icon(Icons.search, size: 22, color: LlackColors.ink2),
            tooltip: '검색 (⌘K)',
            onPressed: () => showDialog(
              context: context,
              builder: (_) => const SearchDialog(),
            ),
          ),
          const SizedBox(height: 8),

          // User profile avatar
          if (user != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Tooltip(
                message: '내 프로필 · 설정',
                child: InkWell(
                  onTap: () => showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    backgroundColor: Colors.transparent,
                    builder: (_) => const SettingsSheet(),
                  ),
                  borderRadius: BorderRadius.circular(18),
                  child: LlackAvatar(
                    name: user.name,
                    avatarUrl: user.avatarUrl,
                    avatarColor: user.avatarColor,
                    presence: userPresence,
                    size: 36,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildRailIcon({
    required IconData icon,
    required IconData activeIcon,
    required String label,
    required int index,
  }) {
    final state = context.read<AppState>();
    final isSelected = state.tabIndex.value == index;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: IconButton(
        icon: Icon(
          isSelected ? activeIcon : icon,
          color: isSelected ? LlackColors.accent : LlackColors.muted,
          size: 24,
        ),
        tooltip: label,
        onPressed: () => state.goToTab(index),
      ),
    );
  }
}
