import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';

/// 메시지 목록의 날짜 구분 헤더.
///
/// (말풍선과 같은 시각 규약: 얇은 구분선 + 라운드 캡슐)
class MessageDateHeader extends StatelessWidget {
  final DateTime date;

  const MessageDateHeader({super.key, required this.date});

  String _format() {
    return DateFormat('yyyy년 M월 d일 EEEE', 'ko_KR').format(date.toLocal());
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
      child: Row(
        children: [
          const Expanded(child: Divider()),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color: LlackColors.surfaceWell,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: LlackColors.rule),
              ),
              child: Text(
                _format(),
                style: LlackTypography.caption.copyWith(
                  fontWeight: FontWeight.w500,
                  color: LlackColors.muted,
                ),
              ),
            ),
          ),
          const Expanded(child: Divider()),
        ],
      ),
    );
  }
}
