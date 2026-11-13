# Llack

한빛 팀을 위한 사내 메신저. 채널, 직접 메시지, 스레드를 한 화면에서 돌리는
데스크톱 앱입니다.

- **프런트엔드** React 19 + TypeScript + Vite, 데스크톱 셸은 **Tauri 2 (Rust)**
- **백엔드** **FastAPI** (Python 3.12, async SQLAlchemy 2.0), 실시간은 WebSocket
- **모바일** Flutter/Dart 클라이언트 (같은 백엔드를 씁니다)
- **디자인** 자체 디자인 시스템. 토큰은 `desktop/src/styles/tokens.css` 한 곳에 있고,
  규칙은 [DESIGN.md](DESIGN.md)에 잠가 두었습니다.

---

## System Overview

세 개의 실행 단위가 하나의 저장소를 나눠 가집니다. 모든 계약은 아래 세 개의
파티션으로 나뉘고, 각 디렉터리에는 그 경계의 contract 파일(`README.md`)이 있습니다.

```
┌───────────────────────────────────────────────────────────────┐
│  데스크톱  desktop/          React 19 + TypeScript + Vite 7     │
│                            + Tauri 2 셸 (Rust)                │
└───────────────┬───────────────────────────────────────────────┘
                │  HTTPS /api/v1  ·  WebSocket /api/v1/ws
┌───────────────▼───────────────────────────────────────────────┐
│  백엔드    backend/          FastAPI · async SQLAlchemy 2.0   │
│                            SQLite(개발) / Postgres(운영)      │
└───────────────┬───────────────────────────────────────────────┘
                │  HTTPS /api/v1  ·  WebSocket /api/v1/ws
┌───────────────▼───────────────────────────────────────────────┐
│  모바일    mobile/           Flutter · Dart SDK ^3.13.3       │
└───────────────────────────────────────────────────────────────┘
```

백엔드는 **의존 방향이 한쪽**입니다. `api` 와 `realtime` 이 `services` 를 부르고,
`services` 가 `models` 와 `core` 를 부르며, 올라가는 방향의 호출은 없습니다.
`models` 의 SQLAlchemy 메타데이터가 곧 DDL의 유일한 출처입니다 — **마이그레이션
도구가 없고**, 스키마는 기동 시 메타데이터에서 만들어지고 `ensure_schema()` 가
실제 스키마와 어긋나면 기동 단계에서 실패합니다
([backend/app/core/README.md](./backend/app/core/README.md)).

클라이언트 셋은 모두 같은 규칙을 공유합니다. REST 접두사는 `/api/v1`, 실시간은
`/api/v1/ws?token=…`, 오류 응답은 `{"error": {"code", "message", "field"}}`
봉투 하나로 통일되어 있고, 401 은 토큰 교환을 최대 한 번만 시도합니다.

## Local Interface & Invariants

저장소 루트에는 소스 파일이 하나 있습니다 — `dev.sh`. 나머지는 설정과 매니페스트입니다.

- `dev.sh` — 원샷 개발 실행 스크립트. `./dev.sh` (기본), `./dev.sh web`,
  `./dev.sh mobile` 세 가지 모드. `set -euo pipefail` 아래에서 `uv`/`node`/`npm`을
  확인하고(`need`), 백엔드 가상환경 → 의존성 → 시드 → 백엔드 기동 → 프런트엔드
  의존성 → 앱 실행 순서를 지킵니다. `uv`는 `uv venv --python 3.12` 로 가상환경을
  만들고 `uv pip install -e ".[dev]"` 로 항상 reinstall 합니다. 시드는
  `backend/llack.db` 가 없을 때만 (`backend/scripts/seed.py`) 돕니다. 백엔드는
  `http://127.0.0.1:8000/api/v1/health` 로 이미 떠 있는지 먼저 물어보고, 없으면
  uvicorn 을 띄운 뒤 최대 40회 × 0.25초 health gate 를 밟습니다. 띄운 백엔드는
  `trap cleanup EXIT INT TERM` 으로 종료 때 내려갑니다 — **이미 떠 있던 백엔드는
  건드리지 않습니다**. `cargo-tauri` 가 있으면 `cargo tauri dev`, 없으면
  `npm run app:dev`.
- `Makefile` — `make help` 가 기본 목표입니다. `make setup` / `make dev` /
  `make dev-web` / `make dev-desktop` / `make seed` / `make test` / `make lint` /
  `make format` / `make contrast` / `make build` / `make clean` / `make db-reset` /
  `make compose-up` / `make compose-down` / `make compose-logs` /
  `make desktop-headless`.
