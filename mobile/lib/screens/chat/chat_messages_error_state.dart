import 'package:flutter/material.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';

/// 메시지를 불러오지 못했을 때의 안내.
///
/// (빈 상태와 구분해서 "다시 시도" 를 보여준다)
class ChatMessagesErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const ChatMessagesErrorState({
    super.key,
    required this.message,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 32, color: LlackColors.muted),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: onRetry,
              child: const Text('다시 시도'),
            ),
          ],
        ),
      ),
    );
  }
}
