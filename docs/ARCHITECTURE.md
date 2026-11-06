# 아키텍처

Llack 은 프로세스 셋으로 동작합니다. 데스크톱 셸(Rust), 그 안의 웹뷰(React),
그리고 백엔드(FastAPI)입니다. 사이에 Redis 도, 메시지 브로커도, 오브젝트 스토리지도
없습니다. 전부는 이 세 프로세스 안에서 끝납니다.

## 전체 그림

```
┌────────────────────────── 사용자 PC ────────────────────────────┐
│                                                                │
│  ┌── Tauri 셸 (Rust, desktop/src-tauri) ─────────────────────┐  │
│  │ 창 · 별도 창 · OS 알림 · 외부 링크 열기 · HTTP 클라이언트 │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │ Tauri IPC (invoke 명령)         │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │  웹뷰 — React 19 + TypeScript                            │  │
│  │    components/  화면 조각        store/    zustand 상태  │  │
│  │    lib/api.ts   REST 클라이언트   lib/ws.ts  실시간 소켓  │  │
│  │    styles/      토큰 한 곳(base.css · app.css 는 보조)   │  │
│  └──────────────┬──────────────────────────┬──────────────┘  │
└─────────────────┼──────────────────────────┼─────────────────┘
                  │ HTTPS  REST /api/v1/*      │ WSS  /api/v1/ws?token=…
┌─────────────────▼──────────────────────────▼─────────────────┐
│  FastAPI (uvicorn)                                            │
│                                                                │
│    api/v1/*.py    라우터 — 얇게, 검증과 응답 모양만            │
│    services/*.py  도메인 로직 — 권한 · 안 읽음 · 멤버십        │
│    models/        SQLAlchemy 테이블 (user … invite)           │
│    realtime/hub.py    열려 있는 소켓 등록부 (메모리)           │
│    realtime/events.py 채널마다 "누가 이 이벤트를 볼까" 를 정함 │
│                                                                │
│    schemas/      Pydantic 응답 모델 (API 계약과 1:1)          │
├────────────────────────────────────────────────────────────────┤
│  SQLite(기본) 또는 Postgres(운영)      UPLOAD_DIR — 디스크      │
└────────────────────────────────────────────────────────────────┘
```

## 프로세스 셋

| 프로세스 | 무엇을 하는가 | 어디에 있는가 |
| --- | --- | --- |
| Tauri 셸 | 창 크기·위치 기억, OS 알림, 외부 링크를 브라우저로 넘기기 | `desktop/src-tauri/src/` (Rust) |
| 웹뷰 | 화면 그리기, REST 호출, WebSocket 유지 | `desktop/src/` (React 19) |
| FastAPI | 인증, 도메인 로직, SQLite/Postgres 읽기·쓰기, 실시간 이벤트 발송 | `backend/app/` (Python 3.12) |

셋은 서로 직접 호출하지 않습니다. 셸과 웹뷰는 Tauri IPC로, 웹뷰와 백엔드는
HTTP/WebSocket으로만 이야기합니다. 덕분에 프런트엔드는 브라우저에서도
그대로 돌아갑니다 — 같은 코드가 `fetch` 와 `WebSocket` 을 씁니다.

셸이 백엔드에 직접 말을 거는 일은 두 가지뿐입니다: 알림에 붙일 채널 이름을
찾아오는 것과, 서버가 살아 있는지 한 번 짚어보는 것입니다. 그 요청은 셸 안의
자체 HTTP 클라이언트(`src-tauri/src/api.rs`)가 하고, 웹뷰를 거치지 않습니다.

## 요청 경로

**메시지 보내기**

1. 사용자가 컴포저에서 Enter → `desktop/src/store/useStore.ts` 가 `POST /api/v1/channels/{cid}/messages` 를 부릅니다.
2. `desktop/src/lib/api.ts` 가 `Authorization: Bearer <access_token>` 을 붙여 REST로 호출합니다.
3. `api/v1/messages.py` 가 `services/messages.py` 를 통해 메시지 행을 만들고 저장합니다.
4. `services/messages.py` 가 `realtime/events.py` 의 `emit_message_created` 를 부릅니다.
5. 이벤트가 `realtime/hub.py` 를 거쳐 그 채널을 볼 수 있는 사람들의 소켓으로 나갑니다.
6. 받는 쪽 웹뷰는 `lib/ws.ts` 가 프레임을 받아 zustand 스토어를 고칩니다. 화면은 그 상태에서 그려집니다.

