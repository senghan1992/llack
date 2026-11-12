import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';

class TaskDialog extends StatefulWidget {
  final TaskStatus initialStatus;

  /// 편집 모드로 열 때 넘기는 할 일. null 이면 생성 모드다.
  final Task? editing;

  const TaskDialog({super.key, this.initialStatus = TaskStatus.todo, this.editing});

  @override
  State<TaskDialog> createState() => _TaskDialogState();
}

class _TaskDialogState extends State<TaskDialog> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  late TaskStatus _status;
  String? _assigneeId;
  DateTime? _dueDate;
  String? _roadmapId;
  bool _isCreating = false;

  @override
  void initState() {
    super.initState();
    final editing = widget.editing;
    if (editing != null) {
      // 편집 모드: 기존 값으로 필드를 채운다.
      _titleCtrl.text = editing.title;
      _descCtrl.text = editing.description;
      _status = editing.status;
      _assigneeId = editing.assigneeId;
      // 마감일은 로컬 기준으로 채운다.
      // (서버는 UTC 인스턴스로 주는데, 그대로 쓰면 하루 밀린다)
      _dueDate = editing.dueAt?.toLocal();
      _roadmapId = editing.roadmapId;
    } else {
      _status = widget.initialStatus;
    }
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  void _submit() async {
    final title = _titleCtrl.text.trim();
    if (title.isEmpty) return;

    setState(() => _isCreating = true);
    final state = context.read<AppState>();
    final editing = widget.editing;
    final desc = _descCtrl.text.trim();
    try {
      if (editing != null) {
        // 편집 모드: 상태는 시트 헤더의 상태 드롭다운이 담당하므로 여기서는 바꾸지 않는다.
        // (updateTask 시그니처에 status 가 없고, null 인자는 "변경 안 함" 이다)
        final ok = await state.updateTask(
          taskId: editing.id,
          title: title,
          // 설명은 항상 문자열로 넘긴다.
          // (null 은 "변경 안 함" 이라 사용자가 지운 설명이 살아남는다.
          //  빈 문자열을 보내야 서버에서 설명이 지워진다)
          description: desc,
          assigneeId: _assigneeId,
          dueAt: _dueDate,
          roadmapId: _roadmapId,
        );
        if (!ok) {
          if (mounted) {
            showAppSnackBar(context, '할 일 수정에 실패했습니다');
            setState(() => _isCreating = false);
          }
          return;
        }
      } else {
        await state.createTask(
          title: title,
          description: desc.isNotEmpty ? desc : null,
          status: _status,
          assigneeId: _assigneeId,
          dueAt: _dueDate,
          roadmapId: _roadmapId,
        );
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(
          context,
          editing != null ? '할 일 수정 실패: $e' : '할 일 생성 실패: $e',
        );
        setState(() => _isCreating = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final members = state.members;
    final roadmaps = state.activeRoadmaps;

    // 드롭다운의 현재 값은 **목록에 있는 값만** 쓸 수 있다.
    // (목록에 없는 값을 주면 Flutter 의 "exactly one item" assert 로 빨간 화면이 된다)
    // 편집 모드에서 담당자/로드맵이 아직 로드되지 않았을 수 있으므로 가드한다.
    final memberIds = members.map((m) => m.user.id).toSet();
    final selectedAssigneeId =
        (_assigneeId != null && memberIds.contains(_assigneeId)) ? _assigneeId : null;
    final roadmapIds = roadmaps.map((r) => r.id).toSet();
    final selectedRoadmapId =
        (_roadmapId != null && roadmapIds.contains(_roadmapId)) ? _roadmapId : null;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(LlackTheme.radiusPanel)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 600),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    widget.editing != null ? '할 일 수정' : '새 할 일 만들기',
                    style: LlackTypography.title,
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        controller: _titleCtrl,
                        // 편집 모드에서는 키보드를 자동으로 띄우지 않는다
                        autofocus: widget.editing == null,
                        decoration: const InputDecoration(
                          labelText: '할 일 제목',
                          hintText: '무엇을 해야 하나요?',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _descCtrl,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: '설명 (선택)',
                          hintText: '자세한 작업 내용이나 참고 링크',
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Status Dropdown — 편집 모드에서는 상태를 바꾸지 않는다.
                      // (상태 변경은 상세 시트 헤더의 상태 드롭다운이 담당한다)
                      if (widget.editing == null) ...[
                        DropdownButtonFormField<TaskStatus>(
                          initialValue: _status,
                          decoration: const InputDecoration(labelText: '상태'),
                          items: TaskStatus.values.map((s) {
                            return DropdownMenuItem(value: s, child: Text(s.label));
                          }).toList(),
                          onChanged: (v) {
                            if (v != null) setState(() => _status = v);
                          },
                        ),
                        const SizedBox(height: 12),
                      ],

                      // Assignee Dropdown — 이름이 길어도 화면을 넘지 않도록 isExpanded (§3-C-6)
                      DropdownButtonFormField<String?>(
                        initialValue: selectedAssigneeId,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: '담당자'),
                        items: [
                          const DropdownMenuItem(value: null, child: Text('담당자 없음')),
                          ...members.map((m) {
                            return DropdownMenuItem(
                              value: m.user.id,
                              child: Text(
                                '${m.user.name}${m.user.title != null ? ' (${m.user.title})' : ''}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            );
                          }),
                        ],
                        onChanged: (v) => setState(() => _assigneeId = v),
                      ),
                      const SizedBox(height: 12),

                      // Roadmap Dropdown
                      if (roadmaps.isNotEmpty) ...[
                        DropdownButtonFormField<String?>(
                          initialValue: selectedRoadmapId,
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: '로드맵'),
                          items: [
                            const DropdownMenuItem(value: null, child: Text('로드맵 없음')),
                            ...roadmaps.map((r) => DropdownMenuItem(
                                  value: r.id,
                                  child: Text(r.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                                )),
                          ],
                          onChanged: (v) => setState(() => _roadmapId = v),
                        ),
                        const SizedBox(height: 12),
                      ],

                      // Due Date Picker
                      OutlinedButton.icon(
                        icon: const Icon(Icons.calendar_today_outlined, size: 16),
                        label: Text(
                          _dueDate == null
                              ? '마감일 설정'
                              : '마감일: ${DateFormat('yyyy.MM.dd').format(_dueDate!)}',
                        ),
                        onPressed: () async {
                          final d = await showDatePicker(
                            context: context,
                            initialDate: _dueDate ?? DateTime.now().add(const Duration(days: 3)),
                            firstDate: DateTime.now().subtract(const Duration(days: 30)),
                            lastDate: DateTime(2035),
                          );
                          if (d != null) setState(() => _dueDate = d);
                        },
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('취소'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: _isCreating ? null : _submit,
                    child: _isCreating
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : Text(widget.editing != null ? '수정' : '만들기'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
