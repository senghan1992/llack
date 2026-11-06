//! Llack 데스크톱 셸.
//!
//! 화면은 프론트엔드(React)가 그리고, 이 셸은 그 밑에서 네 가지만 한다.
//!   · 네이티브 창을 만들고 마지막 위치/크기를 기억한다.
//!   · OS 알림을 띄운다(웹뷰 알림이 아니라 OS 알림 — 포커스 설정을 따른다).
//!   · 메시지의 링크를 기본 브라우저로 연다.
//!   · 셸이 직접 API 를 부를 때 쓰는 HTTP 클라이언트.
//!
//! 에이전트 · 스크린캡처 · 키체인 · 딥링크 · 트레이 · 미니앱 패널은 없다.
//! 필요하면 여기 아니라 프론트엔드에 두는 게 맞다.

mod api;
mod commands;
mod error;
mod state;

use std::time::Duration;

use serde::Deserialize;
use tauri::{AppHandle, Listener, Manager, WindowEvent};
use tauri_plugin_notification::NotificationExt;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

use crate::api::DEFAULT_API_BASE;
use crate::state::AppState;

/// 프론트엔드가 네이티브 알림을 요청할 때 쓰는 이벤트 이름.
const NOTIFY_EVENT: &str = "llack://notify";

/// 창 상태가 저장되는 파일 이름(앱 설정 디렉터리 아래).
const WINDOW_STATE_FILE: &str = "window-state.json";

/// 앱이 뜰 때 하는 연결 확인의 상한 시간.
const PROBE_TIMEOUT: Duration = Duration::from_secs(6);

/// 앱을 띄운다.
pub fn run() {
    if let Err(err) = try_run() {
        eprintln!("Llack 데스크톱 셸을 실행하지 못했습니다: {err:?}");
        std::process::exit(1);
    }
}

/// 앱을 띄우되, 실패는 에러로 돌려준다.
fn try_run() -> anyhow::Result<()> {
    init_tracing();

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            let api_base =
                std::env::var("LLACK_API_BASE").unwrap_or_else(|_| DEFAULT_API_BASE.to_string());
            let mut state = AppState::new(api_base);
            if let Ok(dir) = app.path().app_config_dir() {
                state = state.with_store(dir.join(WINDOW_STATE_FILE));
            }
            app.manage(state);

            let handle = app.handle().clone();
            restore_window(&handle);
            listen_for_notifications(&handle);
            probe_api(&handle);

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::app_info,
            commands::notify,
            commands::set_window_theme,
            commands::open_external,
            commands::save_file,
        ])
        .on_window_event(|window, event| {
            // Only the main window's geometry is remembered. A room window
            // that opens and closes must not move the workspace window.
            if window.label() != "main" {
                return;
            }
            let state = window.state::<AppState>();
            let scale = window.scale_factor().unwrap_or(1.0);

            match event {
                WindowEvent::Resized(size) => {
                    let mut saved = state.window_state();
                    saved.width = size.width as f64 / scale;
                    saved.height = size.height as f64 / scale;
                    state.set_window_state(saved);
                }
                WindowEvent::Moved(position) => {
                    let mut saved = state.window_state();
                    saved.x = Some((position.x as f64 / scale).round() as i32);
                    saved.y = Some((position.y as f64 / scale).round() as i32);
                    state.set_window_state(saved);
                }
                WindowEvent::CloseRequested { .. } => state.save_window_state(),
                WindowEvent::Destroyed => state.save_window_state(),
                _ => {}
            }
        })
        .run(tauri::generate_context!())?;

    Ok(())
}

/// 로그를 stderr 로 보낸다. `RUST_LOG` 로 조정한다.
fn init_tracing() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,llack_lib=debug"));
    tracing_subscriber::fmt().with_env_filter(filter).init();
}

/// 마지막에 닫았을 때의 위치/크기로 창을 되살린다.
fn restore_window(handle: &AppHandle) {
    let Some(window) = handle.get_webview_window("main") else {
        return;
    };

    let saved = handle.state::<AppState>().window_state();
    if saved.width > 0.0 && saved.height > 0.0 {
        let size = tauri::LogicalSize::new(saved.width, saved.height);
        if let Err(err) = window.set_size(size) {
            warn!(?err, "창 크기를 복원하지 못했습니다");
        }
    }
    if let (Some(x), Some(y)) = (saved.x, saved.y) {
        let position = tauri::LogicalPosition::new(x, y);
        if let Err(err) = window.set_position(position) {
            warn!(?err, "창 위치를 복원하지 못했습니다");
        }
    }
}