**읽음 표시, 타이핑, presence** 도 같은 소켓을 씁니다. 읽음은 클라이언트가
`read` 프레임을 보내면 서버가 커서를 옮기고, 서버는 그 사람에게만 `unread`
이벤트를 돌려줍니다.

## 데이터 모델

테이블은 스물두 개입니다. 스키마는 서버가 기동할 때 SQLAlchemy 메타데이터에서
만듭니다 — 마이그레이션 도구가 없습니다(`app/main.py` 의 `lifespan` → `create_all`).

| 테이블 | 하는 일 | 눈여겨볼 점 |
| --- | --- | --- |
| `users` | 사람 | 이메일은 소문자로 정규화되고 유일합니다. `presence` 와 `last_seen_at` 은 presence 상태입니다 |
| `workspaces` | 팀 테넌트 | `slug` 는 유일합니다(초대 주소용) |
| `workspace_memberships` | 팀과 사람의 관계, 역할 | 역할은 `owner` · `admin` · `member` 세 가지입니다. `guest` 는 없습니다 |
| `channels` | 채널과 DM | `kind` 가 `channel` 또는 `dm`. DM 은 `dm_key`(참여자 id 정렬 후 `:` 로 이음)로 찾아냅니다 — 누가 먼저 열었든 같은 대화입니다 |
| `channel_memberships` | 채널과 사람의 관계 | 비공개 채널과 DM 은 이 표가 곧 권한입니다 |
| `messages` | 메시지와 스레드 | `parent_id` 가 있으면 스레드의 답글입니다(1단). 삭제는 soft delete — `deleted_at` 을 찍고 `body` 를 비웁니다(자리 유지) |
| `message_attachments` | 메시지와 파일의 연결 | 같은 파일을 여러 메시지에 달 수 있습니다 |
| `reactions` | 이모지 반응 | (메시지, 사람, 이모지) 유일. 한 사람은 한 메시지에 같은 이모지를 두 번 못 걸습니다 |
| `read_states` | 사람별 읽음 커서 | `last_read_message_id` 하나면 충분합니다. 안 읽음은 이 커서보다 최신인 메시지 수입니다 |
| `files` | 첨부 파일 | 바이트는 디스크(`UPLOAD_DIR`), 행에는 경로만 남습니다 |
| `invites` | 팀 초대 코드 | `token` 이 손에 건네는 코드입니다. 일주일 뒤 만료되고, `accepted_at` / `revoked_at` 으로 상태를 봅니다 |
| `schedule_events` | 팀 일정 | 워크스페이스에 속합니다. `is_private` 면 만든 사람과 초대받은 사람만 봅니다 |
| `schedule_attendees` | 일정의 참석자와 그 응답 | (일정, 사람) 유일. 응답은 `pending` · `accepted` · `declined` · `tentative` |
| `projects` | 팀이 하는 일 | 워크스페이스에 속합니다. `channel_id` 는 이 프로젝트를 이야기하는 방 — 프로젝트는 따로 있는 장소가 아니라 같은 팀을 보는 다른 방법입니다 |
| `project_members` | 프로젝트의 사람 명단 | (프로젝트, 사람) 유일. 이 명단이 곧 “내 프로젝트”입니다 |
| `roadmaps` | 보드의 칩 — 일의 묶음 | 프로젝트 하나에 여러 개. 할 일은 최대 하나의 로드맵에 속합니다 |
| `tasks` | 보드의 카드 | 네 칸(`request` · `todo` · `in-progress` · `done`)과 그 안에서의 순서(`position`)를 가집니다 |
| `milestones` | 납품 시점 — 날짜가 정해진 표식 | 시작과 끝, 색, 그리고 그것을 이루는 카드를 가집니다. 카드가 있으면 진행률은 카드에서 나오고, 없으면 직접 적습니다 |
| `task_comments` | 카드에 붙은 의견 | 카드가 대화를 여는 자리입니다 |
| `org_units` | 조직의 조직 단위 | 워크스페이스 안에 트리로 놓입니다. `parent_id` 가 위쪽을 가리키고, 루트는 `NULL` 입니다 |
| `org_unit_members` | 조직 단위에 속한 사람 | (조직 단위, 사람) 유일. 워크스페이스 멤버만 들어갑니다 |
| `org_unit_managers` | 조직 단위를 관리하는 사람 | (조직 단위, 사람) 유일. 이 사람은 자기 조직 아래 전부를 관리합니다 |

