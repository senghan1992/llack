import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';

/// 공유할 수 있게 다듬은 초대 코드.
///
/// 데스크톱 로그인 화면의 "초대 코드" 칸에 넣는 값이 이 코드다.
/// (화면은 주소를 붙이지 않는다 — 받는 사람은 서버 주소를 직접 알고 있다)
String buildInviteCode(String token) => token.trim();

/// 이메일로 팀원을 초대하고 보낸 초대를 관리하는 화면.
class InviteScreen extends StatefulWidget {
  const InviteScreen({super.key});

  @override
  State<InviteScreen> createState() => _InviteScreenState();
}

class _InviteScreenState extends State<InviteScreen> {
  final _emailController = TextEditingController();
  bool _isCreating = false;
  String? _freshCode;
  String? _revokingInviteId;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AppState>().loadInvites();
    });
  }

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _createInvite() async {
    final email = _emailController.text.trim();
    if (email.isEmpty || _isCreating) return;

    setState(() {
      _isCreating = true;
      _error = null;
    });

    final state = context.read<AppState>();
    Invite? invite;
    try {
      invite = await state.createInvite(email);
    } catch (_) {
      invite = null;
    }

    if (!mounted) return;
    setState(() {
      _isCreating = false;
      if (invite == null) {
        _error = '초대를 만들지 못했습니다';
      } else {
        _freshCode = buildInviteCode(invite.token);
        _emailController.clear();
      }
    });

    if (invite == null) {
      showAppSnackBar(context, '초대를 만들지 못했습니다');
    } else {
      showAppSnackBar(context, '${invite.email}님을 초대했습니다');
    }
  }

  Future<void> _copyCode(String code) async {
    try {
      await Clipboard.setData(ClipboardData(text: code));
      if (!mounted) return;
      showAppSnackBar(context, '초대 코드를 복사했습니다');
    } catch (_) {
      if (!mounted) return;
      showAppSnackBar(context, '초대 코드를 복사하지 못했습니다');
    }
  }

  Future<void> _revokeInvite(Invite invite) async {
    if (_revokingInviteId != null) return;
    setState(() => _revokingInviteId = invite.id);

    final state = context.read<AppState>();
    var succeeded = false;
    try {
      await state.revokeInvite(invite.id);
      succeeded = true;
    } catch (_) {
      succeeded = false;
    }

    if (!mounted) return;
    setState(() => _revokingInviteId = null);
    showAppSnackBar(context, succeeded ? '초대를 취소했습니다' : '초대를 취소하지 못했습니다');
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final invites = state.invites;

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: AppBar(
        backgroundColor: LlackColors.paper,
        surfaceTintColor: Colors.transparent,
        title: const Text('팀원 초대'),
      ),
      body: RefreshIndicator(
        color: LlackColors.accent,
        onRefresh: state.loadInvites,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
          children: [
            Text('이메일로 초대', style: LlackTypography.subtitle),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.done,
                    onSubmitted: (_) => _createInvite(),
                    decoration: InputDecoration(
                      hintText: 'name@company.com',
                      errorText: _error,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: _isCreating ? null : _createInvite,
                  icon: _isCreating
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.send_outlined, size: 17),
                  label: const Text('초대'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '초대 코드를 만들어 팀원에게 전달하세요. 코드는 7일 뒤 만료됩니다.',
              style: LlackTypography.caption,
            ),
            if (_freshCode != null) ...[
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: LlackColors.accentSoft,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: LlackColors.rule),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '새 초대 코드',
                      style: LlackTypography.titleSmall.copyWith(
                        color: LlackColors.accentDeep,
                      ),
                    ),
                    const SizedBox(height: 8),
                    SelectableText(
                      _freshCode!,
                      style: LlackTypography.bodySmall,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      '받는 사람은 로그인 화면의 "초대 코드" 칸에 이 코드를 넣습니다.',
                      style: LlackTypography.caption,
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      onPressed: () => _copyCode(_freshCode!),
                      icon: const Icon(Icons.copy, size: 17),
                      label: const Text('초대 코드 복사'),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 24),
            Text('보낸 초대', style: LlackTypography.subtitle),
            const SizedBox(height: 8),
            if (invites.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 28,
                    horizontal: 16,
                  ),
                  child: Center(
                    child: Text(
                      '아직 보낸 초대가 없습니다',
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
                  itemCount: invites.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, index) {
                    final invite = invites[index];
                    final code = buildInviteCode(invite.token);
                    final isRevoking = _revokingInviteId == invite.id;

                    return Padding(
                      padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  invite.email,
                                  style: LlackTypography.subtitle.copyWith(
                                    fontSize: 14,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 4),
                                SelectableText(
                                  code,
                                  style: LlackTypography.caption,
                                  maxLines: 2,
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.copy, size: 18),
                            tooltip: '${invite.email} 초대 코드 복사',
                            onPressed: () => _copyCode(code),
                          ),
                          isRevoking
                              ? const Padding(
                                  padding: EdgeInsets.all(12),
                                  child: SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  ),
                                )
                              : Tooltip(
                                  message: '${invite.email} 초대 취소',
                                  child: TextButton.icon(
                                    icon: Icon(
                                      Icons.delete_outline,
                                      size: 17,
                                      color: LlackColors.presenceBusy,
                                    ),
                                    label: const Text('취소'),
                                    onPressed: () => _revokeInvite(invite),
                                  ),
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
