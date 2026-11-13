import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/app_snack_bar.dart';
import '../../widgets/llack_avatar.dart';

/// 프로젝트 설정 시트 — 만드는 것과 고치는 것이 같은 시트다.
///
/// 편집 항목: 이름 · 설명 · 연결 채널 · 멤버 · 보관 · 삭제.
/// (데스크톱 ProjectDialog 와 같은 항목들이다)
class ProjectSettingsSheet extends StatefulWidget {
  /// 고칠 프로젝트. null 이면 새로 만드는 것이다.
  final Project? project;

  const ProjectSettingsSheet({super.key, this.project});

  @override
  State<ProjectSettingsSheet> createState() => _ProjectSettingsSheetState();
}

class _ProjectSettingsSheetState extends State<ProjectSettingsSheet> {
  final _nameCtrl = TextEditingController();
  final _descCtrl = TextEditingController();

  String? _channelId;

  /// 함께하는 사람 id
  final Set<String> _memberIds = {};

  bool _isArchived = false;
  bool _isSaving = false;
  String? _error;

  /// 연결 채널 필드를 원래 값으로 되돌릴 때 키를 바꾼다.
  ///
  /// (드롭다운은 고른 값을 스스로 들고 있으므로, 고르지 못하게 되돌릴 때
  ///  필드를 새로 만들어야 화면도 따라온다)
  int _channelFieldKey = 0;