- `docker-compose.yml` — 서비스는 **둘뿐**입니다. `postgres:16-alpine` 과
  `backend/Dockerfile` 로 만든 `api`. Redis·MinIO·S3·Celery 가 없습니다 —
  실시간은 프로세스 안의 허브가 처리하고, 첨부 파일은 `UPLOAD_DIR` 볼륨에
  있습니다. `api` 는 `--workers` 없이 uvicorn 하나만 돕니다.
- `.env.example` — 환경 변수 표면. `SECRET_KEY`(필수), `DATABASE_URL`,
  `UPLOAD_DIR`, `WORKSPACE_QUOTA_BYTES`, `ORPHAN_FILE_HOURS`, `CORS_ORIGINS`,
  `ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`, `JWT_ALGORITHM`,
  `MAX_UPLOAD_BYTES`. `SECRET_KEY`·`DATABASE_URL`·`UPLOAD_DIR` 는 `LLACK_` 붙은
  별칭도 읽습니다.

**루트 불변식**

- `dev.sh` 는 `uv`, `node`, `npm` 이 없으면 중단합니다. 다만 헤더 주석은
  "uv / node / cargo" 라고 적혀 있어도 `cargo` 는 강제되지 않습니다 —
  `cargo-tauri` 는 나중에 선택적으로만 확인하고, 없으면 npm 경로로 넘어갑니다.
- `make setup-backend` 와 `dev.sh` 의 `uv pip install` 은 `--python` 인자가
  다릅니다(디렉터리 vs 실행 파일). 결과는 같지만 명령은 같지 않습니다.
- `docker-compose.yml` 의 `api` healthcheck 는 `/health` 를, `dev.sh` 는
  `/api/v1/health` 를 봅니다. 두 경로가 모두 존재하므로 둘 다 옳습니다.

## Subdirectories & System Boundaries

- [backend](./backend/README.md) — FastAPI 백엔드. `app/`(HTTP·WebSocket·
  도메인 로직·ORM·스키마·기반 모듈), `scripts/`(데모 시드). 10개 계약.
- [desktop](./desktop/README.md) — 데스크톱 앱. `src/`(프런트엔드), `src-tauri/`
  (Rust 셸). 7개 계약.
- [mobile](./mobile/README.md) — Flutter 클라이언트. `lib/`(models·providers·
  screens·services·theme·widgets). 15개 계약.
- [scripts](./scripts/README.md) — 저장소 최상위 개발 도구 두 개
  (`check-contrast.py`, `desktop-headless.sh`). 1개 계약.

계약 없는 디렉터리: `docs/`(문서), `deploy/`(nginx 설정), `.github/workflows/`
(CI), `desktop/src/styles/`·`desktop/src/assets/`·`desktop/public/`(스타일·자산),
`desktop/src-tauri/capabilities/`·`icons/`(설정·자산), `backend/tests/`(테스트),
`mobile/test/`(테스트), `mobile/android|ios|linux|macos|windows|web/`
(Flutter 플랫폼 생성물).

## Global Invariants

- **실시간은 프로세스 안의 허브다.** 백엔드는 uvicorn 워커를 **한 개**만
  씁니다. 여러 개로 올리면 한 워커에 붙은 소켓으로 다른 워커의 이벤트가
  전달되지 않습니다. 허브 앞에 브로커를 두기 전에는 `--workers` 를 올리지
  마세요 [backend/Dockerfile:Dockerfile].
- **권한은 한 곳에서.** 워크스페이스 멤버십은 `require_membership`,
  채널 접근은 `require_channel_access` 가 결정합니다. 관리자 권한은
  `owner`·`admin` 두 역할뿐입니다
  ([backend/app/services/README.md](./backend/app/services/README.md)).
- **삭제는 보통 소프트 삭제입니다.** 메시지는 본문을 `deleted_body` 로 옮기고
  `deleted_at` 을 찍습니다 — 모든 기기에서 되돌릴 수 있어야 하기 때문.
  `restore` 는 `deleted_body` 가 있을 때만 동작합니다.
- **파일 종류는 바이트가 정합니다.** 브라우저가 말한 `content_type` 은 힌트일
  뿐이고, 앞 8192바이트가 판정합니다. SVG 는 업로드되지만 인라인 렌더링은
  되지 않습니다. 디스크 이름은 파일 id 이고 확장자는 **검증된** MIME 에서 옵니다.
