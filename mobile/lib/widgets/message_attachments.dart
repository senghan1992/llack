import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/app_state.dart';
import '../theme/llack_colors.dart';
import '../theme/llack_typography.dart';

/// 메시지 첨부 파일 렌더링 (이미지 썸네일 / 파일 칩).
///
/// 말풍선(message_bubble.dart)의 파일이 700줄을 넘어 분리했다.
/// 말풍선에 들어있을 때와 **동작·속성·색상·애니메이션이 동일**하도록 옮겨 담았다.
class MessageAttachments extends StatelessWidget {
  final List<FileRef> attachments;
  final bool isMine;

  /// 첨부 파일의 상대경로를 실제 이미지 URL 로 바꿔주는 함수.
  /// (서버가 상대경로를 주기 때문에 절대 URL 로 바꿔야 Image.network 가 동작한다)
  final String Function(String url)? fileUrlResolver;

  const MessageAttachments({
    super.key,
    required this.attachments,
    required this.isMine,
    this.fileUrlResolver,
  });

  String _resolveUrl(String url) => fileUrlResolver?.call(url) ?? url;

  String _formatSize(int bytes) {
    if (bytes <= 0) return '';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  /// 첨부 파일 요청에 필요한 인증 헤더.
  /// `GET /api/v1/files/{id}` 는 인증이 필요하므로 헤더 없이 부르면 401 이 되고,
  /// 그 결과 이미지 썸네일이 절대 렌더링되지 않았다.
  /// 토큰이 없으면(로그인 전 등) null 을 돌려 파일 칩으로 fallback 한다.
  Map<String, String>? _authHeaders(BuildContext context) {
    String? token;
    try {
      token = context.read<AppState>().api.accessToken;
    } catch (_) {
      token = null;
    }
    if (token == null || token.isEmpty) return null;
    return {'Authorization': 'Bearer $token'};
  }

  @override
  Widget build(BuildContext context) {
    if (attachments.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Column(
        crossAxisAlignment: isMine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: attachments.map((f) => _buildAttachment(context, f)).toList(),
      ),
    );
  }

  Widget _buildAttachment(BuildContext context, FileRef file) {
    final isImage = file.mime.startsWith('image/');
    final url = _resolveUrl(file.url);

    if (isImage && url.isNotEmpty) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: _buildImageAttachment(context, file, url),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: _buildFileChip(context, file),
    );
  }

  /// 이미지 썸네일. 인증 헤더가 없으면 열기가 불가능하므로 파일 칩으로 fallback 한다.
  Widget _buildImageAttachment(BuildContext context, FileRef file, String url) {
    final headers = _authHeaders(context);
    if (headers == null) return _buildFileChip(context, file);

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: () => _openImageViewer(context, file, url, headers),
        child: Image.network(
          url,
          headers: headers,
          width: 160,
          height: 120,
          fit: BoxFit.cover,
          loadingBuilder: (context, child, progress) {
            // 로딩 중에도 같은 크기의 자리표시자를 그려 레이아웃이 흔들리지 않게 한다.
            if (progress == null) return child;
            return Container(
              width: 160,
              height: 120,
              color: LlackColors.surfaceWell,
              alignment: Alignment.center,
              child: SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: LlackColors.accent),
              ),
            );
          },
          errorBuilder: (context, error, stackTrace) => _buildFileChip(context, file),
        ),
      ),
    );
  }

  /// 이미지를 크게 보는 전체 화면 다이얼로그.
  void _openImageViewer(
    BuildContext context,
    FileRef file,
    String url,
    Map<String, String> headers,
  ) {
    showDialog(
      context: context,
      barrierColor: Colors.black87,
      builder: (ctx) {
        return Dialog.fullscreen(
          backgroundColor: Colors.black,
          child: Stack(
            children: [
              Positioned.fill(
                child: InteractiveViewer(
                  maxScale: 4,
                  child: Center(
                    child: Image.network(
                      url,
                      headers: headers,
                      fit: BoxFit.contain,
                      loadingBuilder: (context, child, progress) {
                        if (progress == null) return child;
                        return const Center(
                          child: SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          ),
                        );
                      },
                      errorBuilder: (context, error, stackTrace) => Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.broken_image_outlined, size: 40, color: Colors.white70),
                            const SizedBox(height: 12),
                            Text(
                              '이미지를 불러오지 못했습니다',
                              style: LlackTypography.bodySmall.copyWith(color: Colors.white70),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              file.name,
                              style: LlackTypography.caption.copyWith(color: Colors.white54),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              Positioned(
                top: 8,
                right: 8,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  tooltip: '닫기',
                  onPressed: () => Navigator.pop(ctx),
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 24,
                child: Text(
                  file.name,
                  textAlign: TextAlign.center,
                  style: LlackTypography.caption.copyWith(color: Colors.white70),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFileChip(BuildContext context, FileRef file) {
    final size = _formatSize(file.size);
    return InkWell(
      // 파일 열기는 데스크톱 앱만 지원한다. 아무 반응 없는 탭 대신 이유를 알려준다.
      onTap: () {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            const SnackBar(
              content: Text('이 파일은 데스크톱 앱에서 확인할 수 있습니다'),
            ),
          );
      },
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: LlackColors.surfaceWell,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: LlackColors.rule),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
             Icon(Icons.insert_drive_file_outlined, size: 16, color: LlackColors.accent),
            const SizedBox(width: 6),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 150),
              child: Text(
                file.name,
                style: LlackTypography.caption.copyWith(color: LlackColors.ink),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (size.isNotEmpty) ...[
              const SizedBox(width: 6),
              Text(size, style: LlackTypography.caption),
            ],
          ],
        ),
      ),
    );
  }
}
