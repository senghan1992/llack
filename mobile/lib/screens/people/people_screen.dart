import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';
import 'invite_screen.dart';

/// 워크스페이스 구성원과 권한을 관리하는 화면.
class PeopleScreen extends StatefulWidget {
  const PeopleScreen({super.key});

  @override
  State<PeopleScreen> createState() => _PeopleScreenState();
}

class _PeopleScreenState extends State<PeopleScreen> {
  final _searchController = TextEditingController();
  String _query = '';
  String? _busyUserId;

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_onSearchChanged);
  }

  @override
  void dispose() {
    _searchController
      ..removeListener(_onSearchChanged)
      ..dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final query = _searchController.text.trim().toLowerCase();
    if (query == _query) return;
    setState(() => _query = query);
  }

  Role? _myRole(AppState state) {
    final currentUserId = state.currentUser?.id;
    if (currentUserId != null) {
      for (final member in state.members) {
        if (member.user.id == currentUserId) return member.role;
      }
    }
    return state.orgOverview?.myRole;
  }

  bool _canManage(AppState state) {
    final role = _myRole(state);
    return role == Role.owner || role == Role.admin;
  }

  Future<void> _openInviteScreen() async {
    await Navigator.of(
      context,
    ).push<void>(MaterialPageRoute<void>(builder: (_) => const InviteScreen()));
  }

  Future<void> _changeRole(Member member, Role role) async {
    if (member.role == Role.owner) {
      showAppSnackBar(context, '소유자의 역할은 변경할 수 없습니다');
      return;
    }
    if (_busyUserId != null) return;

    setState(() => _busyUserId = member.user.id);
    final state = context.read<AppState>();
    var succeeded = false;
    try {
      succeeded = await state.updateMemberRole(member, role);
      if (succeeded) {
        // 변경 API만으로는 다른 화면의 요약 정보가 오래된 채 남을 수 있다.
        await state.refreshWorkspace();
        await state.loadOrg();
      }
    } catch (_) {
      succeeded = false;
    }

    if (!mounted) return;
    setState(() => _busyUserId = null);
    showAppSnackBar(context, succeeded ? '권한을 변경했습니다' : '권한을 변경하지 못했습니다');
  }

  Future<void> _removeMember(Member member) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('구성원 내보내기'),
        content: Text('${member.user.name}님을 이 워크스페이스에서 내보낼까요?'),
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
            child: const Text('내보내기'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busyUserId = member.user.id);
    final state = context.read<AppState>();
    var succeeded = false;
    try {
      succeeded = await state.removeMember(member);
      if (succeeded) {
        await state.refreshWorkspace();
        await state.loadOrg();
      }
    } catch (_) {
      succeeded = false;
    }

    if (!mounted) return;
    setState(() => _busyUserId = null);
    showAppSnackBar(context, succeeded ? '워크스페이스에서 내보냈습니다' : '구성원을 내보내지 못했습니다');
  }

  List<Member> _filteredMembers(AppState state) {
    if (_query.isEmpty) return state.members;
    return state.members.where((member) {
      final name = member.user.name.toLowerCase();
      final email = member.user.email.toLowerCase();
      final title = member.user.title?.toLowerCase() ?? '';
      return name.contains(_query) ||
          email.contains(_query) ||
          title.contains(_query);
    }).toList();
  }

  List<Role> _roleOptions(Member member, Role? myRole) {
    if (member.role == Role.owner || myRole == Role.owner) {
      return Role.values;
    }
    return const [Role.admin, Role.member];
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final myRole = _myRole(state);
    final canManage = _canManage(state);
    final members = _filteredMembers(state);

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: AppBar(
        backgroundColor: LlackColors.paper,
        surfaceTintColor: Colors.transparent,
        title: const Text('구성원'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add_alt_1, size: 21),
            tooltip: '팀원 초대',
            onPressed: _openInviteScreen,
          ),
        ],
      ),
      body: RefreshIndicator(
        color: LlackColors.accent,
        onRefresh: () async {
          await state.refreshWorkspace();
          await state.loadOrg();
        },
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            OutlinedButton.icon(
              onPressed: _openInviteScreen,
              icon: const Icon(Icons.mail_outline, size: 18),
              label: const Text('팀원 초대'),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: '이름, 직함, 이메일로 검색',
                prefixIcon: Icon(
                  Icons.search,
                  size: 20,
                  color: LlackColors.muted,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Text(
                    '워크스페이스 구성원 ${state.members.length}명',
                    style: LlackTypography.subtitle,
                  ),
                ),
                if (!canManage)
                  Text(
                    '읽기 전용',
                    style: LlackTypography.caption.copyWith(
                      color: LlackColors.muted,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            if (members.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 28,
                    horizontal: 16,
                  ),
                  child: Center(
                    child: Text(
                      _query.isEmpty ? '구성원이 없습니다' : '검색 결과가 없습니다',
                      style: LlackTypography.bodySmall.copyWith(
                        color: LlackColors.muted,
                      ),
                    ),
                  ),
                ),
              )
            else
              Card(
                child: ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: members.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, index) {
                    final member = members[index];
                    final user = member.user;
                    final isBusy = _busyUserId == user.id;
                    final presence = state.getPresence(user.id);

                    return ListTile(
                      leading: LlackAvatar(
                        name: user.name,
                        avatarUrl: user.avatarUrl,
                        avatarColor: user.avatarColor,
                        presence: presence,
                        size: 38,
                      ),
                      title: Text(
                        user.name,
                        style: LlackTypography.subtitle.copyWith(fontSize: 14),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        user.title ?? user.email,
                        style: LlackTypography.caption,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: isBusy
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (canManage)
                                  Tooltip(
                                    message: member.role == Role.owner
                                        ? '소유자의 역할은 변경할 수 없습니다'
                                        : '${user.name} 권한 변경',
                                    child: DropdownButtonHideUnderline(
                                      child: DropdownButton<Role>(
                                        value: member.role,
                                        isDense: true,
                                        borderRadius: BorderRadius.circular(12),
                                        onChanged: member.role == Role.owner
                                            ? null
                                            : (role) {
                                                if (role != null) {
                                                  _changeRole(member, role);
                                                }
                                              },
                                        items: _roleOptions(member, myRole)
                                            .map(
                                              (role) => DropdownMenuItem<Role>(
                                                value: role,
                                                child: Text(role.label),
                                              ),
                                            )
                                            .toList(),
                                      ),
                                    ),
                                  )
                                else
                                  Text(
                                    member.role.label,
                                    style: LlackTypography.caption,
                                  ),
                                if (canManage)
                                  IconButton(
                                    icon: Icon(
                                      Icons.person_remove_outlined,
                                      size: 19,
                                      color: LlackColors.presenceBusy,
                                    ),
                                    tooltip: '${user.name} 내보내기',
                                    onPressed: () => _removeMember(member),
                                  ),
                              ],
                            ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
