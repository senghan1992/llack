# 윈도우에서 실행하고 빌드하기

이 문서만 따라가면 윈도우 PC 에서 Llack 을 띄우고, 배포할 설치본까지
만들 수 있습니다.

## 준비물

| 뭐 | 필요한 버전 | 설치 |
| --- | --- | --- |
| Node.js | 20 이상 | `winget install OpenJS.NodeJS.LTS` |
| Rust | stable | `winget install Rustlang.Rustup` |
| MSVC 빌드 도구 | Visual Studio 2022 Build Tools | `winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"` |
| WebView2 | 최신 | 윈도우 11 · 최신 윈도우 10 에는 기본 포함. 없으면 `winget install Microsoft.EdgeWebView2Runtime` |

```powershell
winget install OpenJS.NodeJS.LTS
winget install Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools --override `
  "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

설치 후 **PowerShell 창을 새로 열어야** PATH 가 반영됩니다.

- **MSVC 빌드 도구**는 Rust 가 윈도우에서 쓰는 링커(`link.exe`)입니다.
  없으면 빌드가 `linker 'link.exe' not found` 로 실패합니다. 용량이 크고
  5~10분 걸립니다.
- **WebView2** 는 앱이 그리는 데 쓰이는 브라우저 엔진입니다. Tauri 셸의
  모든 화면이 여기에 얹힙니다.

## 백엔드 먼저

앱은 API 가 떠 있어야 일을 합니다. 같은 PC 에서 띄우거나, 배포된 API 주소로
연결합니다.

```powershell
cd <저장소>\backend
uv venv --python 3.12
uv pip install --python .venv -e ".[dev]"
.venv\Scripts\python.exe scripts\seed.py          # 데모 워크스페이스 (선택)
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

윈도우의 가상환경 실행 파일은 `.venv\Scripts\` 아래에 있습니다
(유닉스라면 `.venv/bin/`).

`uv` 가 없다면 `pip install uv` 한 번으로 설치됩니다. 파이썬 3.12 가
필요합니다(`winget install Python.Python.3.12`).

## 앱 띄우기

```powershell
cd <저장소>\desktop
npm ci          # 처음 한 번
npm run app:dev # Tauri 창이 열립니다
```

`npm run app:dev` 는 Vite 개발 서버(127.0.0.1:1420)를 띄우고 Tauri 창을
엽니다. 첫 실행은 Rust 의존성 컴파일로 10~20분 걸립니다. 두 번째부터는
수십 초입니다.

브라우저로만 확인하려면 `npm run dev` (http://127.0.0.1:1420). 이때는
셸 기능(OS 알림, 창 위치 기억)이 없습니다.

## 설치본 만들기

```powershell
cd <저장소>\desktop
npm run app:build
```

결과물은 여기에 생깁니다.

```
desktop/src-tauri/target/release/bundle/msi/    ← .msi (팀 배포용)
desktop/src-tauri/target/release/bundle/nsis/   ← setup.exe (개인 설치용)
```

`npm run app:build` 는 `tauri build` 이고, 그 안에서 프런트엔드 번들
(`tsc --noEmit && vite build`)을 먼저 만듭니다. 별도로 `npm run build` 를
돌릴 필요는 없습니다.

아이콘을 바꾸려면:

```powershell
npm run tauri icon <로고.png>
```

## 배포된 API 를 가리키기

API 주소는 **빌드할 때** 정해집니다. 서버를 배포하면 주소가 고정되므로 —
그 주소를 한 번 정해 두고 앱을 그 주소로 빌드하면 됩니다.

```powershell
$env:LLACK_SERVER_URL = "https://llack.example.com"
npm run app:build
```

개발 중일 때도 같습니다.

```powershell
$env:LLACK_SERVER_URL = "http://127.0.0.1:8000"
npm run app:dev
```

`LLACK_SERVER_URL` 하나가 **세 곳**에 들어갑니다.

| 들어가는 곳 | 쓰임 |
| --- | --- |
| 프런트엔드 번들 (`VITE_API_BASE`) | REST·WebSocket 주소 |
| Tauri CSP | 그 주소로의 요청과 이미지를 허용 |
| Rust 셸 | 알림에 붙일 채널 이름을 물을 때 쓰는 주소 |

### CSP 를 손으로 고칠 필요는 없습니다

`desktop/scripts/tauri.mjs` 가 `LLACK_SERVER_URL` 를 읽어 CSP 를 **만들어
끼워 넣습니다**. `tauri.conf.json` 의 `app.security.csp` 는 기본값이고,
빌드할 때 그 위에 병합됩니다. 따라서 주소를 바꿀 때 JSON 을 손댈 필요가
없습니다 — 환경변수만 바꾸고 다시 빌드하세요.

기본값으로 빌드하면 이렇게 허용됩니다.

| directives | 허용된 주소 |
| --- | --- |
| `connect-src` | `'self' ipc: http://ipc.localhost http://127.0.0.1:8000 http://localhost:8000 ws://127.0.0.1:8000 ws://localhost:8000` |
| `img-src` | `'self' data: blob: asset: http://asset.localhost http://127.0.0.1:8000 http://localhost:8000` |

