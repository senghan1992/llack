import 'package:flutter/material.dart';

/// 실시간으로 새로 도착하거나 방금 전송한 메시지가 아래에서 부드럽게 올라오며 나타나는 래퍼.
///
/// [animate]가 false이면 컨트롤러를 만들지 않고 자식을 그대로 반환한다.
class AnimatedMessageEntry extends StatefulWidget {
  final bool animate;
  final VoidCallback? onAnimationStarted;
  final Widget child;

  const AnimatedMessageEntry({
    super.key,
    required this.animate,
    this.onAnimationStarted,
    required this.child,
  });

  @override
  State<AnimatedMessageEntry> createState() => _AnimatedMessageEntryState();
}

class _AnimatedMessageEntryState extends State<AnimatedMessageEntry>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;
  bool _started = false;

  void _ensureController() {
    _controller ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
    );
  }

  @override
  void initState() {
    super.initState();
    if (widget.animate) {
      _ensureController();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _maybeStart();
  }

  @override
  void didUpdateWidget(covariant AnimatedMessageEntry oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.animate && !_started) {
      _ensureController();
      _maybeStart();
    }
  }

  void _maybeStart() {
    if (!widget.animate || _started) return;
    _started = true;
    widget.onAnimationStarted?.call();
    final controller = _controller!;
    if (MediaQuery.disableAnimationsOf(context)) {
      controller.value = 1.0;
    } else {
      controller.forward();
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (controller == null) {
      return widget.child;
    }

    return AnimatedBuilder(
      animation: controller,
      child: widget.child,
      builder: (context, child) {
        final t = Curves.easeOutCubic.transform(controller.value);
        final opacity = Curves.easeOut.transform(controller.value).clamp(0.0, 1.0);
        final dy = 16.0 * (1.0 - t);
        final scale = 0.985 + 0.015 * t;
        return Opacity(
          opacity: opacity,
          child: Transform.translate(
            offset: Offset(0, dy),
            child: Transform.scale(
              scale: scale,
              alignment: Alignment.bottomCenter,
              child: child,
            ),
          ),
        );
      },
    );
  }
}
