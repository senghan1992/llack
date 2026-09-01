# 윈도우에서 실행하기

이 문서만 따라가면 윈도우 PC 에서 Llack 을 띄울 수 있습니다.

두 단계로 나뉩니다.

- **1단계 — 백엔드 + UI 확인**: Python 과 Node 만 있으면 됩니다. 5분.
- **2단계 — 실제 데스크톱 앱**: Rust 와 MSVC 빌드 도구가 추가로 필요합니다. 첫 빌드 10~20분.

먼저 1단계로 기능을 보고, 데스크톱 창까지 보고 싶을 때 2단계로 가는 걸 권합니다.

---

## 0. 코드 가져오기

서버(EC2)에 있는 코드를 윈도우로 옮깁니다. 서버에 미리 두 가지 파일을 만들어 두었습니다.

| 파일 | 내용 |
| --- | --- |
| `~/llack.bundle` | git 저장소 전체 (커밋 이력 포함). 약 300KB |
| `~/llack.zip` | 소스만 담은 zip. git 없이 열어볼 때 |

### 방법 A — scp (권장)

윈도우 10/11 에는 OpenSSH 가 기본 포함되어 있습니다. **윈도우 PowerShell** 에서:

```powershell
cd $HOME\Downloads

# 평소 서버에 접속하는 방식과 같은 옵션을 쓰세요.
scp -i C:\path\to\your-key.pem ec2-user@<서버주소>:~/llack.bundle .

# 번들에서 저장소를 복원합니다 (git 이 없으면: winget install Git.Git)
git clone llack.bundle llack
cd llack
```

`git clone` 이 끝나면 커밋 이력까지 그대로 들어옵니다:

```powershell
git log --oneline
```

### 방법 B — AWS SSM 으로 접속하는 경우

퍼블릭 IP 없이 Session Manager 로 붙는다면 S3 를 경유하는 게 가장 간단합니다.

서버에서:
```bash
aws s3 cp ~/llack.bundle s3://<본인-버킷>/llack.bundle
```
윈도우에서:
```powershell
aws s3 cp s3://<본인-버킷>/llack.bundle .
git clone llack.bundle llack
```

### 방법 C — 사내 Git 서버 / GitHub 에 올리기

서버에서 원격을 추가해 푸시하면, 윈도우에서는 평소처럼 clone 하면 됩니다.

```bash
cd ~/claude-lab/llack
git remote add origin <저장소 URL>
git push -u origin main
```

### 방법 D — zip 만 받기

git 을 쓰지 않겠다면:

```powershell
scp -i C:\path\to\your-key.pem ec2-user@<서버주소>:~/llack.zip .
Expand-Archive llack.zip -DestinationPath llack
cd llack
```

---

## 1단계 — 백엔드 + UI 확인 (5분)

### 필요한 것

**PowerShell** 에서 (관리자 권한 불필요):

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
```

설치 후 **PowerShell 창을 새로 열어야** PATH 가 반영됩니다.

### 실행

저장소 폴더에서:

```powershell
# 처음 한 번만: 스크립트 실행을 허용합니다
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

