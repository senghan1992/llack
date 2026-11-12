// ignore_for_file: use_null_aware_elements
import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

typedef WsEventHandler = void Function(Map<String, dynamic> event);

/// 연결 상태 변화 통지 (연결됨 / 끊김 + 사유)
typedef WsStatusCallback = void Function(bool connected, String? error);

/// 토큰을 "복사"하지 말고, 연결할 때마다 최신 토큰을 물어본다.
typedef WsTokenProvider = String? Function();

/// 인증 실패(4401) 시 토큰을 갱신해 주는 훅.
/// 성공하면 true 를 돌려주고, 그 새 토큰으로 다시 붙는다.
typedef WsAuthRefresher = Future<bool> Function();

/// WS 연결 하나를 감싼다.
///
/// (구현은 내부에 두고, 테스트에서는 가짜를 끼워 넣는다)
abstract class WsConnection {
  /// 연결이 성립하면 완료한다. (실패하면 오류로 완료한다)
  Future<void> get ready;

  /// 서버가 보내는 데이터.
  Stream<dynamic> get stream;

  /// 서버가 보낸 종료 코드. (닫히지 않았거나 코드 없으면 null)
  int? get closeCode;

  /// 데이터를 보낸다.
  void add(String data);

  /// 연결을 닫는다.
  void close();
}

/// 실제 소켓 연결.
class _SocketConnection implements WsConnection {
  _SocketConnection(Uri uri) : _channel = WebSocketChannel.connect(uri);

  final WebSocketChannel _channel;

  @override
  Future<void> get ready => _channel.ready;

  @override
  Stream<dynamic> get stream => _channel.stream;

  @override
  int? get closeCode => _channel.closeCode;

  @override
  void add(String data) => _channel.sink.add(data);

  @override
  void close() => _channel.sink.close();
}

class WsService {
  WsConnection? _channel;
  Timer? _reconnectTimer;
  Timer? _pingTimer;

  /// 연결이 이 시간 이상 유지됐는지 확인하는 타이머.
  /// (즉시 죽는 연결은 백오프를 리셋하지 않는다)
  Timer? _healthyTimer;

  int _attempt = 0;

  /// 현재 연결에 실제로 쓴 토큰. (다음 연결에서 비교한다)
  String? _connectedToken;

  /// 토큰을 조회하는 훅. (연결 시점에 호출된다)
  WsTokenProvider? _tokenProvider;

  String _baseUrl = 'http://127.0.0.1:8000';
  bool _closed = false;

  /// 같은 오류가 여러 경로(ready 실패 / 스트림 오류 / onDone)에서 들어올 수 있어
  /// 재접속 스케줄이 중복되지 않게 막는다.
  bool _reconnectScheduled = false;

  /// 이 장애에서 이미 토큰 갱신을 시도했는지. (한 번만)
  bool _authRefreshTried = false;

  /// 인증 만료(4401)로 세션이 끝났는지.
  bool _isAuthExpired = false;

  final List<WsEventHandler> _listeners = [];
  bool _isConnected = false;
  String? _lastError;

  /// AppState 가 연결 상태를 UI 로 내보내기 위해 구독한다.
  WsStatusCallback? onStatusChanged;

  /// 인증 실패(4401) 때 토큰 갱신을 시도하는 훅. (AppState 가 넣어준다)
  WsAuthRefresher? authRefresher;

  /// 연결을 만드는 팩토리. (테스트에서 가짜를 끼워 넣는다)
  @visibleForTesting
  WsConnection Function(Uri uri)? connectionFactory;

  /// 서버가 인증 실패로 닫을 때의 코드.
  static const int authFailedCloseCode = 4401;

  /// 세션 만료 안내 문구.
  static const String sessionExpiredMessage = '세션이 만료되었습니다. 다시 로그인해주세요.';

  /// 이 시간 이상 유지된 연결만 "정상" 으로 보고 백오프를 리셋한다.
  static const Duration healthyConnectionThreshold = Duration(seconds: 10);

