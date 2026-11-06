# Llack

한빛 팀을 위한 사내 메신저. 채널, 직접 메시지, 스레드를 한 화면에서 돌리는
데스크톱 앱입니다.

- **프런트엔드** React 19 + TypeScript + Vite, 데스크톱 셸은 **Tauri 2 (Rust)**
- **백엔드** **FastAPI** (Python 3.12, async SQLAlchemy 2.0), 실시간은 WebSocket
- **디자인** 자체 디자인 시스템. 토큰은 `desktop/src/styles/tokens.css` 한 곳에 있고,
  규칙은 [DESIGN.md](DESIGN.md)에 잠가 두었습니다.

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

### 3. 빌드

```bash
cd desktop
npm run build           # 프런트엔드 번들
npm run app:build       # 데스크톱 설치 파일 (deb, dmg, msi)
```

---

## 구조

```
backend/
  app/
    core/         설정, DB 세션, 보안(ARGON2 + JWT), 에러 봉투, ID 발급
    models/       SQLAlchemy 모델 (user, workspace, channel, message, file, schedule)
    schemas/      Pydantic 응답 모델
    api/v1/       라우터 (auth, workspaces, channels, messages, schedule, search, realtime)
    realtime/     WebSocket 허브, 이벤트 발행, presence
    services/     도메인 로직
  scripts/seed.py 데모 워크스페이스
  tests/          103개 테스트
desktop/
  src/
    styles/       tokens.css (토큰 한 곳), base.css, app.css
    lib/          API 클라이언트, WebSocket, 포맷, 달력 계산, 마크다운
    store/        zustand 상태 관리
    components/   화면 조각 (채널 · 스레드 · 일정 · 프로젝트 보드)
  src-tauri/      Rust 데스크톱 셸 (창, 알림, 외부 링크)
docs/API.md        API 계약 (프런트엔드와 백엔드가 함께 읽는 문서)
docs/FILES.md     파일 저장 규칙 (어디에 저장되고, 무엇이 저장되며, 언제 사라지는지)
DESIGN.md          잠긴 디자인 시스템
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

---

## 개발 명령

```bash
cd backend
.venv/bin/pytest -q                  # 103 passed
.venv/bin/ruff check .
.venv/bin/ruff format --check .

cd ../desktop
npm run typecheck
npm run test
npm run build
```

---

## 배포

`backend/Dockerfile`은 백엔드 이미지입니다. SQLite는 단일 인스턴스 배포용이고,
여러 인스턴스로 갈 때는 Postgres를 쓰세요. 데스크톱 앱은 CI에서
`npm run app:build`로 배포합니다.
