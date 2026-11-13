# components — 데스크톱 화면을 이루는 28개 컴포넌트

## Overview

프런트엔드 UI 전체입니다. `desktop/src/App.tsx` 이 이 디렉터리의 컴포넌트들을
배선하고, 각 컴포넌트는 `desktop/src/store/useStore.ts` (Zustand) 와
`desktop/src/lib/api.ts` (REST 클라이언트) 를 통해 상태와 네트워크에 닿습니다.

역할별로 묶으면 이렇습니다.

| 묶음 | 컴포넌트 |
| --- | --- |
| 아바타·색 | `Avatar` |
| 방 헤더 | `ChannelHead` |
| 메시지 목록 | `MessageList`, `MessageRow` |
| 입력 | `Composer`, `ThreadPane` |
| 폼 키트 | `Form`(FormTitle/FormRow/Segmented/Disclosure/DateField/TimeField), `Select`, `MemberSelect`, `PersonPicker` |
| 오버레이 | `Menu`/`MenuSub`, `ChartTip`, `Dialog`, `ConfirmDialog`, `Toasts` |
| 내비게이션 | `Rail` |
| 일정 | `ScheduleView`(ScheduleHead/ScheduleView), `ScheduleDialogs`(EventDialog) |
| 프로젝트 | `ProjectsView`(ProjectsHead/ProjectsView), `ProjectDialogs`(ProjectDialog/TaskDialog), `MilestonePanel`, `MilestoneDialog`, `ProjectChartDialog` |
| 조직 | `OrgView`(OrgHead/OrgView), `OrgDialogs`(OrgUnitDialog) |
| 설정·인증 | `SettingsDialog`, `Gate` |

## Interface

### 아바타·색

- [desktop/src/components/Avatar.tsx:Avatar] — `Avatar({ user, size = "md",
  presence, title }: Props)`. `user`는 `Pick<User, "id" | "name" | "avatar_color">`,
  `size`는 `"sm" | "md" | "lg"`, `presence`는 `Presence | null`.
  이니셜 타일 + 선택적 존재 표시 점.

### 방 헤더

- [desktop/src/components/ChannelHead.tsx:ChannelHead] — 방 헤더.
  `channel: Channel | null`, `members: Member[]`,
  `presence: Record<string, Presence>`, `project: Project | null`,
  `onOpenProject`, `onOpenSearch`, `onOpenPeople`, `onAddPeople`,
  `onOpenPins`, `onToggleRail`, `onOpenSettings`, 선택형 `onClearScreen`,
  선택형 `onExpandChat`, 선택형 `compact`(기본 false).

### 메시지 목록

- [desktop/src/components/MessageList.tsx:MessageList] — `MessageList({ channel,
  messages, loading, hasMore, error, onLoadMore, onOpenThread, onReact, onEdit,
  onDelete, onPin, ownId })`. 날짜 구분선, 메시지 그룹핑, 스크롤 위치 감지.
- [desktop/src/components/MessageRow.tsx:MessageRow] — `MessageRow({ message,
  grouped, own, onOpenThread, onReact, onEdit, onDelete, onPin, replyScope?,
  hideThread?, flat? })`. 반응·첨부·스레드 버튼·호버 도구(툴 배치는 DOM 측정으로
  계산).

### 입력

- [desktop/src/components/Composer.tsx:Composer] — `Composer({ channel,
  threadRoot, onSend, onTyping, onCancelThread })`.
  `onSend: (body: string, attachmentIds?: string[]) => Promise<void> | void`.
  자동 확장, 이모지, 파일 첨부, 회신 배너.
- [desktop/src/components/ThreadPane.tsx:ThreadPane] — `ThreadPane({ channel,
  root, replies, ownId, onClose, onSend, onTyping, onReact, onEdit, onDelete,
  onPin })`. 스레드 옆 패널.

### 폼 키트

