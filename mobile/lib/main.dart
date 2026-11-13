import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:provider/provider.dart';
import 'providers/app_state.dart';
import 'screens/auth_screen.dart';
import 'screens/main_shell.dart';
import 'services/device_settings.dart';
import 'theme/llack_colors.dart';
import 'theme/llack_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('ko_KR', null);

  // 이 기기의 설정 (화면 모드 · 시간 표기) 을 먼저 읽는다.
  await DeviceSettings.instance.load();

  final appState = AppState();

  runApp(
    ChangeNotifierProvider.value(
      value: appState,
      child: const LlackMobileApp(),
    ),
  );
  // 부팅은 첫 프레임 이후에 시작한다.
  // (await 로 먼저 끝내면 Flutter 프레임이 안 그려져 "Atrium 연결 중..." 화면이 보이지 않는다)
  appState.boot();
}

class LlackMobileApp extends StatelessWidget {
  const LlackMobileApp({super.key});

  /// 지금 어두운 화면이어야 하는가.
  ///
  /// `system` 은 OS 설정을 따라간다. (OS 가 밤으로 넘어가면 앱도 어두워진다)
  bool _isDark(BuildContext context, ThemeModeSetting mode) {
    switch (mode) {
      case ThemeModeSetting.light:
        return false;
      case ThemeModeSetting.dark:
        return true;
      case ThemeModeSetting.system:
        return MediaQuery.platformBrightnessOf(context) == Brightness.dark;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<ThemeModeSetting>(
      valueListenable: DeviceSettings.instance.themeMode,
      builder: (context, mode, _) {
        final isDark = _isDark(context, mode);
        // 팔레트를 **MaterialApp 을 그리기 전에** 갈아 끼운다.
        // (화면 안에서 직접 색을 읽는 곳들이 여기서 정한 팔레트를 본다)
        LlackColors.usePalette(isDark ? LlackColors.dark : LlackColors.light);

        return MaterialApp(
      // 화면 모드가 바뀌면 트리를 새로 그린다.
      // (색 토큰을 직접 읽는 곳들이 테마 의존성이 아니라 팔레트 의존성이므로
      //  MaterialApp 이 살아 있는 동안에는 옛 색이 남는다)
      key: ValueKey('atrium-${mode.name}-$isDark'),
      title: 'Atrium',
      debugShowCheckedModeBanner: false,
      theme: isDark ? LlackTheme.dark() : LlackTheme.light(),
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
            return  Scaffold(
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
                      'Atrium 연결 중...',
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
      },
    );
  }
}
