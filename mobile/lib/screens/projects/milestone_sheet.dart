import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../widgets/app_snack_bar.dart';

/// 마일스톤이 쓸 수 있는 색. (데스크톱 MilestoneDialog 의 PRESET_COLORS 와 같다)
///
/// 색은 테마 색이 아니라 데이터다. 회사가 고른 색을 마일스톤이 그대로 쓴다.
const List<String> kMilestonePresetColors = [
  '#4f6cff',
  '#10b981',
  '#f43f5e',
  '#f59e0b',
  '#8b5cf6',
  '#06b6d4',
];

/// 마일스톤 색(hex 문자열) 을 색으로 바꾼다.
///
/// 서버는 색을 '#4f6cff' 처럼 문자열로 준다.
/// 알 수 없는 값이면 액센트 색으로 떨어진다.
Color milestoneColor(String? hex) {
  final value = (hex ?? '').replaceAll('#', '').trim();
  if (value.isEmpty) return LlackColors.accent;
  final parsed = int.tryParse(value.length == 6 ? 'FF$value' : value, radix: 16);
  if (parsed == null) return LlackColors.accent;
  return Color(parsed);
}

/// 마일스톤 만들기/수정 대화상자를 연다.
///
/// [milestone] 가 null 이면 새로 만드는 것이고, 있으면 그 마일스톤을 고치는 것이다.
Future<void> showMilestoneDialog(BuildContext context, {Milestone? milestone}) {
  return showDialog<void>(
    context: context,
    builder: (_) => MilestoneDialog(milestone: milestone),
  );
}

/// 마일스톤 패널 — 보드의 다른 얼굴.
///
/// 마일스톤은 상태 열(칸)이 아니라 **기한이 있는 목표** 다.
/// 기간과 진행률, 거기에 붙은 할 일이 함께 보인다.
class MilestonePanel extends StatelessWidget {
  const MilestonePanel({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final milestones = state.activeMilestones;
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Row(
            children: [
              Expanded(
                child: Text('마일스톤', style: theme.textTheme.titleMedium),
              ),
              ElevatedButton.icon(
                icon: const Icon(Icons.add, size: 16),
                label: const Text('추가'),
                onPressed: () => showMilestoneDialog(context),
              ),
            ],
          ),
        ),
        Expanded(
          child: milestones.isEmpty
              ? const _MilestoneEmpty()
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 96),
                  itemCount: milestones.length,
                  itemBuilder: (context, i) => _MilestoneCard(milestone: milestones[i]),
                ),
        ),
      ],
    );
  }
}