- [desktop/src/components/Form.tsx:FormTitle] — 한 줄 입력. `onEnter` 콜백이
  있으면 Enter 를 가로챕니다.
- [desktop/src/components/Form.tsx:FormRow] — 폼 한 줄. `htmlFor` 가 있을 때만
  `<label htmlFor>` 로 렌더링.
- [desktop/src/components/Form.tsx:Segmented] — `Segmented<T extends string>({
  value, options, onChange, label, disabled? })`. `role="group"`, 옵션마다
  `aria-pressed`.
- [desktop/src/components/Form.tsx:Disclosure] — 접기/펼치기 토글.
  `aria-expanded` / `aria-controls`.
- [desktop/src/components/Form.tsx:DateField] — `YYYY-MM-DD` 값의 날짜 필드.
  `role="combobox"` 트리거 + `role="grid"` 패널(포털).
- [desktop/src/components/Form.tsx:TimeField] — `HH:mm` 값의 시간 필드.
  15분 간격 옵션과 `useSettings` 의 시계 형식(12h/24h)을 따릅니다.
- [desktop/src/components/Select.tsx:Select] — `Select({ value, onChange,
  options, placeholder = "선택", ariaLabel?, size?, disabled? })`.
- [desktop/src/components/Select.tsx:SelectOption] — `{ value, label, lead?,
  hint?, disabled? }`.
- [desktop/src/components/MemberSelect.tsx:MemberSelect] — `MemberSelect({
  members, value, onChange, placeholder?, emptyText? })`. 검색 가능한 다중 선택
  멤버 픽커. `value` 는 이미 고른 user id 배열.
- [desktop/src/components/PersonPicker.tsx:PersonPicker] — `PersonPicker({
  members, exclude?, onPick, placeholder?, emptyText?, ariaLabel?, size? })`.
  한 명만 고르는 픽커.

### 오버레이

- [desktop/src/components/Menu.tsx:Menu] — `Menu({ anchor, at, onClose, children,
  align?, width?, className? })`. `role="menu"` 포털 팝오버.
- [desktop/src/components/Menu.tsx:MenuSub] — `MenuSub({ open, anchor, children,
  width? })`. 부모 메뉴 박스 안에 그려지는 서브메뉴.
- [desktop/src/components/ChartTip.tsx:ChartTip] — `ChartTip({ anchor, children })`.
  차트 마크에 붙는 `role="tooltip"` 포털.
- [desktop/src/components/Dialogs.tsx:Dialog] — `Dialog({ title, onClose,
  children, footer?, wide?, chart? })`. 공용 모달 셸.
- [desktop/src/components/Dialogs.tsx:SearchDialog] — `SearchDialog()`.
  워크스페이스 전역 메시지 검색.
- [desktop/src/components/Dialogs.tsx:PaletteDialog] — `PaletteDialog()`.
  ⌘K 팔레트 — 채널·사람으로의 빠른 이동.
- [desktop/src/components/Dialogs.tsx:NewChannelDialog] — `NewChannelDialog()`.
  이름·주제·비공개 여부·함께할 사람을 고르는 채널 생성 폼.
- [desktop/src/components/Dialogs.tsx:PeopleDialog] — `PeopleDialog()`.
  워크스페이스 멤버 목록과 역할 관리.
- [desktop/src/components/Dialogs.tsx:NewDmDialog] — `NewDmDialog()`.
  이름으로 사람을 찾아 1:1 대화를 여는 다이얼로그.
- [desktop/src/components/Dialogs.tsx:PinsDialog] — `PinsDialog()`.
  현재 방의 고정된 메시지 목록.
- [desktop/src/components/Dialogs.tsx:ChannelSettingsDialog] —
  `ChannelSettingsDialog()`. 채널 이름·주제 변경, 나가기, 사람 추가 진입.
- [desktop/src/components/Dialogs.tsx:InviteDialog] — `InviteDialog()`.
  초대 코드 생성·취소와 토큰 복사.