- **ID 는 접두사가 붙은 ULID.** `usr_`, `wsp_`, `chl_`, `msg_` … 로 시작하는
  30글자이고, 시간순으로 정렬됩니다. DB 시퀀스가 아닙니다
  ([backend/app/core/README.md](./backend/app/core/README.md)).
- **쓰기는 커밋 후 방송합니다.** 모든 변경 라우트는 커밋을 마친 뒤에만
  realtime 이벤트를 보냅니다 — 방송이 항상 durable write 를 따릅니다.
- **WS 는 HTTP 로 먼저 확인합니다.** `/api/v1/ws?token=…` 는 쿼리 토큰으로만
  인증하고, 실패하면 close code `4401` 로 끊습니다. 클라이언트는 그 코드를
  받으면 재연도를 시도하지 않습니다.
- **클라이언트는 하나의 상태 컨테이너를 가집니다.** 데스크톱은 단일 Zustand
  스토어, 모바일은 단일 `AppState` ChangeNotifier. 서버 이벤트가 HTTP 응답보다
  먼저 오기 때문에 두 경로가 **같은 id 기준 upsert 규칙**을 씁니다
  (`upsertById`).
- **CSP 와 전역 API 를 닫아 둡니다.** Tauri CSP 는 `script-src 'self'`,
  `object-src`/`form-action` `'none'` 이고 `withGlobalTauri` 는 `false` 입니다.
  웹뷰에 노출되는 Tauri 커맨드는 정확히 5개입니다.

## Global Side Effects

- **파일 시스템** — 첨부 파일은 `UPLOAD_DIR/<workspace>/<id 앞 2자>/<id><확장자>`
  에 쓰입니다. 기본값 `backend/var/uploads`, 파일당 50MiB, 워크스페이스당 5GiB.
  어떤 메시에도 붙지 않은 업로드는 기본 24시간 뒤 지워집니다
  (`ORPHAN_FILE_HOURS=0` 이면 지우지 않음).
- **데이터베이스** — 기동 때마다 스키마를 만들고 늘립니다. 개발 DB 는 SQLite
  한 파일(`backend/llack.db`), 운영은 Postgres. `make db-reset` 으로 SQLite 를
  지우고 다시 만들 수 있습니다.
- **네트워크** — 데스크톱 웹뷰는 `${VITE_API_BASE}/api/v1` 로 나가고, 셸은
  `LLACK_API_BASE` / `LLACK_API_TOKEN` 환경변수로 `/health` 와
  `/api/v1/channels/{id}` 만 부릅니다. 모바일은 `SharedPreferences` 에 토큰과
  서버 주소를 둡니다.
- **브라우저 저장소** — 데스크톱은 `localStorage` 의 `llack.access`,
  `llack.refresh`, `llack.settings` 를 씁니다. 모바일은 `SharedPreferences` 의
  `llack.access`, `llack.refresh`, `llack.api_base`.
- **OS 알림** — 데스크톱 셸만 OS 알림을 띄웁니다 (`llack://notify` 이벤트).
  브라우저 빌드에서는 조용히 넘어갑니다.
- **창 상태** — 셸은 `app_config_dir()/window-state.json` 에 창 크기·위치를
  저장합니다. 라벨이 `"main"` 인 창만 기록하므로 방(pop-out) 창은 워크스페이스
  창을 움직이지 못합니다.
- **네트워크 바깥** — `make contrast` 는 Playwright 로 실제 앱을 띄워 대비를
  잽니다. `make desktop-headless` 는 Xvfb 위에 실제 Tauri 바이너리를 띄우고
  PNG를 남깁니다. 둘 다 hermetic 테스트가 아니라 눈으로 확인하는 도구입니다.

## System Verification

- Run: `make test` — `cd backend && .venv/bin/pytest -q` (**156 passed**)
- Run: `make lint` — `cd backend && .venv/bin/ruff check app tests scripts`,
  `cd backend && .venv/bin/ruff format --check .`,
  `cd desktop && npm run typecheck`
- Run: `cd desktop && npm test` — vitest, 4개 파일 26개 테스트
- Run: `cd desktop && npm run typecheck` — `tsc --noEmit`
- Run: `cd desktop/src-tauri && cargo test` — lib 타깃 `llack_lib` 단위 테스트 5개
- Run: `cd mobile && flutter test` — Flutter SDK 가 필요합니다
- Run: `make contrast` — 실행 중인 앱이 있어야 하는 실시간 점검 (수동)
- Run: `make desktop-headless` — `xvfb`·`ffmpeg` 가 필요한 실시간 점검 (수동)

