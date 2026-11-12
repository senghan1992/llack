import 'dart:async';

import 'package:flutter/material.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_theme.dart';
import '../theme/llack_typography.dart';

/// 앱 전역 스낵바를 띄운다.
///
/// **어디서 불렸는지**에 따라 그리는 경로가 다르다.
///
/// 1. 일반 화면(모달 밖) → 기존 [ScaffoldMessenger] 경로
///    - 하단 네비게이션 **위**에 떠서 탭 바를 가리지 않는다.
///    - 채팅 화면이면 채팅 영역 안에 떠서 composer 를 가리지 않는다.
/// 2. 모달(다이얼로그/바텀시트) 안 → **루트 오버레이에 직접** 얹는다.
///    - [ScaffoldMessenger] 로 띄운 스낵바는 루트 Scaffold 가 그리므로,
///      루트 Scaffold 아래 계층인 모달 뒤에 숨어서 **사용자에게 보이지 않는다.**
///
/// - 자동 닫힘(기본 4초), 탭하면 즉시 닫힘
/// - 키보드가 올라와 있으면 키보드 위(inset)에 붙는다
/// - 한 번에 하나만: 새 메시지가 오면 이전 것을 교체한다
/// - 루트 오버레이를 못 찾으면(극히 드먼 예외) [ScaffoldMessenger] 경로로 폴백한다
/// - [actionLabel]/[onAction] 을 주면 오른쪽에 액션(예: "실행 취소")이 붙는다
void showAppSnackBar(
  BuildContext context,
  String message, {
  Duration duration = const Duration(seconds: 4),
  String? actionLabel,
  VoidCallback? onAction,
}) {
  final route = ModalRoute.of(context);
  final messenger = ScaffoldMessenger.maybeOf(context);

  // 일반 화면에서 불린 경우 → 기존 ScaffoldMessenger 경로를 그대로 쓴다
  // (하단 네비 위, 채팅 화면이면 채팅 영역 안에 떠서 composer 를 가리지 않는다)
  if (route is! PopupRoute && messenger != null) {
    // 기존 스낵바를 먼저 내리고 새 것을 띄운다 (그렇지 않으면 스낵바가 큐잉되어 두 개가 차례로 뜬다)
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          action: (actionLabel != null && onAction != null)
              ? SnackBarAction(label: actionLabel, onPressed: onAction)
              : null,
          duration: duration,
          // 액션이 있으면 SnackBar 가 "계속 표시" 로 바뀌어 duration 이 무시된다 → 자동 닫힘을 살린다
          persist: false,
        ),
      );
    return;
  }

  // 모달(다이얼로그/바텀시트) 안에서 불린 경우 → 루트 오버레이에 직접 얹는다
  final overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay == null) {
    // 오버레이를 못 찾으면 아무것도 안 뜨는 것보다 나으므로 기존 경로로 폴백한다
    messenger?.showSnackBar(
      SnackBar(
        content: Text(message),
        action: (actionLabel != null && onAction != null)
            ? SnackBarAction(label: actionLabel, onPressed: onAction)
            : null,
        duration: duration,
        persist: false,
      ),
    );
    return;
  }
  _AppSnackBarHost.show(
    overlay,
    message,
    duration,
    actionLabel: actionLabel,
    onAction: onAction,
  );
}

/// 루트 오버레이 위 스낵바 한 개를 관리한다. (한 번에 하나만 보인다)
class _AppSnackBarHost {
  _AppSnackBarHost._();

  static OverlayEntry? _entry;

  static void show(
    OverlayState overlay,
    String message,
    Duration duration, {
    String? actionLabel,
    VoidCallback? onAction,
  }) {
    // 새 메시지가 오면 이전 것을 교체한다 (스낵바와 같은 UX)
    _remove();

    late final OverlayEntry entry;
    entry = OverlayEntry(
      builder: (context) => AppSnackBar(
        message: message,
        duration: duration,
        actionLabel: actionLabel,
        onAction: onAction,
        onDismiss: () {
          // 이미 다른 메시지로 교체되었거나 제거된 경우 다시 제거하지 않는다
          // (OverlayEntry 는 한 번만 제거할 수 있다)
          if (!identical(_entry, entry)) return;
          _entry = null;
          entry.remove();
        },
      ),
    );
    _entry = entry;
    overlay.insert(entry);
  }

  static void _remove() {
    final entry = _entry;
    _entry = null;
    entry?.remove();
  }
}

/// 루트 오버레이에 직접 얹히는 스낵바.
///
/// [Scaffold] 안에 있지 않으므로 어떤 모달(다이얼로그/바텀시트) 뒤에도 가려지지 않는다.
class AppSnackBar extends StatefulWidget {
  final String message;
  final Duration duration;

  /// 오른쪽에 붙는 액션 라벨 (예: "실행 취소"). null 이면 텍스트만 보인다.
  final String? actionLabel;
  final VoidCallback? onAction;

  final VoidCallback onDismiss;

  const AppSnackBar({
    super.key,
    required this.message,
    required this.duration,
    this.actionLabel,
    this.onAction,
    required this.onDismiss,
  });

  @override
  State<AppSnackBar> createState() => _AppSnackBarState();
}

class _AppSnackBarState extends State<AppSnackBar> with SingleTickerProviderStateMixin {
  static const Duration _animationDuration = Duration(milliseconds: 180);

  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: _animationDuration,
    reverseDuration: _animationDuration,
  );
  late final Animation<double> _fade = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
  late final Animation<Offset> _slide = Tween<Offset>(
    begin: const Offset(0, 0.35),
    end: Offset.zero,
  ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _controller.forward();
    _timer = Timer(widget.duration, _dismiss);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _dismiss() async {
    if (!mounted) return;
    await _controller.reverse();
    if (!mounted) return;
    widget.onDismiss();
  }

  /// 액션을 누르면 콜백을 부르고 닫는다.
  Future<void> _handleAction() async {
    widget.onAction?.call();
    await _dismiss();
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    // 키보드가 올라와 있으면 키보드 위에 붙고, 아니면 안전 영역 위쪽에 붙는다
    final keyboardInset = media.viewInsets.bottom;

    return Positioned(
      left: 0,
      right: 0,
      bottom: keyboardInset,
      child: SafeArea(
        top: false,
        // 키보드가 이미 화면 아래를 덮고 있으므로 안전 영역 여백은 중복이 된다
        bottom: keyboardInset == 0,
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) => Opacity(
            opacity: _fade.value,
            child: Transform.translate(offset: _slide.value, child: child),
          ),
          child: GestureDetector(
            // 탭하면 즉시 닫힌다
            onTap: _dismiss,
            child: Container(
              margin: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                color: LlackColors.surfaceRaise,
                borderRadius: BorderRadius.circular(LlackTheme.radiusInput),
                border: Border.all(color: LlackColors.rule, width: 1),
                boxShadow: LlackTheme.shadowE2,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.message,
                      style: LlackTypography.bodySmall.copyWith(color: LlackColors.ink),
                    ),
                  ),
                  if (widget.actionLabel != null && widget.onAction != null)
                    GestureDetector(
                      onTap: _handleAction,
                      child: Padding(
                        padding: const EdgeInsets.only(left: 12),
                        child: Text(
                          widget.actionLabel!,
                          style: LlackTypography.bodySmall.copyWith(
                            color: LlackColors.accentDeep,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