  /// 재접속 최소 간격. (초당 1회 루프 방지)
  static const Duration minReconnectDelay = Duration(seconds: 5);

  /// 재접속 최대 간격.
  static const Duration maxReconnectDelay = Duration(seconds: 30);

  bool get isConnected => _isConnected;
  bool get isAuthExpired => _isAuthExpired;
  String? get lastError => _lastError;

  void addListener(WsEventHandler handler) {
    _listeners.add(handler);
  }

  void removeListener(WsEventHandler handler) {
    _listeners.remove(handler);
  }

  /// 앱(또는 사용자 요청)으로 직접 연결을 시작한다.
  ///
  /// 토큰은 **복사하지 않는다.** 연결할 때마다 [tokenProvider] 로 최신 토큰을 물어본다.
  /// (토큰이 갱신돼도 다음 연결은 새 토큰으로 간다)
  void connect({required String baseUrl, required WsTokenProvider tokenProvider}) {
    _tokenProvider = tokenProvider;
    final token = tokenProvider.call();
    if (token == null || token.isEmpty) {
      // 로그인 상태가 아니면 붙지 않는다.
      return;
    }
    _isAuthExpired = false;
    if (_baseUrl == baseUrl && token == _connectedToken && (_isConnected || _channel != null)) {
      // 같은 서버에 같은 토큰으로 이미 붙어 있다(또는 붙는 중이다).
      return;
    }
    _baseUrl = baseUrl;
    _closed = false;
    // 명시적인 연결 요청이므로 백오프를 초기화한다.
    _attempt = 0;
    _reconnectTimer?.cancel();
    _reconnectScheduled = false;
    _closeChannel();
    _open();
  }

  void _open() {
    if (_closed) return;
    // 이미 열려 있는(또는 여는 중인) 연결이 있으면 새로 열지 않는다.
    if (_channel != null) return;
    // 연결 **시점**의 토큰을 물어본다. (토큰이 갱신돼도 다음 연결은 새 토큰으로 간다)
    final token = _tokenProvider?.call();
    if (token == null || token.isEmpty) return;

    final isHttps = _baseUrl.startsWith('https://');
    final scheme = isHttps ? 'wss' : 'ws';
    final hostPort = _baseUrl
        .replaceFirst(RegExp(r'^https?://'), '')
        .replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.parse('$scheme://$hostPort/api/v1/ws?token=${Uri.encodeComponent(token)}');

    try {
      final connection = connectionFactory?.call(uri) ?? _SocketConnection(uri);
      _channel = connection;
      _connectedToken = token;
      _reconnectScheduled = false;

      connection.ready.then((_) {
        if (_closed || _channel != connection) return;
        _setStatus(true, null);
        _startPing();
        // **10초 이상 살아 있어야** 백오프를 리셋한다.
        // (붙었다가 1초 만에 죽어도 attempt 가 0 으로 돌아가면 1초 루프가 된다)
        _healthyTimer?.cancel();
        _healthyTimer = Timer(healthyConnectionThreshold, () {
          if (_closed || _channel != connection) return;
          _attempt = 0;
          _authRefreshTried = false;
        });
      }).catchError((Object error) {
        if (_closed || _channel != connection) return;
        debugPrint('[WS] connect failed: $error');
        _channel = null;
        _setStatus(false, '서버에 연결할 수 없습니다.');
        _scheduleReconnect();
      });

      connection.stream.listen(
        (data) {
          try {
            final parsed = jsonDecode(data as String);
            if (parsed is Map<String, dynamic>) {
              for (final listener in List.of(_listeners)) {
                listener(parsed);
              }
            }
          } catch (e) {
            debugPrint('[WS] parse error: $e');
          }
        },
        onError: (error) {
          debugPrint('[WS] error: $error');
          if (_closed || _channel != connection) return;
          _channel = null;
          _setStatus(false, '연결이 끊어졌습니다.');
          _scheduleReconnect();
        },
        onDone: () {
          final code = connection.closeCode;
          debugPrint('[WS] disconnected (code=$code)');
          if (_closed || _channel != connection) return;
          _channel = null;
          if (code == authFailedCloseCode) {
            // 인증 실패: 만료된 토큰이다.
            unawaited(_handleAuthFailed());
            return;
          }
          _setStatus(false, '연결이 끊어졌습니다.');
          _scheduleReconnect();
        },
        cancelOnError: true,
      );
    } catch (e) {
      debugPrint('[WS] connection failed: $e');
      _channel = null;
      _setStatus(false, '서버에 연결할 수 없습니다.');
      _scheduleReconnect();
    }
  }