- [desktop/src/components/Dialogs.tsx:AddPeopleDialog] — `AddPeopleDialog()`.
  채널에 사람 추가.
- [desktop/src/components/Dialogs.tsx:LeaveChannelDialog] —
  `LeaveChannelDialog()`. 방 나가기 확인.
- [desktop/src/components/Dialogs.tsx:DeleteDmDialog] — `DeleteDmDialog()`.
  1:1 대화 삭제 확인.
- [desktop/src/components/ConfirmDialog.tsx:ConfirmDialog] — `ConfirmDialog({
  title, message, detail, confirmLabel = "삭제", busy = false, onConfirm,
  onClose })`.
- [desktop/src/components/Toasts.tsx:Toasts] — `Toasts()`. store 의 토스트를
  `role="status"`, `aria-live="polite"` 로 렌더링.

### 내비게이션

- [desktop/src/components/Rail.tsx:Rail] — `Rail()`. 왼쪽 탐색 레일 —
  워크스페이스 전환, 검색, 일정/프로젝트/조직 진입, 채널·DM 목록, 존재 상태,
  프로필 메뉴.

### 일정

- [desktop/src/components/ScheduleView.tsx:ScheduleHead] — `ScheduleHead({
  onToggleRail, actions? })`. 보드 헤더.
- [desktop/src/components/ScheduleView.tsx:ScheduleView] — `ScheduleView()`.
  월 달력 + 선택 날짜의 일정 목록 + "내 앞으로" 목록.
- [desktop/src/components/ScheduleDialogs.tsx:EventDialog] — `EventDialog()`.
  일정 생성/편집 폼과 읽기 전용 보기.

### 프로젝트

- [desktop/src/components/ProjectsView.tsx:ProjectsHead] — `ProjectsHead({
  onToggleRail, actions? })`.
- [desktop/src/components/ProjectsView.tsx:ProjectsView] — `ProjectsView()`.
  프로젝트 목록 사이드바 + 상태별 칸반 보드 + 마일스톤 패널.
- [desktop/src/components/ProjectDialogs.tsx:ProjectDialog] — `ProjectDialog()`.
  프로젝트 생성/편집.
- [desktop/src/components/ProjectDialogs.tsx:TaskDialog] — `TaskDialog()`.
  할 일 생성/편집 + 의견 스레드.
- [desktop/src/components/MilestonePanel.tsx:MilestonePanel] —
  `MilestonePanel({ project }: { project: Project })`. 프로젝트의 마일스톤 목록.
- [desktop/src/components/MilestoneDialog.tsx:MilestoneDialog] —
  `MilestoneDialog()`. 마일스톤 생성/편집.
- [desktop/src/components/ProjectChartDialog.tsx:ProjectChartDialog] —
  `ProjectChartDialog()`. 마일스톤·할 일·일정을 겹쳐 그리는 간트 차트.

### 조직

- [desktop/src/components/OrgView.tsx:OrgHead] — `OrgHead({ onToggleRail,
  actions? })`. 조직 관리 헤더.
- [desktop/src/components/OrgView.tsx:OrgView] — `OrgView()`. 관리자 목록,
  조직 트리 사이드바, 조직 상세 편집 패널.
- [desktop/src/components/OrgDialogs.tsx:OrgUnitDialog] — `OrgUnitDialog()`.
  "새 조직" 생성 대화상자.

### 설정·인증

- [desktop/src/components/SettingsDialog.tsx:SettingsDialog] —
  `SettingsDialog()`. 알림 / 외관 / 계정 및 조직 / 파일 및 링크 4개 구역.
- [desktop/src/components/Gate.tsx:Gate] — `Gate()`. 로그인 / 회원가입 폼.

### 재수출

- [desktop/src/components/Dialogs.tsx:export type { Member, User }] —
  `../lib/types` 의 `Member` 와 `User` 타입을 재수출합니다.

## Invariants

