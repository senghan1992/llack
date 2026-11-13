import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../services/device_settings.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';
import '../../widgets/presence_badge.dart';
import 'server_settings_dialog.dart';
import '../../widgets/app_snack_bar.dart';

class SettingsSheet extends StatelessWidget {
  const SettingsSheet({super.key});

  void _showEditProfileDialog(BuildContext context) {
    final user = context.read<AppState>().currentUser;
    if (user == null) return;

    // 컨트롤러를 다이얼로그 위젯이 소유하도록 분리했다 (dispose 누락 방지)
    showDialog<void>(
      context: context,
      builder: (_) => const _EditProfileDialog(),
    );
  }

  /// 내 상태(프리전스)를 바꾼다.
  ///
  /// updatePresence 는 내부에서 updateMe 를 부르므로 실패하면 예외를 던진다.
  /// 그대로 흘려보내면 Unhandled exception 으로 끝나 아무 변화가 없다.
  Future<void> _changePresence(BuildContext context, Presence presence) async {
    final state = context.read<AppState>();
    try {
      await state.updatePresence(presence);
    } catch (e) {
      if (!context.mounted) return;
      showAppSnackBar(context, '상태를 바꾸지 못했습니다');
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    final user = state.currentUser;
    if (user == null) return const SizedBox.shrink();

    final currentPresence = state.getPresence(user.id);

    return Material(
      // ListTile 이 그리는 ink 를 가리지 않도록, 배경색은 Container 가 아니라 Material 이 갖는다.
      // (DecoratedBox 로 감싸면 "ink splashes may be invisible" assertion 이 매 빌드마다 뜬다)
      color: LlackColors.surfaceRaise,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 12),
                decoration: BoxDecoration(
                  color: LlackColors.rule,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),

            // Profile card
            Row(
              children: [
                LlackAvatar(
                  name: user.name,
                  avatarUrl: user.avatarUrl,
                  avatarColor: user.avatarColor,
                  presence: currentPresence,
                  size: 48,
                  fontSize: 18,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user.name, style: theme.textTheme.titleLarge?.copyWith(fontSize: 16), maxLines: 1, overflow: TextOverflow.ellipsis),
                      if (user.title != null && user.title!.isNotEmpty)
                        Text(user.title!, style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.ink2), maxLines: 1, overflow: TextOverflow.ellipsis),
                      Text(user.email, style: theme.textTheme.labelSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 20),
                  tooltip: '프로필 수정',
                  onPressed: () => _showEditProfileDialog(context),
                ),
              ],
            ),

            const SizedBox(height: 16),
            const Divider(height: 1),
            const SizedBox(height: 12),

            // Presence selection
            Text('내 상태 설정', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
            const SizedBox(height: 8),

            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Presence.online,
                Presence.busy,
                Presence.dnd,
                Presence.away,
                Presence.brb,
              ].map((p) {
                final isSelected = currentPresence == p;
                final col = PresenceBadge.colorForPresence(p);
                return ChoiceChip(
                  label: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(width: 7, height: 7, decoration: BoxDecoration(color: col, shape: BoxShape.circle)),
                      const SizedBox(width: 6),
                      Text(p.label),
                    ],
                  ),
                  selected: isSelected,
                  selectedColor: col.withValues(alpha: 0.15),
                  labelStyle: theme.textTheme.labelMedium?.copyWith(
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w400,
                    color: isSelected ? col : LlackColors.ink2,
                  ),
                  onSelected: (val) {
                    if (val) _changePresence(context, p);
                  },
                );
              }).toList(),
            ),

            const SizedBox(height: 16),
            const Divider(height: 1),

            ListTile(
              leading: const Icon(Icons.dns_outlined, size: 20),
              title: Text('서버 주소 설정', style: LlackTypography.body),
              subtitle: Text(state.api.baseUrl, style: theme.textTheme.labelSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
              contentPadding: EdgeInsets.zero,
              onTap: () => showServerSettingsDialog(context),
            ),

            // ── 화면 모드 · 시간 표기 (이 기기에 저장된다) ──────────────
            const SizedBox(height: 16),
            const Divider(height: 1),
            const SizedBox(height: 12),

            ValueListenableBuilder<ThemeModeSetting>(
              valueListenable: DeviceSettings.instance.themeMode,
              builder: (context, mode, _) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('화면 모드', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: ThemeModeSetting.values.map((m) {
                        return ChoiceChip(
                          label: Text(m.label),
                          selected: mode == m,
                          selectedColor: LlackColors.accentSoft,
                          labelStyle: theme.textTheme.labelMedium?.copyWith(
                            fontWeight: mode == m ? FontWeight.w700 : FontWeight.w400,
                            color: mode == m ? LlackColors.accentDeep : LlackColors.ink2,
                          ),
                          onSelected: (v) {
                            if (v) DeviceSettings.instance.setThemeMode(m);
                          },
                        );
                      }).toList(),
                    ),
                  ],
                );
              },
            ),

            const SizedBox(height: 16),

            ValueListenableBuilder<ClockFormatSetting>(
              valueListenable: DeviceSettings.instance.clockFormat,
              builder: (context, format, _) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('시간 표기', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: ClockFormatSetting.values.map((f) {
                        return ChoiceChip(
                          label: Text(f.label),
                          selected: format == f,
                          selectedColor: LlackColors.accentSoft,
                          labelStyle: theme.textTheme.labelMedium?.copyWith(
                            fontWeight: format == f ? FontWeight.w700 : FontWeight.w400,
                            color: format == f ? LlackColors.accentDeep : LlackColors.ink2,
                          ),
                          onSelected: (v) {
                            if (v) DeviceSettings.instance.setClockFormat(f);
                          },
                        );
                      }).toList(),
                    ),
                  ],
                );
              },
            ),

            ListTile(
              leading: Icon(Icons.logout, size: 20, color: LlackColors.presenceBusy),
              title: Text('로그아웃', style: TextStyle(color: LlackColors.presenceBusy)),
              contentPadding: EdgeInsets.zero,
              onTap: () async {
                Navigator.pop(context);
                await state.logout();
              },
            ),
          ],
        ),
        ),
      ),
    );
  }
}

