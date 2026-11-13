# store — 단일 Zustand 스토어

## Overview

앱의 상태는 `desktop/src/store/useStore.ts` **한 파일**에 모입니다.
`create<StoreState>((set, get) => ({ ... }))` 로 만들어지는 Zustand 스토어
하나이고, `useStore` 를 selector로 구독하는 컴포넌트들이 여기 한 상태를
공유합니다.

담당하는 영역은 세 가지입니다.

1. **세션** — 로그인, 워크스페이스 부트스트랩, 워크스페이스 전환
2. **대화** — 채널·DM·메시지·스레드·읽음·입력 중·초안
3. **보드** — 일정, 프로젝트·할 일·로드맵·마일스톤, 조직

화면 상태(다이얼로그 종류, 토스트, 레이아웃)도 같은 스토어에 있습니다.

## Interface

### 내보내는 것

- [desktop/src/store/useStore.ts:useStore] — 유일한 공개 값.
  `export const useStore = create<StoreState>((set, get) => ({ ... }))`.
- [desktop/src/store/useStore.ts:ReplyScope] — `"channel" | "thread"`.
- [desktop/src/store/useStore.ts:DialogKind] — 열 수 있는 대화상자의 종류.
  `"palette"`, `"search"`, `"channels"`, `"people"`, `"settings"`,
  `"newChannel"`, `"newDm"`, `"pins"`, `"invite"`, `"channelSettings"`,
  `"addPeople"`, `"leaveChannel"`, `"deleteDm"`, `"event"`, `"project"`,
  `"task"`, `"newOrgUnit"`, `"milestone"`, `"projectChart"`, 또는 `null`.
- [desktop/src/store/useStore.ts:Toast] — `{ id, text, action? }`.
  `action` 은 `{ label, run }`.

### `StoreState` — 상태 필드

- 세션: `status: "boot" | "anon" | "ready"`, `bootError`, `session: Session | null`,
  `user: User | null`, `workspaceId`, `workspaceName`.
- 명단·선택: `channels: Channel[]`, `members: Member[]`,
  `channelMembers: Record<string, Member[]>`, `activeId: string | null`.
- 레이아웃: `view: "channel" | "schedule" | "projects" | "org"`,
  `board: "schedule" | "projects" | null`, `wide`, `splitEnabled`,
  `railCollapsed`, `idle`.
- 대화: `recentRooms: string[]`, `drafts: Record<string, string>`,
  `messages: Record<string, Message[]>`, `hasMore`, `loading`, `loadingMore`,
  `errors: Record<string, string>`, `threadRoot: Message | null`, `replies`,
  `replyTo: { message, scope } | null`, `typing: Record<string, TypingEntry[]>`.
- 오버레이·존재: `dialog: DialogKind`, `dialogTarget: string | null`,
  `toasts: Toast[]`, `connected`, `presence: Record<string, Presence>`,
  `muted`, `invites: Invite[]`.
- 일정: `events: ScheduleEvent[]`, `eventsLoading`, `eventsError`,
  `eventMonth: string`(`YYYY-MM`), `eventDay: string`(`YYYY-MM-DD`).
- 프로젝트: `projects: Project[]`, `projectsLoading`, `projectsError`,
  `activeProjectId`, `tasks: Record<string, Task[]>`,
  `roadmaps: Record<string, Roadmap[]>`, `activeRoadmapId`, `myTasks: Task[]`,
  `projectFilter: "all" | "mine"`, `milestones: Record<string, Milestone[]>`,
  `milestonesLoading`, `milestonesError`, `boardMode: "board" | "milestones"`.
- 조직: `orgUnits: OrgUnit[]`, `orgAdmins: Member[]`, `orgMyRole: Role | undefined`,
  `orgCanManageAdmins`, `orgLoading`, `orgError`, `activeOrgUnitId`,
  `orgManagedUnitIds`.

### `StoreState` — 액션

- 인증: `boot()`, `signIn(email, password)`,
  `signUp({ email, password, name, workspace_name })`, `signOut()`,
  `loadWorkspace(workspaceId)`.
