import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/screens/settings/server_settings_dialog.dart';

void main() {
  group('서버 주소 검증', () {
    test('빈 값은 오류', () {
      expect(validateServerUrl(''), isNotNull);
      expect(validateServerUrl('   '), isNotNull);
    });

    test('스킴이 없으면 오류', () {
      expect(validateServerUrl('192.168.0.10:8000'), isNotNull);
      expect(validateServerUrl('llack.example.com'), isNotNull);
    });

    test('공백이 포함되면 오류', () {
      expect(validateServerUrl('http://192.168.0.10 :8000'), isNotNull);
    });

    test('http/https 주소는 통과', () {
      expect(validateServerUrl('http://192.168.0.10:8000'), isNull);
      expect(validateServerUrl('https://llack.example.com'), isNull);
      expect(validateServerUrl('  http://10.0.2.2:8000  '), isNull);
    });
  });
}
