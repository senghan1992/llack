import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:llack_mobile/screens/search/search_dialog.dart';
import 'package:provider/provider.dart';

/// 검색 요청을 직접 제어해서 "늦게 도착한 이전 응답" 이 새 결과를 덮어쓰는지 확인한다.
class _ControlledSearchAppState extends AppState {
  final List<Completer<List<SearchResult>>> pending = [];

  @override
  Future<List<SearchResult>> search(String query) async {
    final completer = Completer<List<SearchResult>>();
    pending.add(completer);
    return completer.future;
  }
}

SearchResult _result(String body) {
  final author = User(id: 'u1', email: 'a@hanbit.co.kr', name: '홍길동');
  return SearchResult(
    message: Message(
      id: 'm$body',
      channelId: 'c1',
      userId: 'u1',
      author: author,
      body: body,
      createdAt: DateTime(2026, 1, 1),
    ),
    channel: Channel(
      id: 'c1',
      workspaceId: 'w1',
      name: 'general',
      kind: 'channel',
      isPrivate: false,
      createdBy: 'u1',
      createdAt: DateTime(2026, 1, 1),
    ),
  );
}

void main() {
  testWidgets('느린 이전 검색 응답이 최신 검색 결과를 덮어쓰지 않는다', (tester) async {
    final state = _ControlledSearchAppState();

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: state,
        child: const MaterialApp(home: Scaffold(body: SearchDialog())),
      ),
    );
    await tester.pump();

    // 첫 번째 검색 (느린 응답)
    await tester.enterText(find.byType(TextField).first, 'slow');
    await tester.pump(const Duration(milliseconds: 350));
    expect(state.pending.length, 1);

    // 두 번째 검색 (최신 검색어)
    await tester.enterText(find.byType(TextField).first, 'fast');
    await tester.pump(const Duration(milliseconds: 350));
    expect(state.pending.length, 2);

    // 최신 응답이 먼저 도착
    state.pending[1].complete([_result('최신 결과')]);
    await tester.pump();
    await tester.pump();
    expect(find.text('최신 결과'), findsOneWidget);

    // 이전 응답이 늦게 도착해도 결과를 덮어쓰지 않아야 한다.
    state.pending[0].complete([_result('오래된 결과')]);
    await tester.pump();
    await tester.pump();
    expect(find.text('최신 결과'), findsOneWidget);
    expect(find.text('오래된 결과'), findsNothing);
  });
}