/// 프로젝트 타임라인 — 마일스톤 기간을 가로 막대로 보여준다.
///
/// 마일스톤은 "언제부터 언제까지" 라는 기간이 있기 때문에,
/// 기간을 한눈에 보면 어느 것이 겹치는지 알 수 있다.
class TimelinePanel extends StatelessWidget {
  const TimelinePanel({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final milestones = state.activeMilestones;
    final theme = Theme.of(context);

    if (milestones.isEmpty) {
      return LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Text(
                '타임라인에 표시할 마일스톤이 없습니다',
                style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
              ),
            ),
          ),
        ),
      );
    }

    // 전체 기간 (가장 이른 시작 ~ 가장 늦은 종료)
    var earliest = milestones.first.startAt;
    var latest = milestones.first.endAt;
    for (final m in milestones) {
      if (m.startAt.isBefore(earliest)) earliest = m.startAt;
      if (m.endAt.isAfter(latest)) latest = m.endAt;
    }
    // 하루짜리 마일스톤도 그려지도록 폭을 최소 1일로 둔다.
    final totalMs = latest.difference(earliest).inMilliseconds <= 0
        ? const Duration(days: 1).inMilliseconds
        : latest.difference(earliest).inMilliseconds;

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
      itemCount: milestones.length,
      itemBuilder: (context, i) {
        final m = milestones[i];
        final color = milestoneColor(m.color);
        final left = m.startAt.difference(earliest).inMilliseconds / totalMs;
        final width = m.endAt.difference(m.startAt).inMilliseconds / totalMs;
        return Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      m.title,
                      style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w700),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    '${_shortDate(m.startAt)} – ${_shortDate(m.endAt)}',
                    style: theme.textTheme.labelSmall,
                  ),
                ],
              ),
              const SizedBox(height: 6),
              LayoutBuilder(
                builder: (context, constraints) => Stack(
                  children: [
                    Container(
                      height: 16,
                      decoration: BoxDecoration(
                        color: LlackColors.surfaceWell,
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    Positioned(
                      left: constraints.maxWidth * left.clamp(0.0, 1.0),
                      // 하루짜리 기간도 보이게 최소 폭을 준다.
                      width: (constraints.maxWidth * width).clamp(8.0, constraints.maxWidth),
                      top: 0,
                      bottom: 0,
                      child: Container(
                        decoration: BoxDecoration(
                          color: color,
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  static String _shortDate(DateTime value) => DateFormat('yy.MM.dd').format(value.toLocal());
}

/// 마일스톤이 하나도 없을 때의 안내.
class _MilestoneEmpty extends StatelessWidget {
  const _MilestoneEmpty();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                   Icon(Icons.flag_outlined, size: 28, color: LlackColors.muted),
                  const SizedBox(height: 12),
                  Text(
                    '이 프로젝트에는 마일스톤이 없습니다',
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '기한이 있는 목표를 마일스톤으로 만들고, 그에 닿는 할 일을 연결해 보세요.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 마일스톤 한 장.
class _MilestoneCard extends StatelessWidget {
  final Milestone milestone;

  const _MilestoneCard({required this.milestone});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = milestoneColor(milestone.color);
    final progress = milestone.progress.clamp(0, 100).toDouble();

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    milestone.title,
                    style: theme.textTheme.titleMedium,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  tooltip: '마일스톤 수정',
                  constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                  onPressed: () => showMilestoneDialog(context, milestone: milestone),
                ),
                IconButton(
                  icon: Icon(Icons.delete_outline, size: 18, color: LlackColors.presenceBusy),
                  tooltip: '마일스톤 삭제',
                  onPressed: () => _confirmDelete(context),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${_date(milestone.startAt)} – ${_date(milestone.endAt)}',
              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: progress / 100,
                      minHeight: 6,
                      backgroundColor: LlackColors.surfaceWell,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text('${progress.round()}%', style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              milestone.taskCount > 0
                  ? '할 일 ${milestone.taskCount}개 · 완료 ${milestone.doneCount}개'
                  : '연결된 할 일 없음',
              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
            ),
            if (milestone.description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                milestone.description,
                style: theme.textTheme.bodySmall,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _date(DateTime value) => DateFormat('yyyy.MM.dd').format(value.toLocal());

  /// 삭제는 확인을 한 뒤에 한다.
  Future<void> _confirmDelete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('마일스톤 삭제'),
        content: Text('\'${milestone.title}\' 마일스톤을 삭제할까요?\n연결된 할 일은 그대로 남습니다.'),
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
    if (confirmed != true || !context.mounted) return;

    final state = context.read<AppState>();
    final ok = await state.deleteMilestone(milestone.id);
    if (!context.mounted) return;
    if (!ok) showAppSnackBar(context, '마일스톤을 삭제하지 못했습니다');
  }
}

/// 마일스톤 대화상자 — 만드는 것과 고치는 것이 같은 대화상자다.
///
/// 제목 · 기간 · 설명 · 색 · 진행률 · 붙어 있는 할 일을 한 번에 다룬다.
class MilestoneDialog extends StatefulWidget {
  /// 고칠 마일스톤. null 이면 새로 만드는 것이다.
  final Milestone? milestone;

  const MilestoneDialog({super.key, this.milestone});

  @override
  State<MilestoneDialog> createState() => _MilestoneDialogState();
}

class _MilestoneDialogState extends State<MilestoneDialog> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();

  DateTime? _startAt;
  DateTime? _endAt;
  String _color = kMilestonePresetColors.first;

  /// 수동 진행률(%). 할 일이 하나도 없을 때만 손으로 고른다.
  int _progress = 0;

  /// 이 마일스톤에 붙은 할 일 id
  final Set<String> _pickedTaskIds = {};

  bool _isSaving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final milestone = widget.milestone;
    if (milestone == null) {
      _startAt = DateTime.now();
      _endAt = DateTime.now().add(const Duration(days: 14));
      return;
    }
    _titleCtrl.text = milestone.title;
    _descCtrl.text = milestone.description;
    // 서버는 UTC 인스턴스로 준다. 하루 밀리지 않게 로컬 날짜로 채운다.
    _startAt = milestone.startAt.toLocal();
    _endAt = milestone.endAt.toLocal();
    _color = milestone.color.isEmpty ? kMilestonePresetColors.first : milestone.color;
    _progress = milestone.progress.round().clamp(0, 100);
    // 붙어 있는 할 일은 "이 마일스톤을 달고 있는 카드" 로 알 수 있다.
    final tasks = context.read<AppState>().activeProjectTasks;
    for (final task in tasks) {
      if (task.milestoneId == milestone.id) _pickedTaskIds.add(task.id);
    }
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  /// 고른 할 일들. (진행률은 여기서 자동으로 계산한다)
  List<Task> _linkedTasks(List<Task> tasks) =>
      tasks.where((t) => _pickedTaskIds.contains(t.id)).toList();

  Future<void> _pickDate({required bool isStart}) async {
    final current = isStart ? _startAt : _endAt;
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime(2035),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _error = null;
      if (isStart) {
        _startAt = picked;
        // 기간은 시작일보다 먼저 끝날 수 없다. 함께 고르면 끝일을 맞춰준다.
        if (_endAt != null && _endAt!.isBefore(picked)) _endAt = picked;
      } else {
        _endAt = picked;
      }
    });
  }

  Future<void> _save() async {
    final title = _titleCtrl.text.trim();
    if (title.isEmpty) {
      setState(() => _error = '마일스톤 제목을 입력해 주세요');
      return;
    }
    final startAt = _startAt;
    final endAt = _endAt;
    if (startAt == null || endAt == null) {
      setState(() => _error = '시작일과 종료일을 입력해 주세요');
      return;
    }
    if (endAt.isBefore(startAt)) {
      setState(() => _error = '종료일은 시작일보다 빠를 수 없습니다');
      return;
    }
    if (_isSaving) return;

    setState(() {
      _isSaving = true;
      _error = null;
    });

    final state = context.read<AppState>();
    final taskIds = _pickedTaskIds.toList();
    try {
      final milestone = widget.milestone;
      if (milestone == null) {
        await state.createMilestone(
          title: title,
          startAt: startAt,
          endAt: endAt,
          description: _descCtrl.text.trim(),
          color: _color,
          progress: _progress,
          taskIds: taskIds,
        );
      } else {
        final ok = await state.updateMilestone(
          milestoneId: milestone.id,
          title: title,
          startAt: startAt,
          endAt: endAt,
          description: _descCtrl.text.trim(),
          color: _color,
          progress: _progress,
          taskIds: taskIds,
        );
        if (!ok) {
          if (!mounted) return;
          setState(() {
            _isSaving = false;
            _error = '마일스톤을 수정하지 못했습니다';
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
        _error = '마일스톤을 저장하지 못했습니다: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = context.watch<AppState>();
    final tasks = state.activeProjectTasks;
    final linked = _linkedTasks(tasks);
    final auto = linked.isNotEmpty;
    final doneCount = linked.where((t) => t.status == TaskStatus.done).length;
    final autoPercent = linked.isEmpty ? 0 : (doneCount * 100 / linked.length).round();

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480, maxHeight: 620),
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
                    widget.milestone == null ? '새 마일스톤' : '마일스톤',
                    style: theme.textTheme.titleLarge,
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_error != null) ...[
                        Text(
                          _error!,
                          style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.presenceBusy),
                        ),
                        const SizedBox(height: 12),
                      ],
                      TextField(
                        controller: _titleCtrl,
                        autofocus: widget.milestone == null,
                        decoration: const InputDecoration(
                          labelText: '마일스톤 제목',
                          hintText: '예: 1분기 리뉴얼',
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              icon: const Icon(Icons.calendar_today_outlined, size: 16),
                              label: Text(
                                _startAt == null ? '시작일' : '시작일: ${_dateLabel(_startAt!)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              onPressed: () => _pickDate(isStart: true),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: OutlinedButton.icon(
                              icon: const Icon(Icons.event_outlined, size: 16),
                              label: Text(
                                _endAt == null ? '종료일' : '종료일: ${_dateLabel(_endAt!)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              onPressed: () => _pickDate(isStart: false),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _descCtrl,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: '설명 (선택)',
                          hintText: '마일스톤에 대한 간단한 설명',
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text('색상', style: theme.textTheme.labelMedium),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: kMilestonePresetColors.map((hex) {
                          final selected = hex.toLowerCase() == _color.toLowerCase();
                          return GestureDetector(
                            onTap: () => setState(() => _color = hex),
                            child: Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: milestoneColor(hex),
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: selected ? LlackColors.ink : Colors.transparent,
                                  width: 2,
                                ),
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                      const SizedBox(height: 16),
                      Text('진행률', style: theme.textTheme.labelMedium),
                      const SizedBox(height: 4),
                      if (auto)
                        Text(
                          '✓ 연결된 할 일 기반 자동 계산 ($doneCount/${linked.length} 완료) · $autoPercent%',
                          style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                        )
                      else ...[
                        Slider(
                          value: _progress.toDouble(),
                          min: 0,
                          max: 100,
                          divisions: 20,
                          label: '$_progress%',
                          onChanged: (v) => setState(() => _progress = v.round()),
                        ),
                        Text(
                          '수동 진행률 $_progress% (연결된 할 일이 없을 때 사용)',
                          style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
                        ),
                      ],
                      if (tasks.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        Text('할 일 연결', style: theme.textTheme.labelMedium),
                        const SizedBox(height: 4),
                        // ListTile 은 자기 Material 안에서 그려야 ink 가 보인다.
                        Material(
                          color: LlackColors.surfaceWell,
                          borderRadius: BorderRadius.circular(8),
                          clipBehavior: Clip.antiAlias,
                          child: Column(
                            children: tasks.map((task) {
                              return CheckboxListTile(
                                dense: true,
                                value: _pickedTaskIds.contains(task.id),
                                controlAffinity: ListTileControlAffinity.leading,
                                title: Text(
                                  task.title,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall,
                                ),
                                onChanged: (checked) {
                                  setState(() {
                                    if (checked == true) {
                                      _pickedTaskIds.add(task.id);
                                    } else {
                                      _pickedTaskIds.remove(task.id);
                                    }
                                  });
                                },
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Row(
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
                        : Text(widget.milestone == null ? '추가' : '수정'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _dateLabel(DateTime value) => DateFormat('yyyy.MM.dd').format(value);
}
