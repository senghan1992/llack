/// 목록에 항목을 넣는 규칙.
///
/// 백엔드는 WebSocket 이벤트를 HTTP 응답보다 먼저 보낸다.
/// (POST /channels → emit_channel_created → 그 다음 HTTP 응답)
/// 그래서 같은 항목이 WS 경로와 REST 경로로 두 번 들어올 수 있고,
/// 어느 쪽이 이기느냐에 따라 화면에 1개가 아니라 2개로 보인다.
///
/// 두 경로가 **같은 규칙(아이디 기준 upsert)** 을 쓰면 순서와 상관없이
/// 목록에는 항상 1개만 남는다.
library;

/// [list] 에 [item] 을 넣는다.
/// 같은 id 가 이미 있으면 그 자리를 [item] 으로 교체하고,
/// 없으면 [prepend] 가 true 면 앞에, false 면 뒤에 넣는다.
///
/// [idOf] 로 항목의 id 를 얻는다. (Channel 은 id, Task 는 id, ScheduleEvent 는 id)
List<T> upsertById<T>(
  List<T> list,
  T item,
  String Function(T) idOf, {
  bool prepend = false,
}) {
  final id = idOf(item);
  final idx = list.indexWhere((element) => idOf(element) == id);
  if (idx != -1) {
    final next = List<T>.of(list);
    next[idx] = item;
    return next;
  }
  if (prepend) {
    return [item, ...list];
  }
  return [...list, item];
}
