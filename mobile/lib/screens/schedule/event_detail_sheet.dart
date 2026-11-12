import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../../theme/llack_typography.dart';
import '../../widgets/app_snack_bar.dart';
import 'event_dialog.dart';

/// 일정 상세 시트를 띄운다.
///
/// 카드에서 누르면 안쪽 정보(설명/참석자/작성자)를 보고 생성자는 수정·삭제할 수 있다.
Future<void> showEventDetailSheet(
  BuildContext context, {
  required ScheduleEvent event,
  required bool isCreator,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true, // 키보드가 올라와도 내용이 가려지지 않게 스크롤 가능하게
    backgroundColor: Colors.transparent,
    builder: (ctx) => _EventDetailSheet(eventId: event.id, initialEvent: event, isCreator: isCreator),
  );
}

/// 일정 삭제 확인 다이얼로그.
Future<bool> confirmDeleteEvent(BuildContext context, ScheduleEvent event) async {
  final deleted = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('일정 삭제'),
      content: Text('\'${event.title}\' 일정을 삭제하시겠습니까?'),
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
  return deleted == true;
}

/// 일정 상세 시트 본체.
///
/// 수정하면 목록의 값이 바뀌므로, 상태에서 id 로 다시 찾아 그린다.
class _EventDetailSheet extends StatelessWidget {
  final String eventId;
  final ScheduleEvent initialEvent;
  final bool isCreator;

  const _EventDetailSheet({
    required this.eventId,
    required this.initialEvent,
    required this.isCreator,
  });

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final theme = Theme.of(context);
    // 수정 후에는 목록의 새 값을 보여준다
    final event = state.events.firstWhere(
      (e) => e.id == eventId,
      orElse: () => initialEvent,
    );
    final myId = state.currentUser?.id;