- 방·이동: `openChannel(channelId)`, `enterChannel(channelId)`,
  `stepRoom(direction, onlyUnread?)`, `setDraft(channelId, body)`,
  `clearScreen()`, `setWide(wide)`, `setRailCollapsed(collapsed)`,
  `closeBoard()`, `expandBoard()`, `besideBoard()`.
- 일정: `openSchedule()`, `loadEvents(month?)`, `setEventDay(day)`,
  `setEventMonth(month)`, `createEvent(input)`, `updateEvent(eventId, input)`,
  `deleteEvent(eventId)`, `rsvpEvent(eventId, response)`.
- 프로젝트: `openProjects()`, `ensureProjects()`, `openProject(projectId)`,
  `loadProjects()`, `loadProjectTasks(projectId)`, `loadMyTasks()`,
  `selectProject(projectId)`, `setProjectFilter(filter)`.
- 조직: `openOrg()`, `loadOrg()`, `selectOrgUnit(unitId)`,
  `createOrgUnit(input)`, `updateOrgUnit(unitId, input)`, `deleteOrgUnit(unitId)`,
  `addOrgUnitMember(unitId, userId)`, `removeOrgUnitMember(unitId, userId)`,
  `addOrgUnitManager(unitId, userId)`, `removeOrgUnitManager(unitId, userId)`.
- 프로젝트·할 일: `createProject(input)`, `updateProject(projectId, input)`,
  `deleteProject(projectId)`, `addProjectMember(projectId, userId)`,
  `removeProjectMember(projectId, userId)`, `createTask(projectId, input)`,
  `loadRoadmaps(projectId)`, `deleteRoadmap(projectId, roadmapId)`,
  `setActiveRoadmap(roadmapId)`, `loadMilestones(projectId)`,
  `createMilestone(projectId, input)`, `updateMilestone(milestoneId, input)`,
  `deleteMilestone(milestoneId)`, `setBoardMode(mode)`,
  `updateTask(taskId, input)`, `moveTask(taskId, status, position?)`,
  `deleteTask(taskId)`, `addTaskComment(taskId, body)`,
  `deleteTaskComment(commentId)`.
- 메시지: `loadMessages(channelId, older?)`, `sendMessage(body, parentId?,
  attachmentIds?)`, `editMessage(messageId, body)`, `deleteMessage(messageId)`,
  `toggleReaction(message, emoji)`, `togglePin(message)`, `markRead(channelId)`,
  `setTyping(channelId, on)`.
- 스레드: `openThread(message)`, `closeThread()`,
  `setReplyTo(message | null, scope?)`.
- 채널·멤버·프로필: `createChannel(input)`, `updateChannel(channelId, input)`,
  `updateMemberRole(userId, role)`, `loadChannelMembers(channelId)`,
  `addChannelMember(channelId, userId)`, `removeMember(userId)`,
  `joinChannel(channelId)`, `leaveChannel(channelId)`, `deleteDm(channelId)`,
  `startDm(userId)`, `updateProfile(input)`.
- 초대: `loadInvites()`, `createInvite(email, role?)`, `revokeInvite(inviteId)`,
  `acceptInvite(token)`.
- UI: `setDialog(dialog, target?)`, `toast(text, action?)`, `dismissToast(id)`,
  `reportError(error, fallback?)`.

### 모듈 내부 도우미 (공개 아님)

- [desktop/src/store/useStore.ts:replaceUser], `upsertMessage`, `upsertEvent`,
  `upsertProject`, `withTask`, `findMilestone`, `replaceMessage`,
  `withMyReaction`, `findMessage`, `canSplit`, `toggleBoard`, `railRooms`,
  `pickNeighbour`, `pickUnread`.
- [desktop/src/store/useStore.ts:RECENT_LIMIT] — `8`.

## Invariants

- [desktop/src/store/useStore.ts:canSplit] — 나란히 보기에는 세 가지가 모두
  필요합니다: `wide` && `splitEnabled` && 대화방이 열려 있음.
- [desktop/src/store/useStore.ts:toggleBoard] — 나란히 볼 수 없으면 보드가 대화
  자리를 대신하고(`view = kind`, `board = null`), 다시 누르면 대화가 돌아옵니다.
  나란히 볼 수 있으면 `view` 는 `"channel"` 로 두고 같은 보드를 토글합니다.
