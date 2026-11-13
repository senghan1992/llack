import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/theme/llack_colors.dart';
import 'package:llack_mobile/widgets/message_markdown.dart';

/// span 목록을 평평하게 펴 준다. (중첩 span 을 다 찾게 한다)
List<TextSpan> _flatten(List<InlineSpan> spans) {
  final out = <TextSpan>[];

  void walk(InlineSpan span) {
    if (span is! TextSpan) return;
    out.add(span);
    for (final child in span.children ?? const <InlineSpan>[]) {
      walk(child);
    }
  }

  for (final span in spans) {
    walk(span);
  }
  return out;
}

/// 글자가 정확히 일치하는 span 을 찾는다.
TextSpan? _spanWithText(List<TextSpan> spans, String text) {
  for (final span in spans) {
    if (span.text == text) return span;
  }
  return null;
}

/// 화면에 그린 메시지의 recognizer 를 꺼낸다.
List<LinkTapRecognizer> _renderedRecognizers(WidgetTester tester) {
  final text = tester.widget<Text>(find.byType(Text));
  final root = text.textSpan;
  if (root == null) return const [];
  return linkRecognizersIn([root]);
}

/// 화면에 그린 메시지의 span 을 꺼낸다.
List<TextSpan> _renderedSpans(WidgetTester tester) {
  final text = tester.widget<Text>(find.byType(Text));
  final root = text.textSpan;
  return _flatten([?root]);
}

void main() {
  group('buildMessageSpans', () {
    test('**굵게** 는 굵은 글자로 승격된다', () {
      final spans = _flatten(buildMessageSpans('안녕 **굵게** 하세요'));

      final bold = _spanWithText(spans, '굵게');
      expect(bold, isNotNull);
      expect(bold!.style?.fontWeight, FontWeight.w700);
      // 앞뒤 글자는 그대로다
      expect(_spanWithText(spans, '안녕 '), isNotNull);
      expect(_spanWithText(spans, ' 하세요'), isNotNull);
    });

    test('*기울임* 은 기울어진 글자로 승격된다', () {
      final spans = _flatten(buildMessageSpans('이건 *기울임* 이다'));

      final italic = _spanWithText(spans, '기울임');
      expect(italic, isNotNull);
      expect(italic!.style?.fontStyle, FontStyle.italic);
    });

    test('~~취소선~~ 은 줄이 그어진다', () {
      final spans = _flatten(buildMessageSpans('~~취소선~~'));

      final strike = _spanWithText(spans, '취소선');
      expect(strike, isNotNull);
      expect(strike!.style?.decoration, TextDecoration.lineThrough);
    });

    test('`코드` 는 등폭 글자로 승격된다', () {
      final spans = _flatten(buildMessageSpans('실행: `flutter test`'));

      final code = _spanWithText(spans, 'flutter test');
      expect(code, isNotNull);
      expect(code!.style?.fontFamilyFallback, contains('monospace'));
    });

    test('https 링크는 recognizer 를 가진 span 이 된다', () {
      final spans = _flatten(buildMessageSpans('참고 https://example.com/docs'));

      final link = _spanWithText(spans, 'https://example.com/docs');
      expect(link, isNotNull);
      expect(link!.recognizer, isA<LinkTapRecognizer>());
      expect(link.style?.color, LlackColors.accentDeep);
    });

    test('링크 뒤의 문장 부호는 링크에 들어가지 않는다', () {
      final spans = _flatten(buildMessageSpans('https://example.com.'));

      expect(_spanWithText(spans, 'https://example.com'), isNotNull);
      expect(_spanWithText(spans, '.'), isNotNull);
    });

    test('@멘션 은 강조된 span 이 된다', () {
      final spans = _flatten(buildMessageSpans('@홍길동 확인해주세요'));

      final mention = _spanWithText(spans, '@홍길동');
      expect(mention, isNotNull);
      expect(mention!.style?.color, LlackColors.accentDeep);
      expect(mention.style?.fontWeight, FontWeight.w600);
    });

    test('코드 블록은 여러 줄과 들여쓰기가 그대로 남는다', () {
      final spans = _flatten(buildMessageSpans('앞\n```dart\nvoid main() {\n  print(1);\n}\n```\n뒤'));

      final block = _spanWithText(spans, 'void main() {\n  print(1);\n}');
      expect(block, isNotNull);
      expect(block!.style?.fontFamilyFallback, contains('monospace'));
    });

    test('원본 HTML 은 해석하지 않는다', () {
      final spans = _flatten(buildMessageSpans('<b>굵게</b>'));

      // <b> 태그는 글자로 남고 굵게로 승격되지 않는다.
      expect(_spanWithText(spans, '<b>굵게</b>'), isNotNull);
      expect(_spanWithText(spans, '굵게'), isNull);
    });

    test('마크이 아닌 글자는 그대로 남는다', () {
      final body = '그냥 평범한 메시지 100% 입니다';
      final spans = _flatten(buildMessageSpans(body));

      expect(spans.map((span) => span.text).join(), body);
    });
  });

  group('MessageMarkdown', () {
    testWidgets('본문이 마크다운으로 그려진다', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: MessageMarkdown(body: '**굵게** 메시지')),
        ),
      );
      await tester.pump();

      final spans = _renderedSpans(tester);
      final bold = _spanWithText(spans, '굵게');
      expect(bold, isNotNull);
      expect(bold!.style?.fontWeight, FontWeight.w700);
    });

    testWidgets('링크를 누르면 onLinkTap 이 불린다', (tester) async {
      String? tapped;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageMarkdown(
              body: 'https://example.com',
              onLinkTap: (url) => tapped = url,
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('https://example.com', findRichText: true));
      await tester.pumpAndSettle();

      expect(tapped, 'https://example.com');
    });

    testWidgets('위젯이 사라지면 링크 recognizer 도 해제된다', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: MessageMarkdown(body: 'https://example.com')),
        ),
      );
      await tester.pump();

      final recognizers = _renderedRecognizers(tester);
      expect(recognizers, hasLength(1));
      expect(recognizers.first.isDisposed, isFalse);

      // 메시지가 화면에서 사라지면 recognizer 도 해제되어야 한다.
      // (RichText 가 해제해 주지 않는다)
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: SizedBox.shrink())),
      );
      await tester.pump();

      expect(recognizers.first.isDisposed, isTrue);
    });

    testWidgets('본문이 바뀌면 예전 recognizer 는 해제된다', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: MessageMarkdown(body: 'https://example.com')),
        ),
      );
      await tester.pump();

      final first = _renderedRecognizers(tester).first;

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: MessageMarkdown(body: 'https://example.org')),
        ),
      );
      await tester.pump();

      expect(first.isDisposed, isTrue);
    });
  });

  test('빠른 이모티콘은 15종이다', () {
    expect(quickReactions, hasLength(15));
    expect(quickReactions.first, '👍');
    expect(quickReactions.last, '☕');
  });
}
