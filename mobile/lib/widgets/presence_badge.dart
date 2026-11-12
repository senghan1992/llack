import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/llack_colors.dart';

class PresenceBadge extends StatelessWidget {
  final Presence presence;
  final double size;
  final bool showLabel;

  const PresenceBadge({
    super.key,
    required this.presence,
    this.size = 10,
    this.showLabel = false,
  });

  static Color colorForPresence(Presence presence) {
    switch (presence) {
      case Presence.online:
        return LlackColors.presenceOnline;
      case Presence.busy:
        return LlackColors.presenceBusy;
      case Presence.dnd:
        return LlackColors.presenceDnd;
      case Presence.away:
        return LlackColors.presenceAway;
      case Presence.brb:
        return LlackColors.presenceBrb;
      case Presence.offline:
        return LlackColors.presenceOffline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = colorForPresence(presence);

    final dot = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(
          color: LlackColors.paper,
          width: 1.5,
        ),
      ),
    );

    if (!showLabel) {
      // 색만 있는 점은 스크린리더에 의미가 없으므로 상태 이름을 읽어준다.
      return Semantics(label: presence.label, child: dot);
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        dot,
        const SizedBox(width: 5),
        Text(
          presence.label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
        ),
      ],
    );
  }
}
