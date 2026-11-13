import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/llack_colors.dart';
import '../theme/llack_typography.dart';

/// 빠른 이모티콘 15종.
///
/// 데스크톱 작성창(desktop/src/lib/markdown.ts 의 QUICK_REACTIONS) 과 같은 목록이다.
/// (작성창 이모티콘 버튼 · 말풍선 반응 메뉴가 같은 목록을 쓴다)
const quickReactions = <String>[
  '👍', '👎', '❤️', '🎉', '👀',
  '🔥', '✅', '🙏', '😅', '🤝',
  '💡', '🚀', '🐛', '📌', '☕',
];

/// 링크를 탭할 때 쓰는 recognizer.
///
/// Flutter 의 RichText 는 **TextSpan 안의 recognizer 를 자동으로 해제하지 않는다.**
/// 그래서 [MessageMarkdown] 가 이 recognizer 를 직접 해제한다.
/// (해제 여부를 테스트에서 확인할 수 있게 [isDisposed] 를 둔다)
class LinkTapRecognizer extends TapGestureRecognizer {
  bool _disposed = false;

  /// 이미 해제되었는지.
  bool get isDisposed => _disposed;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// 메시지 본문을 마크다운 span 으로 바꿔준다.
///
/// 데스크톱(desktop/src/lib/markdown.ts 의 renderBody) 과 같은 규칙이다.
/// - 인라인 코드 `` `코드` ``
/// - 굵게 `**굵게**` · 기울임 `*기울임*` · 취소선 `~~취소선~~`
/// - `https://` 링크 (탭하면 [onLinkTap])
/// - `@멘션`
/// - ``` 펜스로 감싼 코드 블록 (여러 줄 · 들여쓰기 보존)
///
/// **원본 HTML 은 해석하지 않는다.** (고정된 마크만 span 으로 승격한다)
///
/// 만들어진 링크 recognizer 는 호출자가 해제해야 한다.
/// ([MessageMarkdown] 는 자동으로 해제한다)
List<InlineSpan> buildMessageSpans(
  String body, {
  TextStyle? baseStyle,
  Color? linkColor,
  Color? mentionColor,
  void Function(String url)? onLinkTap,
}) {
  final base = baseStyle ?? LlackTypography.body;
  final link = linkColor ?? LlackColors.accentDeep;
  final mention = mentionColor ?? LlackColors.accentDeep;
  return _parseBlocks(
    body,
    base: base,
    linkColor: link,
    mentionColor: mention,
    onLinkTap: onLinkTap,
  );
}

/// span 트리 안에 있는 링크 recognizer 를 모두 모은다.
///
/// [MessageMarkdown] 가 이것을 모아서 직접 해제한다.
List<LinkTapRecognizer> linkRecognizersIn(List<InlineSpan> spans) {
  final found = <LinkTapRecognizer>[];

  void walk(InlineSpan node) {
    if (node is! TextSpan) return;
    final recognizer = node.recognizer;
    if (recognizer is LinkTapRecognizer) found.add(recognizer);
    for (final child in node.children ?? const <InlineSpan>[]) {
      walk(child);
    }
  }

  for (final span in spans) {
    walk(span);
  }
  return found;
}

/// 메시지 본문을 마크다운으로 그린다.
///
/// 평문 Text 대신 이 위젯을 쓰면 코드 · 굵게 · 링크 · 멘션이 그대로 보인다.
class MessageMarkdown extends StatefulWidget {
  /// 원본 본문 (마크다운 문법이 들어 있는 텍스트)
  final String body;

  /// 본문 기본 스타일. (없으면 [LlackTypography.body])
  final TextStyle? textStyle;

  /// 링크 색. (없으면 [LlackColors.accentDeep])
  final Color? linkColor;

  /// 멘션 색. (없으면 [LlackColors.accentDeep])
  final Color? mentionColor;

