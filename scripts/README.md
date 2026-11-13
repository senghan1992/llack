# Scripts

## Overview

저장소 최상위의 개발 도구 두 개입니다. 둘 다 루트 `Makefile`(`../Makefile`)에서
불러 쓰고, 애플리케이션 코드가 참조하지 않으며, 서로에게도 의존하지 않습니다.
pytest 스위트(`make test` → `backend/tests`)의 일부가 **아니므로** 자동화 테스트가
아니라 **실행 중인 앱을 상대로 하는 수동 점검**입니다.

- **`check-contrast.py`** — Playwright로 웹 프런트엔드를 실제로 렌더링한 뒤, 라이트/다크
  두 테마에서 화면에 그려진 모든 글자를 WCAG AA 대비 기준으로 검사합니다. 앱의 모든
  `:hover` 규칙을 하나씩 강제로 켜서 hover 상태의 글자도 함께 잽니다.
- **`desktop-headless.sh`** — 가상 화면(Xvfb) 위에 **실제 Tauri 릴리스 바이너리**를
  띄우고 창을 잘라 PNG로 저장합니다. 브라우저로는 확인할 수 없는 데스크톱 셸 경로
  (API 주소 주입, 창 상태, OS 알림)까지 함께 검증하기 위한 도구입니다.

## Interface

### `scripts/check-contrast.py` — Python 3 CLI

| 플래그 | 기본값 | 의미 |
| --- | --- | --- |
| `--url` | `$LLACK_SMOKE_UI`, 없으면 `http://127.0.0.1:1420` | 점검할 웹 프런트엔드 주소 `[scripts/check-contrast.py:--url]` |
| `--email` | `hyunjin@hanbit.co.kr` | 로그인 이메일 `[scripts/check-contrast.py:--email]` |
| `--password` | `hanbit2026` | 로그인 비밀번호 `[scripts/check-contrast.py:--password]` |
| `--api` | `$LLACK_SMOKE_API`, 없으면 `http://127.0.0.1:8000` | **파싱만 하고 쓰지 않는 예약 옵션** — 소스 주석에 "안 쓰는 옵션 · 예약"이라 명시돼 있습니다 `[scripts/check-contrast.py:--api]` |

환경 변수:

- `LLACK_SMOKE_UI` — `--url`의 기본값 `[scripts/check-contrast.py:LLACK_SMOKE_UI]`
- `LLACK_SMOKE_API` — `--api`의 기본값 `[scripts/check-contrast.py:LLACK_SMOKE_API]`

공개 함수:

- `luminance(rgb)` — WCAG 상대 휘도 계산 `[scripts/check-contrast.py:luminance]`
- `contrast(a, b)` — 대비율 `(max+0.05)/(min+0.05)` `[scripts/check-contrast.py:contrast]`
- `check(sample)` — `(대비, 필요한 대비, 가장 나쁜 배경)` 3-튜플 반환 `[scripts/check-contrast.py:check]`
- `hover_selectors(css)` — CSS 문자열에서 `:hover` 선택자 목록 추출 `[scripts/check-contrast.py:hover_selectors]`
- `screens()` — `(화면 이름, 화면을 여는 동작)` 8쌍 목록 `[scripts/check-contrast.py:screens]`
- `main()` — 전체 실행과 종료 코드 반환 `[scripts/check-contrast.py:main]`

종료 코드: `0` 위반 없음 · `1` 위반 있음 · `2` Playwright 미설치 `[scripts/check-contrast.py:main]`

### `scripts/desktop-headless.sh` — bash

| 플래그 | 기본값 | 의미 |
| --- | --- | --- |
| `--shot PATH` | `<repo>/desktop/headless.png` | 캡처 PNG를 쓸 경로 `[scripts/desktop-headless.sh:--shot]` |
| `--display NUM` | `$LLACK_DISPLAY`, 없으면 `:99` | 사용할 X 디스플레이 `[scripts/desktop-headless.sh:--display]` |
| `--login` | 꺼짐 | xdotool로 로그인 폼에 계정 정보를 입력합니다 `[scripts/desktop-headless.sh:--login]` |
| `--stop` | 꺼짐 | 띄워둔 앱과 Xvfb를 정리하고 캡처 없이 종료합니다 `[scripts/desktop-headless.sh:--stop]` |
| `-h`, `--help` | — | 스크립트 머리말을 출력하고 `0`으로 종료 `[scripts/desktop-headless.sh:--help]` |

