//! 프론트엔드가 호출할 수 있는 명령.
//!
//! 명령은 "웹뷰가 못 하는 일"만 맡는다. 화면 그리기, 메시지 전송 같은 일은
//! 전부 프론트엔드가 하고, 여기서는 OS 를 건드리는 일만 노출한다.

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, State, WebviewWindow};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;
use url::Url;

use crate::error::Error;
use crate::state::AppState;

/// `app_info` 가 돌려주는 값.
#[derive(Debug, Clone, Serialize)]
pub struct AppInfo {
    /// 앱 버전(`Cargo.toml` 의 version).
    pub version: String,
    /// 셀이 talking 하는 API 주소.
    pub api_base: String,
    /// OS 이름(`linux` / `macos` / `windows`).
    pub os: String,
    /// 이 앱이 Tauri 셸인지. 항상 `true`.
    pub tauri: bool,
}

/// `notify` 가 받는 payload.
#[derive(Debug, Clone, Deserialize)]
pub struct NotificationPayload {
    /// 알림 제목.
    pub title: String,
    /// 알림 본문.
    pub body: String,
    /// 알림음 이름. 없으면 OS 기본 소리를 쓴다.
    #[serde(default)]
    pub sound: Option<String>,
}

/// 앱 정보.
#[tauri::command]
pub fn app_info(app: AppHandle, state: State<'_, AppState>) -> AppInfo {
    AppInfo {
        version: app.package_info().version.to_string(),
        api_base: state.api_base(),
        os: tauri_plugin_os::platform().to_string(),
        tauri: true,
    }
}

/// OS 알림을 띄운다. 웹뷰 안에서 띄우는 알림과 달리 OS 알림 영역에 올라가서
/// 포커스 설정(방해 금지 등)을 그대로 따른다.
#[tauri::command]
pub fn notify(app: AppHandle, payload: NotificationPayload) -> Result<(), Error> {
    let mut builder = app
        .notification()
        .builder()
        .title(&payload.title)
        .body(&payload.body);

    if let Some(sound) = payload.sound.as_deref().filter(|s| !s.trim().is_empty()) {
        builder = builder.sound(sound);
    }

    builder
        .show()
        .map_err(|err| Error::Notification(err.to_string()))
}

/// 창(웹뷰) 테마를 바꾼다. `light` / `dark`.
#[tauri::command]
pub fn set_window_theme(window: WebviewWindow, mode: String) -> Result<(), Error> {
    let theme = match mode.trim().to_ascii_lowercase().as_str() {
        "light" => tauri::Theme::Light,
        "dark" => tauri::Theme::Dark,
        other => return Err(Error::Theme(format!("지원하지 않는 테마입니다: {other}"))),
    };

    window
        .set_theme(Some(theme))
        .map_err(|err| Error::Theme(err.to_string()))
}

/// 메시지에 들어 있는 링크를 기본 브라우저로 연다.
/// `http` / `https` 만 허용하고, 그 밖의 스킴(`file:` · `javascript:` …)은
/// 거부한다.
#[tauri::command]
pub fn open_external(app: AppHandle, url: String) -> Result<(), Error> {
    let parsed = Url::parse(url.trim()).map_err(|err| Error::InvalidUrl(err.to_string()))?;
    match parsed.scheme() {
        "http" | "https" => {}
        other => return Err(Error::UnsupportedScheme(other.to_string())),
    }

    app.opener()
        .open_url(parsed.to_string(), None::<String>)
        .map_err(|err| Error::Internal(err.to_string()))
}

/// 첨부 파일을 지정한 폴더에 저장한다.
///
/// 웹뷰가 파일을 직접 받아 온 뒤 셸에게 바이트를 건넨다 — 그래야 세션
/// 토큰이 웹뷰 밖으로 나가지 않는다. 본문은 그대로(`application/octet-stream`)
/// 오고, 폴더와 파일 이름은 헤더에 담는다. 경로에 한글이 들어갈 수 있어서
/// 16진수로 옮겨 보낸다.
#[tauri::command]
pub fn save_file(request: tauri::ipc::Request) -> Result<String, Error> {
    let dir = header_text(&request, "x-llack-dir")?;
    let name = header_text(&request, "x-llack-name")?;

    let bytes = match request.body() {
        tauri::ipc::InvokeBody::Raw(bytes) => bytes.as_slice(),
        tauri::ipc::InvokeBody::Json(_) => {
            return Err(Error::File("파일 내용이 비어 있습니다".to_string()))
        }
    };

    write_into_folder(&dir, &name, bytes)
}

/// 폴더에 파일을 쓴다. 파일 이름은 경로가 아니라 이름만 쓴다 —
/// `../` 로 폴더 밖으로 나갈 수 없게.
fn write_into_folder(dir: &str, name: &str, bytes: &[u8]) -> Result<String, Error> {
    let safe = std::path::Path::new(name)
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .filter(|name| !name.is_empty())
        .ok_or_else(|| Error::File("파일 이름이 올바르지 않습니다".to_string()))?;

    let target = std::path::Path::new(dir).join(&safe);
    std::fs::write(&target, bytes).map_err(|err| {
        Error::File(format!("{} 저장하지 못했습니다: {err}", target.display()))
    })?;

    Ok(target.to_string_lossy().into_owned())
}

/// 헤더에 담긴 16진수 문자열을 사람이 읽는 글자로 되돌린다.
fn header_text(request: &tauri::ipc::Request, name: &str) -> Result<String, Error> {
    let raw = request
        .headers()
        .get(name)
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| Error::File(format!("{name} 헤더가 없습니다")))?;

    decode_hex(raw).ok_or_else(|| Error::File(format!("{name} 헤더를 읽지 못했습니다")))
}

/// 16진수 문자열을 바이트로 되돌린다.
fn decode_hex(raw: &str) -> Option<String> {
    if raw.len() % 2 != 0 {
        return None;
    }
    let bytes: Option<Vec<u8>> = raw
        .as_bytes()
        .chunks(2)
        .map(|pair| std::str::from_utf8(pair).ok().and_then(|text| u8::from_str_radix(text, 16).ok()))
        .collect();
    String::from_utf8(bytes?).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_a_file_into_the_folder() {
        let dir = std::env::temp_dir().join("llack-save-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = write_into_folder(dir.to_str().unwrap(), "안녕.txt", b"hello")
            .expect("저장해야 합니다");
        assert_eq!(std::fs::read(&path).unwrap(), b"hello");
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn a_name_cannot_escape_the_folder() {
        let dir = std::env::temp_dir().join("llack-save-test-escape");
        std::fs::create_dir_all(&dir).unwrap();
        let path = write_into_folder(dir.to_str().unwrap(), "../escaped.txt", b"x")
            .expect("저장해야 합니다");
        assert_eq!(
            std::path::Path::new(&path).parent(),
            Some(dir.as_path()),
            "폴더 밖으로 나가면 안 됩니다"
        );
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn hex_round_trips() {
        assert_eq!(decode_hex("616263").as_deref(), Some("abc"));
        assert_eq!(decode_hex("eab5").as_deref(), None);
        assert_eq!(decode_hex("ed959c").as_deref(), Some("한"));
        assert_eq!(decode_hex("abc"), None);
    }
}