  /// 인증 실패(4401): 토큰 갱신을 **한 번** 시도한다.
  Future<void> _handleAuthFailed() async {
    if (_authRefreshTried) {
      // 한 번 갱신했는데 또 실패했다 → 더 붙지 않는다.
      _isAuthExpired = true;
      _setStatus(false, sessionExpiredMessage);
      return;
    }
    _authRefreshTried = true;
    var renewed = false;
    final refresher = authRefresher;
    if (refresher != null) {
      try {
        renewed = await refresher();
      } catch (_) {
        renewed = false;
      }
    }
    if (!renewed) {
      // 리프레시 토큰까지 만료 → 재시도하지 않는다.
      _isAuthExpired = true;
      _setStatus(false, sessionExpiredMessage);
      return;
    }
    // 새 토큰으로 즉시 다시 붙는다. (1회)
    _setStatus(false, '연결이 끊어졌습니다.');
    _attempt = 0;
    _reconnectTimer?.cancel();
    _reconnectScheduled = false;
    _open();
  }

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 25), (_) {
      send({'type': 'ping'});
    });
  }

  void _scheduleReconnect() {
    _isConnected = false;
    _pingTimer?.cancel();
    _pingTimer = null;
    _healthyTimer?.cancel();
    _healthyTimer = null;

    if (_closed || _reconnectScheduled) return;
    _reconnectScheduled = true;

    // 5, 5, 5, 8, 16, 30, 30 ... 초 — 즉시 죽어도 attempt 를 줄이지 않는다.
    // (장애 30초 안에 연결 시도는 5회 이하)
    final delay = _reconnectDelay();
    _attempt++;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(delay, () {
      _reconnectScheduled = false;
      if (!_closed) _open();
    });
  }

  Duration _reconnectDelay() {
    final raw = _attempt < 5 ? (1 << _attempt) : maxReconnectDelay.inSeconds;
    final seconds = raw < minReconnectDelay.inSeconds ? minReconnectDelay.inSeconds : raw;
    return Duration(seconds: seconds);
  }

  void _setStatus(bool connected, String? error) {
    final changed = _isConnected != connected || _lastError != error;
    _isConnected = connected;
    _lastError = connected ? null : error;
    if (changed) {
      onStatusChanged?.call(connected, _lastError);
    }
  }

  void send(Map<String, dynamic> payload) {
    final connection = _channel;
    if (connection != null && _isConnected) {
      try {
        connection.add(jsonEncode(payload));
      } catch (e) {
        debugPrint('[WS] send error: $e');
      }
    }
  }

  void sendTyping(String channelId, {bool on = true}) {
    send({'type': 'typing', 'channel_id': channelId, 'on': on});
  }

  void sendRead(String channelId, {String? messageId}) {
    send({
      'type': 'read',
      'channel_id': channelId,
      if (messageId != null) 'message_id': messageId,
    });
  }

  void disconnect() {
    _closed = true;
    _pingTimer?.cancel();
    _pingTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _healthyTimer?.cancel();
    _healthyTimer = null;
    _closeChannel();
    _attempt = 0;
    _authRefreshTried = false;
    _isAuthExpired = false;
    _setStatus(false, null);
  }

  /// 현재 연결을 정리한다. (onDone 이 재접속을 예약하지 않도록 _channel 을 먼저 비운다)
  void _closeChannel() {
    final connection = _channel;
    _channel = null;
    try {
      connection?.close();
    } catch (e) {
      debugPrint('[WS] close error: $e');
    }
  }
}
