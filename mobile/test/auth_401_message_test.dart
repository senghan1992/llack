import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/services/api_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 401 의 뜻을 경로에 따라 구분해야 한다 (F-2).
///
/// - 로그인/회원가입 401 → "이메일 또는 비밀번호가 맞지 않습니다"
/// - 그 밖의 401 → 세션 만료 (로그인 화면에 있는 사용자에게
///   "비밀번호가 틀렸다" 라고 말하면 안 된다)

/// 항상 401 을 돌려주는 가짜 서버.
class _UnauthorizedServer {
  _UnauthorizedServer(this.status, this.body);

  final int status;
  final String body;
  final List<String> paths = [];
  HttpServer? _server;

  int get port => _server!.port;

  Future<void> start() async {
    SharedPreferences.setMockInitialValues({});
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server!.listen((request) async {
      paths.add(request.uri.path);
      // 본문을 먼저 읽어야 한다. (안 읽으면 dart:io 가 400 으로 응답한다)
      await utf8.decoder.bind(request).join();
      request.response.statusCode = status;
      request.response.headers.contentType = ContentType.json;
      request.response.write(body);
      await request.response.close();
    });
  }

  Future<void> stop() async {
    await _server?.close(force: true);
  }
}

/// 포트만 바꿀 수 있는 API.
class _TestApi extends ApiService {
  _TestApi(this.port);

  final int port;

  @override
  String get apiEndpoint => 'http://127.0.0.1:$port/api/v1';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // flutter_test 는 모든 HTTP 요청을 400 으로 막는다. (가짜 서버를 쓰려면 꺼야 한다)
  setUp(() {
    HttpOverrides.global = null;
  });

  const errorBody = '{"error":{"code":"unauthorized","message":"authentication required"}}';

  test('로그인 401 은 "비밀번호가 맞지 않습니다" 라고 말한다', () async {
    final server = _UnauthorizedServer(401, errorBody);
    await server.start();
    final api = _TestApi(server.port);

    try {
      await api.login('a@hanbit.co.kr', 'wrong-password');
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.status, 401);
      expect(e.message, '이메일 또는 비밀번호가 맞지 않습니다.');
    } finally {
      await server.stop();
    }
  });

  test('회원가입 401 도 "비밀번호가 맞지 않습니다" 라고 말한다', () async {
    final server = _UnauthorizedServer(401, errorBody);
    await server.start();
    final api = _TestApi(server.port);

    try {
      await api.signup(email: 'a@hanbit.co.kr', password: 'pw', name: '가', workspaceName: '한빛');
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.message, '이메일 또는 비밀번호가 맞지 않습니다.');
    } finally {
      await server.stop();
    }
  });

  test('그 밖의 엔드포인트 401 은 세션 만료로 말한다', () async {
    final server = _UnauthorizedServer(401, errorBody);
    await server.start();
    final api = _TestApi(server.port);

    try {
      await api.getMe();
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.status, 401);
      expect(e.message, '세션이 만료되었습니다. 다시 로그인해주세요.');
      expect(e.message.contains('비밀번호'), isFalse);
    } finally {
      await server.stop();
    }
  });

  test('서버가 세션 만료라고 말했으면 그 말을 쓴다', () async {
    final server = _UnauthorizedServer(
      401,
      '{"error":{"code":"unauthorized","message":"token has expired"}}',
    );
    await server.start();
    final api = _TestApi(server.port);

    try {
      await api.getMe();
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.message, 'token has expired');
    } finally {
      await server.stop();
    }
  });

  test('리프레시까지 실패하면 원래 요청을 다시 시도하지 않는다', () async {
    final server = _UnauthorizedServer(401, errorBody);
    await server.start();
    final api = _TestApi(server.port);
    // 리프레시 토큰이 있는 상태
    await api.setTokens('expired-access', 'refresh-token');

    try {
      await api.getMe();
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.status, 401);
      expect(e.message, '세션이 만료되었습니다. 다시 로그인해주세요.');
      // 원래 요청(/me)은 한 번만, 리프레시는 한 번만.
      expect(server.paths.where((p) => p.endsWith('/me')).length, 1);
      expect(server.paths.where((p) => p.endsWith('/auth/refresh')).length, 1);
      // 토큰은 지워졌다 (로그인 화면으로 유도된다).
      expect(api.accessToken, isNull);
    } finally {
      await server.stop();
    }
  });

  test('리프레시 토큰이 없으면 곧바로 세션 만료로 말한다', () async {
    final server = _UnauthorizedServer(401, errorBody);
    await server.start();
    final api = _TestApi(server.port);

    try {
      await api.getMe();
      fail('401 이면 예외가 나야 한다');
    } on ApiException catch (e) {
      expect(e.message, '세션이 만료되었습니다. 다시 로그인해주세요.');
      // 리프레시 요청 자체를 하지 않는다.
      expect(server.paths.where((p) => p.endsWith('/auth/refresh')), isEmpty);
    } finally {
      await server.stop();
    }
  });
}
