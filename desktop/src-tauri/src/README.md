# llack 셸 코어 (src-tauri/src)

## Overview

Tauri 2 데스크톱 셸(`llack` 크레이트, lib 이름 `llack_lib`)의 Rust 구현부입니다.
셸은 화면을 그리지 않습니다. 그 아래에서 네 가지만 담당합니다.

- 네이티브 창(크기·위치 기억 포함)
- OS 알림
- 외부 브라우저로 링크 열기
- 웹뷰에 노출하지 않는 요청을 위한 셸 자체 HTTP 클라이언트

에이전트 · 스크린캡처 · 키체인 · 딥링크 · 트레이 · 미니앱 패널은 없습니다.

모듈 구성은 [desktop/src-tauri/src/lib.rs:mod] 에서 네 개로 고정됩니다 —
`api`, `commands`, `error`, `state`. 네 모듈 모두 crate 내부 private 이며
`pub mod` 재노출은 없습니다.

## Interface

### `lib.rs` — 앱 진입점과 창/알림 수명주기

- [desktop/src-tauri/src/lib.rs:run] — 공개 진입점. `try_run()` 실패 시 stderr로
  출력하고 `std::process::exit(1)`.
- [desktop/src-tauri/src/lib.rs:generate_handler!] — 등록된 Tauri 커맨드 목록.
  정확히 5개: `commands::app_info`, `commands::notify`, `commands::set_window_theme`,
  `commands::open_external`, `commands::save_file`.
- [desktop/src-tauri/src/lib.rs:NOTIFY_EVENT] — `"llack://notify"`. 프런트엔드가
  셸에 OS 알림을 요청하는 이벤트 이름.
- [desktop/src-tauri/src/lib.rs:WINDOW_STATE_FILE] — `"window-state.json"`.
  `app_config_dir()` 아래에 저장되는 창 기하 파일명.
- [desktop/src-tauri/src/lib.rs:PROBE_TIMEOUT] — `Duration::from_secs(6)`.
  시작 시 API 헬스 체크 상한.
- [desktop/src-tauri/src/lib.rs:NotifyEvent] — `llack://notify` 페이로드 구조체.
  `title`/`body`/`channel`/`channel_id`/`sound` 필드는 모두 `#[serde(default)]`.
- [desktop/src-tauri/src/main.rs:main] — 바이너리 진입점. `llack_lib::run()` 호출.

### `commands.rs` — 웹뷰에 노출되는 커맨드

- [desktop/src-tauri/src/commands.rs:app_info] — `#[tauri::command]`.
  `AppInfo { version, api_base, os, tauri }` 반환. `version`은 앱 패키지 정보,
  `api_base`는 `AppState::api_base()`, `os`는 `tauri_plugin_os::platform()`.
- [desktop/src-tauri/src/commands.rs:notify] — `#[tauri::command]`.
  `NotificationPayload { title, body, sound }`를 받아 OS 알림을 띄웁니다.
- [desktop/src-tauri/src/commands.rs:set_window_theme] — `#[tauri::command]`.
  `mode`가 `"light"`/`"dark"`일 때만 웹뷰 창 테마를 바꿉니다.
- [desktop/src-tauri/src/commands.rs:open_external] — `#[tauri::command]`.
  기본 브라우저로 URL을 엽니다.
- [desktop/src-tauri/src/commands.rs:save_file] — `#[tauri::command]`.
  `x-llack-dir` / `x-llack-name` 헤더와 raw 바디로 디스크에 쓰고, 쓴 절대 경로를
  `String`으로 반환합니다.
- [desktop/src-tauri/src/commands.rs:AppInfo], [desktop/src-tauri/src/commands.rs:NotificationPayload]
  — 커맨드 입출력 구조체.

### `api.rs` — 셸 전용 HTTP 클라이언트

- [desktop/src-tauri/src/api.rs:DEFAULT_API_BASE] — `"http://127.0.0.1:8000"`.
  `LLACK_API_BASE`가 없을 때의 기본 백엔드 주소.
- [desktop/src-tauri/src/api.rs:API_PREFIX] — `"/api/v1"`.
- [desktop/src-tauri/src/api.rs:REQUEST_TIMEOUT] — `Duration::from_secs(5)`.
- [desktop/src-tauri/src/api.rs:ApiClient] — `base: Url`, `http: Client`,
  `token: Option<String>` (전부 private).
  - [desktop/src-tauri/src/api.rs:ApiClient::new] — `LLACK_API_TOKEN` 환경변수에서
    bearer 토큰을 읽습니다.
  - [desktop/src-tauri/src/api.rs:ApiClient::base_url], [desktop/src-tauri/src/api.rs:ApiClient::endpoint]
  - [desktop/src-tauri/src/api.rs:ApiClient::health] — `GET {base}/health`.
  - [desktop/src-tauri/src/api.rs:ApiClient::channel_label] —
    `GET {base}/api/v1/channels/{id}` 에서 표시용 라벨을 뽑습니다.