- [desktop/src/components/Avatar.tsx:Avatar] — 타일 배경은
  `readableOn(user.avatar_color || colorFor(user.id))` 를 거치므로 이니셜은
  언제나 읽을 수 있습니다. 존재 표시 점은 `presence` 가 있을 때만.
- [desktop/src/components/ChannelHead.tsx:ChannelHead] — 표시는 최대
  `compact ? 2 : 5` 개의 멤버 아바타, 라벨은 항상 전체 인원 수를 말합니다.
  글리프는 `is_private` 이면 `Lock`, 아니면 `Hash`.
- [desktop/src/components/ChartTip.tsx:ChartTip] — `EDGE = 120` 보다 위면 아래로,
  아래로 두면 창을 넘으면 위로 뒤집힙니다. 가로 위치는 `GUTTER = 8` 안쪽으로
  클램프됩니다.
- [desktop/src/components/Composer.tsx:Composer] — 텍스트 영역이 자동 확장되되
  `Math.min(node.scrollHeight, 220)` 로 잘립니다. Enter 는 Shift 가 아니고
  `isComposing` 이 false 일 때만 전송합니다. 입력 중에는 `onTyping(true)`,
  2500ms 뒤 `onTyping(false)`.
- [desktop/src/components/Composer.tsx:Composer] — 채널 초안은 store 의
  `s.drafts[channelId]` 에, 스레드 답글은 로컬 상태에 남습니다. 회신 배너는
  대기 중인 회신의 scope 이 컴포저의 surface 와 같을 때만 보입니다.
- [desktop/src/components/ConfirmDialog.tsx:ConfirmDialog] — 초기 포커스는
  취소 버튼입니다(`autoFocus`). 파괴적 동작이 실수로 눌리지 않게 하기 위함이고,
  확인 버튼은 `busy` 동안 비활성입니다.
- [desktop/src/components/Gate.tsx:Gate] — 이메일·이름·워크스페이스는 제출 전에
  trim 하고 비밀번호는 그대로입니다. 비밀번호 필드는 signup 모드에서만
  `minLength={8}` 입니다.
- [desktop/src/components/Menu.tsx:Menu] — Escape 와 바깥 pointerdown 으로
  닫힙니다. `align === "right"` 면 우측 정렬, 세로로는 아래로 열리고 넘치면 위로,
  가로는 `[8, window.innerWidth - box.width - 8]` 로 클램프됩니다.
- [desktop/src/components/MessageList.tsx:MessageList] — `GROUP_WINDOW_MS =
  5 * 60 * 1000` 안에서 같은 날·같은 작성자·이전 메시지가 삭제되지 않은 경우에만
  묶입니다. 아래 80px 안이면 `atBottom`, `scrollTop < 60` 이면 `onLoadMore`.
- [desktop/src/components/MessageRow.tsx:MessageRow] — 삭제된 메시지는
  "삭제된 메시지입니다." 로 고정되고 편집·삭제 도구가 사라집니다. 첨부는
  `settings.imagePreview` 가 켜져 있고 mime 이 `image/` 로 시작할 때만 인라인
  `<img>` 로 나갑니다.
- [desktop/src/components/MessageRow.tsx:measureSpot] — 내 메시지의 도구는
  말풍선 왼쪽에, 남의 메시지의 도구는 마지막 잉크 줄 바로 뒤에 놓입니다.
  화면 밖이면 줄 위로 떠오르되 콘텐츠 박스 안으로 클램프됩니다.
- [desktop/src/components/Form.tsx:DateField] — 표시 월은 anchor, 선택값의 월,
  오늘 순으로 정해집니다. Escape 는 패널이 열려 있을 때만 처리하고
  `stopPropagation` 으로 뒤의 대화상자를 닫지 않습니다. 방향키로 ±1일/±7일,
  PageUp/PageDown 은 ±1개월.
