//! Llack desktop shell.
//!
//! Thin by design: window and tray lifecycle, the Tauri command surface, and
//! the background realtime task. All the logic those wrap lives in
//! `llack-core`, which has no webview dependency and is unit-tested.

mod agent_commands;
mod commands;
mod keychain;
mod realtime_task;
mod state;
mod tray;

use std::sync::Arc;

use tauri::{Emitter, Manager, WindowEvent};

use crate::keychain::KeychainTokenStore;
use crate::state::AppState;

/// The default server, overridable at runtime by the user and at build time by
/// an integrator shipping a pre-configured binary to their company.
const DEFAULT_SERVER_URL: &str = match option_env!("LLACK_DEFAULT_SERVER_URL") {
    Some(url) => url,
    None => "http://localhost:8000",
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    init_tracing();

    tauri::Builder::default()
        // Must be registered first: it intercepts the second launch before any
        // window is created.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // A second launch should surface the running window, not start a
            // second copy of a chat client.
            tray::reveal_main_window(app);
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."));

            let tokens = KeychainTokenStore::shared();
            let state = Arc::new(AppState::new(data_dir.clone(), tokens.clone())?);

            // The agent is built here rather than in `AppState::new` because
            // its approval notifier needs an `AppHandle`, which does not exist
            // until setup. A failure is logged and swallowed: a machine with no
            // writable data directory should still be a working chat client
            // without an agent panel, not a client that refuses to launch.
            match llack_core::agent::AgentEngine::open(
                data_dir,
                home_dir(),
                tokens,
                Arc::new(agent_commands::PanelNotifier::new(app.handle().clone())),
                llack_core::agent::HostCapabilities::desktop(),
            ) {
                Ok(engine) => state.install_agent(Arc::new(engine)),
                Err(error) => {
                    tracing::warn!(%error, "the agent panel is unavailable");
                }
            }

            app.manage(state);

            tray::build(app.handle())?;

            // `llack://` links (invitations, deep links into a message) arrive
            // here; the UI decides how to route them.
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                let handle = app.handle().clone();
                app.deep_link().on_open_url(move |event| {
                    let urls: Vec<String> =
                        event.urls().iter().map(ToString::to_string).collect();
                    let _ = handle.emit("llack://deep-link", serde_json::json!({ "urls": urls }));
                    tray::reveal_main_window(&handle);
                });
            }

            app.handle().emit(
                "llack://ready",
                serde_json::json!({
                    "default_server_url": DEFAULT_SERVER_URL,
                    "version": env!("CARGO_PKG_VERSION"),
                    "platform": std::env::consts::OS,
                }),
            )?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Closing the window hides it instead of quitting, so
                // notifications keep arriving. Quit is on the tray menu.
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            // connection & auth
            commands::bootstrap,
            commands::login,
            commands::register,
            commands::logout,
            commands::current_user,
            // workspaces
            commands::list_workspaces,
            commands::select_workspace,
            commands::list_workspace_users,
            // channels
            commands::cached_channels,
            commands::refresh_channels,
            commands::browse_channels,
            commands::create_channel,
            commands::open_dm,
            commands::join_channel,
            commands::leave_channel,
            commands::update_membership,
            commands::mark_read,
            // messages
            commands::cached_history,
            commands::refresh_history,
            commands::load_older_messages,
            commands::thread_replies,
            commands::send_message,
            commands::edit_message,
            commands::delete_message,
            commands::toggle_reaction,
            commands::typing,
            // outbox
            commands::pending_messages,
            commands::drain_outbox,
            commands::retry_failed_messages,
            commands::discard_pending_message,
            // search
            commands::search,
            commands::search_messages,
            // files
            commands::upload_file,
            commands::download_file,
            // mini-apps
            commands::list_installed_apps,
            commands::list_available_apps,
            commands::install_app,
            commands::uninstall_app,
            commands::open_app_panel,
            // shell
            commands::set_presence,
            commands::reconnect,
            commands::cache_stats,
            commands::prune_cache,
            // agent — the whole IPC surface the panel has
            agent_commands::agent_provider_status,
            agent_commands::agent_provider_connect,
            agent_commands::agent_provider_disconnect,
            agent_commands::agent_provider_request,
            agent_commands::agent_provider_abort,
            agent_commands::agent_tools,
            agent_commands::agent_sessions,
            agent_commands::agent_open_session,
            agent_commands::agent_focus,
            agent_commands::agent_tool_call,
            agent_commands::agent_resolve_approval,
            agent_commands::agent_cancel,
            agent_commands::agent_pick_root,
            agent_commands::agent_verify_audit,
        ])
        .run(tauri::generate_context!())
        .expect("could not start Llack");
}

fn init_tracing() {
    use tracing_subscriber::{fmt, EnvFilter};

    let filter = EnvFilter::try_from_env("LLACK_LOG")
        .unwrap_or_else(|_| EnvFilter::new("info,llack=debug,llack_core=debug"));
    let _ = fmt().with_env_filter(filter).with_target(true).try_init();
}

/// The user's home directory, for the agent's path policy.
///
/// Duplicated from `state.rs` rather than shared, because the two want
/// different things from a missing value: `state` uses it per upload, this uses
/// it once at startup. Both treat `None` as "the home-relative rules do not
/// fire", which is safe — the absolute deny rules are unaffected.
fn home_dir() -> Option<std::path::PathBuf> {
    #[cfg(windows)]
    {
        std::env::var_os("USERPROFILE").map(std::path::PathBuf::from)
    }
    #[cfg(not(windows))]
    {
        std::env::var_os("HOME").map(std::path::PathBuf::from)
    }
}