환경 변수:

- `LLACK_DISPLAY` — 디스플레이 기본값 `[scripts/desktop-headless.sh:LLACK_DISPLAY]`
- `LLACK_HEADLESS_HOME` — 격리된 앱 프로필 홈 (기본 `/tmp/llack-headless-home`) `[scripts/desktop-headless.sh:LLACK_HEADLESS_HOME]`
- `LLACK_EMAIL` — 로그인 이메일 (기본 `hyunjin@hanbit.co.kr`) `[scripts/desktop-headless.sh:LLACK_EMAIL]`
- `LLACK_PASSWORD` — 로그인 비밀번호 (기본 `hanbit2026`) `[scripts/desktop-headless.sh:LLACK_PASSWORD]`

기동 대상 바이너리는 `<repo>/desktop/src-tauri/target/release/llack` 로 하드코딩돼
있습니다 `[scripts/desktop-headless.sh:BIN]`.

인자 파서는 `--shot` · `--display` · `--login` · `--stop` · `-h|--help` 를 처리하는
`case` 문이며, 알 수 없는 인자는 stderr에 알리고 `2`로 종료합니다
`[scripts/desktop-headless.sh:--help]`.
`--stop` 은 도구 확인보다 **먼저** 실행되므로 이 모드에서는 `ffmpeg` · `Xvfb` 가
없어도 됩니다 `[scripts/desktop-headless.sh:--stop]`.

## Invariants

### `scripts/check-contrast.py`

- 필요한 대비는 WCAG AA 기준입니다. 글자 크기가 24px 이상이거나, 18.66px 이상이면서
  글자 굵기가 700 이상이면 `3.0`, 그 외에는 `4.5` 입니다 `[scripts/check-contrast.py:check]`.
- 한 글자는 **배경 후보 중 가장 나쁜 것과** 비교됩니다. 후보가 여러 개(그라디언트 색
  스톱, 조상 배경)면 그중 대비가 가장 낮은 것을 고릅니다 `[scripts/check-contrast.py:check]`.
- 배경 합성은 조상 체인을 거슬러 올라가며 하고, 바탕은 문서 루트의 배경색이며 그 색이
  완전히 투명하면 불투명 흰색으로 대체합니다 `[scripts/check-contrast.py:MEASURE]`.
- 알파가 있는 글자색은 첫 번째 배경 후보 위에 합성하고, 요소의 `opacity`는 전경색에
  곱해집니다 `[scripts/check-contrast.py:check]`.
- 보이지 않는 요소(숨김 · 크기 0)와 유효 opacity가 `0.15` 미만인 요소는 정적·hover
  두 검사 모두에서 건너뜁니다 `[scripts/check-contrast.py:main]`.
- hover 선택자는 `desktop/src/styles/app.css` 를 읽어 정규식으로 뽑습니다. 주석을 먼저
  지우고, `:hover` 를 제거한 나머지가 `@` 로 시작하면 버립니다 `[scripts/check-contrast.py:hover_selectors]`.
- hover 상태는 CDP `CSS.forcePseudoState` 로 강제하고, 검사가 끝나면 강제 상태를
  다시 해제합니다. 검사 대상에는 잠깐 `data-contrast-probe="1"` 을 붙였다가 떼어냅니다
  `[scripts/check-contrast.py:main]`.
- `light` 와 `dark` 두 테마 × `screens()` 의 8개 화면으로 총 16회 순회합니다
  `[scripts/check-contrast.py:screens]`.
- 로그인은 `#gate-email` · `#gate-password` 입력란과 제출 버튼을 통해, 테마·화면 반복문
  **밖에서 한 번만** 수행합니다 `[scripts/check-contrast.py:main]`.
- 위반은 `ratio < need` 일 때만 기록됩니다. 정확히 같으면 통과입니다
  `[scripts/check-contrast.py:main]`.
- 브라우저는 Chromium 기본(헤드리스) 모드이고 뷰포트는 `1440×900` 로 고정입니다
  `[scripts/check-contrast.py:main]`.