- [desktop/src/components/Form.tsx:TimeField] — 15분 간격 옵션, 값 형식은
  `${pad(hour)}:${pad(minute)}`. 12h 모드에서는 오전/오후 를 붙입니다.
- [desktop/src/components/Form.tsx:Disclosure] — `defaultOpen` 이 true 면 한 번
  펼쳐진 뒤 다시 접히지 않습니다.
- [desktop/src/components/Select.tsx:Select] — `disabled` 옵션은 고를 수 없고,
  방향키는 목록을 순환하며 Home/End 는 처음/끝으로 갑니다. Escape 는 팝업만
  닫습니다(`stopPropagation`). 800ms 를 넘기면 타이핑 큐가 새로 시작됩니다.
- [desktop/src/components/MemberSelect.tsx:MemberSelect] — 이미 고른 멤버가
  목록 맨 위에 오고, 검색은 이름·이메일·제목에서 대소문자 무시 부분 일치입니다.
  Escape 는 캡처 단계에서 처리되어 뒤의 대화상자를 닫지 않습니다.
- [desktop/src/components/PersonPicker.tsx:PersonPicker] — `exclude` 에 든 멤버는
  목록에 나오지 않습니다. 마커는 목록 밖으로 나가지 않고 방향키는 순환합니다.
- [desktop/src/components/Dialogs.tsx:Dialog] — Escape 로 닫히고, 스크림을
  눌렀을 때만(`event.target === event.currentTarget`) 닫힙니다.
- [desktop/src/components/Dialogs.tsx:SearchDialog] — 검색은 마지막 입력에서
  220ms 뒤에 실행되고, 결과는 24개로 제한됩니다.
- [desktop/src/components/Dialogs.tsx:PaletteDialog] — 빈 질의일 때 최근 항목
  다음에 처음 12개, 질의가 있으면 최대 20개. `closePalette` 은 현재 열려 있는
  대화상자가 아직 `"palette"` 일 때만 닫습니다.
- [desktop/src/components/Dialogs.tsx:PeopleDialog] — 역할 관리 UI는 현재
  사용자의 역할이 `"owner"` 또는 `"admin"` 일 때만 보입니다.
- [desktop/src/components/Dialogs.tsx:NewChannelDialog] — 이름이 비면(trim 후)
  저장하지 않고, "만들기" 버튼도 비활성입니다. 주제는 비면 `undefined` 로,
  함께할 사람은 자기 자신을 뺀 팀원 목록에서 고릅니다. 비공개 여부는
  `Disclosure` 안의 체크박스로 고릅니다.
- [desktop/src/components/Dialogs.tsx:NewDmDialog] — 목록에는 자기 자신이
  없고, 이름 부분 일치로 걸러냅니다. 결과가 없으면 "일치하는 사람이 없습니다."
- [desktop/src/components/Dialogs.tsx:PinsDialog] — 고정을 아직 안 읽었으면
  스켈레톤 세 줄을 먼저 그리고, 읽은 뒤 비면 "고정된 메시지가 없습니다" 를
  보여줍니다. 본문은 `renderBody` 로 렌더링합니다.
- [desktop/src/components/Dialogs.tsx:AddPeopleDialog] — 대상 방이 없으면
  아무것도 그리지 않습니다(`null`). 이미 방에 있는 사람은 후보에서 빠집니다.
  빈 후보 문구는 필터가 있으면 "그런 사람이 없습니다.", 없으면
  "팀원이 이미 모두 이 방에 있습니다." 입니다.
- [desktop/src/components/Dialogs.tsx:LeaveChannelDialog] — 대상 방이 없으면
  아무것도 그리지 않습니다. 공개 방과 비공개 방의 안내 문구가 다릅니다.
  나가기 버튼은 `busy` 동안 비활성입니다.
- [desktop/src/components/Dialogs.tsx:DeleteDmDialog] — 대상 대화가 없으면
  아무것도 그리지 않습니다. 상대의 이름은 `dm_user.name` 을 먼저 쓰고 없으면
  채널 이름으로 갑니다. 삭제가 실패하면 `reportError` 로 알립니다.
