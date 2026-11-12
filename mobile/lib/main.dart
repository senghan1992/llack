import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:provider/provider.dart';
import 'providers/app_state.dart';
import 'screens/auth_screen.dart';
import 'screens/main_shell.dart';
import 'theme/llack_colors.dart';
import 'theme/llack_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('ko_KR', null);

  final appState = AppState();

  runApp(
    ChangeNotifierProvider.value(
      value: appState,
      child: const LlackMobileApp(),
    ),
  );
  // 부팅은 첫 프레임 이후에 시작한다.
  // (await 로 먼저 끝내면 Flutter 프레임이 안 그려져 "Llack 연결 중..." 화면이 보이지 않는다)
  appState.boot();
}

class LlackMobileApp extends StatelessWidget {
  const LlackMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Llack',
      debugShowCheckedModeBanner: false,
      theme: LlackTheme.light(),
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('ko', 'KR'),
        Locale('en', 'US'),
      ],
      // 앱은 한국어 제품이므로 Material 위젯도 한국어로 고정한다.
      // (locale 이 없으면 기기 로케일을 따라가서 날짜·시간 선택기가 영어 + 12시간제로 나온다)
      locale: const Locale('ko', 'KR'),
      home: Consumer<AppState>(
        builder: (ctx, state, _) {
          if (state.isBooting) {
            return const Scaffold(
              backgroundColor: LlackColors.paper,
              body: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        color: LlackColors.accent,
                      ),
                    ),
                    SizedBox(height: 16),
                    Text(
                      'Llack 연결 중...',
                      style: TextStyle(
                        fontSize: 13,
                        color: LlackColors.muted,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }

          if (!state.isAuthenticated) {
            return const AuthScreen();
          }

          return const MainShell();
        },
      ),
    );
  }
}
