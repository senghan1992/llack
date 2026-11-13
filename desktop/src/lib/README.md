# lib — HTTP 클라이언트, 도메인 타입, 포맷터, 셸 브리지

## Overview

부수적인 코드가 아니라 **프런트엔드의 계약 계층**입니다. 화면 컴포넌트
(`../components/`)와 상태 저장소(`../store/`)가 이 디렉터리만 통해 백엔드와
셸에 닿습니다.

| 파일 | 역할 |
| --- | --- |
| `api.ts` | REST 클라이언트 (`/api/v1`), 토큰, 오류 |
| `types.ts` | 도메인 모델 전부 |
| `ws.ts` | 실시간 WebSocket 클라이언트 |
| `settings.ts` | 기기별 사용자 설정(localStorage) |
| `theme.ts` | 라이트/다크 적용 |
| `desktop.ts` | Tauri 셸 브리지 (알림·폴더·파일) |
| `popout.ts` | 방을 별도 창으로 떼어내기 |
| `format.ts` | 날짜·시간·크기·아바타 포맷 |
| `calendar.ts` | 달력 날짜 계산 |
| `gantt.ts` | 간트 차트 시간 축 계산 |
| `color.ts` | 아바타 색과 대비 |
| `markdown.ts` | 메시지 본문 렌더링 |
| `presence.ts` | 존재 상태 목록과 라벨 |
| `keys.ts` | 입력 중 판정 |

## Interface

### `api.ts` — REST 클라이언트

- [desktop/src/lib/api.ts:API_BASE] — `import.meta.env.VITE_API_BASE` 또는
  기본값 `"http://127.0.0.1:8000"` (끝의 `/` 하나 제거).
- [desktop/src/lib/api.ts:API] — `` `${API_BASE}/api/v1` ``.
- [desktop/src/lib/api.ts:tokens] — 토큰 저장소. `access`/`refresh` 게터,
  `set(access, refresh)`, `clear()`.
- [desktop/src/lib/api.ts:ApiError] — `Error` 확장. `status: number`,
  `code: string`, `field: string | null`.
- [desktop/src/lib/api.ts:NETWORK_CODE] — `"network"`.
- [desktop/src/lib/api.ts:NETWORK_MESSAGE] — 백엔드가 닿지 않을 때의 한국어 문구.
- [desktop/src/lib/api.ts:friendlyMessage] — `friendlyMessage(error: unknown,
  fallback: string): string`.
- [desktop/src/lib/api.ts:api] — 백엔드 연산별 메서드를 담은 HTTP 클라이언트
  표면. 인증·워크스페이스·채널·DM·메시지·반응·고정·멤버·검색·초대·일정·파일·
  조직·프로젝트·할 일·로드맵·마일스톤을 모두 다룹니다.
