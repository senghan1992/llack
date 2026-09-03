# Llack

사내 협업 OS — 채팅, 파일 공유, 그리고 팀이 만든 앱을 하나의 창에서 쓰는 데스크톱 애플리케이션.

- **데스크톱**: Rust (Tauri 2) + React/TypeScript
- **백엔드**: FastAPI + SQLAlchemy 2 + WebSocket
- **미니앱 플랫폼**: 매니페스트 기반, 스코프 권한, 샌드박스 패널

Slack/Teams 를 대체하려는 것이 아니라, **매일 쓰면서 불편했던 지점들을 구조적으로 다르게**
만든 초안입니다. 어디를 어떻게 다르게 했는지는 [설계 의도](#설계-의도) 를 보세요.

---

> **윈도우에서 확인하시려면 → [docs/WINDOWS.md](docs/WINDOWS.md)**
> 설치 없이 보시려면 → **[docs/WEB.md](docs/WEB.md)** (`make demo` 로 파일 하나면 끝납니다)
> 코드 가져오기부터 데스크톱 창 띄우기까지 단계별로 정리해 두었습니다.
> 윈도우에는 `make` 가 없으므로 `.\llack.ps1` 스크립트를 쓰세요.

## 배포하기 — 딱 이것만 하면 됩니다

팀에게 주소 하나를 공유하기까지, 순서대로 여섯 가지입니다.
(자세한 설명이 필요해지면 그때 [docs/DEPLOY.md](docs/DEPLOY.md) 를 여세요.)

**1. 서버 한 대를 준비하세요.** Docker 가 설치된 리눅스 서버면 됩니다 (2 vCPU / 4GB 권장).

**2. 코드를 올리고 시크릿 키를 만드세요.**

```bash
git clone <이 저장소> && cd llack
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# 출력된 값을 .env 의 LLACK_SECRET_KEY= 에 붙여넣기
```

키가 비어 있거나 개발용 값이면 서버가 스스로 기동을 거부하니, 잊어도 사고로 이어지지 않습니다.

**3. 띄우세요.**

```bash
docker compose up -d --build
```

이 한 줄로 전부 뜹니다: 웹 화면(nginx) · API · Postgres · Redis · 파일 저장소.
마이그레이션도 부팅 때 자동으로 적용됩니다.

**4. HTTPS 를 연결하세요.** 사내 표준 프록시가 있다면 그것으로 `서버:80` 을 가리키면 되고,
없다면 [Caddy](https://caddyserver.com) 두 줄이 가장 쉽습니다 (인증서 자동 발급):

```
llack.우리회사.com {
    reverse_proxy 127.0.0.1:80
}
```

브라우저 알림과 클립보드는 HTTPS 에서만 동작하므로 이 단계는 건너뛰지 마세요.

**5. 첫 관리자 계정을 만드세요.** 기본값이 "초대 없이는 가입 불가"라서 첫 사람만 예외 절차가 필요합니다:

```bash
# ① .env 에서 LLACK_REQUIRE_INVITE=false 로 바꾸고
docker compose up -d api
# ② 접속해서 계정 만들기 → 화면 안내대로 워크스페이스 만들기
# ③ .env 를 LLACK_REQUIRE_INVITE=true 로 되돌리고
docker compose up -d api
```

**6. 팀을 초대하세요.** 사이드바 하단 톱니(환경설정) → **구성원 초대** → 이메일 입력 →
링크 복사 → 전달. 받은 사람은 링크로 접속해 가입하면 자동으로 팀에 합류합니다.

끝입니다. 이후 기억할 것은 세 가지뿐입니다:

- **백업**: 상태는 도커 볼륨 두 개(`postgres-data`, `minio-data`)가 전부입니다.
- **메일**: 환경설정 → **메일 (SMTP)** 에 회사 메일 서버 정보를 넣고 테스트 메일로
  확인하세요. 그러면 비밀번호 분실 시 코드가 가입 이메일로 갑니다. 아직 안 잡았으면
  환경설정 → 구성원 초대 → **임시 비밀번호 발급** (관리자) 으로 대신할 수 있습니다.
- **잘 도는지 확인**: `curl https://주소/health` → `{"status":"ok"}`.

---

## 5분 만에 띄워보기 (macOS / Linux)

외부 의존성이 필요 없습니다. SQLite + 프로세스 내 pub/sub + 로컬 파일 저장으로 그대로 돌아갑니다.

```bash
make setup          # Python venv, npm 의존성, SDK 빌드
make seed           # 마이그레이션 + 시드 데이터 (사람 4명, 채널 5개, 앱 1개)
make dev            # http://localhost:8000/docs
```

다른 터미널에서:

```bash
make ui             # http://localhost:1420 — 브라우저에서 UI 확인
# 또는
make desktop        # 실제 데스크톱 앱 (아래 시스템 요구사항 참고)
```

로그인: `alice@example.com` / `llack-dev-password`

프로덕션과 같은 경로(Postgres + Redis + S3)로 돌리려면:

```bash
make compose-up     # Postgres, Redis, MinIO, API
```

---

## 현재 상태

| 영역 | 상태 | 검증 |
| --- | --- | --- |
| 백엔드 API (80+ 엔드포인트) | 동작 | pytest 110개 통과 |
| 실시간 게이트웨이 (WebSocket) | 동작 | 종단 검증 17항목 통과 |
| 미니앱 플랫폼 + 권한 경계 | 동작 | 종단 검증 25항목 통과 |
| Rust 코어 (API/캐시/동기화/에이전트) | 동작 | cargo test 189개 통과 |
| Tauri 셸 (창·트레이·알림·패널) | 코드 완성 | 이 환경에서는 링크 불가 (아래 참고) |
| React UI | 동작 | tsc 통과 · 헤드리스 브라우저 스모크 46검사 (`make smoke-ui`) |
| 미니앱 SDK + 예제 앱 | 동작 | 로드 및 동작 확인 |

**Tauri 셸에 대하여**: 이 개발 환경(Amazon Linux 2023)에는 `webkit2gtk` 패키지가 없어
데스크톱 바이너리를 링크할 수 없습니다. Rust 로직 전체를 의존성 없는 `llack-core` 크레이트로
분리해 둔 이유가 이것입니다 — 어디서든 빌드·테스트됩니다. 셸 자체는 macOS / Windows /
Ubuntu 에서 `make desktop` 으로 빌드하세요. 필요한 시스템 패키지는
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#데스크톱-빌드-요구사항) 에 적어두었습니다.

---

## 설계 의도

Slack/Teams 를 쓰면서 걸렸던 것들을 어떻게 다르게 만들었는지, 그리고 **왜** 그 선택이
구조적으로 다른지입니다.

### 1. 스레드가 채널을 가리지 않는다

Slack 의 스레드는 오버레이라서 열면 읽던 채널이 사라집니다. Llack 은 스레드를
**오른쪽에 도킹된 패널**로 띄웁니다. 채널과 스레드를 동시에 봅니다.

### 2. 검색이 하나다

Slack 은 사람 찾기 · 채널 찾기 · 메시지 찾기가 서로 다른 UI 입니다.
Llack 은 `⌘K` 하나에서 **채널 · 사람 · 앱 · 메시지 본문**을 한 번에 검색하고,
결과에서 바로 행동합니다 (참여 · DM 열기 · 패널 열기 · 이동).
카테고리를 먼저 고를 필요가 없습니다.

### 3. 사내 앱이 일급 시민이다

Teams 의 앱은 탭 안에 들어갑니다. Llack 은 **좌측 독에 워크스페이스와 같은 층위**로
앱을 놓고, 채널 옆에 분할 패널로 띄웁니다. 배포 현황을 보면서 그 채널에서 이야기할 수 있습니다.

팀이 앱을 만드는 비용도 낮췄습니다. API 키도, OAuth 도, 앱 전용 DB 도 필요 없습니다:
매니페스트 하나 + 정적 HTML 하나면 됩니다. 상태 저장은 SDK 의 `llack.storage` 를 쓰세요.
[예제 앱](examples/apps/standup) 이 전체 모양을 한 파일에 담고 있습니다.

### 4. 오프라인에서 쓴 메시지가 사라지지 않는다

메시지를 보낼 때 클라이언트가 먼저 ULID 와 `client_msg_id` 를 붙여 **로컬 아웃박스**에
넣습니다. 연결이 없으면 큐에 남고, 복구되면 순서대로 전송합니다.
서버가 `client_msg_id` 를 멱등키로 취급하므로 **재전송이 중복 게시가 되지 않습니다** —
응답만 유실된 경우에도 그렇습니다.

### 5. 이벤트 유실을 조용히 넘기지 않는다

WebSocket 프레임마다 단조 증가 `seq` 가 붙습니다. 클라이언트가 번호 점프를 감지하면
"내 화면이 불완전하다"는 사실을 알고 해당 채널을 다시 불러옵니다.
구멍 난 대화 기록을 그럴듯하게 보여주지 않습니다.

### 6. 알림 설정이 실제로 지켜진다

`all` / `mentions` / `nothing` 과 음소거를 서버가 팬아웃 시점에 판단합니다.
음소거한 채널에서 멘션당해도 데스크톱 알림이 오지 않고, 배지에는 멘션만 반영됩니다.
클라이언트가 받아놓고 걸러내는 방식이 아닙니다.

---

## 저장소 구조

```
llack/
├── backend/                 FastAPI 백엔드
│   ├── app/
│   │   ├── core/            설정, DB, 보안, ULID, 오류, 로깅
│   │   ├── models/          SQLAlchemy 2.0 모델
│   │   ├── schemas/         Pydantic v2 요청·응답
│   │   ├── services/        도메인 로직 (라우터가 얇은 이유)
│   │   ├── realtime/        이벤트 버스, 연결 허브, 프레즌스
│   │   └── api/v1/          라우터 (auth, channels, messages, apps, …)
│   ├── alembic/             마이그레이션
│   ├── scripts/             시드, 종단 검증
│   └── tests/               110개
│
├── desktop/                 데스크톱 클라이언트
│   ├── core/                ★ 순수 Rust: API·실시간·캐시·동기화·에이전트 (189개 테스트)
│   ├── src-tauri/           얇은 Tauri 셸: 창, 트레이, 알림, IPC
│   └── src/                 React UI
│
├── packages/llack-app-sdk/  미니앱 SDK (TypeScript)
├── examples/apps/standup/   예제 미니앱 (참조 구현)
└── docs/                    설계 문서
```

## 문서

- [docs/WINDOWS.md](docs/WINDOWS.md) — 윈도우에서 실행하기 (전송 · 설치 · 확인 · 문제 해결)
- [docs/DEPLOY.md](docs/DEPLOY.md) — 배포: 무엇이 뜨는지, 첫 부팅, 운영 루틴, 정직한 한계
- [docs/WEB.md](docs/WEB.md) — 설치 없이 보기: 서버 없는 데모 한 파일, 또는 SSH 터널 + 브라우저 모드
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 구조, 데이터 모델, 실시간 프로토콜, 배포
- [docs/APP_PLATFORM.md](docs/APP_PLATFORM.md) — 미니앱 플랫폼: 매니페스트, 스코프, 보안 모델
- [docs/AGENT.md](docs/AGENT.md) — 에이전트 패널: 도구, 승인 등급, 감사 로그, **없는 것**
- [docs/ROADMAP.md](docs/ROADMAP.md) — 이 초안에 없는 것과 다음에 할 것

## 주요 명령

```bash
make help           # 전체 명령
make test           # 백엔드 110개 + Rust 189개
make smoke          # 실행 중인 서버에 대한 종단 검증
make smoke-ui       # 헤드리스 브라우저로 UI 흐름 46검사
make lint           # ruff + tsc + clippy
make reset-db       # DB 초기화 후 재시드
```

윈도우는 같은 명령을 `.\llack.ps1 <명령>` 으로 실행합니다 (`.\llack.ps1 help`).

## 라이선스

사내 사용을 전제로 한 비공개 코드입니다.