- [desktop/src/store/useStore.ts:railRooms] — 레일 순서는 고정입니다. 먼저
  들어간 채널(`kind === "channel" && is_member !== false`), 그다음 DM
  (`kind === "dm"`).
- [desktop/src/store/useStore.ts:pickNeighbour] / [desktop/src/store/useStore.ts:pickUnread]
  — 레일 끝에서 멈춥니다. 처음으로 돌아가지 않습니다. `pickUnread` 는
  `unread_count > 0` 인 방만 고릅니다.
- [desktop/src/store/useStore.ts:stepRoom] — 레일 순서대로 걸으며 양 끝에서
  멈춥니다.
- [desktop/src/store/useStore.ts:findMessage] — 모든 방의 메시지 목록 →
  스레드 답글 → 스레드 루트 순으로 찾습니다.
- [desktop/src/store/useStore.ts:withMyReaction] — 현재 사용자의 반응만 뒤집고
  다른 사람의 수는 그대로 둡니다. 마지막 사용자를 지우면 반응 항목 자체가
  사라집니다.
- [desktop/src/store/useStore.ts:replaceUser] — 바꾼 사용자가 명단에 없으면
  배열을 그대로(같은 참조) 돌려줍니다.
- [desktop/src/store/useStore.ts:upsertMessage] / `upsertEvent` / `upsertProject`
  — 같은 id 있으면 제자리에서 교체하고, 없으면 덧붙입니다.
- [desktop/src/store/useStore.ts:replaceMessage] — 목록을 매핑해 같은 id의
  메시지를 바꿉니다. 덧붙이지는 않습니다.
- [desktop/src/store/useStore.ts:withTask] — 태스크는 `tasks[task.project_id]`
  에 들어갑니다. 프로젝트별 목록이 태스크 자신의 프로젝트 id로 키가 됩니다.
- [desktop/src/store/useStore.ts:findMilestone] — 모든 프로젝트의 마일스톤
  목록을 훑습니다. 마일스톤은 프로젝트가 아니라 한 장의 평평한 맵에 들어
  있습니다.
- [desktop/src/store/useStore.ts:RECENT_LIMIT] — 최근 방 목록은 최대 8개입니다.
- [desktop/src/store/useStore.ts:boot] — 토큰이 하나도 없으면 네트워크 호출 없이
  곧바로 `status = "anon"` 이 됩니다. 워크스페이스 목록이 비어도 `anon` 입니다.
- [desktop/src/store/useStore.ts:boot] — 부팅 중 401 이면 토큰을 지우고 `anon`
  으로 갑니다. 그 밖의 실패는 `status = "anon"` + `bootError` 로 끝납니다.
  (토스트는 5초에 사라지지만 `bootError` 는 남습니다.)
- [desktop/src/store/useStore.ts:signIn] / [desktop/src/store/useStore.ts:signUp]
  — `loadWorkspace` 가 401 로 실패하면 토큰을 지웁니다. 서버가 거부한 세션은
  남기지 않습니다.
- [desktop/src/store/useStore.ts:signOut] — 모든 조각을 명시적으로 초기화합니다
  (채널, 멤버, 메시지, 최근 방, 초안, 일정, 프로젝트, 할 일, 로드맵,
  마일스톤, 조직…).
- [desktop/src/store/useStore.ts:loadWorkspace] — 워크스페이스가 바뀌면 이전
  워크스페이스의 방과 보드를 모두 비웁니다. 다른 팀의 방은 이 팀의 방이
  아닙니다.
- [desktop/src/store/useStore.ts:loadWorkspace] — 열린 방이 없으면 첫 채널
  (없으면 첫 DM)을 엽니다. 프로젝트 목록은 백그라운드로
  `void get().loadProjects()` 로 받아옵니다.
- [desktop/src/store/useStore.ts:openChannel] — 이미 열려 있는 방을 다시 열면
  보드가 접히고(`view "channel"`, `board null`), 읽음 처리됩니다.