- [desktop/src/lib/api.ts:fileUrl] — `fileUrl(path: string): string`.
- 주요 메서드 그룹:
  - [desktop/src/lib/api.ts:api.signup] / [desktop/src/lib/api.ts:api.login] /
    [desktop/src/lib/api.ts:api.me] / [desktop/src/lib/api.ts:api.updateMe]
  - [desktop/src/lib/api.ts:api.workspaces] / [desktop/src/lib/api.ts:api.bootstrap]
  - [desktop/src/lib/api.ts:api.channels] / [desktop/src/lib/api.ts:api.createChannel] /
    [desktop/src/lib/api.ts:api.channel] / [desktop/src/lib/api.ts:api.updateChannel] /
    [desktop/src/lib/api.ts:api.deleteChannel]
  - [desktop/src/lib/api.ts:api.joinChannel] / [desktop/src/lib/api.ts:api.leaveChannel] /
    [desktop/src/lib/api.ts:api.channelMembers] / [desktop/src/lib/api.ts:api.addChannelMember]
  - [desktop/src/lib/api.ts:api.messages] / [desktop/src/lib/api.ts:api.sendMessage] /
    [desktop/src/lib/api.ts:api.replies] / [desktop/src/lib/api.ts:api.editMessage] /
    [desktop/src/lib/api.ts:api.deleteMessage] / [desktop/src/lib/api.ts:api.markRead] /
    [desktop/src/lib/api.ts:api.pins]
  - [desktop/src/lib/api.ts:api.react] / [desktop/src/lib/api.ts:api.unreact] /
    [desktop/src/lib/api.ts:api.pin] / [desktop/src/lib/api.ts:api.unpin]
  - [desktop/src/lib/api.ts:api.dms] / [desktop/src/lib/api.ts:api.openDm] /
    [desktop/src/lib/api.ts:api.members] / [desktop/src/lib/api.ts:api.updateMember] /
    [desktop/src/lib/api.ts:api.removeMember]
  - [desktop/src/lib/api.ts:api.search] / [desktop/src/lib/api.ts:api.users] /
    [desktop/src/lib/api.ts:api.invites] / [desktop/src/lib/api.ts:api.createInvite] /
    [desktop/src/lib/api.ts:api.revokeInvite] / [desktop/src/lib/api.ts:api.acceptInvite]
  - [desktop/src/lib/api.ts:api.events] / [desktop/src/lib/api.ts:api.createEvent] /
    [desktop/src/lib/api.ts:api.updateEvent] / [desktop/src/lib/api.ts:api.deleteEvent] /
    [desktop/src/lib/api.ts:api.rsvpEvent]
  - [desktop/src/lib/api.ts:api.upload] — `POST /files?workspace_id=…` (FormData).
  - [desktop/src/lib/api.ts:api.orgOverview] / [desktop/src/lib/api.ts:api.createOrgUnit] /
    [desktop/src/lib/api.ts:api.updateOrgUnit] / [desktop/src/lib/api.ts:api.deleteOrgUnit] /
    [desktop/src/lib/api.ts:api.addOrgUnitMember] / [desktop/src/lib/api.ts:api.removeOrgUnitMember] /
    [desktop/src/lib/api.ts:api.addOrgUnitManager] / [desktop/src/lib/api.ts:api.removeOrgUnitManager]
  - [desktop/src/lib/api.ts:api.projects] / [desktop/src/lib/api.ts:api.createProject] /
    [desktop/src/lib/api.ts:api.updateProject] / [desktop/src/lib/api.ts:api.deleteProject] /
    [desktop/src/lib/api.ts:api.addProjectMember] / [desktop/src/lib/api.ts:api.removeProjectMember]
  - [desktop/src/lib/api.ts:api.myTasks] / [desktop/src/lib/api.ts:api.projectTasks] /
    [desktop/src/lib/api.ts:api.createTask] / [desktop/src/lib/api.ts:api.updateTask] /
    [desktop/src/lib/api.ts:api.deleteTask] / [desktop/src/lib/api.ts:api.addTaskComment] /
    [desktop/src/lib/api.ts:api.deleteTaskComment]
  - [desktop/src/lib/api.ts:api.roadmaps] / [desktop/src/lib/api.ts:api.deleteRoadmap] /
    [desktop/src/lib/api.ts:api.milestones] / [desktop/src/lib/api.ts:api.createMilestone] /
    [desktop/src/lib/api.ts:api.updateMilestone] / [desktop/src/lib/api.ts:api.deleteMilestone]

### `types.ts` — 도메인 모델

- [desktop/src/lib/types.ts:Presence] — `"online" | "busy" | "dnd" | "away" | "brb" | "offline"`.
- [desktop/src/lib/types.ts:Role] — `"owner" | "admin" | "member"`.
- [desktop/src/lib/types.ts:ChannelKind] — `"channel" | "dm"`.
- [desktop/src/lib/types.ts:User], `Member`, `Workspace`, `Reaction`, `FileRef`,
  `ReplyTo`, `Message`, `Channel` — 대화 도메인.
- [desktop/src/lib/types.ts:OrgUnit], `OrgOverview`, `OrgSummary`, `OrgUnitInput` — 조직 도메인.
- [desktop/src/lib/types.ts:Bootstrap] — `workspace`, `channels`, `dms`, `members`,
  `me`, `org`.
