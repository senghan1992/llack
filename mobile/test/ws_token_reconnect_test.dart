import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/services/ws_service.dart';

/// 액세스 토큰이 만료되어도 실시간이 복구되어야 한다 (§9-47).
///
/// - 토큰을 연결 시점에 조회한다
/// - 4401(인증 실패)을 구분해 토큰 갱신을 한 번만 시도한다
/// - 즉시 죽는 연결은 백오프를 늘린다 (1초 루프 방지)

/// 가짜 WS 연결.
class _FakeConnection implements WsConnection {
  final StreamController<dynamic> _controller = StreamController<dynamic>();
  final Completer<void> _ready = Completer<void>();
  final List<String> sent = [];
  int? closeCodeValue;

  @override
  Future<void> get ready => _ready.future;

  @override
  Stream<dynamic> get stream => _controller.stream;

  @override
  int? get closeCode => closeCodeValue;

  @override
  void add(String data) => sent.add(data);

  @override
  void close() {
    if (!_controller.isClosed) _controller.close();
  }

  /// 연결 성립.
  void completeReady() {
    if (!_ready.isCompleted) _ready.complete();
  }

  /// 서버가 이 코드로 닫는다. (4401 = 인증 실패)
  void serverClose(int code) {
    closeCodeValue = code;
    if (!_controller.isClosed) _controller.close();
  }
}

void main() {
  late WsService ws;
  late List<_FakeConnection> connections;
  late List<String> usedTokens;

  setUp(() {
    ws = WsService();
    connections = [];
    usedTokens = [];
    ws.connectionFactory = (uri) {
      usedTokens.add(uri.queryParameters['token'] ?? '');
      final connection = _FakeConnection();
      connections.add(connection);
      return connection;
    };
  });

  tearDown(() {
    ws.disconnect();
  });

  testWidgets('토큰이 갱신되면 다음 연결은 새 토큰으로 간다', (tester) async {
    var token = 'token-1';
    ws.connect(baseUrl: 'http://127.0.0.1:8000', tokenProvider: () => token);
    await tester.pump();

    expect(usedTokens, ['token-1']);

    // 토큰이 갱신되었다.
    token = 'token-2';
    // 연결이 끊기면 다시 붙는다. (이때 새 토큰을 읽어야 한다)
    connections.last.serverClose(1000);
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));

    expect(usedTokens, ['token-1', 'token-2']);
    ws.disconnect();
  });

  testWidgets('4401 이면 토큰 갱신을 한 번만 시도하고 새 토큰으로 재연결한다', (tester) async {
    var token = 'expired';
    var refreshCalls = 0;
    ws.authRefresher = () async {
      refreshCalls++;
      token = 'fresh';
      return true;
    };
    ws.connect(baseUrl: 'http://127.0.0.1:8000', tokenProvider: () => token);
    await tester.pump();
    connections.last.completeReady();
    await tester.pump();

    // 만료된 토큰으로 붙었다가 4401 로 닫혔다.
    connections.last.serverClose(4401);
    await tester.pump();

    expect(refreshCalls, 1);
    expect(usedTokens, ['expired', 'fresh']);

    // 다시 4401 로 닫혀도 또 갱신하지 않는다 (무한 루프 방지).
    connections.last.serverClose(4401);
    await tester.pump();
    expect(refreshCalls, 1);
    expect(ws.isAuthExpired, isTrue);
    expect(ws.lastError, WsService.sessionExpiredMessage);
    ws.disconnect();
  });

  testWidgets('토큰 갱신까지 실패하면 재시도하지 않고 세션 만료 상태가 된다', (tester) async {
    var refreshCalls = 0;
    ws.authRefresher = () async {
      refreshCalls++;
      return false;
    };
    ws.connect(baseUrl: 'http://127.0.0.1:8000', tokenProvider: () => 'expired');
    await tester.pump();
    connections.last.completeReady();
    await tester.pump();

    connections.last.serverClose(4401);
    await tester.pump();

    expect(refreshCalls, 1);
    expect(ws.isAuthExpired, isTrue);
    expect(ws.lastError, WsService.sessionExpiredMessage);

    // 재시도하지 않는다.
    await tester.pump(const Duration(seconds: 60));
    expect(usedTokens.length, 1);
    ws.disconnect();
  });

  testWidgets('즉시 죽는 연결은 백오프가 커진다 (1초 루프가 없다)', (tester) async {
    ws.connect(baseUrl: 'http://127.0.0.1:8000', tokenProvider: () => 't');
    await tester.pump();
    connections.last.completeReady();
    await tester.pump();

    // 붙자마자 죽었다.
    connections.last.serverClose(1000);
    await tester.pump();

    // 1초 뒤에는 붙지 않는다 (최소 간격 5초).
    await tester.pump(const Duration(seconds: 1));
    expect(usedTokens.length, 1);

    // 5초 뒤에 다시 붙는다.
    await tester.pump(const Duration(seconds: 4));
    expect(usedTokens.length, 2);

    // 장애 30초 안에 연결 시도는 5회 이하.
    await tester.pump(const Duration(seconds: 25));
    expect(usedTokens.length, lessThanOrEqualTo(5));
    ws.disconnect();
  });

  testWidgets('오래 유지된 연결은 다음 장애 때 백오프를 리셋한다', (tester) async {
    ws.connect(baseUrl: 'http://127.0.0.1:8000', tokenProvider: () => 't');
    await tester.pump();

    // 여러 번 즉시 죽어서 attempt 를 키운다.
    for (var i = 0; i < 4; i++) {
      connections.last.completeReady();
      await tester.pump();
      connections.last.serverClose(1000);
      await tester.pump();
      await tester.pump(const Duration(seconds: 40));
    }

    // 이번 연결은 10초 이상 살아 있다 → 백오프 리셋.
    connections.last.completeReady();
    await tester.pump();
    await tester.pump(const Duration(seconds: 11));
    connections.last.serverClose(1000);
    await tester.pump();

    final before = usedTokens.length;
    // 리셋됐다면 5초 뒤에 다시 붙는다.
    await tester.pump(const Duration(seconds: 5));
    expect(usedTokens.length, before + 1);
    ws.disconnect();
  });
}