- [desktop/src/store/useStore.ts:openChannel] — 보드는 `wide && splitEnabled`
  일 때만 대화 옆에 둘 수 있고, 보드가 될 수 있는 것은 `"schedule"` 과
  `"projects"` 뿐입니다. 조직 보드는 없습니다.
- [desktop/src/store/useStore.ts:setWide] — 보드가 열려 있는 상태에서 창을
  좁히면 보드를 버리지 않고 주 pane 을 넘겨받습니다(`view = board`,
  `board = null`).
- [desktop/src/store/useStore.ts:setRailCollapsed] — 레일 접힘 상태는 읽는
  사람의 것이고 다음 실행에도 남습니다: `setSettings({ railCollapsed })` 로
  먼저 저장한 뒤 상태를 갱신합니다.
- [desktop/src/store/useStore.ts:loadEvents] — 달력 창은 기준 월로부터 계산됩니다.
  from 은 1일의 7일 전, to 는 다음 달 마지막 날의 7일 뒤, next 는 to + 2개월.
- [desktop/src/store/useStore.ts:createEvent] — 다른 달에 만든 일정은 보기도
  따라갑니다: `eventMonth` 을 바꾸고 그 달의 일정을 다시 불러옵니다.
- [desktop/src/store/useStore.ts:selectProject] — 활성 프로젝트가 바뀌면
  `activeRoadmapId` 는 `null`, `boardMode` 는 `"board"` 로 초기화됩니다.
- [desktop/src/store/useStore.ts:loadRoadmaps] / [desktop/src/store/useStore.ts:loadProjectTasks]
  — 실패해도 빈 배열을 저장할 뿐 예외를 던지지 않습니다. 보드가 계속 쓸 수
  있어야 합니다.
- [desktop/src/store/useStore.ts:moveTask] — 카드는 왕복 전에 `tasks` 에 먼저
  기록되고, 서버가 거절하면 이전 태스크로 되돌린 뒤 오류를 다시 던집니다.
- [desktop/src/store/useStore.ts:createTask] / `updateTask` / `moveTask` /
  `deleteTask` — 마일스톤 진행률과 개수는 서버에 있으므로 태스크가 바뀔 때마다
  마일스톤 목록을 다시 읽습니다.
- [desktop/src/store/useStore.ts:createOrgUnit] — 성공하면 `true`, 실패하면
  `reportError` 후 `false` 를 돌려줍니다. 같은 조직의 다른 액션들은
  (`updateOrgUnit`, `deleteOrgUnit`, `addOrgUnitMember`, `removeOrgUnitMember`,
  `addOrgUnitManager`, `removeOrgUnitManager`) 예외를 다시 던지지 않고 토스트로
  알립니다.
- [desktop/src/store/useStore.ts:loadMessages] — 이미 그 방의 페이지를 불러오는
  중이거나 `hasMore` 가 false 면 이전 페이지를 받지 않습니다. 이전 페이지는
  `limit 40` + `before = 첫 메시지 id`, 첫 페이지는 `limit 50` 입니다.
- [desktop/src/store/useStore.ts:sendMessage] — 열린 방도 없고 본문도 비어있지도
  않고 첨부도 없으면 아무것도 보내지 않습니다. `parentId` 가 있으면 scope 은
  `"thread"`, 아니면 `"channel"` 이고 `reply_to_id` 와 `inline` 은
  `"channel"` scope 일 때만 전송합니다.
- [desktop/src/store/useStore.ts:toggleReaction] — 반응은 왕복 전에 스토어에
  먼저 칠해지고, 서버가 거절하면 이전 집합으로 되돌린 뒤 오류를 다시
  던집니다.
- [desktop/src/store/useStore.ts:markRead] — 읽음 표시는 정확히 하나만 갑니다.
  연결되어 있으면 WebSocket, 아니면 REST. 두 다 같이 보내면 서버가 서로
  경합합니다. 어느 쪽이든 그 채널의 `unread_count` 는 0 이 됩니다.
- [desktop/src/store/useStore.ts:openThread] — 받아온 답글은 같은 스레드 루트가
  계속 열려 있을 때만 적용됩니다. 그동안 다른 스레드가 열렸다면 덮어쓰지
  않습니다.