- [desktop/src/lib/types.ts:Invite] — 초대.
- [desktop/src/lib/types.ts:RsvpResponse] — `"accepted" | "declined" | "tentative"`.
- [desktop/src/lib/types.ts:EventResponse] — `RsvpResponse | "pending"`.
- [desktop/src/lib/types.ts:ScheduleAttendee], `ScheduleEvent`, `EventInput` — 일정 도메인.
- [desktop/src/lib/types.ts:SearchResult] — `message` + `channel`.
- [desktop/src/lib/types.ts:TaskStatus] — `"request" | "todo" | "in-progress" | "done"`.
- [desktop/src/lib/types.ts:Project], `TaskComment`, `Task`, `ProjectInput`,
  `Roadmap`, `TaskInput` — 프로젝트 도메인.
- [desktop/src/lib/types.ts:Milestone], `MilestoneInput` — 마일스톤 도메인.
- [desktop/src/lib/types.ts:Tokens], `Session` — `Session` 은 `Tokens` 에
  `user` 와 `workspace` 를 더한 것.
- [desktop/src/lib/types.ts:WsEvent] — 실시간 이벤트. `type` 은 `hello`,
  `message.created`, `message.updated`, `message.deleted`, `reaction.updated`,
  `typing`, `presence`, `user.updated`, `channel.created`, `channel.updated`,
  `members.changed`, `unread`, `event.created`, `event.updated`, `event.deleted`,
  `project.created`, `project.updated`, `project.deleted`, `task.created`,
  `task.updated`, `task.deleted`, `org.changed`, `pong` 중 하나.

### `ws.ts` — 실시간 클라이언트

- [desktop/src/lib/ws.ts:Realtime] — `onEvent` / `onOpen` / `onClose` 콜백,
  `connected` 게터, `connect(token)`, `send(payload)`, `close()`.

### `settings.ts` — 기기별 설정

- [desktop/src/lib/settings.ts:ThemeMode] — `"light" | "dark" | "system"`.
- [desktop/src/lib/settings.ts:NotificationPreview] — `"preview" | "subject"`.
- [desktop/src/lib/settings.ts:ClockFormat] — `"24h" | "12h"`.
- [desktop/src/lib/settings.ts:FileOpenMode] — `"open" | "save"`.
- [desktop/src/lib/settings.ts:Settings] — `notifications`, `notificationPreview`,
  `theme`, `clock`, `fileOpen`, `downloadFolder`, `imagePreview`, `splitView`,
  `railCollapsed`.
- [desktop/src/lib/settings.ts:getSettings] / `setSettings` / `subscribeSettings` /
  `useSettings` / `useSetSettings`.

### `theme.ts`

- [desktop/src/lib/theme.ts:resolvedTheme] — `resolvedTheme(mode: ThemeMode): "light" | "dark"`.
- [desktop/src/lib/theme.ts:currentTheme] — `currentTheme(): "light" | "dark"`.
- [desktop/src/lib/theme.ts:applyTheme] — `applyTheme(): void`.
- [desktop/src/lib/theme.ts:watchTheme] — `watchTheme(): void`.

### `desktop.ts` — Tauri 셸 브리지

- [desktop/src/lib/desktop.ts:inDesktop] — `inDesktop(): Promise<boolean>`.
- [desktop/src/lib/desktop.ts:useInDesktop] — `useInDesktop(): boolean`.
- [desktop/src/lib/desktop.ts:notify] — `notify(title: string, body: string): Promise<void>`.
- [desktop/src/lib/desktop.ts:pickFolder] — `pickFolder(title: string): Promise<string | null>`.
- [desktop/src/lib/desktop.ts:saveFile] — `saveFile(dir: string, name: string, bytes: Uint8Array): Promise<string>`.
- [desktop/src/lib/desktop.ts:fetchFile] — `fetchFile(url: string): Promise<Uint8Array>`.

### `popout.ts` — 방 창