  @override
  void initState() {
    super.initState();
    final project = widget.project;
    if (project == null) {
      // 새로 만들 때는 만든 사람이 자동으로 함께한다. (데스크톱과 같다)
      final me = context.read<AppState>().currentUser;
      if (me != null) _memberIds.add(me.id);
      return;
    }
    _nameCtrl.text = project.name;
    _descCtrl.text = project.description;
    _channelId = project.channelId;
    _isArchived = project.isArchived;
    for (final member in project.members) {
      _memberIds.add(member.id);
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  /// 저장한다. (새로 만들기와 고치기)
  Future<void> _save() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty) {
      setState(() => _error = '프로젝트 이름을 입력해 주세요');
      return;
    }
    if (_isSaving) return;

    setState(() {
      _isSaving = true;
      _error = null;
    });

    final state = context.read<AppState>();
    final project = widget.project;
    try {
      if (project == null) {
        await state.createProject(
          name: name,
          description: _descCtrl.text.trim(),
          channelId: _channelId,
          memberIds: _memberIds.toList(),
        );
      } else {
        final ok = await state.updateProject(
          projectId: project.id,
          name: name,
          description: _descCtrl.text.trim(),
          // 채널을 "연결 없음" 으로 되돌리는 것은 코어 API 가 null 을
          // "변경 안 함" 으로 보아 지원하지 않는다. (지운 자리가 곧바로 붙는다)
          channelId: _channelId,
          isArchived: _isArchived,
        );
        if (!ok) {
          if (!mounted) return;
          setState(() {
            _isSaving = false;
            _error = '프로젝트를 저장하지 못했습니다';
          });
          return;
        }
      }
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSaving = false;
        _error = '프로젝트를 저장하지 못했습니다: $e';
      });
    }
  }

  /// 프로젝트를 지운다. (확인 한 뒤에)
  Future<void> _delete() async {
    final project = widget.project;
    if (project == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('프로젝트 삭제'),
        content: Text('\'${project.name}\' 프로젝트를 삭제할까요?\n이 안의 할 일과 마일스톤도 함께 사라집니다.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: LlackColors.presenceBusy),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final state = context.read<AppState>();
    final ok = await state.deleteProject(project.id);
    if (!mounted) return;
    if (!ok) {
      showAppSnackBar(context, '프로젝트를 삭제하지 못했습니다');
      return;
    }
    Navigator.pop(context);
  }

  /// 멤버를 넣는다. (고치는 중이면 곧바로 서버에 반영된다)
  Future<void> _addMember(String userId) async {
    final project = widget.project;
    setState(() => _memberIds.add(userId));
    if (project == null) return; // 새로 만들 때는 저장할 때 한꺼번에 넣는다.

    final state = context.read<AppState>();
    final ok = await state.addProjectMember(project.id, userId);
    if (!mounted) return;
    if (!ok) {
      setState(() => _memberIds.remove(userId));
      showAppSnackBar(context, '멤버를 추가하지 못했습니다');
    }
  }

  /// 멤버를 뺀다.
  Future<void> _removeMember(String userId) async {
    final project = widget.project;
    setState(() => _memberIds.remove(userId));
    if (project == null) return; // 새로 만들 때는 저장할 때 한꺼번에 넣는다.

    final state = context.read<AppState>();
    final ok = await state.removeProjectMember(project.id, userId);
    if (!mounted) return;
    if (!ok) {
      setState(() => _memberIds.add(userId));
      showAppSnackBar(context, '멤버를 빼지 못했습니다');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = context.watch<AppState>();
    final project = widget.project;

    // 워크스페이스의 사람들 중 아직 함께하지 않는 사람
    final workspaceMembers = state.members;
    final candidates = workspaceMembers
        .where((m) => !_memberIds.contains(m.user.id))
        .map((m) => m.user)
        .toList();
    final selected = workspaceMembers
        .where((m) => _memberIds.contains(m.user.id))
        .map((m) => m.user)
        .toList();

    // 드롭다운의 값은 목록에 있는 값만 쓸 수 있다.
    // (목록에 없는 값을 주면 Flutter 의 "exactly one item" assert 로 빨간 화면이 된다)
    final channelIds = state.channels.map((c) => c.id).toSet();
    final selectedChannelId = (_channelId != null && channelIds.contains(_channelId)) ? _channelId! : '';

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      // ListTile 이 자기 Material 안에서 그려지도록 시트 바탕을 Material 로 감싼다.
      child: Material(
        color: LlackColors.surfaceRaise,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        clipBehavior: Clip.antiAlias,
        child: SafeArea(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 손잡이
                Center(
                  child: Container(
                    width: 36,
                    height: 4,
                    margin: const EdgeInsets.symmetric(vertical: 8),
                    decoration: BoxDecoration(
                      color: LlackColors.rule,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 8, 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          project == null ? '새 프로젝트' : '프로젝트 설정',
                          style: theme.textTheme.titleLarge,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, size: 20),
                        onPressed: () => Navigator.pop(context),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (_error != null) ...[
                          Text(
                            _error!,
                            style: theme.textTheme.bodySmall
                                ?.copyWith(color: LlackColors.presenceBusy),
                          ),
                          const SizedBox(height: 12),
                        ],
                        TextField(
                          controller: _nameCtrl,
                          autofocus: project == null,
                          decoration: const InputDecoration(
                            labelText: '프로젝트 이름',
                            hintText: '예: 2026 하반기 리뉴얼',
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _descCtrl,
                          maxLines: 3,
                          decoration: const InputDecoration(
                            labelText: '설명',
                            hintText: '프로젝트 목적 및 개요',
                          ),
                        ),
                        const SizedBox(height: 16),
                        DropdownButtonFormField<String>(
                          key: ValueKey('channel-$_channelFieldKey'),
                          initialValue: selectedChannelId,
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: '연결 채널'),
                          items: [
                            const DropdownMenuItem(value: '', child: Text('연결 없음')),
                            ...state.channels.map((c) => DropdownMenuItem(
                                  value: c.id,
                                  child: Text(
                                    c.name,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                )),
                          ],
                          onChanged: (v) {
                            // 채널을 "연결 없음" 으로 되돌리는 것은 코어 API 가
                            // null 을 "변경 안 함" 으로 보아 지원하지 않는다.
                            if (v == '' && _channelId != null) {
                              showAppSnackBar(context, '연결 채널을 지우는 것은 아직 지원되지 않습니다');
                              setState(() => _channelFieldKey++);
                              return;
                            }
                            setState(() => _channelId = (v == null || v.isEmpty) ? null : v);
                          },
                        ),
                        const SizedBox(height: 16),
                        Text('함께하는 사람', style: theme.textTheme.labelMedium),
                        const SizedBox(height: 8),
                        if (selected.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Text(
                              '아직 함께하는 사람이 없습니다.',
                              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                            ),
                          )
                        else
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: selected.map((user) {
                              return Container(
                                padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
                                decoration: BoxDecoration(
                                  color: LlackColors.surfaceWell,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    LlackAvatar(name: user.name, size: 22, fontSize: 10),
                                    const SizedBox(width: 6),
                                    Text(user.name, style: theme.textTheme.bodySmall),
                                    IconButton(
                                      icon: const Icon(Icons.close, size: 14),
                                      tooltip: '빼기',
                                      visualDensity: VisualDensity.compact,
                                      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                                      padding: EdgeInsets.zero,
                                      onPressed: () => _removeMember(user.id),
                                    ),
                                  ],
                                ),
                              );
                            }).toList(),
                          ),
                        if (candidates.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              Expanded(
                                child: Text('사람 추가', style: theme.textTheme.bodySmall),
                              ),
                              Flexible(
                                child: DropdownButton<String>(
                                  isExpanded: true,
                                  hint: const Text('고르세요'),
                                  items: candidates
                                      .map((u) => DropdownMenuItem(
                                            value: u.id,
                                            child: Text(
                                              u.name,
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                          ))
                                      .toList(),
                                  onChanged: (v) {
                                    if (v != null) _addMember(v);
                                  },
                                ),
                              ),
                            ],
                          ),
                        ],
                        if (project != null) ...[
                          const SizedBox(height: 8),
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            value: _isArchived,
                            title: const Text('보관'),
                            subtitle: Text(
                              '보관하면 목록에서 물러난다. 나중에 되돌릴 수 있다.',
                              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                            ),
                            onChanged: (v) => setState(() => _isArchived = v),
                          ),
                        ],
                        if (project != null) ...[
                          const SizedBox(height: 8),
                          OutlinedButton.icon(
                            icon: Icon(Icons.delete_outline, size: 18, color: LlackColors.presenceBusy),
                            label: const Text('프로젝트 삭제'),
                            style: OutlinedButton.styleFrom(foregroundColor: LlackColors.presenceBusy),
                            onPressed: _delete,
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('취소'),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton(
                        onPressed: _isSaving ? null : _save,
                        child: _isSaving
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : Text(project == null ? '만들기' : '저장'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