- [desktop/src/store/useStore.ts:closeThread] — 대기 중인 `replyTo` 는 scope 가
  `"thread"` 일 때만 함께 지워집니다.
- [desktop/src/store/useStore.ts:enterChannel] — 멤버가 아닌 공개 채널을 열면
  자동으로 참여합니다. 비공개 채널은 그대로 엽니다.
- [desktop/src/store/useStore.ts:leaveChannel] — 공개 방은 나간 뒤에도
  `is_member false` 로 워크스페이스 디렉터리에 남고, 비공개 방은 완전히
  사라집니다. 빈 pane 을 남기지 않고 다른 멤버 채널로 옮깁니다.
- [desktop/src/store/useStore.ts:deleteDm] — DM과 그 메시지는 양쪽에서 사라지고,
  활성 방은 다른 멤버 채널로 옮겨집니다.
- [desktop/src/store/useStore.ts:updateProfile] — 새 프로필은 보이는 곳
  전부에 반영됩니다: 헤더의 user, `session.user`, 멤버 명단, 존재 상태 맵,
  모든 채널 명단.
- [desktop/src/store/useStore.ts:createInvite] — 선택된 워크스페이스가 없으면
  요청 전에 `Error('워크스페이스가 선택되지 않았습니다')` 를 던집니다.
- [desktop/src/store/useStore.ts:setDialog] — `dialogTarget` 는 대화상자가 열려
  있을 때만 유지됩니다.
- [desktop/src/store/useStore.ts:toast] — 모든 토스트는 증가하는 id를 갖고
  5000ms 뒤 자동으로 사라집니다.
- [desktop/src/store/useStore.ts:reportError] — `ApiError` 면 서버가 준 메시지를,
  그 외에는 폴백 문구를 보여주고, 메시지를 반환합니다.
- [desktop/src/store/useStore.ts:realtime.onEvent] — `message.created` 중
  `parent_id` 가 있는 것은 `inline` 플래그가 있을 때만 방 목록에 답글로
  붙습니다. 내가 쓴 메시지의 스레드 답글은 상대가 쓴 경우에만 알림을 줍니다.
- [desktop/src/store/useStore.ts:realtime.onEvent] — `message.deleted` 는
  메시지의 본문과 반응을 비우고 `deleted_at` 을 찍습니다. `unread` 는 채널의
  `unread_count` 를 갱신합니다. `channel.created` 는 이미 있는 채널을
  무시합니다. `org.changed` 는 조직 화면이 열려 있을 때(`state.view === "org"`)
  만 조직을 다시 읽습니다.
- [desktop/src/store/useStore.ts:realtime.onEvent] — OS 알림은 내가 쓴 메시지가
  아닐 때만 갑니다: 내 메시지에 대한 스레드 답글, 열려 있지 않은 방의 메시지,
  나를 언급한 메시지.
- [desktop/src/lib/api.ts:api] — 모든 요청은 Bearer 액세스 토큰을 싣고, 401
  면 `POST /auth/refresh` 로 토큰을 교환한 뒤 **한 번만** 재시도합니다.

## Side Effects

- [desktop/src/store/useStore.ts:boot] — 네트워크: `api.workspaces()`,
  `api.me()`, `api.bootstrap()` 그리고 `realtime.connect()` 로 WebSocket
  (`${API_BASE}` 의 http 를 ws 로 바꾼 `/api/v1/ws?token=…`).
- [desktop/src/store/useStore.ts:signIn] / `signUp` — 네트워크:
  `POST /auth/login`, `POST /auth/signup`. localStorage: `tokens.set` 이
  `"llack.access"` / `"llack.refresh"` 에 씁니다. WebSocket:
  `realtime.connect(session.access_token)`.
- [desktop/src/store/useStore.ts:signOut] — WebSocket: `realtime.close()`.
  localStorage: `tokens.clear()` 가 두 토큰 키를 지웁니다.
- [desktop/src/store/useStore.ts:loadWorkspace] — 네트워크:
  `GET /workspaces/{id}/bootstrap` + 백그라운드로
  `GET /workspaces/{id}/projects`, `GET /workspaces/{id}/tasks`.