- [desktop/src/lib/popout.ts:roomLabel] — `roomLabel(channelId: string): string`.
- [desktop/src/lib/popout.ts:roomTitle] — `roomTitle(channel: Channel): string`.
- [desktop/src/lib/popout.ts:openRoomWindow] — `openRoomWindow(channel: Channel): Promise<void>`.
- [desktop/src/lib/popout.ts:currentRoomId] — `currentRoomId(): Promise<string | null>`.
- [desktop/src/lib/popout.ts:setRoomTitle] — `setRoomTitle(title: string): Promise<void>`.

### `format.ts`

- [desktop/src/lib/format.ts:formatTime], `formatDate`, `formatDateLong`, `weekday`,
  `dayLabel`, `dueLabel`, `isSameDay`, `dateRange`, `periodLabel`, `initials`,
  `formatBytes`, `relativeTime`, `colorFor`, `mentionsUser`.

### `calendar.ts`

- [desktop/src/lib/calendar.ts:dateKey], `monthKey`, `parseDateKey`, `parseMonthKey`,
  `startOfMonth`, `addMonths`, `monthGrid`, `startOfDay`, `endOfDay`, `dayOf`,
  `toLocalInput`, `toDateInput`, `toTimeInput`, `fromDateTimeInput`, `isSameMonth`.

### `gantt.ts`

- [desktop/src/lib/gantt.ts:dayStart], `nextDay`, `monthStartOf`, `monthCells`, `ratio`.
- [desktop/src/lib/gantt.ts:MonthCell] — `{ key, label, year, start, end }`.

### `color.ts`

- [desktop/src/lib/color.ts:AVATAR_PALETTE] — 아바타 색 7개.
- [desktop/src/lib/color.ts:AVATAR_INK] — `"#fcfcfb"`.
- [desktop/src/lib/color.ts:AVATAR_MIN_CONTRAST] — `5`.
- [desktop/src/lib/color.ts:parseHex], `contrastRatio`, `readableOn`.

### `markdown.ts`

- [desktop/src/lib/markdown.ts:escapeHtml] — `escapeHtml(input: string): string`.
- [desktop/src/lib/markdown.ts:renderBody] — `renderBody(body: string): string`.
- [desktop/src/lib/markdown.ts:QUICK_REACTIONS] — 빠른 반응 이모지 목록.

### `presence.ts`

- [desktop/src/lib/presence.ts:PresenceState] — `{ value, label, hint }`.
- [desktop/src/lib/presence.ts:PRESENCE_STATES] — 선택 가능한 상태 목록.
- [desktop/src/lib/presence.ts:presenceLabel] — `presenceLabel(presence: Presence | null | undefined): string`.

### `keys.ts`

- [desktop/src/lib/keys.ts:isWriting] — `isWriting(target: EventTarget | null): boolean`.

## Invariants

- [desktop/src/lib/api.ts:request] — `authorization: Bearer <토큰>` 헤더는
  액세스 토큰이 있을 때만 붙습니다. `content-type: application/json` 는 body 가
  있고 FormData 가 아닐 때만이라, 업로드 multipart 경계는 브라우저가 그대로 씁니다.
- [desktop/src/lib/api.ts:request] — 401 은 정확히 한 번만 재시도합니다.
  리프레시 토큰이 있고, 리프레시가 성공했고, 재시도 요청은 `retry = false` 로
  갑니다.
- [desktop/src/lib/api.ts:request] — 응답이 실패하면 `ApiError` 가 되며 code 기본값
  `"internal"`, message 기본값 `"요청이 실패했습니다 (<status>)"`, field 기본값
  `null`이고 값은 `payload.error.{code,message,field}` 에서 옵니다.
- [desktop/src/lib/api.ts:request] — 204 는 `undefined` 로 풀리고, 그 외 성공 응답은
  텍스트를 파싱해 빈 값이나 JSON 이 아니면 `null` 이 됩니다.
- [desktop/src/lib/api.ts:networkError] — 전송 실패(예외)는 언제나
  `ApiError(0, NETWORK_CODE, NETWORK_MESSAGE)` 로 바뀝니다. 서버가 없는 것과
  서버가 답한 것을 구분합니다.