- [desktop/src/components/MilestoneDialog.tsx:MilestoneDialog] — 종료일이
  시작일보다 빠를 수 없습니다. 제목·시작일·종료일·프로젝트가 모두 있을 때만
  저장합니다. 진행률 컨트롤은 태스크를 하나라도 고르면 자동 계산(읽기 전용),
  아니면 수동 슬라이더(0–100, step 5)입니다.
- [desktop/src/components/OrgView.tsx:OrgView] — 조직을 자기 자신의 하위로
  옮길 수 없습니다. 하위 조직 집합을 재귀적으로 걸어내어 부모 후보에서
  제외합니다. 이름·종류·설명 길이는 각각 120/60/500자로 제한됩니다.
- [desktop/src/components/OrgView.tsx:OrgView] — 관리 지정은 역할이
  `"owner"`/`"admin"` 이고 관리 대상이 아니고 `unit.can_manage` /
  `unit.can_appoint_managers` 가 참일 때만 노출됩니다.
- [desktop/src/components/ProjectDialogs.tsx:ProjectDialog] — 이름이 비면
  저장하지 않습니다. `canManage` 는 생성자이거나 역할이 `"owner"`/`"admin"`
  일 때만 참이라, 아니면 저장 버튼 자체가 사라집니다.
- [desktop/src/components/ProjectDialogs.tsx:TaskDialog] — 제목이 비면,
  프로젝트가 없으면 저장하지 않습니다. 마감일은 그날의 23:59:00로
  저장됩니다(`endOfDayIso`). 프로젝트를 바꾸면 `roadmapId` 가 비워집니다.
- [desktop/src/components/ProjectsView.tsx:ProjectsView] — 칸반 보드는
  `COLUMNS` 네 개의 상태로 나누고 각 칸 안에서 `task.position` 오름차순으로
  정렬합니다. `MINE_LIMIT = 8` 까지만 "내 할일" 목록에 보여줍니다.
- [desktop/src/components/ProjectChartDialog.tsx:ProjectChartDialog] —
  `STATUS_TONE`/`STATUS_LABEL` 은 request/todo/in-progress/done 네 상태만
  다룹니다. 차트 범위는 마일스톤의 `start_at`/`end_at` 과 비어있지 않은
  `due_at` 만으로 계산합니다. 오늘 규칙은 오늘이 범위 안에 있을 때만 그립니다.
- [desktop/src/components/ScheduleDialogs.tsx:EventDialog] — 제목이 비면
  "일정 제목을 입력해 주세요", 시작일이 없으면 "날짜를 고르세요",
  종료 시각이 시작 시각보다 빠르면 "종료 시각이 시작 시각보다 빠릅니다".
  종일 일정의 payload는 시작 "00:00", 종료 "23:59", 종료일 = 시작일로 고정됩니다.
  삭제와 저장은 생성자이거나 역할이 `"owner"`/`"admin"` 일 때만 허용됩니다.
- [desktop/src/components/ScheduleView.tsx:ScheduleView] — 요일 헤더는 일요일
  시작(`일, 월, 화, 수, 목, 금, 토`). "내 앞으로"는 사용자가 응답한 일정 중
  아직 끝나지 않은 것만, 시작 시각 순으로, 최대 6개.
- [desktop/src/components/Rail.tsx:Rail] — 채널 섹션은 `kind === "channel"`
  이고 `is_member !== false` 인 것만, DM 섹션은 `kind === "dm"` 만.
  "조직 관리" 항목은 역할이 `"owner"`/`"admin"` 이거나 관리하는 조직이 있을 때만.
- [desktop/src/components/SettingsDialog.tsx:SettingsDialog] — 데스크톱 알림
  스위치는 브라우저 빌드(`!desktop`)에서 비활성, 알림 내용 세그먼트는
  `desktop && settings.notifications` 일 때만 쓸 수 있습니다.