  /// 링크를 눌렀을 때의 동작.
  ///
  /// 이게 없으면 링크를 클립보드에 복사하고 snack bar 로 알려준다.
  final void Function(String url)? onLinkTap;

  const MessageMarkdown({
    super.key,
    required this.body,
    this.textStyle,
    this.linkColor,
    this.mentionColor,
    this.onLinkTap,
  });

  @override
  State<MessageMarkdown> createState() => _MessageMarkdownState();
}

class _MessageMarkdownState extends State<MessageMarkdown> {
  /// 이번에 그린 링크 recognizer 목록.
  ///
  /// RichText 가 해제해 주지 않으므로 직접 해제한다.
  final List<LinkTapRecognizer> _recognizers = [];

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }

  /// recognizer 를 전부 해제한다.
  void _disposeRecognizers() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
  }

  void _handleLinkTap(String url) {
    final onLinkTap = widget.onLinkTap;
    if (onLinkTap != null) {
      onLinkTap(url);
      return;
    }
    // 앱에 url_launcher 가 없어 링크를 곧바로 열 수는 없다.
    // 대신 복사해 두라고 알려준다.
    Clipboard.setData(ClipboardData(text: url));
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(
      SnackBar(content: Text('링크를 복사했습니다: $url')),
    );
  }

  @override
  Widget build(BuildContext context) {
    // 지난 빌드의 recognizer 를 먼저 해제한다.
    _disposeRecognizers();
    final spans = buildMessageSpans(
      widget.body,
      baseStyle: widget.textStyle,
      linkColor: widget.linkColor,
      mentionColor: widget.mentionColor,
      onLinkTap: _handleLinkTap,
    );
    _recognizers.addAll(linkRecognizersIn(spans));

    return Text.rich(
      TextSpan(children: spans, style: widget.textStyle),
      style: widget.textStyle,
    );
  }
}

// ── 파싱 ──────────────────────────────────────────────────────────

/// ``` 펜스로 나눈 조각을 순서대로 span 으로 만든다.
List<InlineSpan> _parseBlocks(
  String body, {
  required TextStyle base,
  required Color linkColor,
  required Color mentionColor,
  void Function(String url)? onLinkTap,
}) {
  final spans = <InlineSpan>[];
  // 펜스로 나눈 조각 중 홀수 번째(1, 3, 5…)가 코드 블록이다.
  final parts = body.split('```');
  for (var i = 0; i < parts.length; i++) {
    if (i.isOdd) {
      final code = _stripCodeFence(parts[i]);
      if (code.isNotEmpty) {
        spans.add(TextSpan(text: code, style: _codeStyle(base, block: true)));
      }
    } else {
      spans.addAll(
        _parseInline(
          parts[i],
          base: base,
          linkColor: linkColor,
          mentionColor: mentionColor,
          onLinkTap: onLinkTap,
        ),
      );
    }
  }
  return spans;
}

/// 코드 블록에서 언어 이름 줄과 끝의 줄바꿈 하나를 뺀다.
String _stripCodeFence(String part) {
  var code = part;
  // 첫 줄이 언어 이름이면(예: dart) 버린다.
  code = code.replaceFirst(RegExp(r'^[a-zA-Z0-9+#-]*\n'), '');
  // 끝의 줄바꿈 하나는 버린다.
  if (code.endsWith('\n')) {
    code = code.substring(0, code.length - 1);
  }
  return code;
}

