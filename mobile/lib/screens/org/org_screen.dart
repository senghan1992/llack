import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../responsive/screen_type.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/llack_avatar.dart';
import '../chat/chat_navigator.dart';
import '../main_shell.dart';
import '../../widgets/app_snack_bar.dart';

class OrgScreen extends StatefulWidget {
  /// 태블릿에서는 좌측 레일에 검색/아바타가 있어 앱바 공통 액션을 숨긴다.
  final bool showCommonActions;

  const OrgScreen({super.key, this.showCommonActions = true});

  @override
  State<OrgScreen> createState() => _OrgScreenState();
}

class _OrgScreenState extends State<OrgScreen> with AutomaticKeepAliveClientMixin {
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

  void _showNewUnitDialog(BuildContext context) {
    // 컨트롤러를 대화상자가 직접 소유하도록 위젯으로 분리했다 (9-10a)
    showDialog<void>(
      context: context,
      builder: (_) => const _NewOrgUnitDialog(),
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

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: LlackAppBar(
        tabTitle: '조직도',
        showCommonActions: widget.showCommonActions,
        actions: [
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
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
                          child: const Icon(Icons.corporate_fare, color: Colors.white, size: 24),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                state.activeWorkspace?.name ?? '워크스페이스',
                                style: theme.textTheme.titleLarge?.copyWith(fontSize: 16),
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

                  const SizedBox(height: 20),

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
                          leading: const Icon(Icons.account_tree_outlined, color: LlackColors.accent, size: 20),
                          title: Text(
                            unit.name,
                            style: theme.textTheme.titleMedium?.copyWith(fontSize: 14),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text('${unit.kind} · 멤버 ${unit.memberCount}명', style: theme.textTheme.labelSmall),
                          children: [
                            if (unit.description.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                                child: Text(unit.description, style: theme.textTheme.bodyMedium?.copyWith(color: LlackColors.muted)),
                              ),
                            ...unit.members.map((u) {
                              final p = state.getPresence(u.id);
                              return ListTile(
                                dense: true,
                                leading: LlackAvatar(name: u.name, avatarUrl: u.avatarUrl, avatarColor: u.avatarColor, presence: p, size: 30),
                                title: Text(u.name, style: theme.textTheme.bodyMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                                subtitle: u.title != null ? Text(u.title!, style: theme.textTheme.labelSmall, maxLines: 1, overflow: TextOverflow.ellipsis) : null,
                                trailing: IconButton(
                                  icon: const Icon(Icons.chat_bubble_outline, size: 18, color: LlackColors.accent),
                                  tooltip: '1:1 대화',
                                  onPressed: () => _startDmWithUser(context, u),
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
                  Text('전체 구성원 (${allMembers.length})', style: theme.textTheme.titleMedium),
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
                                        style: theme.textTheme.titleMedium?.copyWith(fontSize: 14),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    if (isMe) ...[
                                      const SizedBox(width: 6),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                        decoration: BoxDecoration(
                                          color: LlackColors.accentSoft,
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                        child: Text(
                                          '나',
                                          style: theme.textTheme.labelSmall?.copyWith(
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
                                  color: mem.role == Role.owner ? LlackColors.accent : LlackColors.muted,
                                  fontWeight: mem.role != Role.member ? FontWeight.w600 : FontWeight.w400,
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
                                  icon: const Icon(Icons.chat_bubble_outline, size: 18, color: LlackColors.accent),
                                  tooltip: '1:1 대화',
                                  onPressed: () => _startDmWithUser(context, user),
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

/// 새 조직 단위 다이얼로그.
///
/// 컨트롤러를 이 위젯이 직접 소유해 dispose 로 정리한다 (9-10a).
/// 생성 중에는 버튼을 잠가 연타 중복 생성을 막고 (9-4),
/// 실패하면 이유를 스낵바로 알려준다.
class _NewOrgUnitDialog extends StatefulWidget {
  const _NewOrgUnitDialog();

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
      title: Text('새 조직 단위', style: theme.textTheme.titleLarge),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _nameCtrl,
            autofocus: true,
            decoration: const InputDecoration(labelText: '조직 단위 이름', hintText: '예: 프로덕트 디자인팀'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _kindCtrl,
            decoration: const InputDecoration(labelText: '분류', hintText: '부서, 팀, 실 등'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _descCtrl,
            decoration: const InputDecoration(labelText: '설명', hintText: '조직 역할 및 업무 소개'),
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