- [desktop/src/lib/api.ts:friendlyMessage] — `NETWORK_CODE` 는 원래 메시지,
  401 은 "이메일 또는 비밀번호가 맞지 않습니다.", 409 는 "이미 등록된 이메일입니다.",
  500 이상은 "서버에서 문제가 발생했습니다. 잠시 뒤 다시 시도해 주세요.",
  그 외 `ApiError` 는 원래 메시지, `ApiError` 가 아니면 호출자의 폴백.
- [desktop/src/lib/api.ts:refreshTokens] — 리프레시는 single-flight 입니다.
  진행 중이면 모듈 레벨 `refreshing` promise 를 함께 쓰고 `finally` 에서 `null` 로
  되돌립니다.
- [desktop/src/lib/api.ts:tokens] — 토큰은 localStorage 의 고정 키
  `"llack.access"` 과 `"llack.refresh"` 에 항상 쌍으로 쓰거나 지웁니다.
- [desktop/src/lib/api.ts:fileUrl] — 절대 http/https 경로는 그대로 두고,
  나머지는 `API_BASE` 에 붙이며, 토큰이 있을 때만 `token` 쿼리 파라미터를
  덧붙입니다.
- [desktop/src/lib/api.ts:api.leaveChannel] — 채널 나가기는 DELETE 가 아니라
  `POST /channels/{id}/leave` 입니다.
- [desktop/src/lib/api.ts:api.unreact] — `DELETE /messages/{id}/reactions/{emoji}`
  이며 이모지는 퍼센트 인코딩됩니다.
- [desktop/src/lib/api.ts:api.upload] — 업로드는 `/files?workspace_id=…` 로 갑니다.
  파일은 워크스페이스가 소유합니다.
- [desktop/src/lib/types.ts:OrgOverview] — 조직 단위 목록은 평평한 배열이고,
  트리는 `parent_id` → `id` 로 다시 만듭니다.
- [desktop/src/lib/types.ts:OrgUnit] — `depth` 는 루트에서 0 이고 중첩 한 단계마다
  1 씩 늘어납니다.
- [desktop/src/lib/types.ts:Channel] — `is_member` 은 뷰어가 그 채널에 있는지
  알려줍니다. 공개 채널은 나간 뒤에도 워크스페이스 디렉터리에 남습니다.
- [desktop/src/lib/types.ts:Message] — `inline` 은 회글이 채널에 쓰였다는 뜻이라
  스레드에도 채널에도 함께 보입니다.
- [desktop/src/lib/types.ts:Milestone] — `progress` 는 지금 유효한 진행률입니다.
  카드가 연결돼 있으면 연결된 카드의 진행률, 아니면 슬라이더 값.
  `auto_progress` 는 연결 카드에서 온 값인지, `manual_progress` 는 슬라이더 값인지
  를 말합니다.
- [desktop/src/lib/types.ts:TaskInput] — `milestone_id` 를 `null` 로 넣으면
  마일스톤이 해제됩니다. `roadmap_id`, `assignee_id` 도 같습니다.
- [desktop/src/lib/calendar.ts:monthGrid] — 항상 정확히 42칸(6주)을 내며 첫 칸은
  1일 당 주의 일요일입니다(요일 인덱스는 일요일이 0).
- [desktop/src/lib/calendar.ts:fromDateTimeInput] — 폼의 로컬 날짜·시각을
  해석해 `toISOString()` UTC 문자열로 돌려줍니다.
- [desktop/src/lib/color.ts:readableOn] — 대비가 이미 충분하면 정규화된 hex를
  그대로 주고, 부족하면 색의 명도만 낮춰(색상 Hue 유지, 0.94배씩 최대 60단계)
  최소 대비를 채웁니다. 파싱 불가하면 입력 그대로.
- [desktop/src/lib/color.ts:AVATAR_MIN_CONTRAST] — 아바타 이니셜이 타일 위에서
  유지해야 하는 최소 대비는 5입니다.
- [desktop/src/lib/settings.ts:DEFAULTS] — 기본값은 `notifications true`,
  `notificationPreview "preview"`, `theme "light"`, `clock "24h"`,
  `fileOpen "open"`, `downloadFolder null`, `imagePreview true`,
  `splitView true`, `railCollapsed false`.