.\llack.ps1 doctor      # 필요한 도구가 있는지 진단
.\llack.ps1 setup       # 의존성 설치 (2~3분)
.\llack.ps1 seed        # DB 생성 + 시드 데이터
.\llack.ps1 dev         # 백엔드 서버 실행
```

`dev` 는 창을 붙잡고 있으니, **새 PowerShell 창**을 열어 UI 를 띄웁니다:

```powershell
cd <저장소 폴더>
.\llack.ps1 ui          # http://localhost:1420
```

### 무엇을 확인할 수 있는지

- **http://localhost:8000/docs** — 76개 엔드포인트를 브라우저에서 직접 호출해볼 수 있습니다.
  `POST /auth/login` 에 `alice@example.com` / `llack-dev-password` 를 넣고 토큰을 받아
  `Authorize` 에 넣으면 나머지 API 를 모두 눌러볼 수 있습니다.
- **http://localhost:1420** — UI 레이아웃(독 · 사이드바 · 전사록 · 컴포저 · ⌘K 팔레트)을
  볼 수 있습니다.

> **브라우저에서는 로그인 화면까지만 보입니다.** UI 가 데이터를 가져오는 통로가
> Tauri IPC 라서, 브라우저에는 그 통로가 없습니다. 로딩 후 로그인 화면으로 떨어지는 게
> 정상 동작입니다. 실제 대화 화면을 보려면 2단계로 가세요.

테스트도 여기서 돌려볼 수 있습니다:

```powershell
.\llack.ps1 test        # 백엔드 77개 (Rust 가 있으면 코어 50개도)
```

서버가 켜져 있는 상태에서 종단 검증:

```powershell
.\llack.ps1 smoke       # 실시간 17항목 + 미니앱 25항목
```

---

## 2단계 — 데스크톱 앱 (10~20분)

### 추가로 필요한 것

```powershell
winget install Rustlang.Rustup

winget install Microsoft.VisualStudio.2022.BuildTools --override `
  "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

- **Rust**: 설치 후 새 PowerShell 창을 열어야 `cargo` 가 인식됩니다.
- **MSVC 빌드 도구**: Rust 가 윈도우에서 쓰는 링커(`link.exe`)입니다. 없으면
  빌드가 `linker 'link.exe' not found` 로 실패합니다. 용량이 크고 5~10분 걸립니다.
- **WebView2**: 윈도우 11 과 최신 윈도우 10 에는 기본 포함입니다. 없다면
  `winget install Microsoft.EdgeWebView2Runtime`.

`.\llack.ps1 doctor` 가 이 세 가지를 다 확인해줍니다.

### 실행

백엔드를 먼저 띄워둔 상태에서 (`.\llack.ps1 dev`), 새 창에서:

```powershell
.\llack.ps1 desktop
```

첫 실행은 Rust 의존성 컴파일로 **10~20분** 걸립니다. 두 번째부터는 수십 초입니다.
컴파일이 끝나면 Llack 창이 열립니다.

로그인: `alice@example.com` / `llack-dev-password`

### 설치 파일(.msi / .exe) 만들기

```powershell
.\llack.ps1 build
```

결과물은 `desktop\target\release\bundle\` 아래에 생깁니다.

---

## 무엇을 눌러볼지

시드 데이터에 확인용 상황을 미리 만들어 두었습니다.

| 볼 것 | 어디서 |
| --- | --- |
| **도킹된 스레드 패널** | `#개발` 채널의 첫 메시지에서 "답글 2개" 클릭 → 채널이 가려지지 않는 것 확인 |
| **통합 검색** | `Ctrl+K` → "토큰" 입력 → 채널·사람·메시지가 한 목록에 |
| **미니앱 패널** | 좌측 독의 보라색 앱 아이콘 클릭 (아래 "예제 앱" 참고) |
| **앱 권한 화면** | 좌측 독 맨 아래 **+** → 앱이 요청하는 권한이 한국어로 표시됨 |
| **앱이 올린 메시지** | `#배포` 채널 — 봇 계정으로 올라간 메시지에 "앱" 태그 |
| **멘션 강조** | `#공지` 채널의 `@channel` 메시지 |
| **코드 블록** | `#배포` 채널의 배포 로그 |
| **음소거 동작** | 채널 헤더의 🔔 을 눌러 끄면, 그 채널 안 읽음이 배지에서 빠짐 |
| **오프라인 전송** | 백엔드를 끄고 메시지 전송 → "연결되면 자동 전송" → 백엔드를 켜면 실제로 전송됨 |

### 예제 미니앱까지 보려면

앱 패널은 앱의 실제 웹페이지를 불러옵니다. 세 번째 PowerShell 창에서:

