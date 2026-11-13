import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../responsive/screen_type.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';
import '../chat/chat_navigator.dart';
import '../main_shell.dart';
import '../people/people_screen.dart';
import '../people/person_picker.dart';

class OrgScreen extends StatefulWidget {
  /// 태블릿에서는 좌측 레일에 검색/아바타가 있어 앱바 공통 액션을 숨긴다.
  final bool showCommonActions;

  const OrgScreen({super.key, this.showCommonActions = true});

  @override
  State<OrgScreen> createState() => _OrgScreenState();
}

class _OrgScreenState extends State<OrgScreen>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      // Core 가 이미 조직도를 불러왔다면 다시 부르지 않는다 (F-5 중복 요청 방지).
      // 목록이 비었는지로는 판단하지 않는다 — 로더가 성공했는지만 본다.
      if (!state.hasLoadedOrg) state.loadOrg();
    });
  }

  Role? _currentRole(AppState state) {
    final currentUserId = state.currentUser?.id;
    if (currentUserId != null) {
      for (final member in state.members) {
        if (member.user.id == currentUserId) return member.role;
      }
    }
    return state.orgOverview?.myRole;
  }

  bool _canManageOrg(AppState state) {
    final role = _currentRole(state);
    return role == Role.owner || role == Role.admin;
  }

  void _showNewUnitDialog(
    BuildContext context, {
    String? parentId,
    String? parentName,
  }) {
    // 컨트롤러를 대화상자가 직접 소유하도록 위젯으로 분리했다 (9-10a)
    showDialog<void>(
      context: context,
      builder: (_) =>
          _NewOrgUnitDialog(parentId: parentId, parentName: parentName),
    );
  }

  Future<void> _openPeopleScreen() async {
    await Navigator.of(
      context,
    ).push<void>(MaterialPageRoute<void>(builder: (_) => const PeopleScreen()));
  }

  Future<void> _editUnit(OrgUnit unit, List<OrgUnit> units) async {
    final updated = await showDialog<bool>(
      context: context,
      builder: (_) => _EditOrgUnitDialog(unit: unit, units: units),
    );
    if (updated == true && mounted) {
      showAppSnackBar(context, '조직을 수정했습니다');
    }
  }

  Future<void> _deleteUnit(OrgUnit unit) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('조직 삭제'),
        content: Text('${unit.name} 조직을 삭제할까요? 하위 조직이나 구성원이 있으면 삭제할 수 없습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: TextButton.styleFrom(
              foregroundColor: LlackColors.presenceBusy,
            ),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final state = context.read<AppState>();
    final succeeded = await state.deleteOrgUnit(unit.id);
    if (!mounted) return;
    showAppSnackBar(context, succeeded ? '조직을 삭제했습니다' : '조직을 삭제하지 못했습니다');
  }

  Future<void> _addUnitMember(OrgUnit unit) async {
    final excluded = unit.members.map((user) => user.id).toSet();
    final user = await showPersonPicker(
      context,
      title: '${unit.name} 구성원 추가',
      excludedUserIds: excluded,
      searchAllUsers: true,
    );
    if (user == null || !mounted) return;

    final state = context.read<AppState>();
    final succeeded = await state.addOrgUnitMember(unit.id, user.id);
    if (!mounted) return;
    showAppSnackBar(context, succeeded ? '구성원을 추가했습니다' : '구성원을 추가하지 못했습니다');
  }

  Future<void> _removeUnitMember(OrgUnit unit, User user) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('조직 구성원 제거'),
        content: Text('${user.name}님을 ${unit.name}에서 제거할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: TextButton.styleFrom(
              foregroundColor: LlackColors.presenceBusy,
            ),
            child: const Text('제거'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final state = context.read<AppState>();
    final succeeded = await state.removeOrgUnitMember(unit.id, user.id);
    if (!mounted) return;
    showAppSnackBar(context, succeeded ? '구성원을 제거했습니다' : '구성원을 제거하지 못했습니다');
  }

  Future<void> _addUnitManager(OrgUnit unit) async {
    final excluded = unit.managers.map((user) => user.id).toSet();
    final user = await showPersonPicker(
      context,
      title: '${unit.name} 관리자 지정',
      excludedUserIds: excluded,
      searchAllUsers: true,
    );
    if (user == null || !mounted) return;

    final state = context.read<AppState>();
    final succeeded = await state.addOrgUnitManager(unit.id, user.id);
    if (!mounted) return;
    showAppSnackBar(
      context,
      succeeded ? '조직 관리자를 지정했습니다' : '조직 관리자를 지정하지 못했습니다',
    );
  }

  Future<void> _removeUnitManager(OrgUnit unit, User user) async {
    final state = context.read<AppState>();
    final succeeded = await state.removeOrgUnitManager(unit.id, user.id);
    if (!mounted) return;
    showAppSnackBar(
      context,
      succeeded ? '조직 관리자를 해임했습니다' : '조직 관리자를 해임하지 못했습니다',
    );
  }

  Future<void> _appointWorkspaceAdmin() async {
    final state = context.read<AppState>();
    final occupiedIds = state.members
        .where(
          (member) => member.role == Role.owner || member.role == Role.admin,
        )
        .map((member) => member.user.id)
        .toSet();

    final user = await showPersonPicker(
      context,
      title: '워크스페이스 관리자 임명',
      excludedUserIds: occupiedIds,
    );
    if (user == null || !mounted) return;

    Member? member;
    for (final candidate in state.members) {
      if (candidate.user.id == user.id) {
        member = candidate;
        break;
      }
    }
    if (member == null) return;
    await _changeWorkspaceRole(member, Role.admin, '관리자를 임명했습니다');
  }

  Future<void> _demoteWorkspaceAdmin(Member admin) async {
    // 백엔드에 워크스페이스 관리자 전용 API가 없으므로, 임면 해제도
    // admin 역할을 member로 되돌리는 역할 변경으로 처리한다.
    await _changeWorkspaceRole(admin, Role.member, '관리자 임면을 해제했습니다');
  }

  Future<void> _changeWorkspaceRole(
    Member member,
    Role role,
    String successMessage,
  ) async {
    final state = context.read<AppState>();
    var succeeded = false;
    try {
      // 전용 관리자 API가 없으므로 워크스페이스 관리자 임명은
      // 멤버 역할을 admin으로 바꾸는 것으로 구현한다.
      succeeded = await state.updateMemberRole(member, role);
      if (succeeded) {
        await state.refreshWorkspace();
        await state.loadOrg();
      }
    } catch (_) {
      succeeded = false;
    }

    if (!mounted) return;
    showAppSnackBar(
      context,
      succeeded ? successMessage : '워크스페이스 관리자 역할을 변경하지 못했습니다',
    );
  }

  /// 조직도의 💬 버튼 → 1:1 대화창을 실제로 연다.
  ///
  /// 예전에는 state.openDm() 만 불러서 채널만 만들고 화면은 그대로였다.
  /// 검색/신규DM 과 똑같이 공통 헬퍼(ChatNavigator)를 쓰도록 통일했다.
  Future<void> _startDmWithUser(BuildContext context, User user) async {
    final state = context.read<AppState>();
    if (user.id == state.currentUser?.id) return;

    // await 전에 navigator 를 잡아둔다 (다이얼로그가 닫히면 context 가 사라진다)
    final navigator = Navigator.of(context, rootNavigator: true);
    final compact = FormFactor(context).isCompact;

    try {
      await ChatNavigator.openDm(
        state: state,
        navigator: navigator,
        userId: user.id,
        push: compact,
      );
      // 대화창이 실제로 열리므로 "열렸습니다" 스낵바는 중복이라 넣지 않는다.
    } catch (error) {
      if (!context.mounted) return;
      // 실패 사유를 한국어로 알려준다 (422/403/404/네트워크 구분)
      showAppSnackBar(context, ChatNavigator.describeDmError(error));
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    final overview = state.orgOverview;
    final isLoading = state.isLoadingOrg;
    final allMembers = state.members;
    final canManageOrg = _canManageOrg(state);

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: LlackAppBar(
        tabTitle: '조직도',
        showCommonActions: widget.showCommonActions,
        actions: [
          if (canManageOrg)
            IconButton(
              icon: const Icon(Icons.add_rounded, size: 22),
              tooltip: '조직 단위 추가',
              onPressed: () => _showNewUnitDialog(context),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => state.loadOrg(),
        color: LlackColors.accent,
        child: isLoading && overview == null
            ? const Center(child: CircularProgressIndicator(strokeWidth: 2))
            : ListView(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                children: [
                  // Workspace Summary Banner
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: LlackColors.surfaceWell,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: LlackColors.rule),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: LlackColors.accent,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          alignment: Alignment.center,
                          child: const Icon(
                            Icons.corporate_fare,
                            color: Colors.white,
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                state.activeWorkspace?.name ?? '워크스페이스',
                                style: theme.textTheme.titleLarge?.copyWith(
                                  fontSize: 16,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '전체 멤버 ${allMembers.length}명',
                                style: theme.textTheme.labelSmall,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 12),

                  Card(
                    child: ListTile(
                      leading: Icon(
                        Icons.people_outline,
                        color: LlackColors.accent,
                      ),
                      title: const Text('구성원'),
                      subtitle: const Text('권한 변경 · 내보내기 · 팀원 초대'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: _openPeopleScreen,
                    ),
                  ),

                  if (overview != null && overview.myRole == Role.owner) ...[
                    const SizedBox(height: 16),
                    _WorkspaceAdminSection(
                      admins: overview.admins,
                      onAppoint: _appointWorkspaceAdmin,
                      onDemote: _demoteWorkspaceAdmin,
                    ),
                    const SizedBox(height: 16),
                  ],

                  const SizedBox(height: 4),

                  // 로드 실패와 "구성원 없음" 을 구분해서 보여준다 (§1-A-13)
                  if (state.orgError != null) ...[
                    SectionErrorBanner(
                      message: state.orgError!,
                      onRetry: () => state.retryOrg(),
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Units tree
                  if (overview != null && overview.units.isNotEmpty) ...[
                    Text('부서 및 팀', style: theme.textTheme.titleMedium),
                    const SizedBox(height: 8),
                    ...overview.units.map((unit) {
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ExpansionTile(
                          leading: Icon(
                            Icons.account_tree_outlined,
                            color: LlackColors.accent,
                            size: 20,
                          ),
                          title: Text(
                            unit.name,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontSize: 14,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            '${unit.kind} · 멤버 ${unit.memberCount}명 · 하위 조직 ${unit.childCount}개',
                            style: theme.textTheme.labelSmall,
                          ),
                          children: [
                            if (unit.description.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                  vertical: 4,
                                ),
                                child: Text(
                                  unit.description,
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: LlackColors.muted,
                                  ),
                                ),
                              ),
                            if (canManageOrg)
                              Padding(
                                padding: const EdgeInsets.fromLTRB(
                                  12,
                                  8,
                                  12,
                                  4,
                                ),
                                child: Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: () =>
                                          _editUnit(unit, overview.units),
                                      icon: const Icon(
                                        Icons.edit_outlined,
                                        size: 17,
                                      ),
                                      label: const Text('편집'),
                                    ),
                                    OutlinedButton.icon(
                                      onPressed: () => _showNewUnitDialog(
                                        context,
                                        parentId: unit.id,
                                        parentName: unit.name,
                                      ),
                                      icon: const Icon(Icons.add, size: 17),
                                      label: const Text('하위 조직 추가'),
                                    ),
                                    TextButton.icon(
                                      onPressed: () => _addUnitMember(unit),
                                      icon: const Icon(
                                        Icons.person_add_alt,
                                        size: 17,
                                      ),
                                      label: const Text('구성원 추가'),
                                    ),
                                    TextButton.icon(
                                      onPressed: () => _addUnitManager(unit),
                                      icon: const Icon(
                                        Icons.badge_outlined,
                                        size: 17,
                                      ),
                                      label: const Text('관리자 지정'),
                                    ),
                                    TextButton.icon(
                                      onPressed: () => _deleteUnit(unit),
                                      icon: Icon(
                                        Icons.delete_outline,
                                        size: 17,
                                        color: LlackColors.presenceBusy,
                                      ),
                                      label: Text(
                                        '삭제',
                                        style: TextStyle(
                                          color: LlackColors.presenceBusy,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            if (unit.managers.isNotEmpty) ...[
                              Padding(
                                padding: const EdgeInsets.fromLTRB(
                                  16,
                                  10,
                                  16,
                                  2,
                                ),
                                child: Text(
                                  '조직 관리자',
                                  style: theme.textTheme.titleSmall,
                                ),
                              ),
                              ...unit.managers.map((user) {
                                return ListTile(
                                  dense: true,
                                  leading: LlackAvatar(
                                    name: user.name,
                                    avatarUrl: user.avatarUrl,
                                    avatarColor: user.avatarColor,
                                    presence: state.getPresence(user.id),
                                    size: 30,
                                  ),
                                  title: Text(
                                    user.name,
                                    style: theme.textTheme.bodyMedium,
                                  ),
                                  trailing: canManageOrg
                                      ? IconButton(
                                          icon: Icon(
                                            Icons.person_remove_outlined,
                                            size: 18,
                                            color: LlackColors.presenceBusy,
                                          ),
                                          tooltip: '${user.name} 관리자 해임',
                                          onPressed: () =>
                                              _removeUnitManager(unit, user),
                                        )
                                      : null,
                                );
                              }),
                            ],
                            Padding(
                              padding: const EdgeInsets.fromLTRB(16, 10, 16, 2),
                              child: Text(
                                '구성원',
                                style: theme.textTheme.titleSmall,
                              ),
                            ),
                            ...unit.members.map((u) {
                              final p = state.getPresence(u.id);
                              return ListTile(
                                dense: true,
                                leading: LlackAvatar(
                                  name: u.name,
                                  avatarUrl: u.avatarUrl,
                                  avatarColor: u.avatarColor,
                                  presence: p,
                                  size: 30,
                                ),
                                title: Text(
                                  u.name,
                                  style: theme.textTheme.bodyMedium,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: u.title != null
                                    ? Text(
                                        u.title!,
                                        style: theme.textTheme.labelSmall,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      )
                                    : null,
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    IconButton(
                                      icon: Icon(
                                        Icons.chat_bubble_outline,
                                        size: 18,
                                        color: LlackColors.accent,
                                      ),
                                      tooltip: '1:1 대화',
                                      onPressed: () =>
                                          _startDmWithUser(context, u),
                                    ),
                                    if (canManageOrg)
                                      IconButton(
                                        icon: Icon(
                                          Icons.person_remove_outlined,
                                          size: 18,
                                          color: LlackColors.presenceBusy,
                                        ),
                                        tooltip: '${u.name} 조직에서 제거',
                                        onPressed: () =>
                                            _removeUnitMember(unit, u),
                                      ),
                                  ],
                                ),
                              );
                            }),
                          ],
                        ),
                      );
                    }),
                    const SizedBox(height: 16),
                  ],

                  // All Members Roster
                  Text(
                    '전체 구성원 (${allMembers.length})',
                    style: theme.textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Card(
                    child: ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: allMembers.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (ctx, i) {
                        final mem = allMembers[i];
                        final user = mem.user;
                        final p = state.getPresence(user.id);
                        final isMe = user.id == state.currentUser?.id;

                        return ListTile(
                          leading: LlackAvatar(
                            name: user.name,
                            avatarUrl: user.avatarUrl,
                            avatarColor: user.avatarColor,
                            presence: p,
                            size: 36,
                          ),
                          // 이름이 길면 역할 배지가 밀려나지 않도록 (§3-C-5)
                          // 이름 + "나" pill 묶음이 남는 폭을 가져가고, 역할 라벨은 오른쪽 끝에 붙는다 (§9-40)
                          title: Row(
                            children: [
                              Expanded(
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Flexible(
                                      child: Text(
                                        user.name,
                                        style: theme.textTheme.titleMedium
                                            ?.copyWith(fontSize: 14),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    if (isMe) ...[
                                      const SizedBox(width: 6),
                                      Container(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 5,
                                          vertical: 1,
                                        ),
                                        decoration: BoxDecoration(
                                          color: LlackColors.accentSoft,
                                          borderRadius: BorderRadius.circular(
                                            4,
                                          ),
                                        ),
                                        child: Text(
                                          '나',
                                          style: theme.textTheme.labelSmall
                                              ?.copyWith(
                                                color: LlackColors.accentDeep,
                                                fontWeight: FontWeight.w700,
                                              ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                mem.role.label,
                                style: theme.textTheme.labelSmall?.copyWith(
                                  color: mem.role == Role.owner
                                      ? LlackColors.accent
                                      : LlackColors.muted,
                                  fontWeight: mem.role != Role.member
                                      ? FontWeight.w600
                                      : FontWeight.w400,
                                ),
                              ),
                            ],
                          ),
                          subtitle: Text(
                            user.title ?? user.email,
                            style: theme.textTheme.labelSmall,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: !isMe
                              ? IconButton(
                                  icon: Icon(
                                    Icons.chat_bubble_outline,
                                    size: 18,
                                    color: LlackColors.accent,
                                  ),
                                  tooltip: '1:1 대화',
                                  onPressed: () =>
                                      _startDmWithUser(context, user),
                                )
                              // 자기 자신은 DM 버튼이 없지만, 자리만큼 비워야
                              // ListTile 제목 영역의 폭이 같아져 역할 라벨이 같은 열에 정렬된다 (§9-40)
                              : const SizedBox(width: 48),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
      ),
    );
  }
}

/// 워크스페이스 소유자에게만 관리자 임명·임면 해제 조작을 보여준다.
class _WorkspaceAdminSection extends StatelessWidget {
  const _WorkspaceAdminSection({
    required this.admins,
    required this.onAppoint,
    required this.onDemote,
  });

  final List<Member> admins;
  final VoidCallback onAppoint;
  final ValueChanged<Member> onDemote;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('워크스페이스 관리자', style: theme.textTheme.titleMedium),
                      const SizedBox(height: 2),
                      Text(
                        '워크스페이스 소유자가 관리자를 임명합니다',
                        style: theme.textTheme.labelSmall,
                      ),
                    ],
                  ),
                ),
                TextButton.icon(
                  icon: const Icon(Icons.person_add_alt_1, size: 18),
                  label: const Text('관리자 임명'),
                  onPressed: onAppoint,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (admins.isEmpty)
              Text(
                '아직 워크스페이스 관리자가 없습니다',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: LlackColors.muted,
                ),
              )
            else
              ...admins.map(
                (admin) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  leading: LlackAvatar(
                    name: admin.user.name,
                    avatarUrl: admin.user.avatarUrl,
                    avatarColor: admin.user.avatarColor,
                    size: 32,
                  ),
                  title: Text(
                    admin.user.name,
                    style: theme.textTheme.bodyMedium,
                  ),
                  subtitle: Text(
                    admin.user.title ?? admin.role.label,
                    style: theme.textTheme.labelSmall,
                  ),
                  trailing: admin.role == Role.admin
                      ? TextButton(
                          onPressed: () => onDemote(admin),
                          child: Text(
                            '임면 해제',
                            style: TextStyle(color: LlackColors.presenceBusy),
                          ),
                        )
                      : Text(
                          admin.role.label,
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: LlackColors.accent,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// 새 조직 단위 다이얼로그.
///
/// 컨트롤러를 이 위젯이 직접 소유해 dispose 로 정리한다 (9-10a).
/// 생성 중에는 버튼을 잠가 연타 중복 생성을 막고 (9-4),
/// 실패하면 이유를 스낵바로 알려준다.
class _NewOrgUnitDialog extends StatefulWidget {
  const _NewOrgUnitDialog({this.parentId, this.parentName});

  final String? parentId;
  final String? parentName;

  @override
  State<_NewOrgUnitDialog> createState() => _NewOrgUnitDialogState();
}

class _NewOrgUnitDialogState extends State<_NewOrgUnitDialog> {
  final _nameCtrl = TextEditingController();
  final _kindCtrl = TextEditingController(text: '부서');
  final _descCtrl = TextEditingController();
  bool _isSubmitting = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _kindCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty || _isSubmitting) return;

    setState(() => _isSubmitting = true);
    final state = context.read<AppState>();
    try {
      await state.createOrgUnit(
        name: name,
        parentId: widget.parentId,
        kind: _kindCtrl.text.trim().isNotEmpty ? _kindCtrl.text.trim() : '부서',
        description: _descCtrl.text.trim(),
      );
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      // 실패 이유를 알려야 "버튼이 죽었다" 고 느끼지 않는다
      setState(() => _isSubmitting = false);
      showAppSnackBar(context, '조직 단위 생성에 실패했습니다: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AlertDialog(
      title: Text(
        widget.parentId == null ? '새 조직 단위' : '하위 조직 단위',
        style: theme.textTheme.titleLarge,
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.parentName != null) ...[
            Text(
              '상위 조직: ${widget.parentName}',
              style: theme.textTheme.labelSmall,
            ),
            const SizedBox(height: 10),
          ],
          TextField(
            controller: _nameCtrl,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: '조직 단위 이름',
              hintText: '예: 프로덕트 디자인팀',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _kindCtrl,
            decoration: const InputDecoration(
              labelText: '분류',
              hintText: '부서, 팀, 실 등',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _descCtrl,
            decoration: const InputDecoration(
              labelText: '설명',
              hintText: '조직 역할 및 업무 소개',
            ),
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
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Text('생성'),
        ),
      ],
    );
  }
}

/// 조직 단위의 이름·종류·설명·상위 조직을 편집하는 다이얼로그.
class _EditOrgUnitDialog extends StatefulWidget {
  const _EditOrgUnitDialog({required this.unit, required this.units});

  final OrgUnit unit;
  final List<OrgUnit> units;

  @override
  State<_EditOrgUnitDialog> createState() => _EditOrgUnitDialogState();
}

class _EditOrgUnitDialogState extends State<_EditOrgUnitDialog> {
  late final TextEditingController _nameController;
  late final TextEditingController _kindController;
  late final TextEditingController _descriptionController;
  late String _parentId;
  bool _isSaving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.unit.name);
    _kindController = TextEditingController(text: widget.unit.kind);
    _descriptionController = TextEditingController(
      text: widget.unit.description,
    );
    _parentId = widget.unit.parentId ?? '';
  }

  @override
  void dispose() {
    _nameController.dispose();
    _kindController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Set<String> _descendantIds() {
    final descendants = <String>{};
    void visit(String parentId) {
      for (final unit in widget.units) {
        if (unit.parentId == parentId && descendants.add(unit.id)) {
          visit(unit.id);
        }
      }
    }

    visit(widget.unit.id);
    return descendants;
  }

  List<OrgUnit> _parentOptions() {
    final descendants = _descendantIds();
    final options = widget.units
        .where(
          (unit) => unit.id != widget.unit.id && !descendants.contains(unit.id),
        )
        .toList();
    if (widget.unit.parentId != null &&
        !options.any((unit) => unit.id == widget.unit.parentId)) {
      for (final unit in widget.units) {
        if (unit.id == widget.unit.parentId) {
          options.add(unit);
          break;
        }
      }
    }
    return options;
  }

  Future<void> _save() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      setState(() => _error = '조직 단위 이름을 입력하세요');
      return;
    }
    if (_isSaving) return;

    setState(() {
      _isSaving = true;
      _error = null;
    });

    final state = context.read<AppState>();
    var succeeded = false;
    try {
      succeeded = await state.updateOrgUnit(
        unitId: widget.unit.id,
        name: name,
        // 최상위 조직은 parent_id를 보내지 않는다. 기존 최상위 조직의
        // 이름/설명 편집이 빈 상위 id 조회로 실패하지 않게 하기 위함이다.
        parentId: _parentId.isEmpty && widget.unit.parentId == null
            ? null
            : _parentId,
        kind: _kindController.text.trim(),
        description: _descriptionController.text.trim(),
      );
    } catch (_) {
      succeeded = false;
    }

    if (!mounted) return;
    if (succeeded) {
      Navigator.pop(context, true);
      return;
    }
    setState(() {
      _isSaving = false;
      _error = '조직을 수정하지 못했습니다';
    });
    showAppSnackBar(context, '조직을 수정하지 못했습니다');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final parentOptions = _parentOptions();

    return AlertDialog(
      title: const Text('조직 편집'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _nameController,
              autofocus: true,
              decoration: const InputDecoration(labelText: '조직 단위 이름'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _kindController,
              decoration: const InputDecoration(
                labelText: '분류',
                hintText: '부서, 팀, 실 등',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _descriptionController,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(labelText: '설명'),
            ),
            const SizedBox(height: 12),
            Text('상위 조직', style: theme.textTheme.labelLarge),
            const SizedBox(height: 6),
            DropdownButtonFormField<String>(
              initialValue: _parentId,
              isExpanded: true,
              items: [
                const DropdownMenuItem<String>(
                  value: '',
                  child: Text('최상위 조직'),
                ),
                ...parentOptions.map(
                  (unit) => DropdownMenuItem<String>(
                    value: unit.id,
                    child: Text(unit.name, overflow: TextOverflow.ellipsis),
                  ),
                ),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _parentId = value);
              },
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(
                _error!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: LlackColors.presenceBusy,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _isSaving ? null : () => Navigator.pop(context, false),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: _isSaving ? null : _save,
          child: _isSaving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Text('저장'),
        ),
      ],
    );
  }
}
