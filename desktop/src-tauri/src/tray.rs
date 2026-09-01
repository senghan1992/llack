//! System tray: the affordance that lets the app keep running with its window
//! closed, which is what makes notifications useful at all.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Runtime};

pub fn build<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Llack 열기", true, None::<&str>)?;
    let away = MenuItem::with_id(app, "away", "자리 비움으로 설정", true, None::<&str>)?;
    let dnd = MenuItem::with_id(app, "dnd", "방해 금지", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show, &separator, &away, &dnd, &separator, &quit])?;

    TrayIconBuilder::with_id("main")
        .tooltip("Llack")
        .icon(app.default_window_icon().cloned().ok_or_else(|| {
            tauri::Error::AssetNotFound("no default window icon configured".into())
        })?)
        .menu(&menu)
        // The menu should open on right-click only; a left-click reveals the
        // window, which is what people expect from a chat app's tray icon.
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => reveal_main_window(app),
            "away" => emit_presence(app, "away"),
            "dnd" => emit_presence(app, "dnd"),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                reveal_main_window(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

pub fn reveal_main_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn emit_presence<R: Runtime>(app: &AppHandle<R>, presence: &str) {
    use tauri::Emitter;
    // The UI owns the API call, so it can also update its own indicator.
    let _ = app.emit(
        "llack://presence-request",
        serde_json::json!({ "presence": presence }),
    );
}
