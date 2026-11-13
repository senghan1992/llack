# desktop — 데스크톱 앱 Blueprint

## System Overview

사내 메신저 **Llack**(제품명 Atrium)의 데스크톱 앱입니다. 한 프로세스에 두 층이
들어 있습니다.

```
┌───────────────────────────────────────────────────────────────┐
│  웹뷰 (React 19 + TypeScript + Vite 7)                        │
│  src/ ── App.tsx 배선, lib/ 계약, store/ 상태, components/ 화면 │
└───────────────┬───────────────────────────────────────────────┘
                │  Tauri IPC (invoke / event)
┌───────────────▼───────────────────────────────────────────────┐
│  셸 (Rust, Tauri 2) — src-tauri/                             │
│  네이티브 창(기하 기억) · OS 알림 · 외부 브라우저 · 자체 HTTP │
└───────────────┬───────────────────────────────────────────────┘
                │  HTTPS / WebSocket
        ┌───────▼────────┐
        │  백엔드 /api/v1  │  (저장소 밖: backend/)
        └────────────────┘
```

웹뷰는 화면만 그립니다. 셸은 그 밑에서 네 가지만 담당합니다 — 네이티브 창
(크기·위치 기억 포함), OS 알림, 외부 브라우저로 링크 열기, 웹뷰에 노출하지
않는 요청을 위한 자체 HTTP 클라이언트. 에이전트·스크린캡처·키체인·딥링크·
트레이·미니앱 패널은 없습니다.

백엔드 주소는 `VITE_API_BASE` (기본 `http://127.0.0.1:8000`) 로 정하고,
셸은 `LLACK_API_BASE` / `LLACK_API_TOKEN` 환경변수를 읽습니다.

하위 디렉터리:

- [src](./src/README.md) — 프런트엔드 진입점과 화면 배선
- [src/components](./src/components/README.md) — 화면을 이루는 28개 컴포넌트
- [src/lib](./src/lib/README.md) — HTTP 클라이언트, 도메인 타입, 포맷터, 셸 브리지
- [src/store](./src/store/README.md) — 단일 Zustand 스토어
- [src-tauri](./src-tauri/README.md) — Tauri 2 셸 크레이트 매니페스트
- [src-tauri/src](./src-tauri/src/README.md) — 셸 코어 (Rust 모듈 4개 + 커맨드 5개)

`src/styles/`, `src/assets/`, `public/`, `src-tauri/capabilities/`,
`src-tauri/icons/` 는 스타일·자산·설정 디렉터리라 계약 대상이 아닙니다.
`node_modules/`, `dist/`, `target/`, `src-tauri/target/`, `src-tauri/gen/` 는
생성 산출물이라 제외합니다.

## Local Interface & Invariants

- [desktop/package.json:scripts] — `dev` = `vite`, `build` = `tsc --noEmit &&
  vite build`, `preview` = `vite preview`, `typecheck` = `tsc --noEmit`,
  `test` = `vitest run`, `tauri` = `tauri`, `app:dev` = `tauri dev`,
  `app:build` = `tauri build`, `web` = `vite --host 0.0.0.0`.
- [desktop/package.json:dependencies] — `@tauri-apps/api` ^2.12.4,
  `@tauri-apps/plugin-dialog` ^2.7.3, `@tauri-apps/plugin-fs` ^2.5.2,
  `@tauri-apps/plugin-notification` ^2.8.0, `@tauri-apps/plugin-opener`
  ^2.7.2, `@tauri-apps/plugin-os` ^2.4.0, `lucide-react` ^0.545.0,
  `react` ^19.2.0, `react-dom` ^19.2.0, `zustand` ^5.0.8,
  `@fontsource/{dm-mono,instrument-sans,schibsted-grotesk}`.
- [desktop/package.json:devDependencies] — `@tauri-apps/cli` ^2.12.4,
  `@types/react` ^19.2.0, `@types/react-dom` ^19.2.0,
  `@vitejs/plugin-react` ^5.0.4, `typescript` ^5.9.3, `vite` ^7.1.9,
  `vitest` ^3.2.7.
- [desktop/vite.config.ts:server] — 개발 서버는 `127.0.0.1:1420`, 포트 고정
  (`strictPort: true`), `clearScreen: false`.
- [desktop/vite.config.ts:envPrefix] — `["VITE_", "TAURI_"]`.
- [desktop/vite.config.ts:build] — `target: "es2022"`, `sourcemap: false`,
  `chunkSizeWarningLimit: 900`.
- [desktop/tsconfig.json:compilerOptions] — `strict: true`,
  `noUnusedLocals: true`, `noUnusedParameters: true`,
  `noFallthroughCasesInSwitch: true`, `jsx: "react-jsx"`,
  `moduleResolution: "bundler"`, `isolatedModules: true`, `noEmit: true`.
  `include` 는 `["src"]` 뿐이라 Rust 쪽은 타입 검사에 들어가지 않습니다.
- [desktop/index.html:root] — `#root` 마운트 지점. 진입 스크립트는
  `/src/main.tsx`.
- [desktop/src-tauri/Cargo.toml:package] — 셸 크레이트 `llack` v0.2.0,
  edition 2021, `rust-version = "1.77"`.

## Subdirectories & System Boundaries

- **src** — [./src/README.md](./src/README.md) — 앱 셸. 모든 화면을 배선하고
  키보드·리사이즈를 처리합니다.
