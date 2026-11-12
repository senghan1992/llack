import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/services/api_service.dart';

class _FakeApi extends ApiService {
  final List<String> calls = [];
  List<Message> aroundResult = [];
  List<Message> afterResult = [];
  List<Message> latestResult = [];
  bool failAround = false;

  @override
  Future<(List<Message>, bool, bool)> getMessages(
    String channelId, {
    int limit = 50,
    String? before,
    String? after,
    String? around,
  }) async {
    calls.add('before=$before after=$after around=$around');
    if (around != null) {
      if (failAround) throw ApiException(404, 'not_found', 'message not found');
      return (aroundResult, true, true);
    }
    if (after != null) return (afterResult, false, false);
    return (latestResult, false, false);
  }
}

Message _msg(String id) => Message(
      id: id,
      channelId: 'c1',
      userId: 'u1',
      author: User(id: 'u1', email: 'a@a.co.kr', name: '홍길동'),
      body: id,
      createdAt: DateTime(2026, 1, 1),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('selectChannel(focusMessageId:) 는 around 으로 창을 열고 pending 을 세팅한다', () async {
    final api = _FakeApi();
    api.aroundResult = [_msg('m1'), _msg('m2'), _msg('m3')];
    final state = AppState(api: api);

    state.selectChannel('c1', focusMessageId: 'm2');
    await Future<void>.delayed(Duration.zero);

    expect(api.calls.single, contains('around=m2'));
    expect(state.pendingFocusMessageId, 'm2');
    expect(state.activeMessages.map((m) => m.id), ['m1', 'm2', 'm3']);
    expect(state.hasMoreNewerMessages, isTrue);
    expect(state.hasMoreActiveMessages, isTrue);
  });

  test('같은 채널이어도 focusMessageId 가 있으면 다시 연다', () async {
    final api = _FakeApi();
    api.aroundResult = [_msg('m1')];
    final state = AppState(api: api);
    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    api.calls.clear();

    state.selectChannel('c1', focusMessageId: 'm1');
    await Future<void>.delayed(Duration.zero);
    expect(api.calls.length, 1);
  });

  test('점프가 실패하면 사유를 남기고 최신 위치로 열린다', () async {
    final api = _FakeApi();
    api.failAround = true;
    api.latestResult = [_msg('new1'), _msg('new2')];
    final state = AppState(api: api);

    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    final ok = await state.loadMessagesAround('c1', 'gone');

    expect(ok, isFalse);
    expect(state.pendingFocusMessageId, isNull);
    expect(state.focusErrorMessage, contains('찾을 수 없습니다'));
    expect(state.activeMessages.map((m) => m.id), ['new1', 'new2']);
  });

  test('loadNewerMessages 는 최신 방향 결과를 뒤에 붙인다', () async {
    final api = _FakeApi();
    api.aroundResult = [_msg('m1'), _msg('m2')];
    api.afterResult = [_msg('m3'), _msg('m4')];
    final state = AppState(api: api);

    state.selectChannel('c1');
    await Future<void>.delayed(Duration.zero);
    await state.loadMessagesAround('c1', 'm1');
    await state.loadNewerMessages('c1');

    expect(state.activeMessages.map((m) => m.id), ['m1', 'm2', 'm3', 'm4']);
  });
}
