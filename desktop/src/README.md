# src — 프런트엔드 진입점과 화면 배선

## Overview

React 19 + TypeScript + Vite 7 데스크톱 프런트엔드의 최상위 소스 디렉터리입니다.
직접 가진 소스는 두 파일뿐이고, 나머지는 역할별 하위 디렉터리로 나뉩니다.

- `App.tsx` — 앱 셸. 레일, 방 헤더, 메시지 목록, 컴포저, 스레드 패널, 일정·
  프로젝트·조직 보드, 토스트, 인증 게이트, 모든 대화상자를 배선하고
  키보드·리사이즈를 처리합니다.
- `main.tsx` — 진입점. 폰트·스타일시트를 side-effect import 하고
  `<App/>` 을 `#root` 에 마운트합니다.

하위 디렉터리:

- [components](./components/README.md) — 화면을 이루는 28개 컴포넌트
- [lib](./lib/README.md) — HTTP 클라이언트, 도메인 타입, 포맷터, 셸 브리지
- [store](./store/README.md) — 단일 Zustand 스토어
- `styles/`, `assets/` — 토큰과 스타일시트, 정적 자산 (코드 아님, 계약 대상 밖)

## Interface

- [desktop/src/App.tsx:App] — 기본 export. 앱 루트 컴포넌트.
  store 를 selector로 구독하고 `Rail`, `ChannelHead`, `EmptyRoom`,
  `MessageList`, `Composer`, `ThreadPane`, `ScheduleView`, `ProjectsView`,
  `OrgView`, `Toasts`, `Gate` 와 모든 대화상자를 조립합니다.
  `status === "boot"` 면 부팅 스플래시만, `status === "anon"` 면
  `Gate` 만 그립니다.
- [desktop/src/App.tsx:SPLIT_WIDTH] — `1152`. 이 폭 이상이어야 대화와 보드를
  나란히 둘 수 있습니다. 그 아래에서는 보드가 대화를 대신합니다.
- [desktop/src/main.tsx:container] — `#root` DOM 요소. 없으면 예외를 던집니다.
- [desktop/src/main.tsx:ReactDOM.createRoot] — `React.StrictMode` 안에서
  `<App/>` 을 마운트합니다.
- [desktop/src/store/useStore.ts:StoreState] — `App` 이 바인딩하는 계약.
  `status: "boot" | "anon" | "ready"`, `view: "channel" | "schedule" |
  "projects" | "org"`, `board: "schedule" | "projects" | null`,
  `dialog: DialogKind`, 그리고 `wide`, `splitEnabled`, `railCollapsed`,
  `idle`, `threadRoot`, 채널별 `messages`/`errors`/`loading`/`hasMore`.

### `App` 이 쓰는 store 액션

`boot()`, `openChannel(channelId)`, `stepRoom(direction, onlyUnread?)`,
`clearScreen()`, `setWide(wide)`, `setRailCollapsed(collapsed)`,
`closeBoard()`, `expandBoard()`, `besideBoard()`, `openProject(projectId)`,
`loadMessages(channelId, older?)`, `sendMessage(body, parentId?,
attachmentIds?)`, `editMessage(messageId, body)`, `deleteMessage(messageId)`,
`toggleReaction(message, emoji)`, `togglePin(message)`,
`setTyping(channelId, on)`, `openThread(message)`, `closeThread()`,
`setDialog(dialog, target?)`, `toast(text, action?)`,
`reportError(error, fallback?)` — 모두
[desktop/src/store/useStore.ts:StoreState] 에서 정의됩니다.

## Invariants

- [desktop/src/App.tsx:measure] — 창이 넓은 것은 `window.innerWidth >= SPLIT_WIDTH`
  (1152) 일 때뿐이고, 리사이즈 핸들러가 그 값을 `setWide` 로 넘깁니다.
- [desktop/src/App.tsx:boardActions] — 보드가 대화 옆에 놓이는 것은 `wide` 와
  `splitEnabled` 가 모두 참일 때뿐이고, "보드를 대화 옆에 놓기" 버튼도 그
  조건에서만 그려집니다.
- [desktop/src/App.tsx:onKey] — `Alt+ArrowUp/ArrowDown` 방 이동은 대화상자가
  열려 있거나(시트가 키를 가집니다) 입력 필드·contenteditable·컴포저 안이면
  (`isWriting`) 눌리지 않습니다.
- [desktop/src/App.tsx:onKey] — `Ctrl/Cmd+K` 는 `"palette"` 대화상자를 열고,
  `Ctrl/Cmd+B` 는 `railCollapsed` 를 뒤집습니다. 둘 다 `preventDefault` 합니다.
- [desktop/src/App.tsx:status !== "ready"] — 방을 별도 창으로 떼어내는 것은
  store 의 `status` 가 `"ready"` 일 때만 일어납니다. 다른 상태면 효과가
  일찍 끝납니다.
- [desktop/src/App.tsx:roomId ? null : <Rail />] — 방 창은 레일을 그리지 않고,
  `ChannelHead` 는 항상 `compact` 입니다.
- [desktop/src/App.tsx:pane--full] — 주 pane 은 정확히 하나를 고릅니다.
  빈 상태 → 보드+대화 분할 → `view === "schedule" | "projects" | "org"` 전체
  pane → 대화 pane 순의 우선순위입니다. 조직 보드는 대화 옆에 놓이지 않습니다.
- [desktop/src/App.tsx:threadRoot ?] — `ThreadPane` 은 `threadRoot` 가 있을 때만
  마운트되고, 그 조건으로 루트에 `"app--thread"` 클래스가 붙습니다.