/// 한 줄(문단) 안의 마크를 span 으로 바꾼다.
List<InlineSpan> _parseInline(
  String text, {
  required TextStyle base,
  required Color linkColor,
  required Color mentionColor,
  void Function(String url)? onLinkTap,
}) {
  final spans = <InlineSpan>[];
  final buffer = StringBuffer();
  var i = 0;

  void flush() {
    if (buffer.isNotEmpty) {
      spans.add(TextSpan(text: buffer.toString(), style: base));
      buffer.clear();
    }
  }

  while (i < text.length) {
    final ch = text[i];

    // 인라인 코드: `코드`
    if (ch == '`') {
      final end = text.indexOf('`', i + 1);
      if (end > i + 1) {
        final content = text.substring(i + 1, end);
        if (!content.contains('\n')) {
          flush();
          spans.add(TextSpan(text: content, style: _codeStyle(base)));
          i = end + 1;
          continue;
        }
      }
    }

    // 굵게: **굵게**
    if (ch == '*' && i + 1 < text.length && text[i + 1] == '*') {
      final end = text.indexOf('**', i + 2);
      if (end > i + 2) {
        final content = text.substring(i + 2, end);
        if (!content.contains('*') && !content.contains('\n')) {
          flush();
          spans.addAll(
            _parseInline(
              content,
              base: base.copyWith(fontWeight: FontWeight.w700),
              linkColor: linkColor,
              mentionColor: mentionColor,
              onLinkTap: onLinkTap,
            ),
          );
          i = end + 2;
          continue;
        }
      }
    }

    // 취소선: ~~취소선~~
    if (ch == '~' && i + 1 < text.length && text[i + 1] == '~') {
      final end = text.indexOf('~~', i + 2);
      if (end > i + 2) {
        final content = text.substring(i + 2, end);
        if (!content.contains('~') && !content.contains('\n')) {
          flush();
          spans.addAll(
            _parseInline(
              content,
              base: _strikeStyle(base),
              linkColor: linkColor,
              mentionColor: mentionColor,
              onLinkTap: onLinkTap,
            ),
          );
          i = end + 2;
          continue;
        }
      }
    }

    // 기울임: *기울임*  (앞이 공백/괄호/줄바꿈일 때만 승격한다)
    if (ch == '*' && _isItalicBoundary(text, i)) {
      final end = text.indexOf('*', i + 1);
      if (end > i + 1) {
        final content = text.substring(i + 1, end);
        if (!content.contains('\n')) {
          flush();
          spans.addAll(
            _parseInline(
              content,
              base: base.copyWith(fontStyle: FontStyle.italic),
              linkColor: linkColor,
              mentionColor: mentionColor,
              onLinkTap: onLinkTap,
            ),
          );
          i = end + 1;
          continue;
        }
      }
    }

    // 링크: https://example.com
    if (_isUrlStart(text, i)) {
      final url = _matchUrl(text, i);
      if (url != null) {
        flush();
        spans.add(
          _linkSpan(
            url,
            base: base,
            linkColor: linkColor,
            onLinkTap: onLinkTap,
          ),
        );
        i += url.length;
        continue;
      }
    }

    // 멘션: @이름
    if (ch == '@' && _isMentionBoundary(text, i)) {
      final mention = _matchMention(text, i);
      if (mention != null) {
        flush();
        spans.add(
          TextSpan(
            text: mention,
            style: base.copyWith(color: mentionColor, fontWeight: FontWeight.w600),
          ),
        );
        i += mention.length;
        continue;
      }
    }

    buffer.write(ch);
    i++;
  }

  flush();
  return spans;
}

/// 링크 span 을 만든다. (탭하면 [onLinkTap] 이 불린다)
TextSpan _linkSpan(
  String url, {
  required TextStyle base,
  required Color linkColor,
  void Function(String url)? onLinkTap,
}) {
  final recognizer = LinkTapRecognizer();
  recognizer.onTap = () => onLinkTap?.call(url);
  return TextSpan(
    text: url,
    style: base.copyWith(
      color: linkColor,
      decoration: TextDecoration.underline,
      decorationColor: linkColor,
    ),
    recognizer: recognizer,
  );
}

/// 코드 스타일. (등폭 + 옅은 배경)
TextStyle _codeStyle(TextStyle base, {bool block = false}) {
  final foreground = base.color ?? LlackColors.ink;
  return base.copyWith(
    fontFamilyFallback: LlackTypography.monoFallbacks,
    fontSize: (base.fontSize ?? 14) - 0.5,
    height: block ? 1.35 : base.height,
    backgroundColor: foreground.withValues(alpha: block ? 0.10 : 0.08),
  );
}