- **src/components** —
  [./src/components/README.md](./src/components/README.md) — 화면 컴포넌트 28개.
  스토어와 `lib/api` 를 통해 상태·네트워크에 닿습니다.
- **src/lib** — [./src/lib/README.md](./src/lib/README.md) — REST 클라이언트,
  도메인 타입, 포맷터, Tauri 셸 브리지, WebSocket 클라이언트.
- **src/store** — [./src/store/README.md](./src/store/README.md) — 단일 Zustand
  스토어. 세션·대화·보드 상태와 모든 액션.
- **src-tauri** — [./src-tauri/README.md](./src-tauri/README.md) — 셸 크레이트
  매니페스트 (`Cargo.toml`, `build.rs`, `tauri.conf.json`).
- **src-tauri/src** — [./src-tauri/src/README.md](./src-tauri/src/README.md) —
  셸 코어. `api`/`commands`/`error`/`state` 모듈과 Tauri 커맨드 5개.

## Global Invariants

- [desktop/vite.config.ts:envPrefix] — 환경변수는 `VITE_` 또는 `TAURI_` 접두사가
  있어야 웹뷰 번들에 들어갑니다.
- [desktop/tsconfig.json:compilerOptions] — `strict` 를 켜 두었으므로
  `npm run typecheck` 는 타입 오류를 빌드 전에 잡아 냅니다.
- [desktop/src-tauri/src/lib.rs:generate_handler!] — 웹뷰에 노출되는 Tauri
  커맨드는 정확히 5개입니다: `app_info`, `notify`, `set_window_theme`,
  `open_external`, `save_file`. 셸이 다른 명령을 새로 열면 웹뷰 계약이
  달라집니다.
- [desktop/src-tauri/tauri.conf.json:app.security.csp] — CSP가 구조적으로
  제한적입니다. `script-src` 은 `'self'` 뿐이고 `object-src`/`form-action` 은
  `'none'`. 유일한 완화는 `style-src` 의 `'unsafe-inline'` 입니다.
- [desktop/src-tauri/tauri.conf.json:app.withGlobalTauri] — 전역 Tauri API는
  웹뷰에 노출되지 않습니다.
- [desktop/src/lib/api.ts:request] — 401 은 토큰을 한 번 교환한 뒤 **한 번만**
  재시도합니다.
- [desktop/src/store/useStore.ts:markRead] — 읽음 표시는 WebSocket 과 REST 중
  정확히 하나만 갑니다.
- [desktop/src-tauri/src/lib.rs:try_run] — `.on_window_event(...)` 핸들러는
  `try_run` 안에서 등록됩니다. 창 기하 기록은 라벨이 `"main"` 인 창에서만.
  방(pop-out) 창이 워크스페이스 창을 움직이지 못하게 합니다.

## Global Side Effects

- **네트워크** — 웹뷰는 `desktop/src/lib/api.ts` 로 `${API_BASE}/api/v1` 에
  접근하고, 셸은 `desktop/src-tauri/src/api.rs` 로 `/health` 와
  `/api/v1/channels/{id}` 만 호출합니다. 셸의 클라이언트는 rustls TLS 를 쓰고
  openssl 없이 빌드됩니다.
- **실시간** — [desktop/src/lib/ws.ts:Realtime] 가
  `${API_BASE}`(http→ws)/api/v1/ws?token=… 로 붙습니다. 지수 백오프(최대 10초)
  로 재연도하고, 4401 코드 뒤에는 재시도하지 않습니다.
- **디스크** — [desktop/src/lib/settings.ts:setSettings] 가 설정을
  localStorage `"llack.settings"` 에 씁니다(옛 키 `"llack.theme"` 마이그레이션).
  [desktop/src/lib/api.ts:tokens] 가 `"llack.access"` / `"llack.refresh"` 를
  쌍으로 씁니다. 셸은 창 기하를 `app_config_dir()/window-state.json` 에 씁니다.
- **OS 알림** — [desktop/src/lib/desktop.ts:notify] 가 권한을 확인한 뒤
  알림을 띄웁니다. `settings.notifications` 가 꺼져 있거나 브라우저 빌드이면
  아무것도 하지 않습니다.
- **네이티브 창** — [desktop/src-tauri/src/commands.rs:set_window_theme] 이
  웹뷰 테마를 바꾸고, [desktop/src/lib/popout.ts:openRoomWindow] 이 방 창을
  새로 만들거나 기존 창에 포커스를 줍니다.
- **빌드 산출물** — `npm run build` 는 `tsc --noEmit` 후 `vite build` 로
  `dist/` 를 만들고, `tauri build` 는 이를 커스텀 프로토콜로 번들합니다.

## System Verification

- Run: `npm test` — `desktop/` 에서 실행. vitest 가 4개 파일 26개 테스트를
  돕니다 (`src/lib/api.test.ts`, `src/lib/gantt.test.ts`,
  `src/lib/keys.test.ts`, `src/store/useStore.test.ts`).
- Run: `npm run typecheck` — `desktop/` 에서 실행 (`tsc --noEmit`).
  저장소 루트에서는 `make lint` 로, `make build` 로 전체 빌드를 돌립니다.
- Run: `cargo test` — `desktop/src-tauri/` 에서 실행. `llack_lib` 단위 테스트
  5개.