    return AnimatedPadding(
      // 키보드가 올라올 때 시트 높이가 튀지 않도록 애니메이션으로 맞춘다
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Container(
        decoration: const BoxDecoration(
          color: LlackColors.surfaceRaise,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 드래그 핸들
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.symmetric(vertical: 8),
                  decoration: BoxDecoration(color: LlackColors.rule, borderRadius: BorderRadius.circular(2)),
                ),
              ),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // 제목
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(
                              event.title,
                              style: theme.textTheme.titleLarge?.copyWith(fontSize: 19),
                            ),
                          ),
                          if (event.isPrivate)
                            const Padding(
                              padding: EdgeInsets.only(left: 8),
                              child: Icon(Icons.lock_outline, size: 18, color: LlackColors.muted),
                            ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      _DetailRow(
                        icon: Icons.schedule,
                        label: _dateTimeText(event),
                      ),
                      if (event.location.isNotEmpty)
                        _DetailRow(
                          icon: Icons.location_on_outlined,
                          label: event.location,
                        ),
                      _DetailRow(
                        icon: Icons.person_outline,
                        label: '작성자: ${_creatorName(state, event)}',
                      ),
                      if (_channelName(state, event) != null)
                        _DetailRow(
                          icon: Icons.tag,
                          label: '연결 채널: ${_channelName(state, event)}',
                        ),

                      // 설명 전체 (카드는 2줄로 잘린다)
                      if (event.description.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        const Divider(height: 1),
                        const SizedBox(height: 12),
                        Text('설명', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                        const SizedBox(height: 6),
                        Text(event.description, style: theme.textTheme.bodyMedium),
                      ],

                      // 참석자 목록 (이름 + RSVP 상태)
                      const SizedBox(height: 16),
                      const Divider(height: 1),
                      const SizedBox(height: 12),
                      Text('참석자 (${event.attendees.length}명)', style: theme.textTheme.titleMedium?.copyWith(fontSize: 13)),
                      const SizedBox(height: 8),
                      if (event.attendees.isEmpty)
                        Text('참석자가 없습니다.', style: theme.textTheme.labelSmall)
                      else
                        ...event.attendees.map(
                          (a) => Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Row(
                              children: [
                                // 이름 + "나" pill 묶음이 남는 폭을 모두 가져간다 (§9-40)
                                // 안쪽 Row 가 자기 크기(min)만큼만 차지하므로 이름은 말줄임되고
                                // pill 은 이름 바로 뒤에 붙는다
                                Expanded(
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Flexible(
                                        child: Text(
                                          a.user.name,
                                          style: theme.textTheme.bodyMedium,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      if (a.user.id == myId) ...[
                                        const SizedBox(width: 6),
                                        Tooltip(
                                          message: '나 (본인)',
                                          // 모양은 조직도의 "나" 배지와 동일하게 맞춘다
                                          // (padding 5/1 · radius 4 · w700 — 같은 의미의 표시가 두 모양으로 보이면 안 된다)
                                          child: Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                            decoration: BoxDecoration(
                                              color: LlackColors.accentSoft,
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: Text(
                                              '나',
                                              style: theme.textTheme.labelSmall?.copyWith(
                                                color: LlackColors.accentDeep,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                                // RSVP 배지는 Expanded 밖이므로 항상 행의 오른쪽 끝에 붙는다
                                _ResponseBadge(response: a.response),
                              ],
                            ),
                          ),
                        ),

                      // 생성자에게만 수정·삭제 버튼을 보여준다
                      if (isCreator) ...[
                        const SizedBox(height: 12),
                        const Divider(height: 1),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () => _edit(context, event),
                                icon: const Icon(Icons.edit_outlined, size: 18),
                                label: const Text('수정'),
                                style: OutlinedButton.styleFrom(
                                  // 엄지로 누를 수 있도록 44dp 이상 확보 (§9-7)
                                  minimumSize: const Size.fromHeight(44),
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () => _delete(context, event),
                                icon: const Icon(Icons.delete_outline, size: 18, color: LlackColors.presenceBusy),
                                label: const Text('삭제', style: TextStyle(color: LlackColors.presenceBusy)),
                                style: OutlinedButton.styleFrom(
                                  minimumSize: const Size.fromHeight(44),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _edit(BuildContext context, ScheduleEvent event) async {
    // 수정은 기존 다이얼로그를 편집 모드로 재사용한다
    await showDialog<void>(
      context: context,
      builder: (ctx) => EventDialog(initialDate: event.startsAt.toLocal(), editing: event),
    );
  }

  Future<void> _delete(BuildContext context, ScheduleEvent event) async {
    final state = context.read<AppState>();
    if (!await confirmDeleteEvent(context, event)) return;
    final ok = await state.deleteEvent(event.id);
    if (!context.mounted) return;
    if (!ok) {
      // 실패하면 목록에서 지우지 않고 사유를 알린다
      showAppSnackBar(context, '일정을 삭제하지 못했습니다');
      return;
    }
    Navigator.pop(context);
  }

  String _dateTimeText(ScheduleEvent event) {
    final start = event.startsAt.toLocal();
    final end = event.endsAt.toLocal();
    final day = DateFormat('yyyy년 M월 d일 (EEE)', 'ko_KR').format(start);
    if (event.allDay) return '$day · 하루 종일';
    final time = '${DateFormat('HH:mm').format(start)} - ${DateFormat('HH:mm').format(end)}';
    final sameDay = start.year == end.year && start.month == end.month && start.day == end.day;
    return sameDay ? '$day · $time' : '$day $time ~ ${DateFormat('M월 d일 HH:mm').format(end)}';
  }

  String _creatorName(AppState state, ScheduleEvent event) {
    for (final m in state.members) {
      if (m.user.id == event.createdBy) return m.user.name;
    }
    return '알 수 없음';
  }

  String? _channelName(AppState state, ScheduleEvent event) {
    final channelId = event.channelId;
    if (channelId == null) return null;
    for (final c in state.allChannels) {
      if (c.id == channelId) return '# ${c.name}';
    }
    return null;
  }
}

/// 상세 시트의 한 줄 정보 (아이콘 + 값)
class _DetailRow extends StatelessWidget {
  final IconData icon;
  final String label;

  const _DetailRow({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: LlackColors.muted),
          const SizedBox(width: 8),
          Expanded(
            child: Text(label, style: theme.textTheme.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
        ],
      ),
    );
  }
}

/// 참석자의 RSVP 상태 배지
class _ResponseBadge extends StatelessWidget {
  final EventResponse response;

  const _ResponseBadge({required this.response});

  @override
  Widget build(BuildContext context) {
    final color = switch (response) {
      EventResponse.accepted => LlackColors.accent,
      EventResponse.tentative => LlackColors.presenceAway,
      EventResponse.declined => LlackColors.presenceBusy,
      EventResponse.pending => LlackColors.muted,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        response.label,
        style: LlackTypography.caption.copyWith(color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}