- [desktop/src/lib/settings.ts:read] — 저장된 JSON 이 없거나 읽기 실패하거나
  깨졌으면 모든 필드를 기본값으로 되돌리고, enum 필드는 `oneOf()` 로 보정합니다.
  옛 키 `"llack.theme"` 은 저장된 테마가 없을 때만 `"light"`/`"dark"` 면 이관합니다.
- [desktop/src/lib/settings.ts:setSettings] — 패치가 아무것도 바꾸지 않으면
  무동작이므로 같은 값을 쓰면 구독자가 깨지 않습니다. 패치는 통째로 교체하지
  않고 위에 얹습니다.
- [desktop/src/lib/theme.ts:watchTheme] — 멱등입니다. 이미 리스너를 설치했으면
  바로 반환합니다. OS 색상 스킴 변화는 테마 설정이 `"system"` 일 때만, 설정
  변화는 해석된 모드가 마지막 적용값과 다를 때만 다시 적용합니다.
- [desktop/src/lib/ws.ts:Realtime.open] — URL 은 `API_BASE` 의 `http` 를 `ws` 로
  바꾼 뒤 `/api/v1/ws?token=<인코딩>` 을 붙입니다. 성공한 열 때마다 재시도
  횟수가 0으로 돌아갑니다.
- [desktop/src/lib/ws.ts:Realtime.open] — 의도적 `close()` 나 코드 4401 뒤에는
  재시도하지 않고, 그 외에는 `min(800 * 2^attempt, 10000)` ms 간격으로 재시도합니다.
- [desktop/src/lib/ws.ts:Realtime.send] — 소켓이 `OPEN` 일 때만 보내며 페이로드는
  `JSON.stringify` 로 직렬화합니다.
- [desktop/src/lib/desktop.ts:notify] — `settings.notifications` 가 false 면
  아무것도 보내지 않고, 브라우저를 벗어나지 않습니다. 본문은
  `settings.notificationPreview === "preview"` 일 때만 포함됩니다.
- [desktop/src/lib/desktop.ts:saveFile] — 폴더와 파일 이름은 헤더가 latin-1 이라
  한글 경로가 들어갈 수 있어 16진수 인코딩(`X-Llack-Dir`, `X-Llack-Name`)으로
  보냅니다.
- [desktop/src/lib/format.ts:initials] — 한글이 섞인 이름은 마지막 두 글자,
  라틴 단일 단어는 앞 두 글자 대문자, 그 외에는 앞 단어와 뒤 단어의 첫 글자.
- [desktop/src/lib/format.ts:colorFor] — 결정적입니다. 같은 seed 는 항상 같은
  `AVATAR_PALETTE` 항목으로 갑니다.
- [desktop/src/lib/format.ts:mentionsUser] — 이름이 비면 false, 그 외에는 `@이름`
  뒤에 단어 글자나 한글이 오지 않아야 합니다.
- [desktop/src/lib/keys.ts:isWriting] — contentEditable, `<input>`, `<textarea>`,
  `.composer` 안의 요소에서 true 입니다.
- [desktop/src/lib/markdown.ts:renderBody] — 모든 텍스트를 먼저 이스케이프하고
  나서 정해진 표시만 올립니다. 원본 HTML 이 DOM 에 도달하지 않습니다.
- [desktop/src/lib/popout.ts:openRoomWindow] — 이미 열린 방 창이면 두 번째 창을
  만들지 않고 그 창에 포커스만 줍니다. 셸에서는 `room-<id>` 라벨의
  WebviewWindow 를 560×760(최소 380×460)으로 만듭니다.
- [desktop/src/lib/popout.ts:currentRoomId] — 셸에서 창 라벨이 `"room-"` 로
  시작할 때만 방 id를 돌려주고, 그 외에는 `null`(워크스페이스 창)입니다.
- [desktop/src/lib/presence.ts:PRESENCE_STATES] — online, busy, dnd, away, brb 순
  이며 `offline` 은 없습니다.

## Side Effects

