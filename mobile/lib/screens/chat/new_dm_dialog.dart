import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';
import '../../responsive/screen_type.dart';
import 'chat_navigator.dart';

class NewDmDialog extends StatefulWidget {
  const NewDmDialog({super.key});

  @override
  State<NewDmDialog> createState() => _NewDmDialogState();
}

class _NewDmDialogState extends State<NewDmDialog> {
  final _searchCtrl = TextEditingController();
  String _filter = '';

  @override
  void initState() {
    super.initState();
    _searchCtrl.addListener(() {
      setState(() => _filter = _searchCtrl.text.trim().toLowerCase());
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _startDm(Member member) async {
    final state = context.read<AppState>();
    // 다이얼로그를 닫으면 이 context 를 다시 쓸 수 없으므로 먼저 캡처한다.
    final navigator = Navigator.of(context, rootNavigator: true);
    final messenger = ScaffoldMessenger.of(context);
    // 태블릿은 대화창이 이미 옆에 보이므로 push 하지 않는다.
    final push = FormFactor(context).isCompact;

    Navigator.pop(context);
    try {
      // 대화를 만든 뒤 **대화창까지** 열어야 사용자가 바로 대화를 이어갈 수 있다.
      await ChatNavigator.openDm(
        state: state,
        navigator: navigator,
        userId: member.user.id,
        push: push,
      );
    } catch (error) {
      messenger.showSnackBar(
        SnackBar(content: Text(ChatNavigator.describeDmError(error))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final myId = state.currentUser?.id;
    final otherMembers = state.members.where((m) {
      if (m.user.id == myId) return false;
      if (_filter.isEmpty) return true;
      final nameMatch = m.user.name.toLowerCase().contains(_filter);
      final emailMatch = m.user.email.toLowerCase().contains(_filter);
      final titleMatch = m.user.title?.toLowerCase().contains(_filter) ?? false;
      return nameMatch || emailMatch || titleMatch;
    }).toList();

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(LlackTheme.radiusPanel)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440, maxHeight: 520),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                   Text('새 1:1 대화', style: LlackTypography.title),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _searchCtrl,
                autofocus: true,
                decoration: InputDecoration(
                  hintText: '이름, 직함, 이메일로 검색...',
                  prefixIcon: Icon(Icons.search, size: 20, color: LlackColors.muted),
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: otherMembers.isEmpty
                    ? Center(
                        child: Text(
                          _filter.isEmpty ? '멤버가 없습니다' : '검색 결과가 없습니다',
                          style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                        ),
                      )
                    : ListView.separated(
                        itemCount: otherMembers.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (ctx, i) {
                          final mem = otherMembers[i];
                          final presence = state.getPresence(mem.user.id);
                          return ListTile(
                            leading: LlackAvatar(
                              name: mem.user.name,
                              avatarUrl: mem.user.avatarUrl,
                              avatarColor: mem.user.avatarColor,
                              presence: presence,
                              size: 36,
                            ),
                            title: Text(mem.user.name, style: LlackTypography.subtitle.copyWith(fontSize: 14)),
                            subtitle: Text(
                              mem.user.title ?? mem.user.email,
                              style: LlackTypography.caption,
                            ),
                            trailing: Text(
                              presence.label,
                              style: TextStyle(
                                fontSize: 11,
                                color: LlackColors.muted,
                              ),
                            ),
                            onTap: () => _startDm(mem),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
