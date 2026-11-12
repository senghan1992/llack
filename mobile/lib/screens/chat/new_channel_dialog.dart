import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';

class NewChannelDialog extends StatefulWidget {
  const NewChannelDialog({super.key});

  @override
  State<NewChannelDialog> createState() => _NewChannelDialogState();
}

class _NewChannelDialogState extends State<NewChannelDialog> {
  final _nameCtrl = TextEditingController();
  final _topicCtrl = TextEditingController();
  bool _isPrivate = false;
  final Set<String> _selectedMemberIds = {};
  bool _isCreating = false;

  void _submit() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty) return;

    setState(() => _isCreating = true);
    final state = context.read<AppState>();
    try {
      await state.createChannel(
        name: name,
        topic: _topicCtrl.text.trim().isNotEmpty ? _topicCtrl.text.trim() : null,
        isPrivate: _isPrivate,
        memberIds: _selectedMemberIds.isNotEmpty ? _selectedMemberIds.toList() : null,
      );
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        // 다이얼로그가 열려 있는 상태에서 띄우므로 루트 오버레이에 얹혀
        // 다이얼로그 뒤에 숨어서 안 보이는 문제를 피한다.
        showAppSnackBar(context, '생성 실패: $e');
        setState(() => _isCreating = false);
      }
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _topicCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final myId = state.currentUser?.id;
    final otherMembers = state.members.where((m) => m.user.id != myId).toList();

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(LlackTheme.radiusPanel)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 600),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('새 채널 만들기', style: LlackTypography.title),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _nameCtrl,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: '채널 이름',
                  hintText: '예: general, 개발-논의',
                  prefixText: '# ',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _topicCtrl,
                decoration: const InputDecoration(
                  labelText: '주제 (선택)',
                  hintText: '이 채널에서 나눌 이야기',
                ),
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                value: _isPrivate,
                onChanged: (v) => setState(() => _isPrivate = v),
                title: const Text('비공개 채널', style: LlackTypography.body),
                subtitle: const Text('초대받은 멤버만 이 채널을 볼 수 있습니다', style: LlackTypography.caption),
                contentPadding: EdgeInsets.zero,
                activeTrackColor: LlackColors.accent,
              ),
              const SizedBox(height: 8),
              Text('초대할 멤버 (${_selectedMemberIds.length}명 선택됨)', style: LlackTypography.subtitle.copyWith(fontSize: 13)),
              const SizedBox(height: 6),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: LlackColors.surfaceWell,
                    borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                    border: Border.all(color: LlackColors.rule),
                  ),
                  child: ListView.separated(
                    itemCount: otherMembers.length,
                    separatorBuilder: (_, _) => const Divider(height: 1),
                    itemBuilder: (ctx, i) {
                      final mem = otherMembers[i];
                      final isSelected = _selectedMemberIds.contains(mem.user.id);
                      return CheckboxListTile(
                        value: isSelected,
                        onChanged: (chk) {
                          setState(() {
                            if (chk == true) {
                              _selectedMemberIds.add(mem.user.id);
                            } else {
                              _selectedMemberIds.remove(mem.user.id);
                            }
                          });
                        },
                        secondary: LlackAvatar(
                          name: mem.user.name,
                          avatarUrl: mem.user.avatarUrl,
                          avatarColor: mem.user.avatarColor,
                          presence: mem.user.presence,
                          size: 30,
                        ),
                        title: Text(mem.user.name, style: LlackTypography.bodySmall),
                        subtitle: Text(mem.user.email, style: LlackTypography.caption),
                        activeColor: LlackColors.accent,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 10),
                      );
                    },
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('취소'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: _isCreating ? null : _submit,
                    child: _isCreating
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('만들기'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