- 출력에 남는 글자 스니펫은 앞 40자로 잘립니다 `[scripts/check-contrast.py:MEASURE]`.
- 위반 항목은 `(mode, screen, cls, text, selector, ratio)` 튜플로 중복 제거되고,
  마지막 줄에 "N건 위반 · 점검한 hover 규칙 M개" 형태로 요약합니다
  `[scripts/check-contrast.py:main]`.

### `scripts/desktop-headless.sh`

- `ffmpeg` 와 `Xvfb` 는 필수이고, `--login` 은 `xdotool` 도 필요합니다. 없으면
  `exit 1` 로 중단합니다 `[scripts/desktop-headless.sh:need]`.
- 릴리스 바이너리가 실행 파일이 아니면 `desktop/src-tauri` 에서
  `cargo build --release` 로 먼저 빌드합니다 `[scripts/desktop-headless.sh:BIN]`.
- Xvfb 는 `1440x900x24` 화면에 `-nolisten tcp` 로 뜨고, `/tmp/.X11-unix/X<N>` 이 이미
  있으면 새로 띄우지 않습니다 `[scripts/desktop-headless.sh:DISPLAY_NUM]`.
- 앱은 컴포지팅·dmabuf·샌드박스를 끄고 소프트웨어 GL 로 실행됩니다
  (`WEBKIT_DISABLE_COMPOSITING_MODE=1`, `WEBKIT_DISABLE_DMABUF_RENDERER=1`,
  `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1`, `LIBGL_ALWAYS_SOFTWARE=1`,
  `GDK_BACKEND=x11`) `[scripts/desktop-headless.sh:BIN]`.
- 앱 PID 는 `$!` 를 믿지 않고 `pgrep -x llack` 로 이름이 정확히 일치하는 프로세스를
  찾아 정합니다. `setsid` 가 fork 할 수 있기 때문입니다 `[scripts/desktop-headless.sh:APP_PID]`.
- 정리는 PID 파일과 이름이 정확히 `llack` 인 프로세스만 대상으로 합니다. 사용자의 셸까지
  죽일 수 있는 `pkill -f` 는 의도적으로 쓰지 않습니다 `[scripts/desktop-headless.sh:stop_all]`.
- 캡처할 창은 앱 PID가 소유한 `Llack` 이름 창 중 면적이 가장 큰 것입니다
  (`xdotool search --pid` + `getwindowgeometry`) `[scripts/desktop-headless.sh:geom]`.
- 로그인 좌표는 창 기준 고정 오프셋입니다 — 이메일 `(319, 374)` · 비밀번호 `(319, 449)` ·
  로그인 버튼 `(319, 593)` `[scripts/desktop-headless.sh:DO_LOGIN]`.
- 캡처는 `ffmpeg -f x11grab` 한 프레임이며, 창 기하를 알면 그 크기로 잘라냅니다
  `[scripts/desktop-headless.sh:SHOT]`.
- 캡처를 마쳐도 앱은 계속 떠 있습니다. 내리는 방법은 `--stop` 입니다
  `[scripts/desktop-headless.sh:DO_STOP]`.

## Side Effects

### `scripts/check-contrast.py`

- Playwright 로 Chromium 을 띄우고(뷰포트 1440×900) `--url` 을 실제 방문해 로그인하고
  화면을 조작합니다 `[scripts/check-contrast.py:main]`.
- 브라우저 localStorage 를 **변경**합니다 — 키 `llack.settings` 에
  `{"theme": "light"|"dark"}` 를 쓰고 `document.documentElement.dataset.theme` 을
  바꿉니다 `[scripts/check-contrast.py:main]`.
- CDP 세션(`DOM.enable`, `CSS.enable`, `DOM.getDocument`, `DOM.querySelector`,
  `CSS.forcePseudoState`) 으로 실제 노드에 `:hover` 를 강제하고, 검사한 요소에는
  잠깐 `data-contrast-probe="1"` 을 붙였다가 떼어냅니다 `[scripts/check-contrast.py:main]`.
- hover 규칙을 찾으려고 `desktop/src/styles/app.css` 를 디스크에서 읽습니다
  `[scripts/check-contrast.py:CSS_FILE]`.