### 기본키

모든 id 는 접두사가 붙은 ULID입니다: `usr_` `wsp_` `chl_` `msg_` `fil_` `mem_`
`cm_` `rx_` `rs_` `inv_` `evt_` `att_` `prj_` `pm_` `rm_` `tsk_` `tc_` `mst_`
`org_` `om_` `ogm_`. 뒤쪽 26자는
48비트 타임스탬프 + 80비트 랜덤이고,
문자열 정렬이 곧 시간순입니다. 그래서 메시지 커서 페이지네이션이 `id < cursor`
한 줄로 끝나고, 새 메시지가 와도 페이지가 밀리지 않습니다.

### 시간대

모든 타임스탬프 컬럼은 `UTCDateTime`(`app/models/base.py`)입니다. SQLite 는
타임존을 저장하지 않으므로, 넣을 때 UTC 로 정규화하고 읽을 때 UTC 를 붙여
돌려줍니다. 어느 백엔드든 파이썬 쪽에서는 항상 timezone-aware 인 datetime 입니다.

## 실시간: 허브가 어떻게 대상을 정하는가

`realtime/hub.py` 는 메모리 안의 연결 등록부입니다. `user_id` → 열린 소켓 집합.
`send_to_user` / `send_to_users` 두 가지 배신만 합니다.

**누가 그 이벤트를 볼 수 있는가** 는 허브가 정하지 않습니다. `services/members.py` 의
`channel_audience` 가 DB 를 보고 대상자 집합을 만든 뒤, `realtime/events.py` 가
그 사람들에게만 보냅니다.

- 공개 채널: 채널 멤버 + 그 워크스페이스의 모든 멤버
- 비공개 채널: 채널 멤버만
- DM: 두 참여자만
- presence: 같은 워크스페이스의 멤버들(본인 제외)
- 프로젝트와 카드: 그 워크스페이스의 모든 멤버 — 프로젝트는 공개된 일이라
  보드도 같이 봅니다. 명단(`is_member`)은 “나의 것”을 가리킬 뿐, 숨기는
  것은 아닙니다.

**보는 사람마다 다른 내용** 이 필요할 때가 있습니다. 반응의 `me` 플래그, 채널의
안 읽음 개수 — 이건 본인 기준입니다. 그래서 `events.py` 는 대상자마다 한 번씩
렌더링해서 보냅니다. 같은 이벤트를 N 번 만드는 셈이지만, N 은 채널 인원이고
DB 조회는 한 번입니다.

**presence** 는 소켓 등록·해제 시점이 기준입니다. 소켓이 붙으면 `online`,
그 사람의 마지막 소켓이 닫히면 `offline`. 워크스페이스 멤버들에게 `presence`
이벤트로 전파됩니다. `busy`(바쁨)·`dnd`(방해 금지)·`away`(잠시 자리 비움)·
`brb`(곧 돌아오겠습니다)는 사람이 직접 정합니다 —
`PATCH /api/v1/me` 에 `{"presence": "busy"}` 를 보내면 서버가 그 사람의
상태를 바꾸고 곧바로 `presence` 이벤트를 전파합니다. 서버가 대신 정하는
`offline` 은 사람이 claiming 할 수 없습니다.

