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
        let session = Arc::new(Session::new(self.token_store.clone(), config.base_url.clone()));
        session.restore()?;

        let api = Arc::new(ApiClient::new(config, session.clone())?);

        let mut inner = self.inner.write();
        inner.api = Some(api.clone());
        inner.session = Some(session);
        inner.server_url = Some(server_url.to_string());
        inner.sync = None;
        Ok(api)
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

    /// Tear down everything user-specific. Called on sign-out.
    pub fn reset(&self) -> Result<()> {
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
