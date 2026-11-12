import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_theme.dart';
import '../widgets/app_snack_bar.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _isSignUp = false;
  final _formKey = GlobalKey<FormState>();

  // 존재하지 않는 데모 계정 기본값은 두지 않는다 (사용자가 직접 입력해야 한다)
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _wsNameCtrl = TextEditingController();

  bool _obscurePassword = true;

  /// 세션 만료로 튕긴 경우 이메일을 자동으로 채웠는지.
  /// (한 번만 채운다. 사용자가 직접 지우고 고칠 수 있어야 한다)
  bool _emailPrefilled = false;

  /// 네트워크/서버 주소 문제로 인한 실패인지 추정한다.
  /// (실기에서 기본 주소(10.0.2.2 / 127.0.0.1)로는 연결이 안 되므로 안내가 필요하다)
  bool _looksLikeConnectionError(String? message) {
    if (message == null || message.isEmpty) return false;
    const keywords = ['연결', '네트워크', '서버', 'timeout', 'host', '소켓', 'refused'];
    final lower = message.toLowerCase();
    return keywords.any((k) => lower.contains(k.toLowerCase()));
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final state = context.read<AppState>();
    // 이전 실패 메시지를 지워 화면에 남는 잔상(유령) 에러를 막는다
    state.clearAuthError();

    try {
      if (_isSignUp) {
        await state.signup(
          email: _emailCtrl.text.trim(),
          password: _passCtrl.text,
          name: _nameCtrl.text.trim(),
          workspaceName: _wsNameCtrl.text.trim(),
        );
      } else {
        await state.login(_emailCtrl.text.trim(), _passCtrl.text);
      }
    } catch (e) {
      // Core 가 authError 로 알려주지만, 예외가 그대로 올라오는 경우도 방어한다.
      if (!mounted) return;
      showAppSnackBar(context, '로그인에 실패했습니다: $e');
    }
  }

  void _showServerSettings() {
    final state = context.read<AppState>();
    final ctrl = TextEditingController(text: state.api.baseUrl);

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('서버 주소 설정', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '백엔드 API 서버 URL을 입력하세요.\n• 에뮬레이터: http://10.0.2.2:8000\n• 실제 기기: PC 의 LAN 주소 (예: http://192.168.0.10:8000)',
              style: TextStyle(fontSize: 13, color: LlackColors.ink2),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                hintText: 'http://192.168.0.10:8000',
                isDense: true,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () async {
              final url = ctrl.text.trim();
              Navigator.pop(ctx);
              if (!mounted) return;
              await state.changeApiBaseUrl(url);
              if (!mounted) return;
              showAppSnackBar(context, '서버 주소가 변경되었습니다: $url');
            },
            child: const Text('저장'),
          ),
        ],
      ),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _prefillEmailIfSessionExpired();
  }

  /// 세션 만료로 로그인 화면에 돌아온 경우, 마지막으로 로그인했던 이메일을 미리 채운다.
  ///
  /// 비밀번호는 절대 채우지 않는다. 한 번만 채우며, 이후에는 사용자가 직접 고칠 수 있다.
  void _prefillEmailIfSessionExpired() {
    if (_emailPrefilled) return;
    final state = context.read<AppState>();
    if (!state.isSessionExpired) return;
    final email = state.currentUser?.email;
    if (email == null || email.isEmpty) return;
    _emailPrefilled = true;
    _emailCtrl.text = email;
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _nameCtrl.dispose();
    _wsNameCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    final authError = state.authError;
    final isBusy = state.isAuthenticating;
    final sessionExpired = state.isSessionExpired;

    return Scaffold(
      backgroundColor: LlackColors.paper,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 서버 주소 설정 진입점 — 실제 기기에서는 기본 주소로 연결이 안 되므로
                    // 눈에 띄게(아이콘 버튼) 노출한다 (§3-C-10)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.dns_outlined, color: LlackColors.ink2),
                          tooltip: '서버 주소 설정',
                          onPressed: _showServerSettings,
                        ),
                      ],
                    ),

                    // Brand mark
                    Center(
                      child: Container(
                        width: 56,
                        height: 56,
                        decoration: BoxDecoration(
                          color: LlackColors.accent,
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: LlackTheme.shadowE2,
                        ),
                        alignment: Alignment.center,
                        child: const Text(
                          'A',
                          style: TextStyle(
                            color: LlackColors.accentInk,
                            fontSize: 30,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -1,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Center(
                      child: Text(
                        _isSignUp ? '새 워크스페이스 시작하기' : 'Atrium에 로그인',
                        style: theme.textTheme.displayLarge?.copyWith(fontSize: 22),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Center(
                      child: Text(
                        'ArcheAI의 지성과 협업이 모이는 곳',
                        style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                      ),
                    ),
                    const SizedBox(height: 28),

                    // 세션 만료 안내 — 로그아웃된 이유를 사용자에게 알린다.
                    // (빨간 오류 박스와 혼동되지 않도록 중립적인 색을 쓴다)
                    if (sessionExpired) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(bottom: 16),
                        decoration: BoxDecoration(
                          color: LlackColors.accentSoft,
                          borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                          border: Border.all(color: LlackColors.accent.withValues(alpha: 0.35)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.info_outline, size: 18, color: LlackColors.accent),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    '세션이 만료되었습니다. 다시 로그인해주세요.',
                                    style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.ink),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '보안 정책상 연결이 끊겨 로그인 화면으로 돌아왔습니다. 같은 계정으로 다시 로그인해주세요.',
                              style: theme.textTheme.labelSmall?.copyWith(color: LlackColors.muted),
                            ),
                          ],
                        ),
                      ),
                    ],

                    // 오류 메시지는 Core 의 authError 를 그대로 보여준다 (로컬 상태를 두지 않는다)
                    if (authError != null)
                      Container(
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(bottom: 16),
                        decoration: BoxDecoration(
                          color: LlackColors.presenceBusy.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                          border: Border.all(color: LlackColors.presenceBusy.withValues(alpha: 0.3)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              authError,
                              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.presenceBusy),
                            ),
                            if (_looksLikeConnectionError(authError)) ...[
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      '실제 기기에서는 127.0.0.1 로 연결되지 않습니다. PC 의 LAN 주소로 바꿔주세요.',
                                      style: theme.textTheme.labelSmall,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  ElevatedButton(
                                    onPressed: _showServerSettings,
                                    style: ElevatedButton.styleFrom(
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    ),
                                    child: const Text('서버 주소 설정'),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),

                    if (_isSignUp) ...[
                      Text('회사 / 워크스페이스 이름', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                      const SizedBox(height: 6),
                      TextFormField(
                        controller: _wsNameCtrl,
                        decoration: const InputDecoration(hintText: '예: 테크노바코리아'),
                        validator: (v) => v == null || v.trim().isEmpty ? '워크스페이스 이름을 입력하세요' : null,
                      ),
                      const SizedBox(height: 16),
                      Text('내 이름', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                      const SizedBox(height: 6),
                      TextFormField(
                        controller: _nameCtrl,
                        decoration: const InputDecoration(hintText: '홍길동'),
                        validator: (v) => v == null || v.trim().isEmpty ? '이름을 입력하세요' : null,
                      ),
                      const SizedBox(height: 16),
                    ],

                    Text('이메일', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                    const SizedBox(height: 6),
                    TextFormField(
                      controller: _emailCtrl,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      decoration: const InputDecoration(hintText: 'name@company.com'),
                      validator: (v) => v == null || !v.contains('@') ? '올바른 이메일을 입력하세요' : null,
                    ),
                    const SizedBox(height: 16),

                    Text('비밀번호', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                    const SizedBox(height: 6),
                    TextFormField(
                      controller: _passCtrl,
                      obscureText: _obscurePassword,
                      decoration: InputDecoration(
                        hintText: '6자 이상 입력하세요',
                        // 비밀번호를 다시 보려면 지우지 않아도 되도록 토글 제공
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                            size: 20,
                          ),
                          tooltip: _obscurePassword ? '비밀번호 표시' : '비밀번호 숨기기',
                          onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                        ),
                      ),
                      validator: (v) => v == null || v.length < 6 ? '6자 이상 입력하세요' : null,
                    ),
                    const SizedBox(height: 24),

                    ElevatedButton(
                      onPressed: isBusy ? null : _submit,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                        ),
                      ),
                      child: isBusy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Text(
                              _isSignUp ? '워크스페이스 생성' : '로그인',
                              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                            ),
                    ),
                    const SizedBox(height: 16),

                    TextButton(
                      onPressed: isBusy
                          ? null
                          : () {
                              context.read<AppState>().clearAuthError();
                              setState(() => _isSignUp = !_isSignUp);
                            },
                      child: Text(
                        _isSignUp ? '이미 계정이 있으신가요? 로그인' : '새 워크스페이스를 만드시나요? 회원가입',
                        style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.accent),
                      ),
                    ),

                    const SizedBox(height: 20),
                    Center(
                      child: TextButton.icon(
                        icon: const Icon(Icons.settings_outlined, size: 16, color: LlackColors.muted),
                        label: Text(
                          '서버 주소 설정 (${state.api.baseUrl})',
                          style: theme.textTheme.labelSmall,
                        ),
                        onPressed: _showServerSettings,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