### 이름을 하나 고쳐 두기

코드에는 이전 제품명이 남아 있습니다. `backend/app/main.py` 의 FastAPI
`title` 은 `"Atrium"`, `description` 은 `"ArcheAI internal workspace & messenger
API."` 이고, `desktop/src-tauri/tauri.conf.json` 의 `productName` 은
`"Atrium"`, `identifier` 는 `"ai.arche.atrium"` 입니다. 셸의 창 제목 폴백도
`"Atrium"` 입니다. 문서와 코드가 같은 이름으로 읽히도록 정리할 대상입니다.

---

## 처음부터 실행하기

### 1. 백엔드

```bash
cd backend
uv venv                                   # 처음 한 번
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python scripts/seed.py          # 데모 데이터 (한빛 워크스페이스)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`scripts/seed.py`는 멱등이라 여러 번 실행해도 안전합니다. 만들어지는 계정:

| 이름 | 이메일 | 비밀번호 |
| --- | --- | --- |
| 김현진 | hyunjin@hanbit.co.kr | `hanbit2026` |
| 박지민 | jimin@hanbit.co.kr | `hanbit2026` |
| 이채원 | chaewon@hanbit.co.kr | `hanbit2026` |
| 최수아 | sua@hanbit.co.kr | `hanbit2026` |
| 정우진 | woojin@hanbit.co.kr | `hanbit2026` |

시드에는 채널과 메시지, **팀 달력** 의 일정 다섯 개, 그리고 **프로젝트 보드**
(프로젝트 세 개와 카드 열두 개)가 들어 있습니다.

기본 저장소는 SQLite(`backend/llack.db`)입니다. Postgres로 바꾸려면 환경 변수만
바꾸면 됩니다.

```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/llack"
```

### 2. 데스크톱 앱

```bash
cd desktop
npm install
npm run app:dev        # Tauri 창으로 실행
```

브라우저로만 확인하려면 `npm run dev` (http://127.0.0.1:1420) 후 백엔드 주소는
`VITE_API_BASE`로 지정합니다.

```bash
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

### 3. 모바일 앱

```bash
cd mobile
flutter pub get
flutter run
```

### 4. 빌드

```bash
cd desktop
npm run build           # 프런트엔드 번들
npm run app:build       # 데스크톱 설치 파일 (deb, dmg, msi)
```

---

## 기능

**메시지** 실시간 전송, 편집, 삭제(소프트 삭제), 스레드(답글), 반응, 고정,
멘션, 코드 블록, 파일 첨부, 날짜 구분선, 작성자 묶기, 읽지 않은 개수.
**내 메시지는 오른쪽 말풍선**에 놓여 남의 말과 구분됩니다.

**채널** 공개/비공개, 초대, 나가기, 주제, 멤버 목록. 새 채널은 이름과 주제에
**함께할 사람**까지 고르고 만들 수 있습니다. 채널을 우클릭하면 방 열기,
사람 추가, 채널 설정, 방 나가기가 뜹니다. 채널 머리글의 사람 그림에서도
방에 데려올 수 있습니다. **직접 메시지** 1:1 대화와
presence(온라인 · 바쁨 · 방해 금지 · 자리 비움 · 곧 돌아오겠습니다 · 오프라인).
레일의 개인 대화를 우클릭하면 메뉴가 열리고, 그 안에서 **대화 삭제** 를
할 수 있습니다 — 그 대화와 안의 메시지가 사라집니다.

**내 상태** 왼쪽 아래 이름을 누르면 **상태 변경 ›** 서브메뉴에서 상태를
고릅니다(온라인 · 바쁨 · 방해 금지 · 잠시 자리 비움 · 곧 돌아오겠습니다).

**찾기** 워크스페이스 전체 메시지 검색(⌘K 팔레트), 채널과 사람으로의 빠른 이동.

**일정** 팀 달력을 왼쪽 레일의 **일정** 에서 엽니다. 월 단위 달력에서 날짜를
고르면 그날의 일정이 나오고, **일정 추가** 로 회의를 등록합니다. 제목 · 날짜와
시간 · 장소 · 설명 · 참석자 · 연결할 채널을 넣을 수 있고, 다른 사람은
**참석 / 미정 / 불참** 으로 답합니다. 만든 사람(과 관리자)만 고치거나 지울 수
있고, 비공개 일정은 만든 사람과 초대한 사람만 봅니다. 일정을 만들면 팀
화면에 실시간으로 반영됩니다.

