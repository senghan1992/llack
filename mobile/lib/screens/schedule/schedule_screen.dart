import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../models/models.dart';
import '../../providers/app_state.dart';
import '../../theme/llack_colors.dart';
import '../main_shell.dart';
import 'event_detail_sheet.dart';
import 'event_dialog.dart';
import '../../widgets/app_snack_bar.dart';

/// 같은 로컬 날짜인지 비교한다.
///
/// 일정은 UTC 로 저장되므로 **양쪽 다 로컬로 바꿔서** 비교해야 한다.
/// (UTC 인스턴스와 로컬 날짜를 그대로 비교하면 카드가 하루 밀려 보인다)
bool isSameLocalDay(DateTime a, DateTime b) {
  final la = a.toLocal();
  final lb = b.toLocal();
  return la.year == lb.year && la.month == lb.month && la.day == lb.day;
}

/// "내 일정" 인지 판정한다.
///
/// - 내가 만든 일정
/// - 내가 참석자로 등록된 일정
///
/// 목록(하루 목록)과 달력 점이 **같은 판정**을 쓰도록 한 곳에 모았다. (F-8)
/// 판정이 어긋나면 "점은 있는데 목록은 비어 있다" 는 모순이 생긴다.
bool isMyScheduleEvent(ScheduleEvent ev, String? myId) {
  if (myId == null) return false;
  if (ev.createdBy == myId) return true;
  return ev.attendees.any((a) => a.user.id == myId);
}

/// 그날 **보여줄** 일정 목록.
///
/// - 날짜 묶기는 **시작 날짜만** 쓴다 (데스크톱 ScheduleView 와 동일).
///   - 종일 일정은 ends_at 이 "다음 날 자정"(exclusive)이라 종료 날짜에까지 붙으면 이틀에 걸쳐 보인다
///   - "날짜를 가로지르는 일정" 판정도 종료일 쪽에 붙여 달력 점(시작 날짜 기준)과 모순된다
///   - → 목록과 달력 점이 같은 기준(시작 날짜)을 쓰도록 여기서 통일한다
/// - "내 일정만" 필터가 켜져 있으면 **내 일정만** 남긴다.
List<ScheduleEvent> visibleScheduleEvents(
  List<ScheduleEvent> events,
  DateTime day, {
  required bool onlyMyEvents,
  required String? myId,
}) {
  final result = <ScheduleEvent>[];
  for (final e in events) {
    if (!isSameLocalDay(e.startsAt, day)) continue;
    if (onlyMyEvents && !isMyScheduleEvent(e, myId)) continue;
    result.add(e);
  }
  return result;
}

/// 달력 점 표시 판정.
///
/// - `show`: 그날 점을 그릴지
/// - `mine`: 점이 "내 일정" 색(초록)인지 ("팀 일정" 색(회색)인지)
///
/// "내 일정만" 필터가 켜져 있으면 **내 일정만** 센다.
/// (그날 일정이 전부 남의 것이면 점을 아예 그리지 않는다 — 목록이 비어 있는데 점이 있으면 모순이다)
({bool show, bool mine}) calendarDotForDay(
  List<ScheduleEvent> events,
  DateTime day, {
  required bool onlyMyEvents,
  required String? myId,
}) {
  final dayEvs = visibleScheduleEvents(events, day, onlyMyEvents: onlyMyEvents, myId: myId);
  final hasMy = dayEvs.any((e) => isMyScheduleEvent(e, myId));
  return (show: dayEvs.isNotEmpty, mine: hasMy);
}

class ScheduleScreen extends StatefulWidget {
  /// 태블릿에서는 좌측 레일에 검색/아바타가 있어 앱바 공통 액션을 숨긴다.
  final bool showCommonActions;

