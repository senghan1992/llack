import 'package:flutter_test/flutter_test.dart';
import 'package:llack_mobile/main.dart';
import 'package:llack_mobile/providers/app_state.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('LlackMobileApp smoke test', (WidgetTester tester) async {
    final appState = AppState();

    await tester.pumpWidget(
      ChangeNotifierProvider<AppState>.value(
        value: appState,
        child: const LlackMobileApp(),
      ),
    );

    expect(find.byType(LlackMobileApp), findsOneWidget);
  });
}
