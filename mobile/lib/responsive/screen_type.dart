import 'package:flutter/material.dart';

enum ScreenType {
  /// Phone portrait, small screens (< 650dp)
  compact,
  /// Phone landscape, foldables unfolded, mini tablets portrait (650dp - 1000dp)
  medium,
  /// iPads, Android pads in landscape, large tablets (>= 1000dp)
  expanded,
}

class FormFactor {
  final BuildContext context;

  FormFactor(this.context);

  double get width => MediaQuery.sizeOf(context).width;
  double get height => MediaQuery.sizeOf(context).height;

  ScreenType get screenType {
    final w = width;
    if (w < 650) return ScreenType.compact;
    if (w < 1000) return ScreenType.medium;
    return ScreenType.expanded;
  }

  bool get isCompact => screenType == ScreenType.compact;
  bool get isMedium => screenType == ScreenType.medium;
  bool get isExpanded => screenType == ScreenType.expanded;

  /// True for any tablet/pad form factor (medium or expanded)
  bool get isPad => !isCompact;

  /// Whether there is room for a 3-pane split (Nav/Channels + Chat + Thread/Details)
  bool get canShowThreePanes => width >= 1080;

  /// Whether there is room for a 2-pane split (List + Detail)
  bool get canShowTwoPanes => width >= 650;
}