- [desktop/src-tauri/src/api.rs:ApiError] — `InvalidBase(String)` / `Request(reqwest::Error)`
  / `Status(StatusCode)` / `Decode(String)`.

### `error.rs` — 프런트엔드로 나가는 에러 형태

- [desktop/src-tauri/src/error.rs:Error] — `InvalidUrl` / `UnsupportedScheme` /
  `Notification` / `Theme` / `Api` / `File` / `Internal`.
- [desktop/src-tauri/src/error.rs:Error::code] — 변형별 기계 판독 가능한 코드
  (`invalid_url`, `unsupported_scheme`, `notification_failed`, `theme_failed`,
  `api_error`, `file_write_failed`, `internal`).
- [desktop/src-tauri/src/error.rs:ErrorPayload] — `{ code: &'static str, message: String }`.
- [desktop/src-tauri/src/error.rs:Serialize] — `Error`는 `payload()`를 통해
  `{code, message}` 두 필드만 직렬화합니다.

### `state.rs` — 앱 상태와 창 기하 저장

- [desktop/src-tauri/src/state.rs:AppState] — `api_base`, `window`, `client`, `store`
  네 개의 `RwLock`/Option 필드(private).
  - [desktop/src-tauri/src/state.rs:AppState::new] — 잘못된 base여도 생성은
    실패하지 않고 `client: None`으로 degrade 합니다.
  - [desktop/src-tauri/src/state.rs:AppState::with_store] — 저장 경로 설정과
    저장된 창 상태 로드.
  - [desktop/src-tauri/src/state.rs:AppState::api_base], [desktop/src-tauri/src/state.rs:AppState::client],
    [desktop/src-tauri/src/state.rs:AppState::window_state],
    [desktop/src-tauri/src/state.rs:AppState::set_window_state],
    [desktop/src-tauri/src/state.rs:AppState::save_window_state]
- [desktop/src-tauri/src/state.rs:WindowState] — `{ width, height, x, y }`.
  `Default`는 1280×860, 위치는 `None`.

## Invariants

- [desktop/src-tauri/src/api.rs:normalize_base] — `http`/`https` 스킴만 허용하고,
  빈 문자열은 `ApiError::InvalidBase("API 주소가 비어 있습니다")`로 거절합니다.
  `://` 이 없으면 `http://` 를 붙이고, base 경로가 이미 `/api/v1` 로 끝나면
  그 접미사를 잘라 접두사가 두 번 붙지 않게 합니다.
- [desktop/src-tauri/src/api.rs:ApiClient::new] — bearer 토큰은 오직
  `LLACK_API_TOKEN` 에서 나오고, trim 후 빈 문자열이면 토큰 없음으로 취급합니다.
  HTTP 클라이언트는 `REQUEST_TIMEOUT`(5초)과 `Llack/<CARGO_PKG_VERSION>` UA를 씁니다.
- [desktop/src-tauri/src/api.rs:ApiClient::channel_label] — 채널 id는 경로 세그먼트로
  퍼센트 인코딩되고, 라벨 키는 `name` → `slug` → `display_name` → `title` 순으로
  처음 비어있지 않은 문자열 값을 씁니다.
- [desktop/src-tauri/src/commands.rs:open_external] — `http`/`https`만 열고,
  그 외 스킴은 `Error::UnsupportedScheme`, 파싱 실패는 `Error::InvalidUrl`입니다.
- [desktop/src-tauri/src/commands.rs:set_window_theme] — `"light"`/`"dark"`만
  허용하고 그 외는 `Error::Theme`입니다.
- [desktop/src-tauri/src/commands.rs:save_file] — `x-llack-dir`/`x-llack-name`
  헤더가 반드시 있어야 하고, `InvokeBody::Json`은 거절하며 `InvokeBody::Raw`만
  받습니다.
- [desktop/src-tauri/src/commands.rs:write_into_folder] — 파일 이름은
  `Path::file_name()` 으로 축약하므로 대상 폴더 밖으로의 `../` 탈출이 불가능합니다.
- [desktop/src-tauri/src/error.rs:Error::code] — 변형→코드 대응은 고정입니다.
  `ApiError` 네 변형은 모두 `Error::Api`로 접혀 코드 `api_error`가 됩니다.
- [desktop/src-tauri/src/state.rs:AppState::api_base] — 모든 `RwLock` 접근은
  `unwrap_or_else(|err| err.into_inner())` 이므로 lock poisoning이 패닉이
  아니라 복구됩니다.
- [desktop/src-tauri/src/state.rs:AppState::save_window_state] — 저장 경로가 없으면
  아무것도 쓰지 않고, 부모 디렉터리는 `fs::create_dir_all` 로 만든 뒤 씁니다.
  실패는 `tracing::warn!` 로만 남고 앱을 죽이지 않습니다.
