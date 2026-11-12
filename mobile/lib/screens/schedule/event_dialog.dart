import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_theme.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';

class EventDialog extends StatefulWidget {
  final DateTime initialDate;

  /// 수정 모드. 있으면 기존 일정 값으로 초기화하고 "수정" 으로 저장한다.
  final ScheduleEvent? editing;

  const EventDialog({super.key, required this.initialDate, this.editing});

  @override
  State<EventDialog> createState() => _EventDialogState();
}

class _EventDialogState extends State<EventDialog> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _locationCtrl = TextEditingController();

  late DateTime _startDate;
  late TimeOfDay _startTime;
  late DateTime _endDate;
  late TimeOfDay _endTime;
  bool _allDay = false;
  bool _isPrivate = false;
  String? _selectedChannelId;
  final Set<String> _selectedAttendeeIds = {};
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    final editing = widget.editing;
    if (editing != null) {
      // 수정 모드: 기존 일정 값으로 필드를 초기화한다
      _titleCtrl.text = editing.title;
      _descCtrl.text = editing.description;
      _locationCtrl.text = editing.location;
      _startDate = editing.startsAt.toLocal();
      _startTime = TimeOfDay.fromDateTime(editing.startsAt.toLocal());
      _endDate = editing.endsAt.toLocal();
      _endTime = TimeOfDay.fromDateTime(editing.endsAt.toLocal());
      _allDay = editing.allDay;
      _isPrivate = editing.isPrivate;
      _selectedChannelId = editing.channelId;
      _selectedAttendeeIds.addAll(editing.attendees.map((a) => a.user.id));
      return;
    }
    _startDate = widget.initialDate;
    _startTime = const TimeOfDay(hour: 10, minute: 0);
    _endDate = widget.initialDate;
    _endTime = const TimeOfDay(hour: 11, minute: 0);
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    _locationCtrl.dispose();
    super.dispose();
  }

  void _submit() async {
    final title = _titleCtrl.text.trim();
    if (title.isEmpty) return;

    setState(() => _isSubmitting = true);
    final state = context.read<AppState>();

    final start = DateTime(
      _startDate.year,
      _startDate.month,
      _startDate.day,
      _allDay ? 0 : _startTime.hour,
      _allDay ? 0 : _startTime.minute,
    );
    final end = DateTime(
      _endDate.year,
      _endDate.month,
      _endDate.day,
      _allDay ? 23 : _endTime.hour,
      _allDay ? 59 : _endTime.minute,
    );

    try {
      final editing = widget.editing;
      if (editing != null) {
        // 수정 모드: null 인자는 "변경 안 함" 이라 빈 문자열로 비워준다
        // (사용자가 지운 설명/장소를 실제로 지울 수 있게 하려면 "" 를 보내야 한다)
        final ok = await state.updateEvent(
          eventId: editing.id,
          title: title,
          description: _descCtrl.text.trim(),
          location: _locationCtrl.text.trim(),
          startsAt: start,
          endsAt: end,
          allDay: _allDay,
          isPrivate: _isPrivate,
          channelId: _selectedChannelId,
          attendeeIds: _selectedAttendeeIds.toList(),
        );
        if (!mounted) return;
        if (!ok) {
          // 실패하면 대화상자를 닫지 않고 입력값을 유지한 채 알린다
          setState(() => _isSubmitting = false);
          showAppSnackBar(context, '일정 수정 실패: 서버에 저장하지 못했습니다');
          return;
        }
        Navigator.pop(context);
        return;
      }

      await state.createEvent(
        title: title,
        description: _descCtrl.text.trim().isNotEmpty ? _descCtrl.text.trim() : null,
        location: _locationCtrl.text.trim().isNotEmpty ? _locationCtrl.text.trim() : null,
        startsAt: start,
        endsAt: end,
        allDay: _allDay,
        isPrivate: _isPrivate,
        channelId: _selectedChannelId,
        attendeeIds: _selectedAttendeeIds.isNotEmpty ? _selectedAttendeeIds.toList() : null,
      );
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, widget.editing != null ? '일정 수정 실패: $e' : '일정 등록 실패: $e');
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final channels = state.channels;
    final members = state.members;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(LlackTheme.radiusPanel)),
      backgroundColor: LlackColors.surfaceRaise,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 500, maxHeight: 650),
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
                    widget.editing != null ? '일정 수정' : '새 일정 만들기',
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
                        autofocus: true,
                        decoration: const InputDecoration(
                          labelText: '일정 제목',
                          hintText: '예: 주간 스프린트 회의',
                        ),
                      ),
                      const SizedBox(height: 12),
                      SwitchListTile(
                        value: _allDay,
                        onChanged: (v) => setState(() => _allDay = v),
                        title: const Text('하루 종일', style: LlackTypography.body),
                        contentPadding: EdgeInsets.zero,
                        activeTrackColor: LlackColors.accent,
                      ),
                      const SizedBox(height: 8),

                      // Start & End Pickers
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () async {
                                final d = await showDatePicker(
                                  context: context,
                                  initialDate: _startDate,
                                  firstDate: DateTime(2020),
                                  lastDate: DateTime(2035),
                                );
                                if (d != null) {
                                  setState(() {
                                    _startDate = d;
                                    if (_endDate.isBefore(d)) _endDate = d;
                                  });
                                }
                              },
                              child: Text(DateFormat('yyyy.MM.dd').format(_startDate)),
                            ),
                          ),
                          if (!_allDay) ...[
                            const SizedBox(width: 8),
                            Expanded(
                              child: OutlinedButton(
                                onPressed: () async {
                                  final t = await showTimePicker(context: context, initialTime: _startTime);
                                  if (t != null) setState(() => _startTime = t);
                                },
                                child: Text(_startTime.format(context)),
                              ),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () async {
                                final d = await showDatePicker(
                                  context: context,
                                  initialDate: _endDate,
                                  firstDate: _startDate,
                                  lastDate: DateTime(2035),
                                );
                                if (d != null) setState(() => _endDate = d);
                              },
                              child: Text(DateFormat('yyyy.MM.dd').format(_endDate)),
                            ),
                          ),
                          if (!_allDay) ...[
                            const SizedBox(width: 8),
                            Expanded(
                              child: OutlinedButton(
                                onPressed: () async {
                                  final t = await showTimePicker(context: context, initialTime: _endTime);
                                  if (t != null) setState(() => _endTime = t);
                                },
                                child: Text(_endTime.format(context)),
                              ),
                            ),
                          ],
                        ],
                      ),

                      const SizedBox(height: 12),
                      TextField(
                        controller: _locationCtrl,
                        decoration: const InputDecoration(
                          labelText: '장소',
                          hintText: '예: 3층 회의실 B 또는 온라인 링크',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _descCtrl,
                        maxLines: 2,
                        decoration: const InputDecoration(
                          labelText: '설명',
                          hintText: '회의 안건이나 준비 사항',
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Channel connection dropdown
                      // 선택한 채널이 목록에서 사라지면(다른 사람이 삭제, 워크스페이스 전환 등)
                      // DropdownButton assertion 으로 빨간 화면이 된다.
                      // 그래서 값은 매 빌드마다 유효성만 검사해서 넘긴다.
                      _ChannelDropdownField(
                        channels: channels,
                        value: _selectedChannelId,
                        onChanged: (v) => setState(() => _selectedChannelId = v),
                      ),
                      const SizedBox(height: 12),

                      SwitchListTile(
                        value: _isPrivate,
                        onChanged: (v) => setState(() => _isPrivate = v),
                        title: const Text('비공개 일정', style: LlackTypography.body),
                        subtitle: const Text('초대받은 참석자만 일정을 봅니다', style: LlackTypography.caption),
                        contentPadding: EdgeInsets.zero,
                        activeTrackColor: LlackColors.accent,
                      ),

                      const SizedBox(height: 8),
                      Text('참석자 (${_selectedAttendeeIds.length}명)', style: LlackTypography.subtitle.copyWith(fontSize: 13)),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: members.map((m) {
                          final isSel = _selectedAttendeeIds.contains(m.user.id);
                          return FilterChip(
                            label: Text(m.user.name),
                            selected: isSel,
                            selectedColor: LlackColors.accentSoft,
                            checkmarkColor: LlackColors.accent,
                            onSelected: (selected) {
                              setState(() {
                                if (selected) {
                                  _selectedAttendeeIds.add(m.user.id);
                                } else {
                                  _selectedAttendeeIds.remove(m.user.id);
                                }
                              });
                            },
                          );
                        }).toList(),
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
                    onPressed: _isSubmitting ? null : _submit,
                    child: _isSubmitting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : Text(widget.editing != null ? '수정' : '등록'),
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

/// 연결할 채널 드롭다운.
///
/// DropdownButtonFormField 는 `initialValue` 를 **매 빌드마다** assert 로 검사한다.
/// 그래서 선택한 채널이 목록에서 사라지면
/// "There should be exactly one item with [DropdownButton]'s value" assert 가 터져 빨간 화면이 된다.
/// → 값이 유효한 경우에만 넘기고, 값이 바뀔 때마다 key 를 바꿔
///    필드 내부 값도 함께 초기화되게 한다.
class _ChannelDropdownField extends StatelessWidget {
  final List<Channel> channels;
  final String? value;
  final ValueChanged<String?> onChanged;

  const _ChannelDropdownField({
    required this.channels,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final valid = value != null && channels.any((c) => c.id == value) ? value : null;

    return DropdownButtonFormField<String?>(
      // 값이 바뀔 때 필드를 새로 만들어 내부 값이 목록과 어긋나지 않게 한다
      key: ValueKey<String?>('channel-$valid'),
      initialValue: valid,
      isExpanded: true,
      decoration: const InputDecoration(labelText: '연결할 채널'),
      items: [
        const DropdownMenuItem(value: null, child: Text('연결 안 함')),
        ...channels.map(
          (c) => DropdownMenuItem(
            value: c.id,
            child: Text('# ${c.name}', maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ),
      ],
      onChanged: onChanged,
    );
  }
}