**프로젝트** 팀이 하는 일을 왼쪽 레일의 **프로젝트** 에서 봅니다. 왼쪽은
프로젝트 목록이고, 오른쪽은 그 프로젝트의 **보드** — 카드가 네 칸으로
흘러갑니다: **요청 → 할 일 → 진행 중 → 완료**. 카드를 끌어 옮기거나 카드
옆의 › 메뉴로 옮길 수 있습니다. 프로젝트에는 이름과 **설명**을 쓰고,
**사람**을 올려 명단을 만듭니다 — 명단에 올라간 프로젝트는 **내
프로젝트** 에서 따로 보입니다. 카드는 담당자와 마감일을 가질 수 있고,
카드에는 **의견**이 붙습니다. 프로젝트는 그 이야기를 나누는 **채널**을
가리킬 수 있고, 그 채널의 머리글에서 바로 보드로 건너갈 수 있습니다.

목록의 프로젝트 옆에 붙는 **내 할일** 숫자는 내가 맡은 아직 끝나지 않은
카드 수입니다.

**로드맵** — 보드 위에는 **모든 카드** 칩과 그 프로젝트의 **로드맵** 칩들이
나란히 있습니다. 할 일은 최대 하나의 로드맵에 속합니다 — 할 일을 만들거나 고칠
때 로드맵을 고릅니다. 로드맵을 지우면 그 안의 할 일은 보드에 그대로 남고
연결만 끊어집니다. 새 로드맵을 만드는 길은 없습니다 — 로드맵은 팀이 정해
주는 것이고, 앱은 고르는 것과 지우는 것만 합니다.

**마일스톤** 은 “언제까지 내놓나” 입니다 — 제목과 시작일 · 종료일, 자신의 색, 설명,
그리고 그것을 이루는 카드들을 가집니다. 카드가 붙어 있으면 진행률은 그 카드들
중 끝난 카드의 몫으로 나오고, 카드가 없으면 직접 적어 둔 퍼센트가 보입니다.
한 카드는 하나의 마일스톤에만 속합니다.

**프로젝트 차트** 프로젝트 머리글의 기간을 누르면 그 프로젝트의
**간트 차트** 가 모달로 열립니다. 시간축은 그 프로젝트가 차지하는 달이고,
막대는 마일스톤의 기간과 진행률입니다. 아래로 갈수록 **카드 마감일** 은 점으로,
**팀 일정** 은 눈금으로 표시됩니다 — 회의와 마감일이 어느 달에 몰려 있는지
한 번에 보입니다. 차트 아래에는 같은 내용을 말로 옮긴 목록이 붙습니다:
마일스톤의 기간 · 진행률 · 붙어 있는 카드, 그리고 그 기간의 팀 일정.

**팀** 워크스페이스 초대: 관리자가 이메일로 초대 코드를 만들고, 팀원은 그 코드로
들어옵니다. 멤버 권한(owner/admin/member).

**조직 관리** 회사는 하나가 아니라 여러 조직으로 이루어집니다. 왼쪽 레일의
**조직 관리** 에서 부서와 팀을 임의로 늘어놓고(깊이는 제한이 없습니다),
사람을 배치하고, 각 조직의 **관리자**를 정합니다. 워크스페이스의 최초 관리자는
생성할 때 한 명만 지정되고, 그 사람이 워크스페이스 관리자를 더 임명하거나
조직을 계층으로 나눠 각 계층의 관리자를 두게 됩니다. 조직 관리자는 자신이
맡은 조직과 그 아래 조직만 볼 수 있습니다 — 남의 조직은 건드릴 수 없습니다.

**파일** 이미지와 PDF 를 넘어 문서까지 공유합니다 — `.txt` `.csv` `.md`,
`.doc` `.docx` `.xls` `.xlsx` `.ppt` `.pptx`, 한글 `.hwp` `.hwpx`,
`.odt` `.ods` `.odp`, 그리고 `.zip` `.gz`. 업로드된 파일의 형식은 **바이트가
증명하는 것**으로 기록되고(브라우저가 말한 종류는 믿지 않습니다), 이미지는
그대로 열어 보고 나머지는 내려받습니다. 기본 제한은 50 MB(`MAX_UPLOAD_BYTES`).
**어디에 저장되고 무엇이 저장될 수 있는지는 백엔드가 정합니다** — 워크스페이스가
자신의 파일을 소유하고, 워크스페이스마다 몫이 있고, 아무 메시에도 붙지 않은
업로드는 하루 뒤에 사라집니다. 규칙 전체는
[docs/FILES.md](docs/FILES.md) 에 있습니다.

