import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';

/// 채널 설정 시트.
///
/// - 이름 / 주제(topic) / 목적(purpose) 수정
/// - 채널 삭제 (확인 다이얼로그를 거쳐야 한다)
///
/// 데스크톱의 ChannelSettingsDialog(dialogs.tsx) 를 모바일로 옮긴 것.
class ChannelSettingsSheet extends StatefulWidget {
  final Channel channel;

  const ChannelSettingsSheet({super.key, required this.channel});

  @override
  State<ChannelSettingsSheet> createState() => _ChannelSettingsSheetState();
}

class _ChannelSettingsSheetState extends State<ChannelSettingsSheet> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _topicCtrl;
  late final TextEditingController _purposeCtrl;

  bool _saving = false;
  bool _deleting = false;

  /// 이름이 비었을 때 보여줄 안내
  String? _nameError;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController(text: widget.channel.name);
    _topicCtrl = TextEditingController(text: widget.channel.topic ?? '');
    _purposeCtrl = TextEditingController(text: widget.channel.purpose ?? '');
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _topicCtrl.dispose();
    _purposeCtrl.dispose();
    super.dispose();
  }

  /// 이름·주제·목적을 저장한다.
  ///
  /// 저장에 **실패하면 폼을 닫지 않고** 사유를 알린다.
  /// (실패한 값을 잃지 않고 바로 다시 고칠 수 있어야 한다)
  Future<void> _save() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty) {
      setState(() => _nameError = '채널 이름을 입력해주세요.');
      return;
    }

    setState(() {
      _saving = true;
      _nameError = null;
    });

    final state = context.read<AppState>();
    final ok = await state.updateChannel(
      channelId: widget.channel.id,
      name: name,
      topic: _topicCtrl.text.trim(),
      purpose: _purposeCtrl.text.trim(),
    );
    if (!mounted) return;
    setState(() => _saving = false);

    if (!ok) {
      showAppSnackBar(context, '채널 정보를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.');
      return;
    }
    // 스낵바를 먼저 띄운다 (시트를 닫으면 context 를 쓸 수 없다)
    showAppSnackBar(context, '채널 정보를 저장했습니다.');
    Navigator.pop(context);
  }

  /// 채널을 삭제한다. (확인 다이얼로그를 거쳐야 한다)
  Future<void> _deleteChannel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('채널 삭제'),
        content: Text(
          '#${widget.channel.name} 채널을 삭제할까요?\n채널과 그 안의 메시지가 모두 사라집니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: LlackColors.presenceBusy),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _deleting = true);
    final state = context.read<AppState>();
    final ok = await state.deleteChannel(widget.channel.id);
    if (!mounted) return;
    setState(() => _deleting = false);

    if (!ok) {
      showAppSnackBar(context, '채널을 삭제하지 못했습니다. 잠시 후 다시 시도해주세요.');
      return;
    }
    showAppSnackBar(context, '채널을 삭제했습니다.');
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    // 키보드가 올라오면 시트가 가려지지 않게 입력 영역만큼 위로 올린다
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;

    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: SafeArea(
        top: false,
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
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
                     Icon(Icons.tune_rounded, size: 20, color: LlackColors.accent),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '채널 설정',
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
                const SizedBox(height: 16),
                TextField(
                  controller: _nameCtrl,
                  autofocus: true,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: '채널 이름',
                    hintText: '예: general, 개발-논의',
                    prefixText: '# ',
                    errorText: _nameError,
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _topicCtrl,
                  decoration: const InputDecoration(
                    labelText: '주제',
                    hintText: '이 채널에서 나눌 이야기',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _purposeCtrl,
                  maxLines: 2,
                  decoration: const InputDecoration(
                    labelText: '목적',
                    hintText: '이 채널을 만든 이유 (선택)',
                  ),
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    TextButton(
                      onPressed: _saving ? null : () => Navigator.pop(context),
                      child: const Text('취소'),
                    ),
                    const Spacer(),
                    ElevatedButton(
                      onPressed: _saving ? null : _save,
                      child: _saving
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
                ),
                const SizedBox(height: 8),
                const Divider(height: 1),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  icon: Icon(
                    Icons.delete_outline,
                    size: 16,
                    color: LlackColors.presenceBusy,
                  ),
                  label: Text(
                    '채널 삭제',
                    style: TextStyle(color: LlackColors.presenceBusy),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: LlackColors.presenceBusy),
                  ),
                  onPressed: _deleting ? null : _deleteChannel,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
