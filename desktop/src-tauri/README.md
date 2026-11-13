# src-tauri — Tauri 2 셸 크레이트 매니페스트

## Overview

프런트엔드(`desktop/`)를 감싸는 Tauri 2 데스크톱 셸의 크레이트 루트입니다.
이 디렉터리는 셸의 **빌드 매니페스트**를 모으는 곳입니다 — Rust 소스는
[./src/README.md](./src/README.md) 한 곳에 있고, 여기에는 `Cargo.toml`,
`build.rs`, `tauri.conf.json`, `.gitignore` 만 있습니다.

크레이트 이름은 `llack`, lib 이름은 `llack_lib` 이고, **독립형(standalone)**
패키지입니다 — 워크스페이스 멤버가 아닙니다.

- 하위 디렉터리: [src](./src/README.md) — 셸 코어(Rust 모듈 4개 + 커맨드 5개)

## Interface

### `Cargo.toml`

- [desktop/src-tauri/Cargo.toml:package] — `name = "llack"`, `version = "0.2.0"`,
  `edition = "2021"`, `rust-version = "1.77"`, `license = "Proprietary"`,
  `default-run = "llack"`.
- [desktop/src-tauri/Cargo.toml:lib] — `name = "llack_lib"`,
  `crate-type = ["staticlib", "cdylib", "rlib"]`.
- [desktop/src-tauri/Cargo.toml:features] — `default = ["custom-protocol"]`,
  `custom-protocol = ["tauri/custom-protocol"]`.
- [desktop/src-tauri/Cargo.toml:build-dependencies] — `tauri-build = { version = "2" }`.
- [desktop/src-tauri/Cargo.toml:dependencies] — `tauri = { version = "2.12",
  features = ["protocol-asset"] }`, `tauri-plugin-notification = "2.8"`,
  `tauri-plugin-dialog = "2.7"`, `tauri-plugin-opener = "2.7"`,
  `tauri-plugin-os = "2.4"`.
- [desktop/src-tauri/Cargo.toml:reqwest] — `{ version = "0.12",
  default-features = false, features = ["json", "http2", "rustls-tls"] }`.
  웹뷰에 노출하지 않는 요청(알림에 붙일 채널 이름 확인 등)에만 씁니다.
  네이티브 TLS 를 쓰지 않아 openssl 없이 빌드됩니다.
- [desktop/src-tauri/Cargo.toml:serde] / `serde_json` / `tokio` / `thiserror` /
  `anyhow` / `tracing` / `tracing-subscriber` / `url` — 런타임 의존성.
- [desktop/src-tauri/Cargo.toml:profile.release] — `codegen-units = 1`,
  `lto = true`, `opt-level = "s"`, `strip = true`.
- [desktop/src-tauri/Cargo.toml:dev-dependencies] / `[[test]]` — **없음.**
  별도 통합 테스트 타깃이 없고 dev-deps 도 선언되어 있지 않습니다.

### `build.rs`

- [desktop/src-tauri/build.rs:main] — `tauri_build::build()` 한 줄뿐입니다.
  컴파일 시 Tauri 컨텍스트를 생성·검증합니다.

### `tauri.conf.json`

- [desktop/src-tauri/tauri.conf.json:productName] — `"Atrium"`.
- [desktop/src-tauri/tauri.conf.json:identifier] — `"ai.arche.atrium"`.
- [desktop/src-tauri/tauri.conf.json:version] — `"0.2.0"` (Cargo.toml 과 동일).
- [desktop/src-tauri/tauri.conf.json:build] — `beforeDevCommand = "npm run dev"`,
  `devUrl = "http://127.0.0.1:1420"`, `beforeBuildCommand = "npm run build"`,
  `frontendDist = "../dist"`.
- [desktop/src-tauri/tauri.conf.json:app.windows] — 라벨 `"main"`, 제목 `"Atrium"`,
  1280×860 (최소 940×620), 리사이즈 가능, 중앙 정렬, 장식 있음,
  드래그 앤 드롭 허용, 보임.
- [desktop/src-tauri/tauri.conf.json:app.security.csp] — `default-src "'self'"`,
  `script-src "'self'"`, `style-src "'self' 'unsafe-inline'"`,
  `object-src "'none'"`, `base-uri "'self'"`, `form-action "'none'"`,
  그리고 `img-src` / `media-src` / `connect-src` 의 백엔드·asset·ipc 허용 목록.
