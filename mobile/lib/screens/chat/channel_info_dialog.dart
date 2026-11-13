import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';
import 'channel_settings_sheet.dart';
import 'people_picker_sheet.dart';

class ChannelInfoDialog extends StatefulWidget {
  final Channel channel;

  const ChannelInfoDialog({super.key, required this.channel});

  @override
  State<ChannelInfoDialog> createState() => _ChannelInfoDialogState();
}

class _ChannelInfoDialogState extends State<ChannelInfoDialog> {
  List<Message> _pins = [];
  bool _loadingPins = true;
  List<Member> _members = [];
  bool _loadingMembers = true;

  @override
  void initState() {
    super.initState();
    _loadPins();
    _loadMembers();
  }

  /// bootstrap 에는 채널 멤버가 없으므로 서버에서 직접 불러온다.
  void _loadMembers() async {
    final state = context.read<AppState>();
    try {
      final members = await state.membersForChannel(widget.channel.id);
      if (mounted) {
        setState(() {
          _members = members;
          _loadingMembers = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingMembers = false);
    }
  }

  void _loadPins() async {
    try {
      final state = context.read<AppState>();
      final pins = await state.api.getPins(widget.channel.id);
      if (mounted) {
        setState(() {
          _pins = pins;
          _loadingPins = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingPins = false);
    }
  }

  /// 채널 설정 시트 (이름 · 주제 · 목적 수정 · 삭제)를 연다.
  ///
  /// 다이얼로그를 **닫지 않고** 시트를 그 위에 띄운다.
  /// (설정을 바꾸고 돌아오면 같은 대화창에서 결과를 바로 볼 수 있다)
  Future<void> _openSettings(BuildContext context) async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => ChannelSettingsSheet(channel: widget.channel),
    );
    if (!mounted) return;
    setState(() {}); // 바뀐 이름·주제를 즉시 반영한다
  }

  /// 채널에 사람 추가 시트를 연다.
  Future<void> _openPeoplePicker(BuildContext context) async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => PeoplePickerSheet(channel: widget.channel),
    );
    if (!mounted) return;
    // 방금 추가된 사람이 목록에 반영되도록 다시 불러온다
    _loadMembers();
  }

