//! 창을 닫아도 남아 있어야 하는 것.
//!
//! 지금은 두 가지뿐이다.
//!   * API 주소 — 프론트엔드가 어디에 붙어야 하는지.
//!   * 창 크기/위치 — 다음에 띄울 때 같은 자리에서 열리도록.
//!
//! 창 상태는 앱 설정 디렉터리에 `window-state.json` 으로 저장한다. 저장에
//! 실패해도 앱은 계속 돌아간다(그냥 다음에 기본 위치로 열린다).

use std::fs;
use std::path::PathBuf;
use std::sync::RwLock;

use serde::{Deserialize, Serialize};

use crate::api::ApiClient;

/// 마지막으로 창을 닫았을 때의 위치와 크기(논리 픽셀).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct WindowState {
    pub width: f64,
    pub height: f64,
    pub x: Option<i32>,
    pub y: Option<i32>,
}

impl Default for WindowState {
    fn default() -> Self {
        Self {
            width: 1280.0,
            height: 860.0,
            x: None,
            y: None,
        }
    }
}

/// 앱이 살아 있는 동안 함께 들고 있는 상태.
pub struct AppState {
    api_base: RwLock<String>,
    window: RwLock<WindowState>,
    client: Option<ApiClient>,
    store: RwLock<Option<PathBuf>>,
}

impl AppState {
    /// API 주소로 시작하는 상태를 만든다. 주소가 잘못되면 클라이언트만 없이
    /// 동작한다(앱 자체는 뜨고, API 관련 기능만 조용히 실패한다).
    pub fn new(api_base: impl Into<String>) -> Self {
        let api_base = api_base.into();
        let client = match ApiClient::new(&api_base) {
            Ok(client) => Some(client),
            Err(err) => {
                tracing::warn!(?err, "API 주소를 사용할 수 없습니다");
                None
            }
        };

        Self {
            api_base: RwLock::new(api_base),
            window: RwLock::new(WindowState::default()),
            client,
            store: RwLock::new(None),
        }
    }

    /// 상태 파일을 정한다. 파일이 있으면 저장된 창 상태를 읽어온다.
    pub fn with_store(self, path: PathBuf) -> Self {
        if let Some(saved) = read_window_state(&path) {
            *self.window.write().unwrap_or_else(|err| err.into_inner()) = saved;
        }
        *self.store.write().unwrap_or_else(|err| err.into_inner()) = Some(path);
        self
    }

    /// 현재 API 주소.
    pub fn api_base(&self) -> String {
        self.api_base
            .read()
            .unwrap_or_else(|err| err.into_inner())
            .clone()
    }

    /// API 클라이언트. 주소가 잘못된 상태면 `None`.
    /// (연결 풀을 그대로 쓰기 위해 복사해 건넨다 — `reqwest::Client` 는 싸게 복사된다.)
    pub fn client(&self) -> Option<ApiClient> {
        self.client.clone()
    }

    /// 기억해 둔 창 상태.
    pub fn window_state(&self) -> WindowState {
        *self.window.read().unwrap_or_else(|err| err.into_inner())
    }

    /// 창 상태를 갱신한다(저장까지).
    pub fn set_window_state(&self, state: WindowState) {
        *self.window.write().unwrap_or_else(|err| err.into_inner()) = state;
    }

    /// 창 상태를 파일에 저장한다. 실패해도 앱은 계속 동작한다.
    pub fn save_window_state(&self) {
        let path = self
            .store
            .read()
            .unwrap_or_else(|err| err.into_inner())
            .clone();
        let Some(path) = path else {
            return;
        };
        let state = self.window_state();

        if let Some(parent) = path.parent() {
            if let Err(err) = fs::create_dir_all(parent) {
                tracing::warn!(?err, path = %parent.display(), "설정 디렉터리를 만들지 못했습니다");
                return;
            }
        }

        match serde_json::to_vec_pretty(&state) {
            Ok(bytes) => {
                if let Err(err) = fs::write(&path, bytes) {
                    tracing::warn!(?err, path = %path.display(), "창 상태를 저장하지 못했습니다");
                }
            }
            Err(err) => tracing::warn!(?err, "창 상태를 직렬화하지 못했습니다"),
        }
    }
}

/// 저장된 창 상태를 읽는다. 없거나 깨졌으면 `None`.
fn read_window_state(path: &PathBuf) -> Option<WindowState> {
    let bytes = fs::read(path).ok()?;
    match serde_json::from_slice(&bytes) {
        Ok(state) => Some(state),
        Err(err) => {
            tracing::warn!(?err, path = %path.display(), "저장된 창 상태를 읽지 못했습니다");
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn window_state_survives_a_restart() {
        let dir = std::env::temp_dir().join(format!("llack-state-{}", std::process::id()));
        let path = dir.join("window-state.json");

        let state = AppState::new("http://127.0.0.1:8000").with_store(path.clone());
        let mut saved = state.window_state();
        saved.width = 1000.0;
        saved.height = 700.0;
        saved.x = Some(120);
        saved.y = Some(80);
        state.set_window_state(saved);
        state.save_window_state();

        let restored = AppState::new("http://127.0.0.1:8000").with_store(path);
        let window = restored.window_state();
        assert_eq!(window.width, 1000.0);
        assert_eq!(window.height, 700.0);
        assert_eq!(window.x, Some(120));
        assert_eq!(window.y, Some(80));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_missing_store_leaves_the_defaults_alone() {
        let state = AppState::new("http://127.0.0.1:8000")
            .with_store(std::env::temp_dir().join("llack-state-does-not-exist.json"));
        assert_eq!(state.window_state(), WindowState::default());
    }
}