- [desktop/src-tauri/tauri.conf.json:app.security.assetProtocol] — `enable = true`,
  `scope = []`.
- [desktop/src-tauri/tauri.conf.json:app.security.capabilities] — `["default"]`.
- [desktop/src-tauri/tauri.conf.json:app.withGlobalTauri] — `false`.
- [desktop/src-tauri/tauri.conf.json:bundle] — `active = true`, `targets = "all"`,
  아이콘 5종, `linux.deb.depends` = `libwebkit2gtk-4.1-0` + `libgtk-3-0`,
  `macOS.minimumSystemVersion = "10.15"`,
  `windows.webviewInstallMode.type = "downloadBootstrapizer"`.

## Invariants

- [desktop/src-tauri/Cargo.toml:package.rust-version] — 최소 지원 Rust 버전은 1.77.
- [desktop/src-tauri/Cargo.toml:features.custom-protocol] — `custom-protocol` 은
  정확히 `["tauri/custom-protocol"]` 이므로, 켜면 tauri 크레이트의 같은 이름
  기능으로 전달됩니다.
- [desktop/src-tauri/Cargo.toml:features.default] — 기본 기능 집합은 정확히
  `["custom-protocol"]` 입니다. 즉 release 빌드는 프론트엔드 번들(`dist`)을
  커스텀 프로토콜로 서빙합니다.
- [desktop/src-tauri/Cargo.toml:reqwest] — `default-features = false` +
  `["json", "http2", "rustls-tls"]` 만 켜고 네이티브 TLS(openssl)는 의도적으로
  뺐습니다.
- [desktop/src-tauri/tauri.conf.json:app.security.csp] — CSP가 구조적으로 제한적입니다.
  `script-src` 은 `'self'` 뿐(`unsafe-inline`/`eval` 없음), `object-src` 과
  `form-action` 은 `'none'`. 유일한 완화는 `style-src` 의 `'unsafe-inline'` 입니다.
- [desktop/src-tauri/tauri.conf.json:app.security.assetProtocol.scope] — asset
  프로토콜은 켜져 있으나(`enable = true`) scope 배열은 비어 있습니다.
- [desktop/src-tauri/tauri.conf.json:app.withGlobalTauri] — 전역 Tauri API는
  웹뷰에 노출되지 않습니다.
- [desktop/src-tauri/tauri.conf.json:app.security.capabilities] — 참조하는
  capability 세트는 `"default"` 하나뿐입니다.
- [desktop/src-tauri/.gitignore:/target] — 빌드 산출물 `/target` 과 `/gen/schemas` 는
  제외됩니다.

## Side Effects

- [desktop/src-tauri/build.rs:main] — 컴파일 시 `tauri_build::build()` 가
  build-script 출력과 Tauri 컨텍스트(그리고 `.gitignore` 가 제외한
  `gen/schemas` 산출물)를 생성·검증합니다.
- [desktop/src-tauri/Cargo.toml:features.custom-protocol] — 이 기능이 켜져 있으면
  컴파일된 앱이 프론트엔드를 Tauri 커스텀 프로토콜로 서빙합니다(개발 서버 URL 대신).
- [desktop/src-tauri/tauri.conf.json:build.beforeDevCommand] — `tauri dev` 가
  시작 전에 `"npm run dev"` 를 셸로 실행합니다.
- [desktop/src-tauri/tauri.conf.json:build.beforeBuildCommand] — `tauri build` 가
  번들링 전에 `"npm run build"` 로 프론트엔드 자산을 만듭니다.
- [desktop/src-tauri/tauri.conf.json:bundle] — 번들링이 설치 가능한 산출물을
  씁니다(모든 타깃). Windows 는 WebView2 런타임을
  `webviewInstallMode.type = "downloadBootstrapizer"` 로 확보합니다.
- [desktop/src-tauri/tauri.conf.json:bundle.linux.deb] — 생성된 Debian 패키지는
  `libwebkit2gtk-4.1-0` 와 `libgtk-3-0` 을 런타임 의존성으로 선언합니다.

## Verification

- Run: `cargo test` (이 디렉터리에서 실행). lib 타깃 `llack_lib` 의 단위 테스트
  5개가 돕니다 — 상세는 [./src/README.md](./src/README.md).
- Build: `cargo build --release`