- [desktop/src/store/useStore.ts:setRailCollapsed] — localStorage: 전체 설정을
  `"llack.settings"` 에 JSON으로 씁니다.
- [desktop/src/store/useStore.ts:subscribeSettings] — 설정 쓰기가 생기면
  `splitEnabled` 와 `railCollapsed` 를 스토어로 밀어 넣습니다. 나란히 보기를
  끄는데 보드가 열려 있으면 `{ splitEnabled: false, board: null, view: state.board }`.
- 일정: [desktop/src/store/useStore.ts:loadEvents] — `GET /workspaces/{id}/events?from=&to=`.
  [desktop/src/store/useStore.ts:createEvent] — `POST /workspaces/{id}/events`.
  [desktop/src/store/useStore.ts:updateEvent] — `PATCH /events/{id}`.
  [desktop/src/store/useStore.ts:deleteEvent] — `DELETE /events/{id}`.
  [desktop/src/store/useStore.ts:rsvpEvent] — `POST /events/{id}/rsvp`.
- 프로젝트: [desktop/src/store/useStore.ts:loadProjects] —
  `GET /workspaces/{id}/projects` + `GET /workspaces/{id}/tasks`.
  [desktop/src/store/useStore.ts:loadRoadmaps] — `GET /projects/{id}/roadmaps`.
  [desktop/src/store/useStore.ts:deleteRoadmap] — `DELETE /roadmaps/{id}`.
  [desktop/src/store/useStore.ts:loadMilestones] — `GET /projects/{id}/milestones`.
  [desktop/src/store/useStore.ts:createMilestone] — `POST /projects/{id}/milestones`.
  [desktop/src/store/useStore.ts:updateMilestone] — `PATCH /milestones/{id}`.
  [desktop/src/store/useStore.ts:deleteMilestone] — `DELETE /milestones/{id}`.
  [desktop/src/store/useStore.ts:loadProjectTasks] — `GET /projects/{id}/tasks`.
  [desktop/src/store/useStore.ts:loadMyTasks] — `GET /workspaces/{id}/tasks`.
  [desktop/src/store/useStore.ts:createProject] — `POST /workspaces/{id}/projects`.
  [desktop/src/store/useStore.ts:updateProject] — `PATCH /projects/{id}`.
  [desktop/src/store/useStore.ts:deleteProject] — `DELETE /projects/{id}`.
  [desktop/src/store/useStore.ts:addProjectMember] — `POST /projects/{id}/members`.
  [desktop/src/store/useStore.ts:removeProjectMember] —
  `DELETE /projects/{id}/members/{userId}`.
  [desktop/src/store/useStore.ts:createTask] — `POST /projects/{id}/tasks`.
  [desktop/src/store/useStore.ts:updateTask] — `PATCH /tasks/{id}`.
  [desktop/src/store/useStore.ts:moveTask] — `PATCH /tasks/{id}` 에
  `{ status, position }`.
  [desktop/src/store/useStore.ts:deleteTask] — `DELETE /tasks/{id}`.
  [desktop/src/store/useStore.ts:addTaskComment] — `POST /tasks/{id}/comments`.
  [desktop/src/store/useStore.ts:deleteTaskComment] — `DELETE /task-comments/{id}`.
- 조직: [desktop/src/store/useStore.ts:loadOrg] — `GET /workspaces/{id}/org`.
  [desktop/src/store/useStore.ts:createOrgUnit] — `POST /workspaces/{id}/org/units`.
  [desktop/src/store/useStore.ts:updateOrgUnit] — `PATCH /org/units/{id}`.
  [desktop/src/store/useStore.ts:deleteOrgUnit] — `DELETE /org/units/{id}`.
  [desktop/src/store/useStore.ts:addOrgUnitMember] — `POST /org/units/{id}/members`.
  [desktop/src/store/useStore.ts:removeOrgUnitMember] —
  `DELETE /org/units/{id}/members/{userId}`.
  [desktop/src/store/useStore.ts:addOrgUnitManager] — `POST /org/units/{id}/managers`.
  [desktop/src/store/useStore.ts:removeOrgUnitManager] —
  `DELETE /org/units/{id}/managers/{userId}`.
