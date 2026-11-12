import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/llack_colors.dart';
import 'presence_badge.dart';

class LlackAvatar extends StatelessWidget {
  final String name;
  final String? avatarUrl;
  final String? avatarColor;
  final Presence? presence;
  final double size;
  final double fontSize;

  const LlackAvatar({
    super.key,
    required this.name,
    this.avatarUrl,
    this.avatarColor,
    this.presence,
    this.size = 36,
    this.fontSize = 14,
  });

  String _getInitials() {
    if (name.isEmpty) return '?';
    final trimmed = name.trim();
    if (trimmed.length <= 2) return trimmed;
    // Korean or English initial
    return trimmed.substring(0, 1).toUpperCase();
  }

  Color _resolveBgColor() {
    if (avatarColor != null && avatarColor!.isNotEmpty) {
      try {
        final hex = avatarColor!.replaceFirst('#', '');
        return Color(int.parse('FF$hex', radix: 16));
      } catch (_) {}
    }
    return LlackColors.avatarColorForName(name);
  }

  @override
  Widget build(BuildContext context) {
    final bg = _resolveBgColor();

    Widget avatarCore;
    if (avatarUrl != null && avatarUrl!.isNotEmpty) {
      avatarCore = ClipRRect(
        borderRadius: BorderRadius.circular(size / 2),
        child: Image.network(
          avatarUrl!,
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _fallback(bg),
        ),
      );
    } else {
      avatarCore = _fallback(bg);
    }

    if (presence == null) {
      return Semantics(label: name, image: true, child: avatarCore);
    }

    final badgeSize = size * 0.32;

    return Semantics(
      // 스크린리더가 "이름, 상태" 로 읽을 수 있게 한다.
      label: '$name, ${presence!.label}',
      image: true,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          avatarCore,
          Positioned(
            right: -1,
            bottom: -1,
            child: PresenceBadge(
              presence: presence!,
              size: badgeSize.clamp(8.0, 14.0),
            ),
          ),
        ],
      ),
    );
  }

  Widget _fallback(Color bg) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: bg,
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        _getInitials(),
        style: TextStyle(
          color: Colors.white,
          fontSize: fontSize,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.5,
        ),
      ),
    );
  }
}
