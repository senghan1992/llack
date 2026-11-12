import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../theme/llack_colors.dart';

/// "한 번이라도 실시간 연결에 성공했는지" 를 기억하는 공유 상태.
///
/// 셸의 배너와 채널 화면의 스트립이 따로 들면
/// "아직 연결 안 됨" vs "연결 끊김" 판정이 서로 달라질 수 있으므로 한 곳에서 관리한다.
final ValueNotifier<bool> _hasEverConnected = ValueNotifier<bool>(false);

/// 실시간 연결이 끊어진 상태인지 판정한다.
///
/// - 한 번이라도 연결된 적이 있으면 끊어졌다가 다시 연결 중 → 배너를 띄운다
/// - 오류 사유가 있으면(연결 실패) 배너를 띄운다
/// - 아직 연결된 적도 없고 오류도 없으면 "연결 중" 이므로 배너를 띄우지 않는다
bool isConnectionLost(AppState state) {
  if (state.isConnected) return false;
  final reason = state.connectionError;
  return reason != null || _hasEverConnected.value;
}

/// 앱바 아래에 붙일 연결 배너를 돌려준다.
/// 연결이 정상이면 null (앱바 아래에 빈 공간도 남지 않는다).
PreferredSizeWidget? connectionBannerBottom(AppState state) {
  return isConnectionLost(state) ? const ConnectionBannerStrip() : null;
}

/// 실시간 연결이 끊어졌을 때 보여주는 배너(셸용).
///
/// 상태바 inset 패딩을 포함한다. (셸의 body 맨 위에 놓이므로 상태바 영역을 직접 비워야 한다)
class ConnectionBanner extends StatelessWidget {
  const ConnectionBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (state.isConnected) {
      // 한 번이라도 연결된 적이 있으면 "끊어졌습니다" 라고 표시할 수 있다
      _hasEverConnected.value = true;
      return const SizedBox.shrink();
    }
    if (!isConnectionLost(state)) return const SizedBox.shrink();

    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        color: LlackColors.presenceBusy.withValues(alpha: 0.1),
        // 배너는 바깥 Scaffold 의 body 맨 위에 놓이므로, 상태바 inset 를 직접 더해줘야
        // 시계/신호 아이콘 위로 글자가 겹치지 않는다. (각 탭의 앱바가 inset 를 쓰는 것과 별개)
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: MediaQuery.of(context).padding.top + 8,
          bottom: 8,
        ),
        child: _BannerContent(reason: state.connectionError),
      ),
    );
  }
}

/// 앱바 아래에 얹는 얇은 스트립(채널 화면·스레드 화면용).
///
/// 상태바 inset 패딩이 없다. (앱바 아래에 붙으므로 앱바가 이미 상태바를 처리한다)
class ConnectionBannerStrip extends StatelessWidget implements PreferredSizeWidget {
  /// 스트립 높이 (아이콘 + 한 줄 문구)
  static const double height = 30;

  const ConnectionBannerStrip({super.key});

  @override
  Size get preferredSize => const Size.fromHeight(height);

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (state.isConnected) {
      _hasEverConnected.value = true;
      return const SizedBox.shrink();
    }
    if (!isConnectionLost(state)) return const SizedBox.shrink();

    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        color: LlackColors.presenceBusy.withValues(alpha: 0.1),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: _BannerContent(reason: state.connectionError, singleLine: true),
      ),
    );
  }
}

/// 배너 문구를 한 문장으로 정리한다.
///
/// ('실시간 연결이 끊어졌습니다: 연결이 끊어졌습니다.' 처럼 접미어가 겹치면
///  한 문장만 보여준다)
String _bannerMessage(String? error) {
  final text = (error ?? '').trim();
  if (text.isEmpty) {
    return '실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다.';
  }
  // 세션 만료는 그 자체로 한 문장이다.
  if (text.startsWith('세션이 만료')) {
    return text;
  }
  // 같은 말이 두 번 붙으면 한 번만 보여준다.
  if (text == '연결이 끊어졌습니다.' || text.contains('실시간 연결이 끊어졌습니다')) {
    return '실시간 연결이 끊어졌습니다. 다시 연결하는 중입니다.';
  }
  return '실시간 연결이 끊어졌습니다. $text';
}

/// 배너/스트립 공통 내용 (아이콘 + 문구)
class _BannerContent extends StatelessWidget {
  final String? reason;

  /// 스트립은 한 줄로 고정하고(넘치면 말줄임), 셸 배너는 기존처럼 줄바꿈을 허용한다.
  final bool singleLine;

  const _BannerContent({required this.reason, this.singleLine = false});

  @override
  Widget build(BuildContext context) {
    // 필드는 null 승격이 안 되므로 지역 변수로 복사해서 쓴다
    final error = reason;
    final message = _bannerMessage(error);

    return Row(
      children: [
        const Icon(Icons.cloud_off_outlined, size: 16, color: LlackColors.presenceBusy),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            message,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: LlackColors.presenceBusy),
            maxLines: singleLine ? 1 : null,
            overflow: singleLine ? TextOverflow.ellipsis : null,
          ),
        ),
      ],
    );
  }
}