- **디스크에 쓰는 파일이 없습니다.** 스크린샷을 찍거나 저장하지도 않습니다 —
  `open()` · `write` · `page.screenshot()` 호출이 없고, 결과는 위반 목록과 요약 줄을
  stdout으로 내보내고 종료 코드로 알립니다 `[scripts/check-contrast.py:main]`.
  (스크린샷은 `desktop-headless.sh` 쪽 산출물입니다.)

### `scripts/desktop-headless.sh`

- 캡처 PNG 를 기본값 `<repo>/desktop/headless.png` 에, `--shot` 을 주면 그 경로에
  씁니다. 기본 경로는 `.gitignore` 에 올라 있습니다 `[scripts/desktop-headless.sh:SHOT]`.
- 앱의 stdout/stderr 를 `/tmp/llack-headless.log` 에 기록합니다
  `[scripts/desktop-headless.sh:LOG]`.
- PID 파일 `/tmp/llack-headless-app.pid` 와 `/tmp/llack-headless-xvfb.pid` 를
  쓰고, `--stop` 에서 지웁니다 `[scripts/desktop-headless.sh:APP_PID_FILE]`,
  `[scripts/desktop-headless.sh:XVFB_PID_FILE]`.
- Xvfb 자체의 로그를 `/tmp/xvfb<N>.log` 에 씁니다 (`<N>` 은 콜론을 뗀 디스플레이 번호)
  `[scripts/desktop-headless.sh:DISPLAY_NUM]`.
- 격리된 프로필 홈을 **지우고 다시 만듭니다** — `rm -rf "$LLACK_HEADLESS_HOME/data"`
  다음 `mkdir -p "$LLACK_HEADLESS_HOME/data" "$LLACK_HEADLESS_HOME/config"`, 그리고
  `XDG_DATA_HOME` · `XDG_CONFIG_HOME` 을 그쪽으로 돌립니다. 덕분에 매번 로그인 화면에서
  시작하고 평소 쓰는 프로필·창 상태는 오염되지 않습니다
  `[scripts/desktop-headless.sh:HEADLESS_HOME]`.
- 바이너리가 없으면 `cargo build --release` 를 실행해
  `desktop/src-tauri/target/release/` 에 산출물을 씁니다 `[scripts/desktop-headless.sh:BIN]`.
- Xvfb 와 앱 프로세스를 `setsid` 로 분리 실행(데몬화)하고, 캡처 뒤에도 앱을 띄워 둡니다
  `[scripts/desktop-headless.sh:DO_STOP]`.
- 시작 전과 `--stop` 시, 이름이 정확히 `llack` 인 프로세스를 종료합니다
  `[scripts/desktop-headless.sh:stop_all]`.

## Verification

- **`make contrast`** → `python3 scripts/check-contrast.py`
  자동화 테스트 스위트가 **아닌** 수동/실시간 점검입니다. 실행 중인 백엔드
  (`make dev`, 127.0.0.1:8000), 실행 중인 웹 프런트엔드(`make dev-web`,
  127.0.0.1:1420), `pip install playwright && playwright install chromium`,
  그리고 시드 계정(`make seed`)이 모두 있어야 합니다. 위반이 있으면 위반 목록을
  stdout에 찍고 종료 코드 `1` 을 반환합니다.

- **`make desktop-headless`** → `./scripts/desktop-headless.sh --login`
  자동화 테스트 스위트가 **아닌** 수동/실시간 점검입니다. `xvfb` · `ffmpeg` 가 필요하고
  `--login` 은 `xdotool` 도 필요합니다. 릴리스 바이너리가 없으면 스크립트가
  `cargo build --release` 로 빌드합니다. PNG 한 장을 남기고 앱은 계속 떠 있으므로
  `./scripts/desktop-headless.sh --stop` 으로 정리합니다.

두 스크립트 모두 CI 가 고정적으로 돌리는 hermetic 테스트가 아니라, "이 상태에서 지금
실제로 어떻게 보이는가"를 눈으로 확인하기 위한 도구입니다. 참조:
[루트 README](../README.md) · [디자인 규칙](../DESIGN.md) · [Makefile](../Makefile).

`make lint` 의 ruff 는 `cd backend` 한 상태에서 `app tests scripts` 를 돌립니다. 즉
여기 있는 저장소 최상위 `scripts/` 는 린트·포맷 검사 대상이 아닙니다
(`backend/scripts/` 가 대상입니다) `[Makefile:lint]`.