/// 프로필 수정 다이얼로그.
///
/// 컨트롤러를 이 위젯이 직접 소유해 dispose 로 정리한다.
/// 저장 중에는 버튼을 잠가 연타 중복 저장을 막고,
/// 저장이 실패하면 **다이얼로그를 닫지 않고** 사유를 알려준다.
class _EditProfileDialog extends StatefulWidget {
  const _EditProfileDialog();

  @override
  State<_EditProfileDialog> createState() => _EditProfileDialogState();
}

class _EditProfileDialogState extends State<_EditProfileDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _titleCtrl;
  bool _isSubmitting = false;

  /// 고른 아바타 색 (hex). null 이면 서버에 저장된 값을 그대로 쓴다.
  String? _avatarColor;

  @override
  void initState() {
    super.initState();
    final user = context.read<AppState>().currentUser;
    _nameCtrl = TextEditingController(text: user?.name ?? '');
    _titleCtrl = TextEditingController(text: user?.title ?? '');
    _avatarColor = user?.avatarColor;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _titleCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final newName = _nameCtrl.text.trim();
    if (newName.isEmpty || _isSubmitting) return;

    setState(() => _isSubmitting = true);
    final state = context.read<AppState>();
    try {
      await state.updateMe(
        name: newName,
        title: _titleCtrl.text.trim().isNotEmpty ? _titleCtrl.text.trim() : null,
        avatarColor: _avatarColor,
      );
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      // 실패 이유를 알려야 "버튼이 죽었다" 고 느끼지 않는다.
      // 대화상자는 닫지 않는다 (사용자가 입력한 값을 잃지 않게).
      setState(() => _isSubmitting = false);
      showAppSnackBar(context, '프로필을 저장하지 못했습니다: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('프로필 수정', style: LlackTypography.title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _nameCtrl,
            decoration: const InputDecoration(labelText: '이름'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _titleCtrl,
            decoration: const InputDecoration(labelText: '직함 / 부서', hintText: '예: 프로덕트 디자이너'),
          ),
          const SizedBox(height: 16),
          Text('아바타 색', style: LlackTypography.caption),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: LlackColors.avatarPalette.map((hex) {
              final color = LlackColors.colorFromHex(hex) ?? LlackColors.avatarColors.first;
              final selected = _avatarColor?.toLowerCase() == hex.toLowerCase();
              return Semantics(
                button: true,
                selected: selected,
                label: '아바타 색 $hex',
                child: InkWell(
                  onTap: () => setState(() => _avatarColor = hex),
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: color,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: selected ? LlackColors.ink : Colors.transparent,
                        width: 2,
                      ),
                    ),
                    child: selected
                        ? const Icon(Icons.check, size: 16, color: Colors.white)
                        : null,
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _isSubmitting ? null : () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: _isSubmitting ? null : _save,
          child: _isSubmitting
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('저장'),
        ),
      ],
    );
  }
}