  const ScheduleScreen({super.key, this.showCommonActions = true});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> with AutomaticKeepAliveClientMixin {
  /// RSVP 를 낙관적으로 반영하기 위한 임시 값.
  /// (서버 응답이 오면 지워지고, 실패하면 이전 값으로 되돌아간다)
  final Map<String, EventResponse> _pendingRsvp = {};

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      // Core 가 이미 일정을 불러왔다면 다시 부르지 않는다 (F-5 중복 요청 방지).
      // 목록이 비었는지로는 판단하지 않는다 — 로더가 성공했는지만 본다.
      if (!state.hasLoadedEvents) state.loadEvents();
    });
  }

  /// 달을 옮길 때 선택 날짜도 함께 옮긴다.
  /// 안 옮기면 목록은 이전 달 날짜를 가리키는데 달력에는 아무 칸도 선택되어 있지 않아
  /// 화면이 깨진 것처럼 보이기 때문 (§3-C-3).
  ///
  /// 표시할 달은 **선택 날짜에서 파생**한다 (§9-36).
  /// 로컬 상태로 따로 들면 화면 레이아웃(폰↔태블릿) 이 바뀔 때 State 가 재생성되어
  /// 달력은 현재 달로 초기화되지만 선택 날짜는 남아 달과 목록이 어긋난다.
  void _shiftMonth(int delta) {
    final state = context.read<AppState>();
    final current = state.selectedDate;
    state.setSelectedDate(DateTime(current.year, current.month + delta, 1));
  }

  /// 같은 날인지 비교한다.
  /// 일정은 UTC 로 저장되므로 **양쪽 다 로컬로 바꿔서** 비교해야 한다.
  /// (UTC 인스턴트와 로컬 날짜를 그대로 비교하면 카드가 하루 밀려 보인다)
  bool _isSameDay(DateTime a, DateTime b) => isSameLocalDay(a, b);

  /// 화면에 보여줄 RSVP 값 (낙관적 임시 값 → 서버가 확정한 값 순으로 우선한다)
  EventResponse? _displayedResponse(ScheduleEvent ev) {
    return _pendingRsvp[ev.id] ?? ev.myResponse;
  }

  /// RSVP 를 바꾼다.
  ///
  /// 서버 응답을 기다리면 칩이 안 바뀌어 "누른 거 같다" 는 느낌을 준다.
  /// 그래서 먼저 화면에 반영하고(낙관적 업데이트),
  /// 실패하면 임시 값을 지워 이전 값으로 되돌린 뒤 사유를 알린다.
  Future<void> _changeRsvp(ScheduleEvent ev, EventResponse response) async {
    final state = context.read<AppState>();
    setState(() => _pendingRsvp[ev.id] = response);

    final ok = await state.rsvpEvent(ev.id, response);
    if (!mounted) return;
    // 성공이면 서버가 확정한 값이, 실패면 이전 값이 다시 보여야 한다
    setState(() => _pendingRsvp.remove(ev.id));
    if (!ok) {
      showAppSnackBar(context, '참석 여부를 바꾸지 못했습니다');
    }
  }

  /// 일정을 삭제한다. 실패하면 목록에서 지우지 않고 사유를 알린다.
  Future<void> _deleteEvent(ScheduleEvent ev) async {
    final state = context.read<AppState>();
    final ok = await state.deleteEvent(ev.id);
    if (!mounted) return;
    if (!ok) {
      showAppSnackBar(context, '일정을 삭제하지 못했습니다');
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final state = context.watch<AppState>();
    final myId = state.currentUser?.id;
    final selectedDate = state.selectedDate;
    final allEvents = state.events;
    final onlyMyEvents = state.onlyMyEvents;
    final theme = Theme.of(context);
    // 표시할 달은 선택 날짜에서 파생한다 (§9-36: 회전해도 달/선택 날짜가 어긋나지 않게)
    final viewMonth = DateTime(selectedDate.year, selectedDate.month, 1);

    // 선택 날짜에 보여줄 일정. ("나 일정만" 필터 반영)
    // 달력 점도 같은 판정 함수(`visibleScheduleEvents`)를 쓰므로 목록과 달력이 어긋나지 않는다 (F-8).
    final dayEvents = visibleScheduleEvents(
      allEvents,
      selectedDate,
      onlyMyEvents: onlyMyEvents,
      myId: myId,
    );

    // 가로모드(폭 650dp 이상)에서는 달력과 하루 목록을 2단으로 배치한다 (§9-34)
    final isWideLayout = MediaQuery.sizeOf(context).width >= 650;

    // 월 카드 (왼쪽 열)
    final calendarCard = Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 10),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                IconButton(
                  icon: const Icon(Icons.chevron_left),
                  tooltip: '이전 달',
                  onPressed: () => _shiftMonth(-1),
                ),
                Text(
                  DateFormat('yyyy년 M월', 'ko_KR').format(viewMonth),
                  style: theme.textTheme.titleMedium,
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right),
                  tooltip: '다음 달',
                  onPressed: () => _shiftMonth(1),
                ),
              ],
            ),
            const SizedBox(height: 4),
            _buildMonthGrid(state, myId, viewMonth),
            const SizedBox(height: 6),
            // Legend
            // "나 일정만" 필터가 켜져 있으면 팀 일정 점은 아예 보이지 않으므로 범례도 숨긴다 (F-8)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildLegendItem(color: LlackColors.accent, label: '내 일정'),
                if (!onlyMyEvents) ...[
                  const SizedBox(width: 16),
                  _buildLegendItem(color: LlackColors.muted, label: '팀 일정'),
                ],
              ],
            ),
          ],
        ),
      ),
    );

    // 선택한 날짜의 제목 + 그날의 일정 목록 (오른쪽 열 / 세로모드에서는 달력 아래)
    final daySection = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Selected day title
        Row(
          children: [
            Flexible(
              child: Text(
                DateFormat('M월 d일 EEEE', 'ko_KR').format(selectedDate),
                style: theme.textTheme.titleMedium,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '${dayEvents.length}개의 일정',
              style: theme.textTheme.labelSmall,
            ),
          ],
        ),
        const SizedBox(height: 8),

        // 로드 실패와 "일정 없음" 을 구분해서 보여준다 (§1-A-13)
        if (state.eventsError != null)
          Padding(
            padding: const EdgeInsets.only(top: 8, bottom: 4),
            child: SectionErrorBanner(
              message: state.eventsError!,
              onRetry: () => context.read<AppState>().retryEvents(),
            ),
          )
        else if (dayEvents.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 36),
            alignment: Alignment.center,
            child: Text(
              '등록된 일정이 없습니다',
              style: theme.textTheme.bodySmall?.copyWith(color: LlackColors.muted),
            ),
          )
        else
          ...dayEvents.map((ev) => _buildEventCard(context, state, ev, myId)),
      ],
    );

    return Scaffold(
      backgroundColor: LlackColors.paper,
      appBar: LlackAppBar(
        tabTitle: '일정',
        showCommonActions: widget.showCommonActions,
        actions: [
          FilterChip(
            label: Text(
              '내 일정만',
              style: theme.textTheme.labelMedium?.copyWith(
                fontWeight: onlyMyEvents ? FontWeight.w600 : FontWeight.w400,
                color: onlyMyEvents ? LlackColors.accentDeep : LlackColors.ink,
              ),
            ),
            selected: onlyMyEvents,
            selectedColor: LlackColors.accentSoft,
            checkmarkColor: LlackColors.accent,
            onSelected: (_) => state.toggleOnlyMyEvents(),
          ),
          const SizedBox(width: 8),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: LlackColors.accent,
        foregroundColor: LlackColors.accentInk,
        elevation: 2,
        onPressed: () => showDialog(
          context: context,
          builder: (_) => EventDialog(initialDate: selectedDate),
        ),
        tooltip: '새 일정',
        child: const Icon(Icons.add_rounded),
      ),
      body: RefreshIndicator(
        onRefresh: () => state.loadEvents(),
        color: LlackColors.accent,
        // 가로모드/태블릿 폭에서는 달력과 하루 목록을 2단으로 배치한다 (§9-34)
        // (세로모드는 지금과 완전히 동일하게 한 리스트로 둔다)
        child: isWideLayout
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 360,
                    child: SingleChildScrollView(
                      // 하단 여백: FAB 가 마지막 카드 위에 겹쳐 가리지 않도록 확보 (§3-C-2)
                      padding: const EdgeInsets.fromLTRB(16, 8, 8, 96),
                      child: calendarCard,
                    ),
                  ),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(8, 8, 16, 96),
                      child: daySection,
                    ),
                  ),
                ],
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
                children: [
                  calendarCard,
                  const SizedBox(height: 12),
                  daySection,
                ],
              ),
      ),
    );
  }

  Widget _buildLegendItem({required Color color, required String label}) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(label, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }

  Widget _buildMonthGrid(AppState state, String? myId, DateTime viewMonth) {
    final theme = Theme.of(context);
    final year = viewMonth.year;
    final month = viewMonth.month;
    final firstDayOfWeek = DateTime(year, month, 1).weekday % 7; // Sunday = 0
    final daysInMonth = DateTime(year, month + 1, 0).day;

    // 실제로 필요한 주 수만 그려서 달력 하단의 빈 공간을 없앤다 (§3-C-4)
    final weekCount = ((firstDayOfWeek + daysInMonth) / 7).ceil();

    const weekLabels = ['일', '월', '화', '수', '목', '금', '토'];

    return Column(
      children: [
        Row(
          children: weekLabels.map((lbl) {
            return Expanded(
              child: Center(
                child: Text(
                  lbl,
                  style: theme.textTheme.labelSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: lbl == '일' ? LlackColors.presenceBusy : LlackColors.muted,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 4),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: weekCount * 7,
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 7,
            // 칸 높이는 고정한다 (§9-34): 가로모드에서 폭이 커지면 칸이 함께 커져
            // 달력만 화면을 다 먹고 하루 목록이 화면 아래로 밀린다
            mainAxisExtent: 44,
          ),
          itemBuilder: (ctx, index) {
            final dayNumber = index - firstDayOfWeek + 1;
            if (dayNumber < 1 || dayNumber > daysInMonth) {
              return const SizedBox.shrink();
            }

            final date = DateTime(year, month, dayNumber);
            final isSelected = _isSameDay(date, state.selectedDate);
            final isToday = _isSameDay(date, DateTime.now());

            // Check events on this day
            // "나 일정만" 필터가 켜져 있으면 **내 일정만** 센다. (F-8)
            // → 그날 일정이 전부 남의 것이면 점을 아예 그리지 않는다
            final dot = calendarDotForDay(
              state.events,
              date,
              onlyMyEvents: state.onlyMyEvents,
              myId: myId,
            );
            final hasTeamEvent = dot.show;
            final hasMyEvent = dot.mine;

            return InkWell(
              onTap: () => state.setSelectedDate(date),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                decoration: BoxDecoration(
                  color: isSelected
                      ? LlackColors.accent
                      : (isToday ? LlackColors.accentSoft.withValues(alpha: 0.5) : Colors.transparent),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '$dayNumber',
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontWeight: isSelected || isToday ? FontWeight.w700 : FontWeight.w400,
                        color: isSelected
                            ? Colors.white
                            : (isToday ? LlackColors.accentDeep : LlackColors.ink),
                      ),
                    ),
                    const SizedBox(height: 2),
                    if (hasTeamEvent)
                      Container(
                        width: 5,
                        height: 5,
                        decoration: BoxDecoration(
                          color: isSelected
                              ? Colors.white
                              : (hasMyEvent ? LlackColors.accent : LlackColors.muted),
                          shape: BoxShape.circle,
                        ),
                      )
                    else
                      const SizedBox(height: 5),
                  ],
                ),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _buildEventCard(BuildContext context, AppState state, ScheduleEvent ev, String? myId) {
    final theme = Theme.of(context);
    final timeStr = ev.allDay
        ? '하루 종일'
        : '${DateFormat('HH:mm').format(ev.startsAt.toLocal())} - ${DateFormat('HH:mm').format(ev.endsAt.toLocal())}';

    final isCreator = ev.createdBy == myId;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      // 카드 전체를 누르면 상세 시트가 열린다 (참석자/설명 전체/수정 경로) (§9-23)
      // RSVP 칩과 삭제 버튼은 안쪽에서 제스처를 먼저 가져가므로 카드 탭이 같이 발동하지 않는다.
      child: InkWell(
        onTap: () => showEventDetailSheet(context, event: ev, isCreator: isCreator),
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(timeStr, style: theme.textTheme.labelSmall?.copyWith(color: LlackColors.accent, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        Text(ev.title, style: theme.textTheme.titleMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
                      ],
                    ),
                  ),
                  if (ev.isPrivate)
                    const Padding(
                      padding: EdgeInsets.only(left: 6),
                      child: Icon(Icons.lock_outline, size: 16, color: LlackColors.muted),
                    ),
                  if (isCreator)
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 18, color: LlackColors.presenceBusy),
                      padding: EdgeInsets.zero,
                      // 엄지로 누를 수 있도록 터치 영역을 44dp 로 확보한다 (§9-7)
                      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                      tooltip: '일정 삭제',
                      onPressed: () async {
                        final del = await confirmDeleteEvent(context, ev);
                        if (del == true) await _deleteEvent(ev);
                      },
                    ),
                ],
              ),
              if (ev.location.isNotEmpty) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    const Icon(Icons.location_on_outlined, size: 14, color: LlackColors.muted),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(ev.location, style: theme.textTheme.labelSmall, maxLines: 1, overflow: TextOverflow.ellipsis),
                    ),
                  ],
                ),
              ],
              if (ev.description.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(ev.description, style: theme.textTheme.bodyMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
              ],
              const SizedBox(height: 10),
              const Divider(height: 1),
              const SizedBox(height: 8),

              // RSVP response buttons
              Row(
                children: [
                  Text('참석 여부:', style: theme.textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(width: 8),
                  _buildRsvpChip(
                    label: '참석',
                    selected: _displayedResponse(ev) == EventResponse.accepted,
                    color: LlackColors.accent,
                    onTap: () => _changeRsvp(ev, EventResponse.accepted),
                  ),
                  const SizedBox(width: 6),
                  _buildRsvpChip(
                    label: '미정',
                    selected: _displayedResponse(ev) == EventResponse.tentative,
                    color: LlackColors.presenceAway,
                    onTap: () => _changeRsvp(ev, EventResponse.tentative),
                  ),
                  const SizedBox(width: 6),
                  _buildRsvpChip(
                    label: '불참',
                    selected: _displayedResponse(ev) == EventResponse.declined,
                    color: LlackColors.presenceBusy,
                    onTap: () => _changeRsvp(ev, EventResponse.declined),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRsvpChip({
    required String label,
    required bool selected,
    required Color color,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        // 엄지로 누를 수 있도록 최소 높이 44dp 를 확보한다 (§9-7)
        constraints: const BoxConstraints(minHeight: 44),
        alignment: Alignment.center,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: selected ? color.withValues(alpha: 0.15) : LlackColors.surfaceWell,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? color : LlackColors.rule,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? color : LlackColors.ink2,
          ),
        ),
      ),
    );
  }
}
