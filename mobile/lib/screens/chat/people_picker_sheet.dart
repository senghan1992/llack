import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';

/// 채널에 사람 추가 시트.
///
/// 워크스페이스 구성원 중 **아직 이 채널에 없는 사람**을 골라 초대한다.
/// 데스크톱의 AddPeopleDialog(dialogs.tsx) 를 모바일로 옮긴 것.
class PeoplePickerSheet extends StatefulWidget {
  final Channel channel;

  const PeoplePickerSheet({super.key, required this.channel});

  @override
  State<PeoplePickerSheet> createState() => _PeoplePickerSheetState();
}

class _PeoplePickerSheetState extends State<PeoplePickerSheet> {
  final TextEditingController _searchCtrl = TextEditingController();

  /// 현재 채널의 멤버 (이미 있는 사람은 후보에서 뺀다)
  List<Member> _channelMembers = const [];

  bool _loading = true;

  /// 방금 추가한 사람 id (추가 즉시 목록에서 사라지게 한다)
  final Set<String> _addedIds = {};

  /// 추가 요청이 진행 중인 사람 id (행별로 스피너)
  final Set<String> _addingIds = {};

  @override
  void initState() {
    super.initState();
    _loadMembers();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  /// 채널 멤버를 불러온다. (bootstrap 에는 없어서 서버에서 직접 읽는다)
  Future<void> _loadMembers() async {
    final state = context.read<AppState>();
    List<Member> members = const [];
    try {
      members = await state.membersForChannel(widget.channel.id);
    } catch (_) {
      members = const [];
    }
    if (!mounted) return;
    setState(() {
      _channelMembers = members;
      _loading = false;
    });
  }

  /// 채널에 사람을 추가한다.
  Future<void> _add(User user) async {
    setState(() => _addingIds.add(user.id));

    final state = context.read<AppState>();
    final ok = await state.addChannelMember(widget.channel.id, user.id);
    if (!mounted) return;

    setState(() {
      _addingIds.remove(user.id);
      if (ok) _addedIds.add(user.id);
    });

    showAppSnackBar(
      context,
      ok
          ? '${user.name}님을 채널에 추가했습니다.'
          : '채널에 추가하지 못했습니다. 잠시 후 다시 시도해주세요.',
    );
  }

  /// 추가 후보 (워크스페이스 구성원 − 이미 채널에 있는 사람 − 방금 추가한 사람)
  List<User> _candidates(AppState state) {
    final inside = _channelMembers.map((m) => m.user.id).toSet();
    final needle = _searchCtrl.text.trim().toLowerCase();

    return state.members
        .map((m) => m.user)
        .where((u) => !inside.contains(u.id) && !_addedIds.contains(u.id))
        .where((u) {
          if (needle.isEmpty) return true;
          final haystack = '${u.name} ${u.email} ${u.title ?? ''}'.toLowerCase();
          return haystack.contains(needle);
        })
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final candidates = _candidates(state);
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;

    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 손잡이
                  Center(
                    child: Container(
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(
                        color: LlackColors.rule,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                       Icon(Icons.person_add_alt_1_outlined, size: 20, color: LlackColors.accent),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '사람 추가',
                          style: LlackTypography.title,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, size: 20),
                        tooltip: '닫기',
                        onPressed: () => Navigator.pop(context),
                      ),
                    ],
                  ),
                  Text(
                    '#${widget.channel.name} 에 초대할 사람을 고르세요.',
                    style: LlackTypography.caption,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _searchCtrl,
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(
                      hintText: '이름 또는 이메일로 찾기',
                      prefixIcon: Icon(Icons.search, size: 20),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
              ),
            ),
            Flexible(
              child: _loading
                  ? const Padding(
                      padding: EdgeInsets.all(24),
                      child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : candidates.isEmpty
                      ? Padding(
                          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                          child: Text(
                            _searchCtrl.text.trim().isEmpty
                                ? '추가할 수 있는 사람이 없습니다. (이미 모두 채널에 있습니다)'
                                : '그런 사람이 없습니다.',
                            style: LlackTypography.caption,
                          ),
                        )
                      : ListView.separated(
                          shrinkWrap: true,
                          padding: const EdgeInsets.only(bottom: 12),
                          itemCount: candidates.length,
                          separatorBuilder: (_, _) => const Divider(height: 1),
                          itemBuilder: (ctx, i) {
                            final user = candidates[i];
                            final isAdding = _addingIds.contains(user.id);
                            return ListTile(
                              dense: true,
                              contentPadding:
                                  const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
                              leading: LlackAvatar(
                                name: user.name,
                                avatarUrl: user.avatarUrl,
                                avatarColor: user.avatarColor,
                                presence: user.presence,
                                size: 32,
                              ),
                              title: Text(user.name, style: LlackTypography.bodySmall),
                              subtitle: Text(
                                user.title != null && user.title!.isNotEmpty
                                    ? '${user.title} · ${user.email}'
                                    : user.email,
                                style: LlackTypography.caption,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              trailing: isAdding
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : TextButton(
                                      onPressed: () => _add(user),
                                      child: const Text('추가'),
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