/// 취소선 스타일. (기존 밑줄이 있으면 함께 그린다)
TextStyle _strikeStyle(TextStyle base) {
  final decoration = base.decoration;
  if (decoration == null || decoration == TextDecoration.none) {
    return base.copyWith(decoration: TextDecoration.lineThrough);
  }
  return base.copyWith(
    decoration: TextDecoration.combine([decoration, TextDecoration.lineThrough]),
  );
}

/// `*` 앞에 공백/괄호/줄바꿈이 있어야 기울임으로 본다.
bool _isItalicBoundary(String text, int index) {
  if (index == 0) return true;
  final prev = text[index - 1];
  return prev == '(' || _isWhitespace(prev);
}

/// `@` 앞에 공백/줄바꿈이 있어야 멘션으로 본다.
bool _isMentionBoundary(String text, int index) {
  if (index == 0) return true;
  return _isWhitespace(text[index - 1]);
}

/// http:// 또는 https:// 로 시작하는가.
bool _isUrlStart(String text, int index) {
  final lower = text.toLowerCase();
  return lower.startsWith('http://', index) || lower.startsWith('https://', index);
}

/// 링크 주소 하나를 골라낸다. (문장 끝의 기호는 링크에서 뺀다)
String? _matchUrl(String text, int start) {
  final isHttps = text.toLowerCase().startsWith('https://', start);
  final schemeLength = isHttps ? 'https://'.length : 'http://'.length;

  var end = start;
  while (end < text.length && !_isUrlTerminator(text[end])) {
    end++;
  }
  while (end > start && _isTrailingPunctuation(text[end - 1])) {
    end--;
  }
  // 주소는 스킴만으로는 안 된다. (데스크톱 규칙과 같은 최소 길이)
  if (end - start < schemeLength + 2) return null;
  return text.substring(start, end);
}

/// 링크가 끝나는 문자 (공백 · 태그 문자).
bool _isUrlTerminator(String ch) => _isWhitespace(ch) || ch == '<' || ch == '>';

/// 링크 뒤에 붙은 문장 부호.
bool _isTrailingPunctuation(String ch) =>
    ch == '.' || ch == ',' || ch == ':' || ch == ';' || ch == '"' ||
    ch == "'" || ch == ')' || ch == ']';

/// `@이름` 을 골라낸다. (영문·숫자·언더바·한글 뒤에 `.` `-` 가 이어질 수 있다)
String? _matchMention(String text, int start) {
  var i = start + 1;
  if (i >= text.length || !_isMentionWordChar(text[i])) return null;
  i++;

  var count = 0;
  while (i < text.length && count < 30 && _isMentionTailChar(text[i])) {
    i++;
    count++;
  }
  // 한 글자짜리(`@a`)는 멘션으로 보지 않는다. (데스크톱 규칙과 같다)
  if (count < 1) return null;
  return text.substring(start, i);
}

final RegExp _asciiWord = RegExp(r'[A-Za-z0-9_]');

/// 멘션의 첫 글자로 쓸 수 있는 문자 (영문·숫자·언더바·한글).
bool _isMentionWordChar(String ch) {
  final code = ch.codeUnitAt(0);
  if (code >= 0xAC00 && code <= 0xD7A3) return true; // 가-힣
  return _asciiWord.hasMatch(ch);
}

/// 멘션 뒤에 이어질 수 있는 문자 (영문·숫자·언더바·한글·`.`·`-`).
bool _isMentionTailChar(String ch) =>
    _isMentionWordChar(ch) || ch == '.' || ch == '-';

bool _isWhitespace(String ch) =>
    ch == ' ' || ch == '\n' || ch == '\t' || ch == '\r';
