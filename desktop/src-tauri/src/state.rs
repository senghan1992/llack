//! Application state shared by every Tauri command.
//!
//! The API client and realtime handle only exist once the user has chosen a
//! server, so both live behind an `RwLock<Option<..>>` rather than being
//! constructed at launch.

use std::path::PathBuf;
use std::sync::Arc;

use llack_core::error::{Error, Result};
use llack_core::session::TokenStore;
use llack_core::{ApiClient, ApiConfig, Cache, RealtimeHandle, Session, SyncEngine};
use parking_lot::RwLock;

pub struct AppState {
    pub cache: Arc<Cache>,
    pub token_store: Arc<dyn TokenStore>,
    inner: RwLock<Connected>,
    pub data_dir: PathBuf,
    /// The agent, once the window exists.
    ///
    /// Late-initialised because the approval notifier needs an `AppHandle`, and
    /// `AppState` is built before the window is. `None` means the panel is
    /// simply unavailable — every command that needs it says so rather than
    /// unwrapping.
    agent: RwLock<Option<Arc<llack_core::agent::AgentEngine>>>,
}

#[derive(Default)]
struct Connected {
    api: Option<Arc<ApiClient>>,
    session: Option<Arc<Session>>,
    sync: Option<Arc<SyncEngine>>,
    realtime: Option<RealtimeHandle>,
    /// The workspace the UI is currently showing.
    active_workspace_id: Option<String>,
    server_url: Option<String>,
}

impl AppState {
    pub fn new(data_dir: PathBuf, token_store: Arc<dyn TokenStore>) -> Result<Self> {
        std::fs::create_dir_all(&data_dir)
            .map_err(|e| Error::Cache(format!("could not create {}: {e}", data_dir.display())))?;
        let cache = Arc::new(Cache::open(data_dir.join("cache.sqlite3"))?);
        Ok(Self {
            cache,
            token_store,
            inner: RwLock::new(Connected::default()),
            data_dir,
            agent: RwLock::new(None),
        })
    }

    /// Point the client at a server. Called on first launch and on sign-in.
    pub fn connect(&self, server_url: &str, device_name: Option<String>) -> Result<Arc<ApiClient>> {
        let mut config = ApiConfig::new(server_url);
        if let Some(name) = device_name {
            config = config.with_device_name(name);
        }
        // The account key is the server URL, so one machine can hold
        // credentials for several Llack deployments side by side.
        let session = Arc::new(Session::new(
            self.token_store.clone(),
            config.base_url.clone(),
        ));
        session.restore()?;

        let api = Arc::new(ApiClient::new(config, session.clone())?);

        let mut inner = self.inner.write();
        inner.api = Some(api.clone());
        inner.session = Some(session);
        inner.server_url = Some(server_url.to_string());
        inner.sync = None;
        Ok(api)
    }

    /// The path policy context for this machine.
    ///
    /// No roots: nothing here is a session the user granted the agent, so every
    /// path is judged on the deny list alone. Used by `upload_file`, which
    /// reads an arbitrary absolute path the webview handed it.
    pub fn path_context(&self) -> llack_core::agent::policy::SessionContext {
        llack_core::agent::policy::SessionContext {
            tainted: false,
            roots: Vec::new(),
            home: dirs_home(),
            app_data_dir: self.data_dir.clone(),
        }
    }

    pub fn api(&self) -> Result<Arc<ApiClient>> {
        self.inner
            .read()
            .api
            .clone()
            .ok_or_else(|| Error::Config("no server configured yet".into()))
    }

    pub fn session(&self) -> Result<Arc<Session>> {
        self.inner
            .read()
            .session
            .clone()
            .ok_or_else(|| Error::Config("no server configured yet".into()))
    }

    pub fn server_url(&self) -> Option<String> {
        self.inner.read().server_url.clone()
    }

    /// Build the sync engine once the signed-in user is known.
    pub fn install_sync(&self, user_id: &str) -> Result<Arc<SyncEngine>> {
        let api = self.api()?;
        let engine = Arc::new(SyncEngine::new(self.cache.clone(), api, user_id));
        self.inner.write().sync = Some(engine.clone());
        // The agent learns who it belongs to here rather than in each of the
        // three sign-in paths (resume, login, register). Its keychain accounts
        // and its session rows are all keyed by user id, so a missed call would
        // be an agent that silently reads another account's settings.
        if let Ok(agent) = self.agent() {
            agent.set_user(user_id);
        }
        Ok(engine)
    }

    pub fn sync(&self) -> Result<Arc<SyncEngine>> {
        self.inner
            .read()
            .sync
            .clone()
            .ok_or_else(|| Error::Unauthenticated("not signed in".into()))
    }

    pub fn set_realtime(&self, handle: RealtimeHandle) {
        self.inner.write().realtime = Some(handle);
    }

    pub fn realtime(&self) -> Result<RealtimeHandle> {
        self.inner
            .read()
            .realtime
            .clone()
            .ok_or_else(|| Error::Realtime("realtime is not running".into()))
    }

    pub fn take_realtime(&self) -> Option<RealtimeHandle> {
        self.inner.write().realtime.take()
    }

    pub fn set_active_workspace(&self, workspace_id: Option<String>) {
        self.inner.write().active_workspace_id = workspace_id;
    }

    pub fn active_workspace(&self) -> Option<String> {
        self.inner.read().active_workspace_id.clone()
    }

    /// Alias used by the agent commands, which read it per call rather than
    /// caching it — the panel can be open across a workspace switch.
    pub fn active_workspace_id(&self) -> Option<String> {
        self.active_workspace()
    }

    // ── The agent ────────────────────────────────────────────────────────

    pub fn install_agent(&self, engine: Arc<llack_core::agent::AgentEngine>) {
        *self.agent.write() = Some(engine);
    }

    pub fn agent(&self) -> Result<Arc<llack_core::agent::AgentEngine>> {
        self.agent
            .read()
            .clone()
            .ok_or_else(|| Error::Other("에이전트를 사용할 수 없습니다.".into()))
    }

    /// Tear down everything user-specific. Called on sign-out.
    ///
    /// The agent goes first. It holds the provider key in the keychain, live
    /// approval grants in memory, and pending prompts on screen; clearing the
    /// message cache while an approved `host.exec` is still in flight would
    /// leave the most dangerous state behind and the least dangerous state
    /// gone.
    pub fn reset(&self) -> Result<()> {
        if let Ok(agent) = self.agent() {
            // A failure here is reported but does not stop the sign-out: a user
            // who pressed sign-out must end up signed out.
            if let Err(error) = agent.clear_user() {
                tracing::warn!(%error, "could not fully clear agent state on sign-out");
            }
        }
        if let Some(handle) = self.take_realtime() {
            let _ = handle.shutdown();
        }
        self.cache.clear()?;
        let mut inner = self.inner.write();
        inner.sync = None;
        inner.active_workspace_id = None;
        Ok(())
    }
}

/// The user's home directory, without taking a dependency for one lookup.
///
/// Returning `None` is safe: the home-relative rules simply do not fire, and
/// every absolute deny rule still does. It is not safe to *guess* — a wrong
/// home would make `~/.ssh` look like an ordinary directory.
fn dirs_home() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        std::env::var_os("USERPROFILE")
            .map(PathBuf::from)
            .or_else(|| {
                let drive = std::env::var_os("HOMEDRIVE")?;
                let path = std::env::var_os("HOMEPATH")?;
                Some(PathBuf::from(drive).join(path))
            })
    }
    #[cfg(not(windows))]
    {
        std::env::var_os("HOME").map(PathBuf::from)
    }
}