- [desktop/src/lib/api.ts:tokens] — localStorage 에서 토큰을 읽고
  `"llack.access"` / `"llack.refresh"` 에 씁니다.
- [desktop/src/lib/api.ts:request] — `${API}${path}` 로 `fetch` 를 호출합니다.
- [desktop/src/lib/api.ts:refreshTokens] — `POST ${API}/auth/refresh` 로
  `{ refresh_token }` 을 보내고 성공하면 토큰을 저장합니다.
- [desktop/src/lib/api.ts:fileUrl] — 파일 URL에 토큰을 쿼리 파라미터로 붙입니다.
  `<img>` 요소는 authorization 헤더를 보낼 수 없기 때문입니다.
- [desktop/src/lib/desktop.ts:inDesktop] — Tauri `isTauri()` 로 셸 여부를 확인합니다.
- [desktop/src/lib/desktop.ts:notify] —
  `@tauri-apps/plugin-notification` 의 `requestPermission()`,
  `isPermissionGranted()`, `sendNotification()` 을 씁니다.
- [desktop/src/lib/desktop.ts:pickFolder] —
  `@tauri-apps/plugin-dialog` 를 동적 import 해 디렉터리 픽커를 엽니다.
- [desktop/src/lib/desktop.ts:saveFile] —
  `@tauri-apps/api/core` 를 동적 import 해 Tauri 커맨드 `"save_file"` 을 호출합니다.
- [desktop/src/lib/desktop.ts:fetchFile] — 파일 바이트를 `fetch` 로 받고
  buffer 로 읽습니다. 응답이 실패하면 `Error('파일을 받지 못했습니다 (HTTP <status>)')`.
- [desktop/src/lib/popout.ts:openRoomWindow] — 브라우저에서는 `window.open()` 으로
  `?room=<channel id>` 를 붙인 팝업을 열고, 셸에서는 WebviewWindow 를 만들고
  `tauri://created` / `tauri://error` 를 기다립니다. 방 id는 localStorage 의
  `"llack.room.<label>"` 에 씁니다.
- [desktop/src/lib/popout.ts:setRoomTitle] — 브라우저에서는 `document.title`,
  셸에서는 `getCurrentWindow().setTitle()` 을 쓰며 오류는 삼킵니다.
- [desktop/src/lib/settings.ts:read] — localStorage 의 `"llack.settings"` 와 옛
  키 `"llack.theme"` 을 읽습니다.
- [desktop/src/lib/settings.ts:setSettings] — 병합된 설정을 `"llack.settings"` 에
  JSON으로 쓰고 모든 구독자를 부릅니다.
- [desktop/src/lib/theme.ts:applyTheme] — `document.documentElement.dataset.theme`
  을 쓰고, 셸이면 Tauri 커맨드 `"set_window_theme"` 를 호출합니다.
- [desktop/src/lib/theme.ts:watchTheme] — `'(prefers-color-scheme: dark)'`
  미디어 쿼리 리스너와 설정 구독을 등록합니다.
- [desktop/src/lib/ws.ts:Realtime.open] — WebSocket 을 열고 `setTimeout` 으로
  재연도를 예약하며 닫을 때 타이머를 지웁니다.
- [desktop/src/lib/ws.ts:Realtime.send] — 소켓으로 JSON 페이로드를 보냅니다.
- [desktop/src/lib/ws.ts:Realtime.close] — 소켓을 닫고 재시도 타이머를 지웁니다.
- [desktop/src/lib/types.ts:User], [desktop/src/lib/calendar.ts:monthGrid],
  [desktop/src/lib/color.ts:contrastRatio]
  — 순수 모듈입니다. 네트워크·저장소·DOM 에 닿지 않습니다.

## Verification

- Run: `npm test` (desktop/ 에서 실행 — vitest).
  이 디렉터리의 `api.test.ts`, `gantt.test.ts`, `keys.test.ts` 가
  `api.ts`, `gantt.ts`, `keys.ts` 의 계약을 고정합니다.
- Run: `npm run typecheck` (desktop/ 에서 실행 — `tsc --noEmit`)
