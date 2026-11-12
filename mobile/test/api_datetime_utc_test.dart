import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:llack_mobile/services/api_service.dart';

/// 실제 네트워크 대신 가짜 클라이언트로 요청 본문/쿼리를 확인하기 위한 서비스.
class _RecordingApiService extends ApiService {
  @override
  String get apiEndpoint => 'http://127.0.0.1:8000/api/v1';
}

Map<String, dynamic> _eventJson() => {
  'id': 'evt1',
  'workspace_id': 'w1',
  'title': 'r8event',
  'description': '',
  'location': '',
  'starts_at': DateTime.utc(2026, 11, 9, 1).toIso8601String(),
  'ends_at': DateTime.utc(2026, 11, 9, 2).toIso8601String(),
  'all_day': false,
  'is_private': false,
  'created_by': 'u1',
  'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'attendees': <Map<String, dynamic>>[],
};

Map<String, dynamic> _taskJson() => {
  'id': 'tsk1',
  'project_id': 'prj1',
  'title': 'r8task',
  'description': '',
  'status': 'todo',
  'created_by': 'u1',
  'position': 0,
  'created_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'updated_at': DateTime.utc(2026, 1, 1).toIso8601String(),
  'comments': <Map<String, dynamic>>[],
  'comment_count': 0,
};

/// 요청을 가로채어 본문/쿼리를 기록하는 가짜 클라이언트.
class _Recorder {
  Map<String, dynamic>? body;
  String? path;

  http.Client client() => MockClient((req) async {
    path = req.url.toString();
    body = req.body.isEmpty ? null : jsonDecode(req.body) as Map<String, dynamic>;
    if (req.url.path.endsWith('/events') && req.method == 'GET') {
      return http.Response(jsonEncode([_eventJson()]), 200);
    }
    if (req.url.path.contains('/tasks') && req.method == 'GET') {
      return http.Response(jsonEncode([_taskJson()]), 200);
    }
    if (req.url.path.contains('/events')) {
      return http.Response(jsonEncode(_eventJson()), 200);
    }
    return http.Response(jsonEncode(_taskJson()), 200);
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('나가는 날짜·시간은 진짜 UTC 인스턴트다 (§9-25)', () {
    test('createEvent 의 starts_at/ends_at 는 Z 로 끝난다', () async {
      final rec = _Recorder();
      final startsAt = DateTime.utc(2026, 11, 9, 1);
      final endsAt = DateTime.utc(2026, 11, 9, 2);

      await http.runWithClient(() async {
        await _RecordingApiService().createEvent(
          workspaceId: 'w1',
          title: 'r8event',
          startsAt: startsAt,
          endsAt: endsAt,
        );
      }, rec.client);

      expect(rec.body!['starts_at'], '2026-11-09T01:00:00.000Z');
      expect(rec.body!['ends_at'], '2026-11-09T02:00:00.000Z');
      expect(rec.body!['starts_at'].toString().endsWith('Z'), isTrue);
    });

    test('updateEvent 의 starts_at/ends_at 는 Z 로 끝난다', () async {
      final rec = _Recorder();

      await http.runWithClient(() async {
        await _RecordingApiService().updateEvent(
          eventId: 'evt1',
          startsAt: DateTime.utc(2026, 11, 9, 1),
          endsAt: DateTime.utc(2026, 11, 9, 2),
        );
      }, rec.client);

      expect(rec.body!['starts_at'].toString().endsWith('Z'), isTrue);
      expect(rec.body!['ends_at'].toString().endsWith('Z'), isTrue);
    });

    test('로컬 벽시계로 만든 시간도 같은 instant 의 UTC 로 나간다', () async {
      final rec = _Recorder();
      // 로컬 10:00 (어느 시간대든) → 같은 instant 의 UTC 문자열
      final local = DateTime(2026, 11, 9, 10, 0);

      await http.runWithClient(() async {
        await _RecordingApiService().createEvent(
          workspaceId: 'w1',
          title: 'r8event',
          startsAt: local,
          endsAt: local.add(const Duration(hours: 1)),
        );
      }, rec.client);

      expect(rec.body!['starts_at'], local.toUtc().toIso8601String());
      expect(rec.body!['starts_at'].toString().endsWith('Z'), isTrue);
    });

    test('createTask 의 due_at 는 Z 로 끝난다', () async {
      final rec = _Recorder();

      await http.runWithClient(() async {
        await _RecordingApiService().createTask(
          projectId: 'prj1',
          title: 'r8task',
          dueAt: DateTime.utc(2026, 11, 9, 1),
        );
      }, rec.client);

      expect(rec.body!['due_at'].toString().endsWith('Z'), isTrue);
      expect(rec.body!['due_at'], '2026-11-09T01:00:00.000Z');
    });

    test('updateTask 의 due_at 는 Z 로 끝난다', () async {
      final rec = _Recorder();

      await http.runWithClient(() async {
        await _RecordingApiService().updateTask(
          'tsk1',
          dueAt: DateTime.utc(2026, 11, 9, 1),
        );
      }, rec.client);

      expect(rec.body!['due_at'].toString().endsWith('Z'), isTrue);
      expect(rec.body!['due_at'], '2026-11-09T01:00:00.000Z');
    });

    test('getEvents 조회 범위(from/to)도 UTC 로 나간다', () async {
      final rec = _Recorder();
      final from = DateTime(2026, 11, 9, 0);
      final to = DateTime(2026, 11, 10, 0);

      await http.runWithClient(() async {
        await _RecordingApiService().getEvents('w1', from: from, to: to);
      }, rec.client);

      expect(rec.path, contains('from=${from.toUtc().toIso8601String()}'));
      expect(rec.path, contains('to=${to.toUtc().toIso8601String()}'));
      expect(rec.path, contains('Z'));
    });
  });
}