**API 가 이 주소들 바깥에 있으면 앱이 조용히 실패합니다.** 메시지는 안 나가고,
첨부 미리보기도 안 뜹니다. 네트워크 창에 `Refused to connect … Content Security Policy`
가 떠 있는 게 그 증상입니다. `LLACK_SERVER_URL` 을 빼먹었거나 오타를 낸
경우입니다 — 위 표와 실제 주소가 같은지 확인하세요.

### 주소를 바꿔도 서버는 그대로입니다

`LLACK_SERVER_URL` 은 **빌드**할 때 읽습니다. 서버 설정은 손댈 필요가
없습니다. 앱이 가리키는 주소만 바뀝니다. 서버 주소가 바뀐 다음 배포라면
앱도 다시 빌드해 주세요.

CORS 도 맞춰야 합니다. 서버의 `CORS_ORIGINS` 에 데스크톱 앱의 오리진이
들어 있어야 합니다. Tauri 의 오리진은 플랫폼마다 `tauri://localhost`
(macOS) 또는 `http://tauri.localhost` (윈도우·리눅스)입니다. 기본값 `*` 면
그냥 동작합니다.

## 문제가 생기면

### `linker 'link.exe' not found`

MSVC C++ 빌드 도구가 없습니다. 위의 winget 명령을 실행하고 **새 터미널**을
여세요.

### `cargo` 을 찾을 수 없습니다

Rustup 설치 후 새 PowerShell 창을 여세요. `rustup default stable` 로
안정판을 지정해 두는 것도 한 번 해 두면 좋습니다.

### 창이 하얗게만 뜹니다

Vite 개발 서버가 아직 안 올라왔거나 포트가 다릅니다.
`desktop/vite.config.ts` 의 포트(1420)와 `desktop/src-tauri/tauri.conf.json`
의 `devUrl` 이 같은지 확인하세요. 둘 다 `127.0.0.1:1420` 을 쓰도록 맞춰
뒀습니다 — 윈도우에서 `localhost` 가 IPv6(`::1`)로 먼저 해석되면서 연결이
거부되는 문제를 피하기 위한 것입니다.

### 로그인만 안 됩니다

API 가 떠 있는지, 주소가 맞는지 확인하세요. 브라우저에서
`http://127.0.0.1:8000/health` 가 `{"status":"ok"}` 를 주면 API 는 살아
있습니다. 배포된 API 를 쓴다면 `VITE_API_BASE` 를 다시 빌드했는지, CSP 를
넓혔는지 두 가지를 확인하세요.

### 포트 8000 또는 1420 이 이미 사용 중

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <위에서 나온 PID>
```

다른 포트를 쓴다면 API 를 그 포트로 띄우고 `VITE_API_BASE` 를 함께 바꿉니다.
`localhost` 가 아니라 `127.0.0.1` 을 쓰세요 — IPv6 해석 문제 때문입니다.

### `npm ci` 가 멈춥니다

사내 프록시 뒤에 있다면 `npm config set proxy <주소>` /
`npm config set https-proxy <주소>` 가 필요할 수 있습니다.

## 알아두실 것

- **리프레시 토큰은 브라우저 저장소(localStorage)에 있습니다.** 데스크톱 앱도
  마찬가지입니다 — 앱 안의 webview 저장소입니다. OS 키체인에 넣지 않습니다.
  PC 를 여러 대 쓰면 각 기기에서 따로 로그인해야 합니다.
- **자동 업데이트가 없습니다.** 새 버전이 나오면 새 설치본으로 교체합니다.
- **`desktop/src-tauri` 는 워크스페이스가 아니라 독립형 cargo 패키지**입니다.
  cargo 명령은 항상 그 폴더 안에서 돌립니다.

```powershell
cd desktop\src-tauri
cargo clippy --all-targets -- -D warnings
cargo fmt --check
cargo test
```
