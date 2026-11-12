import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../../providers/app_state.dart';
import '../../widgets/app_snack_bar.dart';

/// 서버 주소를 검증한다.
/// - 빈 값, http/https 스킴 누락, 공백 포함, 파싱 불가 를 구분해서 한국어로 알려준다.
String? validateServerUrl(String raw) {
  final url = raw.trim();
  if (url.isEmpty) return '서버 주소를 입력하세요.';
  if (RegExp(r'\s').hasMatch(url)) return '주소에 공백이 포함되어 있습니다.';
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    return 'http:// 또는 https:// 로 시작하는 주소를 입력하세요.';
  }
  final uri = Uri.tryParse(url);
  if (uri == null || uri.host.isEmpty) return '올바른 서버 주소가 아닙니다.';
  return null;
}

/// 주소가 실제로 서버에 닿는지 확인한다.
///
/// 물리 기기에서 127.0.0.1 은 자기 자신을 가리켜서 항상 연결이 실패한다.
/// 그래서 주소를 저장하기 전에 "정말 그 주소로 통하는지"를 한 번 확인한다.
/// (401/404 등 어떤 HTTP 응답이든 오면 "서버에 도달했다" 고 본다)
Future<bool> checkServerReachable(String baseUrl) async {
  final normalized = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
  try {
    final uri = Uri.parse('$normalized/api/v1/me');
    await http
        .get(uri, headers: const {'Accept': 'application/json'})
        .timeout(const Duration(seconds: 8));
    return true;
  } catch (_) {
    // 연결 실패 / 타임아웃 / 잘못된 주소
    return false;
  }
}

/// 서버 주소 설정 다이얼로그를 연다.
///
/// 검증 → 연결 확인 → 저장(재접속) 순서로 진행하고,
/// 실패하면 대화상자를 닫지 않고 그대로 고칠 수 있게 한다.
/// 저장에 성공하면 저장한 주소를 돌려준다.
Future<void> showServerSettingsDialog(BuildContext context) async {
  final savedUrl = await showDialog<String>(
    context: context,
    builder: (_) => const _ServerSettingsDialog(),
  );
  if (savedUrl != null && context.mounted) {
    showAppSnackBar(context, '서버 주소가 변경되었습니다: $savedUrl');
  }
}

/// 서버 주소 설정 다이얼로그 본체.
///
/// 컨트롤러를 이 위젯이 직접 소유한다.
/// (dialog 를 닫은 뒤 컨트롤러를 dispose 하면 나가는 애니메이션 중에
///  TextField 가 이미 dispose 된 컨트롤러를 참조하는 문제가 생긴다)
class _ServerSettingsDialog extends StatefulWidget {
  const _ServerSettingsDialog();

  @override
  State<_ServerSettingsDialog> createState() => _ServerSettingsDialogState();
}

class _ServerSettingsDialogState extends State<_ServerSettingsDialog> {
  late final TextEditingController _controller;
  String? _errorMessage;
  bool _isChecking = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: context.read<AppState>().api.baseUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final state = context.read<AppState>();
    final url = _controller.text.trim();

    // 1) 입력값 검증
    final validation = validateServerUrl(url);
    if (validation != null) {
      setState(() => _errorMessage = validation);
      return;
    }

    // 2) 실제로 연결되는지 확인
    setState(() {
      _isChecking = true;
      _errorMessage = null;
    });
    final reachable = await checkServerReachable(url);
    if (!mounted) return;
    if (!reachable) {
      setState(() {
        _isChecking = false;
        _errorMessage = '서버에 연결할 수 없습니다. 주소와 네트워크를 확인해주세요.';
      });
      return;
    }

    // 3) 저장 (Core 가 WS 재연결과 데이터 재로딩까지 처리한다)
    try {
      await state.changeApiBaseUrl(url);
    } catch (e) {
      if (mounted) {
        setState(() {
          _isChecking = false;
          _errorMessage = '서버 주소를 적용하지 못했습니다: $e';
        });
      }
      return;
    }
    if (!mounted) return;
    Navigator.pop(context, url);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = context.watch<AppState>();

    return AlertDialog(
      title: const Text('서버 주소 설정'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '백엔드 API 서버 URL을 입력하세요.\n'
            '• 에뮬레이터: http://10.0.2.2:8000\n'
            '• 실제 기기: PC 의 LAN 주소 (예: http://192.168.0.10:8000)\n'
            '• 실제 기기에서 127.0.0.1 은 자기 자신을 뜻합니다.',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            autocorrect: false,
            enabled: !_isChecking,
            // 주소를 고치는 순간 이전 오류 문구는 사라져야 한다.
            // (그대로 남아 있으면 "이미 실패했다" 고 오해한다.)
            onChanged: (_) {
              if (_errorMessage != null) {
                setState(() => _errorMessage = null);
              }
            },
            decoration: InputDecoration(
              hintText: 'http://192.168.0.10:8000',
              isDense: true,
              errorText: _errorMessage,
              // 기본값은 1줄 + 말줄임이라 오류 설명이 잘려서 읽히지 않았다.
              errorMaxLines: 3,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            '현재 주소: ${state.api.baseUrl}',
            style: theme.textTheme.labelSmall,
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _isChecking ? null : () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: _isChecking ? null : _save,
          child: _isChecking
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
