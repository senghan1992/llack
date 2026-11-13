import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/widgets/message_composer.dart';
import 'package:llack_mobile/widgets/message_markdown.dart';

Widget _composer({
  Future<bool> Function(String body)? onSend,
  Future<bool> Function(String body, List<String>? attachmentIds)? onSendWithAttachments,
  Future<List<(String, String)>?> Function()? onUploadAttachments,
  ValueChanged<String>? onChanged,
}) {
  return MaterialApp(
    home: Scaffold(
      body: MessageComposer(
        onSend: onSend,
        onSendWithAttachments: onSendWithAttachments,
        onUploadAttachments: onUploadAttachments,
        onChanged: onChanged,
      ),
    ),
  );
}

void main() {
  testWidgets('첨부 업로드 콜백이 불리고 첨부 칩이 보인다', (tester) async {
    var uploadCalls = 0;

    await tester.pumpWidget(
      _composer(
        onUploadAttachments: () async {
          uploadCalls++;
          return [('report.pdf', 'f1')];
        },
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();

    expect(uploadCalls, 1);
    expect(find.text('report.pdf'), findsOneWidget);
  });

  testWidgets('첨부 id 를 붙여 onSendWithAttachments 로 보낸다', (tester) async {
    String? sentBody;
    List<String>? sentIds;

    await tester.pumpWidget(
      _composer(
        onSendWithAttachments: (body, ids) async {
          sentBody = body;
          sentIds = ids;
          return true;
        },
        onUploadAttachments: () async => [('report.pdf', 'f1')],
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), '안녕하세요');
    await tester.pump();

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(sentBody, '안녕하세요');
    expect(sentIds, ['f1']);
    // 보내고 나면 첨부 칩도 사라진다
    expect(find.text('report.pdf'), findsNothing);
  });

  testWidgets('본문이 비어도 첨부가 있으면 보낼 수 있다', (tester) async {
    String? sentBody;
    List<String>? sentIds;

    await tester.pumpWidget(
      _composer(
        onSendWithAttachments: (body, ids) async {
          sentBody = body;
          sentIds = ids;
          return true;
        },
        onUploadAttachments: () async => [('report.pdf', 'f1')],
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(sentBody, '');
    expect(sentIds, ['f1']);
  });

  testWidgets('본문도 첨부도 없으면 전송할 수 없다', (tester) async {
    var sent = 0;

    await tester.pumpWidget(
      _composer(
        onSendWithAttachments: (body, ids) async {
          sent++;
          return true;
        },
        onUploadAttachments: () async => [('report.pdf', 'f1')],
      ),
    );

    final sendButton = tester.widget<IconButton>(
      find.ancestor(of: find.byIcon(Icons.arrow_upward_rounded), matching: find.byType(IconButton)),
    );
    expect(sendButton.onPressed, isNull);
    expect(sent, 0);
  });

  testWidgets('onSendWithAttachments 가 없으면 onSend 로 보낸다', (tester) async {
    String? sentBody;

    await tester.pumpWidget(
      _composer(
        onSend: (body) async {
          sentBody = body;
          return true;
        },
      ),
    );

    await tester.enterText(find.byType(TextField), 'Legacy');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(sentBody, 'Legacy');
  });

  testWidgets('onSendWithAttachments 가 있으면 그것을 먼저 쓴다', (tester) async {
    String? sentByLegacy;
    List<String>? sentIds;

    await tester.pumpWidget(
      _composer(
        onSend: (body) async {
          sentByLegacy = body;
          return true;
        },
        onSendWithAttachments: (body, ids) async {
          sentIds = ids;
          return true;
        },
        onUploadAttachments: () async => [('report.pdf', 'f1')],
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), '첨부 있음');
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();

    expect(sentByLegacy, isNull);
    expect(sentIds, ['f1']);
  });

  testWidgets('onUploadAttachments 가 없으면 종이클립 버튼이 없다', (tester) async {
    await tester.pumpWidget(_composer());

    expect(find.byIcon(Icons.attach_file), findsNothing);
  });

  testWidgets('업로드 중에는 업로드 중 상태를 보여주고 다시 들어갈 수 없다', (tester) async {
    final completer = Completer<List<(String, String)>?>();
    var uploadCalls = 0;

    await tester.pumpWidget(
      _composer(
        onUploadAttachments: () {
          uploadCalls++;
          return completer.future;
        },
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pump();

    expect(find.text('업로드 중'), findsOneWidget);

    // 업로드 중에는 다시_upload 를 시작할 수 없다
    await tester.tap(find.byTooltip('파일 첨부'), warnIfMissed: false);
    await tester.pump();
    expect(uploadCalls, 1);

    completer.complete(null);
    await tester.pumpAndSettle();

    expect(find.text('업로드 중'), findsNothing);
    expect(uploadCalls, 1);
  });

  testWidgets('업로드가 실패하면 이유를 알려주고 칩은 추가하지 않는다', (tester) async {
    await tester.pumpWidget(
      _composer(
        onUploadAttachments: () async => throw Exception('업로드 실패'),
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();

    expect(find.textContaining('업로드 실패'), findsOneWidget);
    expect(find.byIcon(Icons.insert_drive_file_outlined), findsNothing);
  });

  testWidgets('첨부 칩의 × 를 누르면 첨부가 빠진다', (tester) async {
    await tester.pumpWidget(
      _composer(
        onUploadAttachments: () async => [('report.pdf', 'f1')],
      ),
    );

    await tester.tap(find.byIcon(Icons.attach_file));
    await tester.pumpAndSettle();
    expect(find.text('report.pdf'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();

    expect(find.text('report.pdf'), findsNothing);
  });

  testWidgets('onChanged 는 초기값으로도, 글자가 바뀔 때마다 불린다', (tester) async {
    final changes = <String>[];

    await tester.pumpWidget(_composer(onChanged: changes.add));
    await tester.pump();

    expect(changes, ['']);

    await tester.enterText(find.byType(TextField), '안녕');
    await tester.pump();

    expect(changes.last, '안녕');
  });

  testWidgets('이모티콘은 현재 커서 위치에 들어간다', (tester) async {
    await tester.pumpWidget(_composer());

    await tester.enterText(find.byType(TextField), '가나');
    await tester.pump();

    // 커서를 가운데로 옮긴다
    tester.testTextInput.updateEditingValue(
      const TextEditingValue(text: '가나', selection: TextSelection.collapsed(offset: 1)),
    );
    await tester.pump();

    // 이모티콘 버튼을 누르면 그리드가 열린다
    await tester.tap(find.byIcon(Icons.sentiment_satisfied));
    await tester.pumpAndSettle();

    await tester.tap(find.text('🎉'));
    await tester.pumpAndSettle();

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.controller!.text, '가🎉나');
  });

  testWidgets('이모티콘 그리드는 15종을 보여준다', (tester) async {
    await tester.pumpWidget(_composer());

    await tester.tap(find.byIcon(Icons.sentiment_satisfied));
    await tester.pumpAndSettle();

    for (final emoji in quickReactions) {
      expect(find.text(emoji), findsOneWidget);
    }
  });
}