직접 고른 상태(`PRESENCE_CLAIMED`)는 소켓이 다시 붙어도 그대로 살아남습니다 —
앱을 다시 켜도 방해 금지 그대로입니다. `online` 만은 앱이 주는 상태라
소켓이 붙을 때 다시 붙습니다.

**연결 수명** 은 이렇게 흘러갑니다.

1. 클라이언트가 `/api/v1/ws?token=<access_token>` 로 접속합니다. 토큰이 쿼리
   파라미터인 이유는 웹뷰·브라우저가 WebSocket 핸드셰이크에 헤더를 못 붙이기
   때문입니다.
2. 서버가 토큰을 검증하고, 없거나 만료면 코드 `4401` 로 닫습니다.
3. 성공하면 `hello` 를 보냅니다 — 그 안에 지금 상태(`presence`)도 들어 있어
   클라이언트가 자기 얼굴의 칩을 바로 맞출 수 있습니다. 사람이 직접 고른
   상태(`busy`·`dnd`·`away`·`brb`)는 그대로 두고, 나머지는 `online` 으로
   올립니다.
4. 클라이언트가 `ping` 을 보내면 서버가 `pong` 으로 답합니다.
5. 연결이 끊기면 소켓을 등록부에서 지우고, 그 사람의 마지막 소켓이었다면
   `offline` 으로 내립니다.

`desktop/src/lib/ws.ts` 는 이걸 감당합니다. 지수 백오프(최대 10초)로 다시
붙고, `4401`(토큰 만료)일 때는 재시도하지 않습니다 — 그때는 로그인 화면으로
가야 하기 때문입니다.

### 알려두어야 할 한계

허브가 **프로세스 안**에 있습니다. API 를 워커 여러 개로 띄우면, 메시지를
보낸 워커의 이벤트는 다른 워커에 붙은 소켓에 닿지 않습니다. 그래서 운영
배포에서도 API 프로세스는 하나(인스턴스당 하나)로 유지합니다. 여러 대를
늘리려면 먼저 공유 이벤트 버스가 필요합니다.

## SQLite 기본, Postgres 는 운영

기본값은 SQLite 입니다 — `sqlite+aiosqlite:///./llack.db`, 백엔드 디렉터리
아래에 놓입니다. 파일 하나라 설치도 백업도 간단하고, 팀 규모가 수십 명이면
충분합니다.

`DATABASE_URL` 만 바꾸면 Postgres 로 갑니다.

```bash
DATABASE_URL="postgresql+asyncpg://user:pass@localhost/llack"
```

|Postgres 를 쓰는 이유 | SQLite 를 쓰는 이유 |
| --- | --- |
| 데이터가 API 프로세스 밖에서 산다 | 설치할 것이 없다 |
| 백업·복구 도구를 표준으로 쓴다 | 파일 하나를 복사하면 끝난다 |
| 동시 쓰기에 강한 저널링 | 개발할 때 DB 를 지우고 다시 만들 수 있다 |
| 호스팅이 갖다준다 | 노트북에서 그대로 돌아간다 |

두 저장소 사이에서 코드가 달라지는 곳은 없습니다 — SQLAlchemy 가 같은 모델을
양쪽에 올립니다. 다만 SQLite 는 단일 인스턴스 배포용입니다. 여러 인스턴스를
동시에 돌릴 계획이면 먼저 실시간 허브를 공유 버스로 바꿔야 합니다
(위 '알려두어야 할 한계' 참고).

## 프런트엔드 구조

