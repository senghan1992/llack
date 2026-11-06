//! 셸이 직접 부르는 HTTP 클라이언트.
//!
//! 웹뷰는 CSP(`connect-src`) 밖으로 나갈 수 없다. 그리고 OS 알림처럼 "창이
//! 아니라 데스크톱이 하는 일"은 어차피 Rust 가 해야 한다. 이 모듈은 그런
//! 요청만 담당한다.
//!
//!   * `health` — 앱이 뜰 때 백엔드가 살아 있는지 한 번 확인한다.
//!   * `channel_label` — 알림 제목에 붙일 채널 이름(`#일반`)을 API 에서
//!     물어본다. 프론트엔드가 이미 이름을 알고 있으면 이 경로는 쓰이지 않는다.
//!
//! 인증 토큰이 필요하면 `LLACK_API_TOKEN` 환경변수로 주입한다. 없으면
//! 인증이 필요한 엔드포인트는 401 로 실패하고, 호출자는 조용히 물러선다.

use std::time::Duration;

use reqwest::{Client, StatusCode};
use url::Url;

/// 기본 API 주소. 프론트엔드 CSP(`connect-src`)와 같은 로컬 백엔드다.
pub const DEFAULT_API_BASE: &str = "http://127.0.0.1:8000";

/// 백엔드 API 프리픽스(`backend/app/core/config.py` 의 `api_prefix` 와 동일).
const API_PREFIX: &str = "/api/v1";

/// 셸이 만드는 요청은 전부 짧게 끝나야 한다(UI 를 막지 않으려고).
const REQUEST_TIMEOUT: Duration = Duration::from_secs(5);

/// API 호출이 실패할 수 있는 이유.
#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("API 주소가 올바르지 않습니다: {0}")]
    InvalidBase(String),

    #[error("요청을 보내지 못했습니다: {0}")]
    Request(#[from] reqwest::Error),

    #[error("서버가 오류를 반환했습니다 (HTTP {0})")]
    Status(StatusCode),

    #[error("응답을 읽을 수 없습니다: {0}")]
    Decode(String),
}

/// API 한 곳만 바라보는 작은 클라이언트.
#[derive(Clone)]
pub struct ApiClient {
    base: Url,
    http: Client,
    token: Option<String>,
}

impl ApiClient {
    /// API 주소로 클라이언트를 만든다. 주소가 잘못되면 `InvalidBase`.
    pub fn new(base: &str) -> Result<Self, ApiError> {
        let base = normalize_base(base)?;
        let http = Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .user_agent(concat!("Llack/", env!("CARGO_PKG_VERSION")))
            .build()?;
        let token = std::env::var("LLACK_API_TOKEN")
            .ok()
            .filter(|token| !token.trim().is_empty());

        Ok(Self { base, http, token })
    }

    /// 정규화된 API 주소.
    pub fn base_url(&self) -> &Url {
        &self.base
    }

    /// base 아래의 절대 주소를 만든다.
    pub fn endpoint(&self, path: &str) -> Result<Url, ApiError> {
        let path = if path.starts_with('/') {
            path.to_string()
        } else {
            format!("/{path}")
        };
        let joined = format!("{}{}", self.base.as_str().trim_end_matches('/'), path);
        Url::parse(&joined).map_err(|err| ApiError::InvalidBase(err.to_string()))
    }

    /// 백엔드가 살아 있는지 확인한다.
    pub async fn health(&self) -> Result<(), ApiError> {
        let response = self.get(self.endpoint("/health")?).send().await?;
        let status = response.status();
        if status.is_success() {
            Ok(())
        } else {
            Err(ApiError::Status(status))
        }
    }

    /// 채널 id 에 해당하는 표시 이름(`#일반` 등)을 가져온다.
    pub async fn channel_label(&self, channel_id: &str) -> Result<String, ApiError> {
        let path = format!("{API_PREFIX}/channels/{}", encode_segment(channel_id));
        let value = self.get_json(&path).await?;
        label_of(&value).ok_or_else(|| ApiError::Decode("채널 이름이 없습니다".to_string()))
    }

    fn get(&self, url: Url) -> reqwest::RequestBuilder {
        let request = self.http.get(url);
        match &self.token {
            Some(token) => request.bearer_auth(token),
            None => request,
        }
    }

    async fn get_json(&self, path: &str) -> Result<serde_json::Value, ApiError> {
        let response = self.get(self.endpoint(path)?).send().await?;
        let status = response.status();
        if !status.is_success() {
            return Err(ApiError::Status(status));
        }
        let text = response.text().await?;
        serde_json::from_str(&text).map_err(|err| ApiError::Decode(err.to_string()))
    }
}

/// 주소 정규화: 스킴이 없으면 http 를 붙이고, 끝의 슬래시를 지운다.
/// 주소에 `/api/v1` 이 이미 붙어 있으면 벗겨낸다(두 번 붙지 않도록).
fn normalize_base(base: &str) -> Result<Url, ApiError> {
    let trimmed = base.trim();
    if trimmed.is_empty() {
        return Err(ApiError::InvalidBase(
            "API 주소가 비어 있습니다".to_string(),
        ));
    }

    let candidate = if trimmed.contains("://") {
        trimmed.to_string()
    } else {
        format!("http://{trimmed}")
    };

    let mut url = Url::parse(&candidate).map_err(|err| ApiError::InvalidBase(err.to_string()))?;
    match url.scheme() {
        "http" | "https" => {}
        other => {
            return Err(ApiError::InvalidBase(format!(
                "지원하지 않는 스킴입니다: {other}"
            )))
        }
    }

    let mut path = url.path().trim_end_matches('/').to_string();
    if path.ends_with(API_PREFIX) {
        path.truncate(path.len() - API_PREFIX.len());
    }
    url.set_path(if path.is_empty() { "/" } else { &path });

    Ok(url)
}

/// URL 한 조각으로 들어가는 값에서 `/` 와 `?` 등을 escape 한다.
fn encode_segment(value: &str) -> String {
    let mut encoded = String::with_capacity(value.len());
    for byte in value.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(byte as char)
            }
            other => encoded.push_str(&format!("%{other:02X}")),
        }
    }
    encoded
}

/// 응답 JSON 에서 채널 이름을 뽑는다(백엔드 스키마가 조금 달라도 버티게).
fn label_of(value: &serde_json::Value) -> Option<String> {
    for key in ["name", "slug", "display_name", "title"] {
        let Some(text) = value.get(key).and_then(|value| value.as_str()) else {
            continue;
        };
        let text = text.trim();
        if !text.is_empty() {
            return Some(text.to_string());
        }
    }
    None
}
