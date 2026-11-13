// ignore_for_file: use_null_aware_elements
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 이 기기에 저장되는 설정.
///
/// 계정 것과 기기 것을 나눈다.
/// - 계정 것( 이름 · 직함 · 아바타 · 역할 )은 서버에 있고
/// - 기기 것( 화면 모드 · 시간 표기 )은 이 앱을 쓰는 사람마다 달라서 이 기기에 남는다.
///
/// 데스크톱의 `desktop/src/lib/settings.ts` 에 대응한다.
class DeviceSettings {
  DeviceSettings._();

  static const String keyThemeMode = 'llack.theme_mode';
  static const String keyClockFormat = 'llack.clock_format';

  /// 화면 모드. `system` 은 OS 설정을 따라간다.
  final ValueNotifier<ThemeModeSetting> themeMode =
      ValueNotifier<ThemeModeSetting>(ThemeModeSetting.system);

  /// 시간 표기. (24시간 / 12시간)
  final ValueNotifier<ClockFormatSetting> clockFormat =
      ValueNotifier<ClockFormatSetting>(ClockFormatSetting.h24);

  /// 앱 전체에서 쓰는 한 벌.
  static final DeviceSettings instance = DeviceSettings._();

  /// 저장된 값을 읽는다. (Called once at startup)
  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString(keyThemeMode);
    themeMode.value = ThemeModeSetting.fromString(mode);
    final clock = prefs.getString(keyClockFormat);
    clockFormat.value = ClockFormatSetting.fromString(clock);
  }

  /// 화면 모드를 바꾸고 저장한다.
  Future<void> setThemeMode(ThemeModeSetting mode) async {
    if (themeMode.value == mode) return;
    themeMode.value = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyThemeMode, mode.name);
  }

  /// 시간 표기를 바꾸고 저장한다.
  Future<void> setClockFormat(ClockFormatSetting format) async {
    if (clockFormat.value == format) return;
    clockFormat.value = format;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyClockFormat, format.name);
  }
}

/// 화면 모드.
enum ThemeModeSetting {
  light,
  dark,
  system;

  static ThemeModeSetting fromString(String? value) {
    switch (value) {
      case 'light':
        return ThemeModeSetting.light;
      case 'dark':
        return ThemeModeSetting.dark;
      default:
        return ThemeModeSetting.system;
    }
  }

  String get label {
    switch (this) {
      case ThemeModeSetting.light:
        return '밝게';
      case ThemeModeSetting.dark:
        return '어둡게';
      case ThemeModeSetting.system:
        return '시스템';
    }
  }
}

/// 시간 표기.
enum ClockFormatSetting {
  h24,
  h12;

  static ClockFormatSetting fromString(String? value) {
    switch (value) {
      case '12h':
        return ClockFormatSetting.h12;
      default:
        return ClockFormatSetting.h24;
    }
  }

  String get label {
    switch (this) {
      case ClockFormatSetting.h24:
        return '24시간';
      case ClockFormatSetting.h12:
        return '12시간';
    }
  }

  /// 시간을 이 표기에 맞춰 돌려준다. (초는 버린다)
  String format(DateTime time) {
    final local = time.toLocal();
    if (this == ClockFormatSetting.h24) {
      final h = local.hour.toString().padLeft(2, '0');
      final m = local.minute.toString().padLeft(2, '0');
      return '$h:$m';
    }
    final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final m = local.minute.toString().padLeft(2, '0');
    final suffix = local.hour < 12 ? 'AM' : 'PM';
    return '$hour:$m $suffix';
  }
}