- 대화: [desktop/src/store/useStore.ts:loadMessages] —
  `GET /channels/{id}/messages` (limit, before).
  [desktop/src/store/useStore.ts:sendMessage] — `POST /channels/{id}/messages`.
  [desktop/src/store/useStore.ts:editMessage] — `PATCH /messages/{id}`.
  [desktop/src/store/useStore.ts:deleteMessage] — `DELETE /messages/{id}`.
  [desktop/src/store/useStore.ts:toggleReaction] —
  `POST /messages/{id}/reactions` 또는 `DELETE /messages/{id}/reactions/{emoji}`.
  [desktop/src/store/useStore.ts:togglePin] — `POST /messages/{id}/pin` 또는
  `DELETE /messages/{id}/pin`.
  [desktop/src/store/useStore.ts:openThread] — `GET /messages/{id}/replies?limit=100`.
  [desktop/src/store/useStore.ts:createChannel] — `POST /workspaces/{id}/channels`.
  [desktop/src/store/useStore.ts:updateChannel] — `PATCH /channels/{id}`.
  [desktop/src/store/useStore.ts:loadChannelMembers] — `GET /channels/{id}/members`.
  [desktop/src/store/useStore.ts:addChannelMember] — `POST /channels/{id}/members`.
  [desktop/src/store/useStore.ts:updateMemberRole] —
  `PATCH /workspaces/{id}/members/{userId}`.
  [desktop/src/store/useStore.ts:removeMember] —
  `DELETE /workspaces/{id}/members/{userId}`.
  [desktop/src/store/useStore.ts:joinChannel] — `POST /channels/{id}/join`.
  [desktop/src/store/useStore.ts:leaveChannel] — `POST /channels/{id}/leave`.
  [desktop/src/store/useStore.ts:deleteDm] — `DELETE /channels/{id}`.
  [desktop/src/store/useStore.ts:startDm] — `POST /workspaces/{id}/dms`.
  [desktop/src/store/useStore.ts:updateProfile] — `PATCH /me`.
- 초대: [desktop/src/store/useStore.ts:loadInvites] — `GET /workspaces/{id}/invites`.
  [desktop/src/store/useStore.ts:createInvite] — `POST /workspaces/{id}/invites`.
  [desktop/src/store/useStore.ts:revokeInvite] —
  `DELETE /workspaces/{id}/invites/{inviteId}`.
  [desktop/src/store/useStore.ts:acceptInvite] — `POST /invites/accept`.
- [desktop/src/store/useStore.ts:markRead] — WebSocket:
  `realtime.send({ type: "read", channel_id, message_id })`. 연결이 없으면
  `POST /channels/{id}/read` — 그 오류는 `.catch(() => undefined)` 로 삼킵니다.
- [desktop/src/store/useStore.ts:setTyping] — WebSocket:
  `realtime.send({ type: "typing", channel_id, on })`.
- [desktop/src/store/useStore.ts:toast] — 타이머:
  `setTimeout(() => get().dismissToast(id), 5000)`.
- [desktop/src/store/useStore.ts:realtime.onEvent] — OS 알림:
  내 메시지에 대한 스레드 답글, 열려 있지 않은 방의 메시지, 나를 언급한
  메시지, 다른 사람이 만든 일정에 `notify(...)` 를 호출합니다. 알림이 꺼져
  있거나 `notificationPreview` 가 `"subject"` 면 본문은 빠집니다.
- [desktop/src/store/useStore.ts:realtime.onOpen] — 소켓의 onopen/onclose 콜백이
  `connected` 를 뒤집습니다. 재연도 지수 백오프(최대 10초), 4401 코드 뒤에는
  재시도하지 않습니다.
- [desktop/src/store/useStore.ts:realtime] — 모듈 스코프에서 `Realtime` 인스턴스
  하나를 만듭니다. 생성만 하고 소켓은 `connect(token)` 이 열 때 생깁니다.

## Verification

- Run: `npm test` (desktop/ 에서 실행 — vitest).
  `desktop/src/store/useStore.test.ts` 가 이 스토어의 계약을 고정합니다
  (9개 테스트).
- Run: `npm run typecheck` (desktop/ 에서 실행 — `tsc --noEmit`)
