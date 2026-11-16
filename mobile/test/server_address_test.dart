import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/services/api_service.dart';

void main() {
  group('서버 주소', () {
    test('앱은 항상 하나의 주소만 말한다 — 빌드 때 정한 값', () {
      // 배포하면 주소가 고정됩니다. 사용자 입력으로 바뀌지 않습니다.
      final url = ApiService.getDefaultBaseUrl();
      expect(url, isNotEmpty);
      expect(url.startsWith('http://') || url.startsWith('https://'), isTrue);
    });

    test('주소의 끝에 슬래시가 남지 않는다', () {
      // 빌드 값에 뒤 슬래시가 붙어 있어도 이중 슬래시가 생기지 않아야 합니다.
      expect(ApiService.getDefaultBaseUrl().endsWith('/'), isFalse);
    });

    test('API 경로는 그 주소 뒤에 붙는다', () {
      final service = ApiService();
      expect(service.apiEndpoint, '${service.baseUrl}/api/v1');
      expect(service.apiEndpoint.contains('//api'), isFalse);
    });
  });
}