## Side Effects

- [desktop/src/components/Avatar.tsx:Avatar] — `../lib/format`(colorFor, initials),
  `../lib/color`(readableOn), `../lib/presence`(presenceLabel) 호출.
- [desktop/src/components/Composer.tsx:pickFiles] — `api.upload(file, workspaceId)`
  로 파일을 올리고, 실패하면 store 의 `toast(...)` 로 알립니다.
- [desktop/src/components/Composer.tsx:Composer] — store 를 통해
  `setDraft(channelId, next)` / `s.drafts[channelId]` 읽기, `setReplyTo(null)`.
- [desktop/src/components/Composer.tsx:send] — `onSend(body, files.map(f => f.id))`
  호출 후 입력·첨부를 비우고 `onTyping(false)`.
- [desktop/src/components/MessageRow.tsx:openFile] — `settings.fileOpen === "save"`
  이고 폴더가 있으면 `fetchFile(fileUrl(file.url))` 로 받고
  `saveFile(folder, file.name, bytes)` 로 씁니다. 결과는 store 의 `toast` 로
  알립니다.
- [desktop/src/components/MessageRow.tsx:jumpToQuote] — 인용한 메시지를
  `document.getElementById` 로 찾아 스크롤시키고 `msg--pointed` 클래스를
  1400ms 뒤에 뗍니다.
- [desktop/src/components/MessageRow.tsx:MessageRow] — 본문을
  `renderBody(message.body)` 로 만들어 `dangerouslySetInnerHTML` 로 넣고,
  "본문 복사" 항목은 `navigator.clipboard?.writeText(message.body)` 를 씁니다.
- [desktop/src/components/Menu.tsx:Menu] — `document` 의 `keydown`/`pointerdown`
  리스너를 등록·해제하고 `document.body` 에 포털 노드를 만듭니다.
- [desktop/src/components/MessageList.tsx:onScroll] — 상단 근처에서
  `onLoadMore()` 호출.
- [desktop/src/components/Toasts.tsx:Toasts] — store 의 `dismiss(toast.id)` 호출.
- [desktop/src/components/Gate.tsx:Gate] — store 의 `signIn`, `signUp`,
  `acceptInvite` 호출.
- [desktop/src/components/Rail.tsx:openWorkspaceMenu] — `api.workspaces()` 호출.
  `openRoomWindow(target)` 로 새 창을 열고, 실패하면
  `reportError(error, "새 창을 열지 못했습니다")`. 프로필 메뉴에서
  `updateProfile({ presence })`, `signOut()`.
- [desktop/src/components/Dialogs.tsx:SearchDialog] — `api.search(workspaceId,
  term, 24)` 와 `api.channels(workspaceId)` 호출.
- [desktop/src/components/Dialogs.tsx:NewChannelDialog] — `createChannel({ name,
  topic, is_private, member_ids })` 를 부르고, 실패하면 대화상자 안에
  `field__error` 로 사유를 보여줍니다.
- [desktop/src/components/Dialogs.tsx:NewDmDialog] — `startDm(member.user.id)` 를
  부릅니다.
- [desktop/src/components/Dialogs.tsx:PinsDialog] — `api.pins(channel.id)` 를
  부르고, 실패하면 빈 목록으로 떨어집니다.
- [desktop/src/components/Dialogs.tsx:AddPeopleDialog] — `loadChannelMembers(targetId)`
  를 부르고, `addChannelMember(targetId, userId)` 로 초대합니다. 실패는
  store 의 토스트가 담당합니다.
- [desktop/src/components/Dialogs.tsx:LeaveChannelDialog] —
  `leaveChannel(targetId)` 를 부릅니다.
- [desktop/src/components/Dialogs.tsx:DeleteDmDialog] — `deleteDm(targetId)` 를
  부르고, 실패하면 `reportError(error, "대화를 삭제하지 못했습니다")`.