```powershell
.\llack.ps1 example-app     # http://localhost:5180
```

그 다음 좌측 독의 앱 아이콘을 누르면 스탠드업 작성 패널이 뜹니다.
작성 후 "채널에 올리기" 를 누르면 봇 계정으로 채널에 게시됩니다 —
API 키도, 앱 전용 DB 도 없이 동작하는 것을 확인할 수 있습니다.

---

## 문제가 생기면

### `.\llack.ps1` 이 실행되지 않음

```
이 시스템에서 스크립트를 실행할 수 없으므로 ...
```
→ `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` 를 한 번 실행하세요.

### `python` 또는 `node` 를 찾을 수 없음

winget 설치 후 PATH 는 **새 터미널**에만 반영됩니다. PowerShell 을 닫고 새로 열어주세요.

### `linker 'link.exe' not found`

MSVC C++ 빌드 도구가 없습니다. 위 2단계의 winget 명령을 실행하고 새 터미널을 여세요.

### 데스크톱 창이 하얗게만 뜸

Vite 개발 서버가 아직 안 올라왔거나 포트가 다릅니다. `desktop\vite.config.ts` 의 포트
(1420)와 `desktop\src-tauri\tauri.conf.json` 의 `devUrl` 이 같은지 확인하세요.
둘 다 `127.0.0.1:1420` 을 쓰도록 맞춰 두었습니다 — 윈도우에서 `localhost` 가
IPv6(`::1`)로 먼저 해석되면서 연결이 거부되는 문제를 피하기 위한 것입니다.

### 포트 8000 또는 1420 이 이미 사용 중

무엇이 쓰고 있는지 확인하고 종료하거나:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <위에서 나온 PID>
```

다른 포트를 쓰세요:

```powershell
cd backend
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8010

# 종단 검증도 같은 포트를 가리키게 합니다
$env:LLACK_SMOKE_BASE_URL = "http://127.0.0.1:8010"
.venv\Scripts\python.exe scripts\smoke_realtime.py
```

이 경우 앱의 로그인 화면에서 서버 주소를 `http://127.0.0.1:8010` 으로 입력하면 됩니다.

### `winget` 자체가 없음

윈도우 10 구버전입니다. Microsoft Store 에서 "앱 설치 관리자"를 설치하거나,
각 도구를 직접 받으세요:
[Python](https://www.python.org/downloads/windows/) ·
[Node](https://nodejs.org/) ·
[Rust](https://rustup.rs/) ·
[MSVC 빌드 도구](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

### 딥링크(`llack://`)가 동작하지 않음

윈도우에서 커스텀 URL 스킴은 **설치된 앱**에만 등록됩니다. 개발 모드(`desktop`)에서는
동작하지 않는 것이 정상입니다. `.\llack.ps1 build` 로 만든 설치 파일로 설치하면 됩니다.

### DB 를 처음부터 다시 만들고 싶음

```powershell
.\llack.ps1 reset-db
```

---

## 알아두실 것

- 이 초안의 **기본 개발 DB 는 SQLite** 입니다. 별도 설치가 필요 없지만,
  실제 배포에서는 Postgres 를 쓰세요 (`make compose-up` 또는 `LLACK_DATABASE_URL` 지정).
- **리프레시 토큰은 윈도우 자격 증명 관리자**에 저장됩니다. 로그아웃하면 삭제됩니다.
  "Windows 자격 증명" 에서 `com.llack.desktop` 항목으로 확인할 수 있습니다.
- 로컬 캐시(`cache.sqlite3`)는 `%APPDATA%\com.llack.desktop\` 에 생깁니다.
  메시지 본문이 평문으로 들어가므로, 디스크 암호화(BitLocker)를 전제하고 있습니다.
- 아이콘은 코드에서 생성한 자리표시자입니다. 실제 로고로 바꾸려면:
  `cd desktop && npm run tauri icon <로고.png>`