- [desktop/src/App.tsx:dialog === "palette"] — 대화상자는 한 번에 하나만
  마운트되며 store 의 `dialog` 값과 정확히 문자열 비교로 고릅니다.
  (`"channels"` DialogKind 에 해당하는 가지는 없습니다.)
- [desktop/src/App.tsx:status === "boot"] — `"boot"` 은 로딩 스플래시만 그리고
  게이트나 앱은 그리지 않습니다. `"anon"` 은 `Gate` 와 `Toasts` 만.
- [desktop/src/main.tsx:container] — `#root` 가 없으면 렌더 전에 예외를
  던집니다. 루트는 한 번만 마운트됩니다.
- [desktop/src/lib/theme.ts:watchTheme] — 멱등입니다. 프로세스당 한 번만 리스너를
  설치합니다.
- [desktop/src/lib/popout.ts:currentRoomId] — 창 라벨이 `"room-"` 로 시작하거나
  URL 에 `?room=` 이 있을 때만 방 id를 돌려줍니다. 그 외에는 `null`
  (워크스페이스 창)입니다.
- [desktop/src/lib/keys.ts:isWriting] — contentEditable, `input`/`textarea` 태그,
  `.composer` 안의 요소에서 true. `tagName` 이 없는 대상(예: document)에는
  false입니다.

## Side Effects

- [desktop/src/App.tsx:measure] — 창 `"resize"` 리스너를 등록해
  `setWide(window.innerWidth >= SPLIT_WIDTH)` 를 호출하고, 정리할 때
  해제합니다.
- [desktop/src/App.tsx:onKey] — 창 `"keydown"` 리스너를 등록해 팔레트 열기,
  레일 접기, 방 이동을 처리하고 정리할 때 해제합니다.
- [desktop/src/App.tsx:App] — 마운트 시 `watchTheme()` 를 호출합니다. 이는
  `prefers-color-scheme` 미디어 쿼리와 설정 변경을 구독하고
  `document.documentElement.dataset.theme` 을 쓰며, 셸이면 Tauri 커맨드
  `"set_window_theme"` 을 호출합니다.
- [desktop/src/App.tsx:App] — 마운트 시 `boot()` 를 호출합니다. 워크스페이스를
  읽고, 워크스페이스 부트스트랩을 불러오고, 실시간 WebSocket 을 연결합니다
  (401 이면 토큰을 지우고 `"anon"` 으로 물러섭니다).
- [desktop/src/App.tsx:App] — 이 창의 방 id를 `window.localStorage`
  (라벨 `"room-<id>"` → 키 `"llack.room.<label>"`) 또는 `?room=` 쿼리에서
  읽어 컴포넌트 상태에 둡니다.
- [desktop/src/App.tsx:App] — `setRoomTitle` 로 네이티브 창 제목(셸) 또는
  `document.title`(브라우저)을 바꿉니다. 실패는 삼킵니다.
- [desktop/src/App.tsx:App] — 방 창에서는 `status` 가 `"ready"` 가 된 뒤
  `openChannel(roomId)` 를 호출합니다.
- [desktop/src/App.tsx:onSend] — `sendMessage` 를 호출하고 실패는
  `reportError` 로 토스트를 띄웁니다.
- [desktop/src/App.tsx:onDelete] — `editMessage` / `deleteMessage` /
  `toggleReaction` / `togglePin` 을 호출합니다. 삭제가 성공하면
  "메시지를 삭제했습니다" 토스트를 보여줍니다.
- [desktop/src/App.tsx:onLoadMore] — `loadMessages(activeId, true)` 로 이전
  페이지를 받아 앞에 붙입니다(limit 40, 첫 메시지 id 이전).
- [desktop/src/App.tsx:boardActions] — 보드 버튼들이 레이아웃을 바꿉니다:
  `expandBoard`(보드 → 전체 뷰), `besideBoard`(뷰 → 옆 보드, `wide &&
  splitEnabled` 이고 방이 열려 있을 때만), `closeBoard`(보드 → null,
  뷰 → `"channel"`).
- [desktop/src/App.tsx:App] — 컴포저/스레드 패널의 타이핑 콜백이 활성 채널로
  실시간 `"typing"` 프레임을 보냅니다.
- [desktop/src/App.tsx:App] — `openThread(message)` 가 스레드 루트를 잡고
  REST 로 답글을 받습니다. 실패는 무시합니다. 답글이 소켓으로 올 수도
  있습니다.
- [desktop/src/store/useStore.ts:setRailCollapsed] — 레일 모양은
  `setSettings` 로 저장해 재시작에도 남게 합니다. `splitView` 설정은
  `splitEnabled` 를 움직입니다.
- [desktop/src/store/useStore.ts:toast] — 토스트는 5000ms 뒤 자동으로
  사라집니다.
- [desktop/src/main.tsx:document.documentElement.classList.add("js")] —
  렌더 전에 `<html>` 에 `"js"` 클래스를 붙이고, 폰트소스 CSS와
  `./styles/app.css` 를 전역 side-effect import 합니다.
- [desktop/src/main.tsx:ReactDOM.createRoot] — `ReactDOM.createRoot(container).render(<React.StrictMode><App /></React.StrictMode>)`.

## Verification

- Run: `npm test` (desktop/ 에서 실행 — vitest)
- Run: `npm run typecheck` (desktop/ 에서 실행 — `tsc --noEmit`)