  void _leaveOrDelete(BuildContext context) async {
    final state = context.read<AppState>();
    final isDm = widget.channel.isDm;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isDm ? '대화 삭제' : '채널 나가기'),
        content: Text(
          isDm
              ? '이 1:1 대화를 삭제하시겠습니까? 대화 내용이 양쪽 모두에서 삭제됩니다.'
              : '정말 #${widget.channel.name} 채널을 나가시겠습니까?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: LlackColors.presenceBusy),
            child: Text(isDm ? '삭제' : '나가기'),
          ),
        ],
      ),
    );

    if (confirmed != true || !context.mounted) return;

    // 삭제/나가기는 **다이얼로그를 닫기 전에** 수행한다.
    // await 뒤에는 context 를 쓸 수 없으므로,
    // 안내(스낵바)도 다이얼로그가 열려 있는 동안 띄운다.
    // (스낵바는 루트 오버레이에 얹히므로 다이얼로그를 닫은 뒤에도 보인다)
    String? failureMessage;
    try {
      if (isDm) {
        await state.deleteDm(widget.channel.id);
      } else {
        await state.leaveChannel(widget.channel.id);
      }
    } catch (_) {
      failureMessage = isDm ? '대화를 삭제하지 못했습니다' : '채널을 나가지 못했습니다';
    }

    if (!context.mounted) return;

    if (failureMessage != null) {
      showAppSnackBar(context, failureMessage);
    }
    Navigator.pop(context); // close info dialog
  }

  /// 상태에 있는 **최신** 채널 정보.
  /// (설정을 저장하면 이름·주제가 바뀌므로 예전 스냅샷 대신 이 값을 쓴다)
  Channel _latestChannel(AppState state) {
    for (final c in state.allChannels) {
      if (c.id == widget.channel.id) return c;
    }
    return widget.channel;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final channel = _latestChannel(state);

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
                children: [
                  Icon(
                    channel.isDm ? Icons.alternate_email : (channel.isPrivate ? Icons.lock_outline : Icons.tag),
                    size: 22,
                    color: LlackColors.accent,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      channel.name,
                      style: LlackTypography.title,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (!channel.isDm)
                    IconButton(
                      icon: const Icon(Icons.tune_rounded, size: 20),
                      tooltip: '채널 설정',
                      onPressed: () => _openSettings(context),
                    ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              if (channel.topic != null && channel.topic!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(channel.topic!, style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted)),
              ],
              const SizedBox(height: 16),
              const Divider(height: 1),

              // Pinned messages section
              const SizedBox(height: 12),
              Row(
                children: [
                   Icon(Icons.push_pin, size: 16, color: LlackColors.accent),
                  const SizedBox(width: 6),
                  Text('고정된 메시지 (${_pins.length})', style: LlackTypography.subtitle.copyWith(fontSize: 13)),
                ],
              ),
              const SizedBox(height: 8),
              if (_loadingPins)
                const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator(strokeWidth: 2)))
              else if (_pins.isEmpty)
                Text('고정된 메시지가 없습니다', style: LlackTypography.caption)
              else
                Container(
                  constraints: const BoxConstraints(maxHeight: 120),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _pins.length,
                    separatorBuilder: (_, _) => const Divider(height: 1),
                    itemBuilder: (ctx, i) {
                      final p = _pins[i];
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Text('${p.author.name}: ${p.body}', style: LlackTypography.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                      );
                    },
                  ),
                ),

              const SizedBox(height: 16),
              const Divider(height: 1),

              // Members section
              const SizedBox(height: 12),
              Row(
                children: [
                   Icon(Icons.people_outline, size: 16, color: LlackColors.accent),
                  const SizedBox(width: 6),
                  Text(
                    '참여 중인 멤버 (${_members.isNotEmpty ? _members.length : channel.memberCount})',
                    style: LlackTypography.subtitle.copyWith(fontSize: 13),
                  ),
                  const Spacer(),
                  if (!channel.isDm)
                    TextButton(
                      onPressed: () => _openPeoplePicker(context),
                      child: const Text('사람 추가'),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: _loadingMembers
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.all(8),
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : _members.isEmpty
                        ? Text('멤버 정보를 불러오지 못했습니다', style: LlackTypography.caption)
                        : ListView.separated(
                            itemCount: _members.length,
                            separatorBuilder: (_, _) => const Divider(height: 1),
                            itemBuilder: (ctx, i) {
                              final m = _members[i];
                              final p = state.getPresence(m.user.id);
                              return ListTile(
                                dense: true,
                                contentPadding: EdgeInsets.zero,
                                leading: LlackAvatar(
                                  name: m.user.name,
                                  avatarUrl: m.user.avatarUrl,
                                  avatarColor: m.user.avatarColor,
                                  presence: p,
                                  size: 28,
                                ),
                                title: Text(m.user.name, style: LlackTypography.bodySmall),
                                subtitle: m.user.title != null
                                    ? Text(m.user.title!, style: LlackTypography.caption)
                                    : null,
                                trailing: Text(p.label, style: TextStyle(fontSize: 11, color: LlackColors.muted)),
                              );
                            },
                          ),
              ),

              const SizedBox(height: 12),
              OutlinedButton.icon(
                icon: Icon(
                  channel.isDm ? Icons.delete_outline : Icons.logout,
                  size: 16,
                  color: LlackColors.presenceBusy,
                ),
                label: Text(
                  channel.isDm ? '대화방 삭제' : '채널 나가기',
                  style: TextStyle(color: LlackColors.presenceBusy),
                ),
                style: OutlinedButton.styleFrom(
                  side: BorderSide(color: LlackColors.presenceBusy),
                ),
                onPressed: () => _leaveOrDelete(context),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
