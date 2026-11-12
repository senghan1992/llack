/// 채널별 스크롤 위치를 기억한다.
///
/// 오프셋(px) 이 아니라 "최신 메시지로부터의 거리" 를 저장한다.
/// 그래야 대화방을 다시 열 때 그 사이에 새 메시지가 도착해도
/// 사용자가 보던 메시지가 화면에서 밀리지 않는다.
class ChatScrollMemory {
  ChatScrollMemory._();

  static final Map<String, double> _distanceFromBottom = {};

  static void save(String channelId, double distance) {
    _distanceFromBottom[channelId] = distance;
  }

  /// 저장된 거리가 없으면 0 (= 최신 구간) 이다.
  static double load(String channelId) => _distanceFromBottom[channelId] ?? 0;
}
