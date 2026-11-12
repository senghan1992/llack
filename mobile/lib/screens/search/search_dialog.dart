import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../responsive/screen_type.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/llack_avatar.dart';
import '../chat/chat_navigator.dart';

/// 검색 결과에서 사용자가 선택한 대상.
/// 다이얼로그는 이 값을 result 로 돌려주지만, 지금 호출부(main_shell)는 결과를
/// 사용하지 않으므로 다이얼로그가 직접 이동까지 처리한다.
class SearchSelection {
  final String? channelId;
  final String? userId;
  final String? projectId;

  /// 메시지 검색 결과에서 고른 메시지 id (그 메시지로 점프한다)
  final String? messageId;

  const SearchSelection({this.channelId, this.userId, this.projectId, this.messageId});
}

class SearchDialog extends StatefulWidget {
  const SearchDialog({super.key});

  @override
  State<SearchDialog> createState() => _SearchDialogState();
}

class _SearchDialogState extends State<SearchDialog> {
  final _controller = TextEditingController();
  Timer? _debounceTimer;
  List<SearchResult> _messageResults = [];
  bool _isSearching = false;

  /// 검색 요청 시퀀스 번호.
  /// 디바운스는 **타이머만** 취소하므로 이미 출발한 HTTP 요청은 취소되지 않는다.
  /// 느린 이전 응답이 늦게 도착해 새 검색어의 결과를 덮어쓰지 않도록
  /// 요청마다 번호를 붙이고, 더 최신 요청이 있으면 이전 응답은 버린다.
  int _searchSeq = 0;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onQueryChanged);
  }

  void _onQueryChanged() {
    _debounceTimer?.cancel();
    final query = _controller.text.trim();
    if (query.isEmpty) {
      // 검색어를 지우면 진행 중인 요청의 응답도 버린다.
      _searchSeq++;
      setState(() {
        _messageResults = [];
        _isSearching = false;
      });
      return;
    }

    _debounceTimer = Timer(const Duration(milliseconds: 300), () async {
      final seq = ++_searchSeq;
      setState(() => _isSearching = true);
      final state = context.read<AppState>();
      try {
        final res = await state.search(query);
        // 뒤에 더 최신 요청이 있으면 이전 응답은 버린다.
        if (!mounted || seq != _searchSeq) return;
        setState(() => _messageResults = res);
      } catch (_) {
        // 검색 실패는 조용히 무시하고 기존 결과를 유지한다.
      } finally {
        if (mounted && seq == _searchSeq) setState(() => _isSearching = false);
      }
    });
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final query = _controller.text.trim().toLowerCase();

    // Filter local channels, members, projects
    final matchingChannels = query.isEmpty
        ? <Channel>[]
        : state.allChannels.where((c) => c.name.toLowerCase().contains(query)).toList();

    final matchingMembers = query.isEmpty
        ? <Member>[]
        : state.members.where((m) {
            // 자기 자신에게 1:1 대화를 열면 서버가 422 로 거절하므로 제외한다.
            if (m.user.id == state.currentUser?.id) return false;
            return m.user.name.toLowerCase().contains(query) ||
                m.user.email.toLowerCase().contains(query) ||
                (m.user.title?.toLowerCase().contains(query) ?? false);
          }).toList();

    final matchingProjects = query.isEmpty
        ? <Project>[]
        : state.projects.where((p) => p.name.toLowerCase().contains(query)).toList();

    final hasAnyResults = matchingChannels.isNotEmpty ||
        matchingMembers.isNotEmpty ||
        matchingProjects.isNotEmpty ||
        _messageResults.isNotEmpty;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(LlackTheme.radiusPanel)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520, maxHeight: 580),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _controller,
                autofocus: true,
                style: LlackTypography.body,
                decoration: InputDecoration(
                  hintText: '채널, 멤버, 프로젝트, 메시지 검색...',
                  prefixIcon: const Icon(Icons.search, color: LlackColors.muted),
                  suffixIcon: _controller.text.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear, size: 18),
                          onPressed: () => _controller.clear(),
                        )
                      : null,
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: query.isEmpty
                    ? Center(
                        child: Text(
                          '검색어를 입력하면 바로 찾을 수 있습니다',
                          style: LlackTypography.caption,
                        ),
                      )
                    : (!hasAnyResults && !_isSearching)
                        ? Center(
                            child: Text(
                              '검색 결과가 없습니다',
                              style: LlackTypography.bodySmall.copyWith(color: LlackColors.muted),
                            ),
                          )
                        : ListView(
                            children: [
                              if (_isSearching)
                                const LinearProgressIndicator(
                                  minHeight: 2,
                                  color: LlackColors.accent,
                                  backgroundColor: LlackColors.surfaceWell,
                                ),

                              // Channels
                              if (matchingChannels.isNotEmpty) ...[
                                _buildCategoryHeader('채널 (${matchingChannels.length})'),
                                ...matchingChannels.map((c) => ListTile(
                                      dense: true,
                                      leading: _resultIcon(c.isPrivate ? Icons.lock_outline : Icons.tag),
                                      title: Text(c.name, style: LlackTypography.subtitle.copyWith(fontSize: 14)),
                                      subtitle: c.topic != null && c.topic!.isNotEmpty ? Text(c.topic!, style: LlackTypography.caption) : null,
                                      onTap: () {
                                        final state = context.read<AppState>();
                                        final navigator = Navigator.of(context, rootNavigator: true);
                                        final compact = FormFactor(context).isCompact;
                                        Navigator.pop(context, SearchSelection(channelId: c.id));
                                        ChatNavigator.openChannel(
                                          state: state,
                                          navigator: navigator,
                                          channelId: c.id,
                                          push: compact,
                                        );
                                      },
                                    )),
                              ],

                              // Members
                              if (matchingMembers.isNotEmpty) ...[
                                _buildCategoryHeader('멤버 (${matchingMembers.length})'),
                                ...matchingMembers.map((m) => ListTile(
                                      dense: true,
                                      // 사람은 아바타(원형), 나머지는 사각 아이콘 배지로 구분한다.
                                      leading: LlackAvatar(
                                        name: m.user.name,
                                        avatarUrl: m.user.avatarUrl,
                                        avatarColor: m.user.avatarColor,
                                        presence: state.getPresence(m.user.id),
                                        size: 32,
                                        fontSize: 12,
                                      ),
                                      title: Text(m.user.name, style: LlackTypography.subtitle.copyWith(fontSize: 14)),
                                      subtitle: Text(m.user.title ?? m.user.email, style: LlackTypography.caption),
                                      onTap: () async {
                                        final appState = context.read<AppState>();
                                        final navigator = Navigator.of(context, rootNavigator: true);
                                        final messenger = ScaffoldMessenger.of(context);
                                        final compact = FormFactor(context).isCompact;
                                        Navigator.pop(context, SearchSelection(userId: m.user.id));
                                        try {
                                          // 다이얼로그를 닫은 뒤에 context 를 쓰면 push 가 실행되지 않는다.
                                          // navigator 를 미리 캡처해 두었기 때문에 대화가 정상적으로 열린다.
                                          await ChatNavigator.openDm(
                                            state: appState,
                                            navigator: navigator,
                                            userId: m.user.id,
                                            push: compact,
                                          );
                                        } catch (error) {
                                          messenger.showSnackBar(
                                            SnackBar(
                                              content: Text(ChatNavigator.describeDmError(error)),
                                            ),
                                          );
                                        }
                                      },
                                    )),
                              ],

                              // Projects
                              if (matchingProjects.isNotEmpty) ...[
                                _buildCategoryHeader('프로젝트 (${matchingProjects.length})'),
                                ...matchingProjects.map((p) => ListTile(
                                      dense: true,
                                      leading: _resultIcon(Icons.view_kanban_outlined),
                                      title: Text(p.name, style: LlackTypography.subtitle.copyWith(fontSize: 14)),
                                      subtitle: p.description.isNotEmpty ? Text(p.description, style: LlackTypography.caption) : null,
                                      onTap: () async {
                                        final appState = context.read<AppState>();
                                        Navigator.pop(context, SearchSelection(projectId: p.id));
                                        await appState.selectProject(p);
                                        // 프로젝트 탭으로 이동해야 사용자가 결과를 볼 수 있다.
                                        appState.goToTab(2);
                                      },
                                    )),
                              ],

                              // Message search results
                              if (_messageResults.isNotEmpty) ...[
                                _buildCategoryHeader('메시지 (${_messageResults.length})'),
                                ..._messageResults.map((r) => ListTile(
                                      dense: true,
                                      leading: _resultIcon(Icons.chat_bubble_outline),
                                      title: Text(r.message.body, style: LlackTypography.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                                      subtitle: Text(
                                        '#${r.channel.name} · ${r.message.author.name}',
                                        style: LlackTypography.caption,
                                      ),
                                      onTap: () {
                                        final appState = context.read<AppState>();
                                        final navigator = Navigator.of(context, rootNavigator: true);
                                        final compact = FormFactor(context).isCompact;
                                        Navigator.pop(context, SearchSelection(
                                          channelId: r.channel.id,
                                          messageId: r.message.id,
                                        ));
                                        // 찾은 메시지가 화면에 보이도록 점프한다
                                        ChatNavigator.openChannel(
                                          state: appState,
                                          navigator: navigator,
                                          channelId: r.channel.id,
                                          messageId: r.message.id,
                                          push: compact,
                                        );
                                      },
                                    )),
                              ],
                            ],
                          ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 채널/프로젝트/메시지 결과 아이콘.
  /// 사람은 아바타(원형)를 쓰므로 사각 배지로 서로 구분된다.
  Widget _resultIcon(IconData icon) {
    return Container(
      width: 32,
      height: 32,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: LlackColors.accentSoft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(icon, size: 16, color: LlackColors.accentDeep),
    );
  }

  Widget _buildCategoryHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 4, left: 8),
      child: Text(
        title,
        style: LlackTypography.caption.copyWith(fontWeight: FontWeight.w700, color: LlackColors.muted),
      ),
    );
  }
}