```
desktop/src/
  lib/          전송 계층
    api.ts      REST 클라이언트, 토큰 보관, 만료 시 갱신
    ws.ts       실시간 소켓 (백오프 재연결)
    types.ts    API 계약의 타입
    format.ts   시간·숫자·파일 크기·멘션 포맷
    calendar.ts 달력 계산 (주·월·일, 모두 현지 시간 기준)
    markdown.ts 메시지 본문 마크다운
    desktop.ts  Tauri 기능 호출 (알림 등)
  store/        상태 관리
    useStore.ts zustand 스토어 하나 — 워크스페이스·채널·메시지·일정·프로젝트·연결 상태
  components/   화면 조각
    Rail.tsx 사이드바 · MessageList/MessageRow 전사록
    Composer.tsx 입력창 · ThreadPane.tsx 스레드 · Dialogs.tsx 대화상자
    ScheduleView.tsx 달력 화면 · ScheduleDialogs.tsx 일정 등록·수정
    ProjectsView.tsx 프로젝트 보드 · ProjectDialogs.tsx 프로젝트·카드 등록·수정
  styles/       스타일
    tokens.css  토큰 한 곳 (색·글꼴·크기·시간)
    base.css    리셋 · 기본 타이포그래피
    app.css     레이아웃과 유틸리티
```

토큰은 `styles/tokens.css` 의 `:root` 블록 한 곳에서만 나옵니다. 다른 CSS 에
색이나 크기를 리터럴로 쓰지 않습니다. 규칙은 [DESIGN.md](../DESIGN.md) 에 있습니다.

**달력은 같은 규칙을 따릅니다.** 월 화면은 *읽는* 면이 아니라 *고르는* 면이라
주 화면보다 조용합니다 — 일곱 칸, 숫자 하나, 그리고 그날의 일정 개수. 개수는
색이 아니라 숫자로 말합니다(안 읽음 개수와 같은 규칙). 선택된 날은 면의
배경으로, 오늘은 글자의 굵기로 구분합니다.

**보드도 같은 규칙을 따릅니다.** 프로젝트 목록은 달력의 월 화면처럼 *고르는*
면입니다 — 옆의 보드가 읽는 면이고, 카드는 그 보드의 읽는 단위입니다. 마감
날짜는 색이 아니라 말로 말합니다(“3일 남음”, “오늘 마감이”, “2일 지남”). 색만
으로 말하지 않는다는 것은 보드에서도 지켜집니다.

**날짜는 읽는 사람의 시간대로 계산합니다.** `lib/calendar.ts` 는 브라우저의
현지 시간으로만 일과 달을 계산하고, 서버에는 UTC 인스턴트로 보냅니다. 서버는
그 인스턴트를 UTC 로 정규화해 저장할 뿐, 어느 시간대인지 다시 만들어내지
않습니다. 그래서 화면은 언제나 읽는 사람의 하루를 보여줍니다.

**전송 계층과 화면을 나눈 이유**: `lib/` 이 서버와 말하는 방법을 전부 알고
있고, `components/` 는 그 결과만 그립니다. 서버가 같은 오리진으로 옮겨 가거나
API 주소가 바뀌어도 화면 코드는 손대지 않아야 합니다. API 주소를 바꿀 때는
`VITE_API_BASE` 만 주면 됩니다.

## 빌드와 배포에 필요한 것

| 플랫폼 | 필요한 것 |
| --- | --- |
| macOS | Xcode Command Line Tools |
| Windows | MSVC C++ 빌드 도구 + WebView2 런타임 (윈도우 11 은 기본 포함) |
| Ubuntu/Debian | `libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev librsvg2-dev libayatana-appindicator3-dev libdbus-1-dev build-essential` |

`desktop/src-tauri` 는 워크스페이스가 아니라 **독립형 cargo 패키지**입니다.
`Cargo.toml` 이 `desktop/src-tauri/Cargo.toml` 에 있고 루트에 `Cargo.toml` 이
없습니다. 그래서 cargo 명령은 항상 `desktop/src-tauri` 안에서 돌립니다.

Tauri 설정의 CSP 는 `127.0.0.1:8000` 과 `localhost:8000` 만 허용합니다
(`desktop/src-tauri/tauri.conf.json`). API 가 다른 주소에 있으면 그 설정의
`connect-src` 과 `img-src` 을 넓혀야 합니다 — 셸은 웹뷰 안에서 요청을 내기
때문입니다.

배포 절차는 [DEPLOY.md](DEPLOY.md) 에, 윈도우 설치본 만드는 법은
[WINDOWS.md](WINDOWS.md) 에 있습니다.