**화면** 라이트와 다크, 키보드 내비게이션, 화면이 좁을 때 접히는 사이드바,
로딩/빈 화면/오류 상태를 모두 갖춥니다. **자리 비움** 은 내 메뉴에서 직접
바꿉니다 — 팀에 곧바로 알려집니다.

**설정** 앱 전체가 쓰는 것을 한곳에서 고치는 모달입니다. **알림**(데스크톱
알림과 미리보기) · **외관**(화면 모드 — 밝게/어둡게/시스템 — 와 시간 표기) ·
**계정 및 조직**(내 프로필과 소속, 로그아웃) · **파일 및 링크**(다운로드
폴더, 파일을 열 때의 방식, 이미지 미리보기). 이름·직함·아바타·역할은 서버에,
나머지는 이 기기에 남습니다.

---

## API

전체 계약은 [docs/API.md](docs/API.md)에 있습니다. REST는 `/api/v1` 아래에 있고,
실시간 이벤트는 `ws://127.0.0.1:8000/api/v1/ws?token=<access_token>` 입니다.

```bash
# 로그인
curl -s localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"hyunjin@hanbit.co.kr","password":"hanbit2026"}'

# 채널 목록
curl -s localhost:8000/api/v1/workspaces/<workspace_id>/channels \
  -H "authorization: Bearer <access_token>"
```

라우트 전체와 권한 규칙은
[backend/app/api/v1/README.md](./backend/app/api/v1/README.md) 에 있습니다.

---

## 디자인

- 토큰은 `desktop/src/styles/tokens.css` 한 곳에만 있습니다. 색, 글꼴, 크기,
  시간 값은 전부 여기서 나옵니다.
- 폰트는 Latin용 Schibsted Grotesk / Instrument Sans, 한글용 Pretendard Variable,
  시각 정보용 DM Mono.
- 라이트와 다크는 별개의 파레토가 아니라 다크에서 파생된 한 쌍입니다.
- 규칙, 간격 단계, 모서리 반경, 대비 기준은 [DESIGN.md](DESIGN.md)를 보세요.

---

## 확인하는 방법

**브라우저로** — 프런트엔드만 띄우면 바로 들어갑니다. 셸만의 기능(알림,
외부 링크, 창 상태)은 웹에서는 조용히 넘어갑니다.

```bash
make dev        # API  (127.0.0.1:8000)
make dev-web    # 웹  (127.0.0.1:1420)
```

**실제 데스크톱 앱으로** — 데스크톱 셸까지 포함한 진짜 바이너리를 띄우고
스크린샷을 남깁니다. 화면이 없는 서버·컨테이너에서도 됩니다.

```bash
apt-get install -y xvfb ffmpeg xdotool   # 한 번
make desktop-headless                    # 로그인 화면까지 자동 캡처
```

```
scripts/desktop-headless.sh [--shot out.png] [--login] [--stop]
```

- Xvfb 위에 실제 `llack` 바이너리를 띄우고 창만 잘라서 PNG로 저장합니다.
- `--login`은 데모 계정(`hyunjin@hanbit.co.kr` / `hanbit2026`)으로 로그인합니다.
- 앱 프로필은 `/tmp/llack-headless-home`에 격리되므로 매번 로그인 화면에서
  시작하고, 평소 쓰는 프로필·창 상태는 건드리지 않습니다.
- 창을 직접 조작하려면 `DISPLAY=:99`로 접속해 xdotool을 쓰세요.

**대비 점검** — 실행 중인 앱을 Playwright로 띄워 모든 글자의 WCAG AA 대비를
검사하고, `:hover` 규칙을 하나씩 강제로 켜서 hover 상태까지 잽니다.

```bash
make contrast
```

---

## 개발 명령

```bash
cd backend
.venv/bin/pytest -q                  # 156 passed
.venv/bin/ruff check .
.venv/bin/ruff format --check .

cd ../desktop
npm run typecheck
npm run test
npm run build

cd ../mobile
flutter test
```

---

## 배포

`backend/Dockerfile`은 백엔드 이미지입니다. SQLite는 단일 인스턴스 배포용이고,
여러 인스턴스로 갈 때는 Postgres를 쓰세요. 데스크톱 앱은 CI에서
`npm run app:build`로 배포합니다.