- [desktop/src-tauri/src/state.rs:read_window_state] — 파일이 없거나 JSON이 깨졌으면
  `None` (패닉 없음).
- [desktop/src-tauri/src/lib.rs:restore_window] — 저장된 크기는
  `width > 0.0 && height > 0.0` 일 때만, 위치는 `x`와 `y`가 모두 `Some`일 때만
  복원합니다.
- [desktop/src-tauri/src/lib.rs:try_run] — `.on_window_event(...)` 핸들러는
  `try_run` 안에서 등록됩니다. 창 기하 기록은 라벨이 `"main"`인 창에서만.
  방(pop-out) 창이 워크스페이스 창을 움직이지 못하게 합니다.
  크기·위치는 `scale_factor`로 나누어 논리 픽셀로 저장하고, 디스크 쓰기는
  `CloseRequested`/`Destroyed` 에서만 합니다.
- [desktop/src-tauri/src/lib.rs:resolve_title] — payload의 제목이 비어 있지 않으면
  그것을 쓰고, 아니면 `channel`, 그래도 없으면 `channel_id`로 채널 이름을
  조회하며, 최종 폴백은 문자열 `"Atrium"` 입니다.
- [desktop/src-tauri/src/lib.rs:probe_api] — 헬스 체크는 `PROBE_TIMEOUT`(6초) 안에
  끝나야 하고, `ApiClient`가 없으면 조사를 중단합니다.

## Side Effects

- [desktop/src-tauri/src/api.rs:ApiClient::new] — `LLACK_API_TOKEN` 환경변수를
  읽고 reqwest `Client`를 만듭니다.
- [desktop/src-tauri/src/api.rs:ApiClient::health] — 외부 HTTP GET `{base}/health`.
- [desktop/src-tauri/src/api.rs:ApiClient::channel_label] — 외부 HTTP GET
  `{base}/api/v1/channels/{id}` (bearer 토큰 첨부).
- [desktop/src-tauri/src/commands.rs:notify] — `tauri_plugin_notification`으로
  네이티브 OS 알림을 표시합니다.
- [desktop/src-tauri/src/commands.rs:set_window_theme] — `window.set_theme(...)` 호출.
- [desktop/src-tauri/src/commands.rs:open_external] — `tauri_plugin_opener`의
  `open_url`로 기본 브라우저를 엽니다.
- [desktop/src-tauri/src/commands.rs:save_file] — 디스크에 파일을 쓰고 절대 경로를
  반환합니다.
- [desktop/src-tauri/src/commands.rs:write_into_folder] — `std::fs::write`로
  대상 경로의 기존 파일을 덮어씁니다.
- [desktop/src-tauri/src/lib.rs:try_run] — `.setup(...)` 안에서
  notification/dialog/opener/os 플러그인을 초기화하고 `app.manage(state)`로
  `AppState`를 등록합니다.
- [desktop/src-tauri/src/lib.rs:restore_window] — `window.set_size`/
  `window.set_position`으로 `"main"` 창의 크기와 위치를 복원합니다.
- [desktop/src-tauri/src/lib.rs:listen_for_notifications] — `"llack://notify"`
  리스너를 등록하고 비동기 태스크로 알림을 띄웁니다.
- [desktop/src-tauri/src/lib.rs:probe_api] — 시작 시 백엔드 `/health` 를 한 번
  호출하는 태스크를 띄웁니다.
- [desktop/src-tauri/src/lib.rs:init_tracing] — stderr로 출력하는 전역 tracing
  subscriber를 설치합니다 (`RUST_LOG` 없으면 `"info,llack_lib=debug"`).
- [desktop/src-tauri/src/lib.rs:run] — 시작 실패 시 stderr 출력 후
  `std::process::exit(1)`.
- [desktop/src-tauri/src/state.rs:AppState::with_store] — 디스크의
  `window-state.json` 을 읽어 저장된 기하를 메모리에 받아들입니다.
- [desktop/src-tauri/src/state.rs:AppState::save_window_state] — 부모 디렉터리를
  만들고 pretty-print JSON으로 창 상태를 디스크에 씁니다.

## Verification

- Run: `cargo test` (크레이트 루트 `desktop/src-tauri/` 에서 실행).
  [desktop/src-tauri/src/state.rs:mod tests] 와
  [desktop/src-tauri/src/commands.rs:mod tests] 안의 `#[cfg(test)]` 단위 테스트가
  `#[test]` 함수로 들어 있습니다. 별도 `[[test]]` 타깃이나 `[dev-dependencies]`
  는 선언되어 있지 않습니다. lib 타깃에서 5개가 돕니다 —
  `commands::tests::hex_round_trips`,
  `commands::tests::writes_a_file_into_the_folder`,
  `commands::tests::a_name_cannot_escape_the_folder`,
  `state::tests::a_missing_store_leaves_the_defaults_alone`,
  `state::tests::window_state_survives_a_restart`.
- Build: `cargo build --release`
