import 'package:flutter/material.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_typography.dart';

/// 현재 입력 중인 사용자 이름 목록을 한국어 상태 문구로 바꾼다.
String formatTypingUsers(List<String> names) {
  if (names.isEmpty) return '';
  if (names.length == 1) return '${names[0]}님이 입력 중입니다';
  if (names.length == 2) return '${names[0]}, ${names[1]}님이 입력 중입니다';
  return '${names[0]}, ${names[1]} 외 ${names.length - 2}명이 입력 중입니다';
}

/// 채팅 입력창 바로 아래에 표시되는 실시간 타이핑 표시줄.
///
/// [reserveSpace]가 true이면 아무도 입력하지 않을 때도 고정 높이를 유지해
/// 입력창과 전송 버튼이 위아래로 들썩이지 않게 한다.
class TypingIndicator extends StatelessWidget {
  final List<String> typingUsers;
  final bool reserveSpace;

  const TypingIndicator({
    super.key,
    required this.typingUsers,
    this.reserveSpace = false,
  });

  @override
  Widget build(BuildContext context) {
    final active = typingUsers.isNotEmpty;
    if (!active && !reserveSpace) {
      return const SizedBox.shrink();
    }

    final label = formatTypingUsers(typingUsers);
    final disableAnimations = MediaQuery.disableAnimationsOf(context);
    final duration = disableAnimations ? Duration.zero : const Duration(milliseconds: 180);

    return SizedBox(
      height: 22,
      width: double.infinity,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Semantics(
          liveRegion: true,
          label: active ? label : '',
          child: AnimatedOpacity(
            opacity: active ? 1 : 0,
            duration: duration,
            curve: Curves.easeOut,
            child: AnimatedSlide(
              offset: active ? Offset.zero : const Offset(0, 0.25),
              duration: duration,
              curve: Curves.easeOutCubic,
              child: active
                  ? Row(
                      children: [
                        const _TypingDots(),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: LlackTypography.caption.copyWith(
                              color: LlackColors.muted,
                            ),
                          ),
                        ),
                      ],
                    )
                  : const SizedBox.shrink(),
            ),
          ),
        ),
      ),
    );
  }
}

class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final disableAnimations = MediaQuery.disableAnimationsOf(context);
    if (disableAnimations) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < 3; i++) ...[
            if (i > 0) const SizedBox(width: 3),
            Container(
              width: 4,
              height: 4,
              decoration: BoxDecoration(
                color: LlackColors.accent,
                shape: BoxShape.circle,
              ),
            ),
          ],
        ],
      );
    }

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (index) {
            final phase = (_controller.value - index * 0.16) % 1.0;
            final pulse = phase < 0.45 ? (1.0 - (phase / 0.45 - 0.5).abs() * 2.0) : 0.0;
            final bounce = Curves.easeInOut.transform(pulse.clamp(0.0, 1.0));
            return Padding(
              padding: EdgeInsets.only(left: index == 0 ? 0 : 3),
              child: Transform.translate(
                offset: Offset(0, -2.5 * bounce),
                child: Opacity(
                  opacity: 0.35 + 0.65 * bounce,
                  child: Container(
                    width: 4,
                    height: 4,
                    decoration: BoxDecoration(
                      color: LlackColors.accent,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }
}
