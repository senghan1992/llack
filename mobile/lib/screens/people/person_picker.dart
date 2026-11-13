import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';

/// 사람 한 명을 고르는 재사용 가능한 선택기.
///
/// 기본 후보는 워크스페이스 구성원(`AppState.members`)이다.
/// [searchAllUsers]를 켜면 검색어가 두 글자 이상일 때
/// `AppState.searchUsers`로 다른 워크스페이스의 공유 사용자도 후보에 더한다.
class PersonPicker extends StatefulWidget {
  const PersonPicker({
    super.key,
    this.title = '사람 선택',
    this.excludedUserIds = const {},
    this.searchAllUsers = false,
    this.onSelected,
  });

  final String title;
  final Set<String> excludedUserIds;
  final bool searchAllUsers;
  final ValueChanged<User>? onSelected;

  @override
  State<PersonPicker> createState() => _PersonPickerState();
}

class _PersonPickerState extends State<PersonPicker> {
  final _searchController = TextEditingController();
  Timer? _searchDebounce;
  List<User> _searchResults = const [];
  bool _isSearching = false;
  String? _searchError;
  int _searchGeneration = 0;

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_onQueryChanged);
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController
      ..removeListener(_onQueryChanged)
      ..dispose();
    super.dispose();
  }

  void _onQueryChanged() {
    final query = _searchController.text.trim();
    final generation = ++_searchGeneration;
    _searchDebounce?.cancel();

    if (!widget.searchAllUsers || query.length < 2) {
      if (_searchResults.isNotEmpty || _isSearching || _searchError != null) {
        setState(() {
          _searchResults = const [];
          _isSearching = false;
          _searchError = null;
        });
      }
      return;
    }

    setState(() => _searchError = null);
    _searchDebounce = Timer(const Duration(milliseconds: 250), () {
      _searchUsers(query, generation);
    });
  }

  Future<void> _searchUsers(String query, int generation) async {
    if (mounted) setState(() => _isSearching = true);

    try {
      final users = await context.read<AppState>().searchUsers(query);
      if (!mounted || generation != _searchGeneration) return;
      setState(() {
        _searchResults = users;
        _isSearching = false;
        _searchError = null;
      });
    } catch (_) {
      if (!mounted || generation != _searchGeneration) return;
      setState(() {
        _isSearching = false;
        _searchError = '사람을 검색하지 못했습니다';
      });
    }
  }

  void _select(User user) {
    if (widget.onSelected != null) {
      widget.onSelected!(user);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final query = _searchController.text.trim().toLowerCase();
    final peopleById = <String, User>{};

    for (final member in state.members) {
      peopleById[member.user.id] = member.user;
    }
    for (final user in _searchResults) {
      peopleById[user.id] = user;
    }

    final candidates = peopleById.values.where((user) {
      if (widget.excludedUserIds.contains(user.id)) return false;
      if (query.isEmpty) return true;
      final name = user.name.toLowerCase();
      final email = user.email.toLowerCase();
      final title = user.title?.toLowerCase() ?? '';
      return name.contains(query) ||
          email.contains(query) ||
          title.contains(query);
    }).toList();

    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(LlackTheme.radiusPanel),
      ),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 560),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(widget.title, style: LlackTypography.title),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    tooltip: '닫기',
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _searchController,
                autofocus: true,
                decoration: InputDecoration(
                  hintText: '이름, 직함, 이메일로 검색...',
                  prefixIcon: Icon(
                    Icons.search,
                    size: 20,
                    color: LlackColors.muted,
                  ),
                  suffixIcon: _isSearching
                      ? const Padding(
                          padding: EdgeInsets.all(12),
                          child: SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      : null,
                ),
              ),
              if (_searchError != null) ...[
                const SizedBox(height: 8),
                Text(
                  _searchError!,
                  style: LlackTypography.caption.copyWith(
                    color: LlackColors.presenceBusy,
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Expanded(
                child: candidates.isEmpty
                    ? Center(
                        child: Text(
                          query.isEmpty ? '선택할 사람이 없습니다' : '검색 결과가 없습니다',
                          style: LlackTypography.bodySmall.copyWith(
                            color: LlackColors.muted,
                          ),
                        ),
                      )
                    : ListView.separated(
                        itemCount: candidates.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, index) {
                          final user = candidates[index];
                          final presence = state.getPresence(user.id);
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: LlackAvatar(
                              name: user.name,
                              avatarUrl: user.avatarUrl,
                              avatarColor: user.avatarColor,
                              presence: presence,
                              size: 36,
                            ),
                            title: Text(
                              user.name,
                              style: LlackTypography.subtitle.copyWith(
                                fontSize: 14,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            subtitle: Text(
                              user.title ?? user.email,
                              style: LlackTypography.caption,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            trailing: Icon(
                              Icons.chevron_right,
                              size: 20,
                              color: LlackColors.muted,
                            ),
                            onTap: () => _select(user),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// [PersonPicker]를 띄우고 선택한 사람을 돌려준다.
Future<User?> showPersonPicker(
  BuildContext context, {
  String title = '사람 선택',
  Set<String> excludedUserIds = const {},
  bool searchAllUsers = false,
}) {
  return showDialog<User>(
    context: context,
    builder: (dialogContext) => PersonPicker(
      title: title,
      excludedUserIds: excludedUserIds,
      searchAllUsers: searchAllUsers,
      onSelected: (user) => Navigator.of(dialogContext).pop(user),
    ),
  );
}