- [desktop/src/components/Dialogs.tsx:InviteDialog] — `createInvite(email)`,
  `revokeInvite(invite.id)`, `navigator.clipboard?.writeText(token)`.
- [desktop/src/components/Dialogs.tsx:ChannelSettingsDialog] —
  `updateChannel(targetId, { name, topic })`, `leaveChannel(targetId)`,
  `setDialog("addPeople", targetId)`.
- [desktop/src/components/SettingsDialog.tsx:Account] — `api.workspaces()` 호출,
  `loadWorkspace(workspace.id)`, `signOut()`, `updateProfile({ name, title,
  avatar_color })`.
- [desktop/src/components/SettingsDialog.tsx:Files.choose] — `pickFolder(...)`
  네이티브 픽커를 열고 `setSettings({ downloadFolder })` 로 저장합니다.
- [desktop/src/components/ProjectDialogs.tsx:ProjectDialog] —
  `createProject`/`updateProject`/`deleteProject`/`removeProjectMember`.
- [desktop/src/components/ProjectDialogs.tsx:TaskDialog] —
  `createTask`/`updateTask`/`deleteTask`/`addTaskComment`/`deleteTaskComment`,
  `loadMilestones(projectId)`.
- [desktop/src/components/ProjectsView.tsx:ProjectsView] — `ensureProjects()`,
  `selectProject(id)`, `moveTask(taskId, status, position)`, `setBoardMode`,
  `setActiveRoadmap`, `deleteRoadmap`, `openChannel(room.id)`.
- [desktop/src/components/ProjectChartDialog.tsx:ProjectChartDialog] —
  `api.milestones(target)` 와 `api.projectTasks(target)` 를 함께 부르고,
  `api.events(workspaceId, from, to)` 로 일정도 가져옵니다.
- [desktop/src/components/OrgView.tsx:OrgView] — `updateOrgUnit`,
  `updateMemberRole`, `loadOrg`, `removeMember`, `addOrgUnitMember`,
  `removeOrgUnitMember`, `addOrgUnitManager`, `removeOrgUnitManager`,
  `deleteOrgUnit`, `selectOrgUnit`.
- [desktop/src/components/OrgDialogs.tsx:submit] — `createOrgUnit(input)`,
  성공 시에만 `setDialog(null)`.
- [desktop/src/components/MilestonePanel.tsx:MilestonePanel] —
  `deleteMilestone(pending)`, `loadMilestones(project.id)`,
  `setDialog("milestone", ...)`.
- [desktop/src/components/MilestoneDialog.tsx:submit] — `createMilestone(projectId,
  input)` 또는 `updateMilestone(existing.id, input)`, 그리고 `setDialog(null)`.
- [desktop/src/components/ScheduleDialogs.tsx:EventDialog] — `createEvent`,
  `updateEvent`, `deleteEvent`, `rsvpEvent`, `setDialog(null)`.
- [desktop/src/components/ScheduleView.tsx:ScheduleView] — `loadEvents()`,
  `setEventDay(key)`, `setEventMonth(key)`, `setDialog("event", ...)`.
- [desktop/src/components/Select.tsx:Select], [desktop/src/components/MemberSelect.tsx:MemberSelect],
  [desktop/src/components/PersonPicker.tsx:PersonPicker],
  [desktop/src/components/Form.tsx:DateField] — 팝업 패널을 `document.body` 에
  `createPortal` 로 그리고, 창 `resize` / 문서 `scroll` / `pointerdown` /
  `keydown` 리스너를 등록했다가 해제합니다.

## Verification

- Run: `npm test` (desktop/ 에서 실행 — vitest). 이 디렉터리에는 단위 테스트가
  없고, 저장소 계약은 `desktop/src/lib/*.test.ts` 와
  `desktop/src/store/useStore.test.ts` 에서 검증됩니다.
- Run: `npm run typecheck` (desktop/ 에서 실행 — `tsc --noEmit`)
