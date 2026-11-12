import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../responsive/screen_type.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';
import 'chat_navigator.dart';
import 'new_channel_dialog.dart';
import 'new_dm_dialog.dart';

class ChatTab extends StatelessWidget {
  const ChatTab({super.key});

  void _onSelectChannel(BuildContext context, Channel channel) {
    final state = context.read<AppState>();
    final navigator = Navigator.of(context, rootNavigator: true);
    final formFactor = FormFactor(context);

    ChatNavigator.openChannel(
      state: state,
      navigator: navigator,
      channelId: channel.id,
      // 태블릿은 대화창이 이미 옆에 보이므로 push 하지 않는다.
      push: formFactor.isCompact,
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final channels = state.channels;
    final dms = state.dms;
    final activeId = state.activeChannelId;
    final myId = state.currentUser?.id;

    return Scaffold(
      backgroundColor: LlackColors.paper,
      body: RefreshIndicator(
        // boot() 은 콜드 스타트 전용이다. 여기서 쓰면 앱 전체가 스플래시로 교체되고
        // (오프라인이면) 로그아웃까지 된다. 새로고침은 토큰을 건드리지 않는
        // refreshWorkspace() 를 쓴다. (IMPROVEMENT_PLAN §1-A-3)
        onRefresh: () => state.refreshWorkspace(),
        color: LlackColors.accent,
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            // 목록을 못 불러온 경우: "비어 있음" 과 구분해서 오류와 재시도를 보여준다.
            if (state.channelsError != null)
              Container(
                margin: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: LlackColors.presenceBusy.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: LlackColors.presenceBusy.withValues(alpha: 0.3),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        state.channelsError!,
                        style: LlackTypography.bodySmall.copyWith(
                          color: LlackColors.presenceBusy,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: () => state.retryChannels(),
                      child: const Text('다시 시도'),
                    ),
                  ],
                ),
              ),

            // Channels section header
            _buildSectionHeader(
              title: '채널',
              onAdd: () => showDialog(
                context: context,
                builder: (_) => const NewChannelDialog(),
              ),
            ),
            if (channels.isEmpty && state.channelsError == null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Text('채널이 없습니다', style: LlackTypography.caption),
              )
            else
              ...channels.map((ch) {
                final isSelected = ch.id == activeId;
                return _buildChannelTile(
                  context,
                  channel: ch,
                  isSelected: isSelected,
                  onTap: () => _onSelectChannel(context, ch),
                );
              }),

            const SizedBox(height: 16),

            // DMs section header
            _buildSectionHeader(
              title: '직접 메시지',
              onAdd: () => showDialog(
                context: context,
                builder: (_) => const NewDmDialog(),
              ),
            ),
            if (dms.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Text('진행 중인 1:1 대화가 없습니다', style: LlackTypography.caption),
              )
            else
              ...dms.map((dm) {
                final isSelected = dm.id == activeId;
                // find other member for presence
                final otherUser = dm.dmUser ??
                    ((dm.members != null && dm.members!.isNotEmpty)
                        ? dm.members!.firstWhere((m) => m.id != myId, orElse: () => dm.members!.first)
                        : User(id: '', email: '', name: dm.name));
                final presence = state.getPresence(otherUser.id);

                return _buildDmTile(
                  context,
                  dm: dm,
                  otherUser: otherUser,
                  presence: presence,
                  isSelected: isSelected,
                  onTap: () => _onSelectChannel(context, dm),
                );
              }),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionHeader({required String title, required VoidCallback onAdd}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            title.toUpperCase(),
            style: LlackTypography.caption.copyWith(
              fontWeight: FontWeight.w700,
              letterSpacing: 0.8,
              fontSize: 11,
              color: LlackColors.muted,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add_rounded, size: 22, color: LlackColors.ink2),
            onPressed: onAdd,
            tooltip: '$title 추가',
            // 최소 44dp 터치 타깃 확보 (아이콘 크기만 20dp 라 누르기 어려웠다)
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          ),
        ],
      ),
    );
  }

  Widget _buildChannelTile(
    BuildContext context, {
    required Channel channel,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    // ListTile 은 가장 가까운 Material 위에 ink 를 그리는데, ListTile 아래에
    // 색이 있는 Container 를 두면 그 색이 ink 를 가려 버그가 난다
    // ("ListTile background color or ink splashes may be invisible").
    // 그래서 배경색을 Material 로 옮기고, ListTile 은 자기 Material 안에 둔다.
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
      child: Material(
        color: isSelected ? LlackColors.surfaceSelected : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: ListTile(
          dense: true,
          leading: Icon(
            channel.isPrivate ? Icons.lock_outline : Icons.tag,
            size: 18,
            color: isSelected ? LlackColors.accent : LlackColors.ink2,
          ),
          title: Text(
            channel.name,
            style: LlackTypography.body.copyWith(
              fontWeight: isSelected || channel.unreadCount > 0 ? FontWeight.w600 : FontWeight.w400,
              color: isSelected ? LlackColors.accentDeep : LlackColors.ink,
            ),
          ),
          trailing: channel.unreadCount > 0
              ? Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: LlackColors.accent,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${channel.unreadCount}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                )
              : null,
          onTap: onTap,
        ),
      ),
    );
  }

  Widget _buildDmTile(
    BuildContext context, {
    required Channel dm,
    required User otherUser,
    required Presence presence,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    // 채널 타일과 같은 이유로 ListTile 을 자기 Material 안에 둔다.
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
      child: Material(
        color: isSelected ? LlackColors.surfaceSelected : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: ListTile(
          dense: true,
          leading: LlackAvatar(
            name: otherUser.name,
            avatarUrl: otherUser.avatarUrl,
            avatarColor: otherUser.avatarColor,
            presence: presence,
            size: 28,
            fontSize: 11,
          ),
          title: Text(
            otherUser.name,
            style: LlackTypography.body.copyWith(
              fontWeight: isSelected || dm.unreadCount > 0 ? FontWeight.w600 : FontWeight.w400,
              color: isSelected ? LlackColors.accentDeep : LlackColors.ink,
            ),
          ),
          subtitle: otherUser.title != null && otherUser.title!.isNotEmpty
              ? Text(
                  otherUser.title!,
                  style: LlackTypography.caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                )
              : null,
          trailing: dm.unreadCount > 0
              ? Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: LlackColors.accent,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${dm.unreadCount}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                )
              : null,
          onTap: onTap,
        ),
      ),
    );
  }
}