/// 프론트엔드가 `llack://notify` 이벤트를 밀어 넣으면 OS 알림으로 바꾼다.
/// `notify` 명령을 부르는 것과 같은 결과지만, 알림 제목이 비어 있을 때
/// 채널 이름을 API 에서 물어본다.
fn listen_for_notifications(handle: &AppHandle) {
    let handle = handle.clone();
    let listener = handle.clone();
    listener.listen(NOTIFY_EVENT, move |event| {
        let payload: NotifyEvent = match serde_json::from_str(event.payload()) {
            Ok(payload) => payload,
            Err(err) => {
                warn!(?err, "알림 이벤트를 읽지 못했습니다");
                return;
            }
        };

        let handle = handle.clone();
        tauri::async_runtime::spawn(async move {
            let title = resolve_title(&handle, &payload).await;
            if let Err(err) =
                show_notification(&handle, &title, &payload.body, payload.sound.as_deref())
            {
                warn!(?err, "네이티브 알림을 표시하지 못했습니다");
            }
        });
    });
}

/// 앱이 뜰 때 백엔드 연결을 한 번 확인한다.
fn probe_api(handle: &AppHandle) {
    let handle = handle.clone();
    tauri::async_runtime::spawn(async move {
        let Some(client) = handle.state::<AppState>().client() else {
            return;
        };
        let base = client.base_url().to_string();
        match tokio::time::timeout(PROBE_TIMEOUT, client.health()).await {
            Ok(Ok(())) => info!(%base, "API 서버에 연결되어 있습니다"),
            Ok(Err(err)) => warn!(?err, %base, "API 서버에 연결하지 못했습니다"),
            Err(_) => warn!(%base, "API 서버가 응답하지 않습니다"),
        }
    });
}

/// 알림 제목을 정한다. 프론트엔드가 준 제목을 우선하고, 없으면 채널 이름을 쓴다.
async fn resolve_title(handle: &AppHandle, payload: &NotifyEvent) -> String {
    if let Some(title) = payload
        .title
        .as_deref()
        .filter(|title| !title.trim().is_empty())
    {
        return title.to_string();
    }

    let label = match (payload.channel.as_deref(), payload.channel_id.as_deref()) {
        (Some(channel), _) => Some(channel.to_string()),
        (None, Some(channel_id)) => lookup_channel_label(handle, channel_id).await,
        _ => None,
    };

    label.unwrap_or_else(|| "Llack".to_string())
}

/// 채널 id 로 채널 이름을 물어본다. 못 물어봐도 알림 자체는 계속 나간다.
async fn lookup_channel_label(handle: &AppHandle, channel_id: &str) -> Option<String> {
    let client = handle.state::<AppState>().client()?;
    match client.channel_label(channel_id).await {
        Ok(label) => Some(label),
        Err(err) => {
            warn!(?err, "채널 이름을 확인하지 못했습니다");
            None
        }
    }
}

/// OS 알림을 띄운다.
fn show_notification(
    handle: &AppHandle,
    title: &str,
    body: &str,
    sound: Option<&str>,
) -> Result<(), tauri_plugin_notification::Error> {
    let mut builder = handle.notification().builder().title(title).body(body);

    if let Some(sound) = sound.filter(|sound| !sound.trim().is_empty()) {
        builder = builder.sound(sound);
    }

    builder.show()
}

/// 프론트엔드가 `llack://notify` 로 밀어 넣는 payload.
#[derive(Debug, Deserialize)]
struct NotifyEvent {
    /// 알림 제목. 비어 있으면 채널 이름으로 대신한다.
    #[serde(default)]
    title: Option<String>,
    /// 알림 본문.
    #[serde(default)]
    body: String,
    /// 화면에 보여줄 채널 이름(`#일반`).
    #[serde(default)]
    channel: Option<String>,
    /// 채널 id. 이름 대신 id 로 올 때 API 에서 이름을 물어본다.
    #[serde(default)]
    channel_id: Option<String>,
    /// 알림음 이름.
    #[serde(default)]
    sound: Option<String>,
}
