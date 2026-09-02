//! HTTP client for the Llack API.
//!
//! Handles the things every call would otherwise repeat: bearer auth,
//! transparent access-token refresh on 401 (single-flight, so a burst of
//! parallel requests spends the refresh token once), and decoding the server's
//! error envelope into a typed [`Error`].

use std::sync::Arc;
use std::time::Duration;

use reqwest::{Method, StatusCode};
use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::error::{ApiErrorEnvelope, Error, Result};
use crate::models::*;
use crate::session::Session;

/// Refresh this far ahead of expiry, so a token does not lapse mid-flight.
const REFRESH_SKEW_SECONDS: i64 = 60;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Clone)]
pub struct ApiConfig {
    /// Server root, without the API prefix (e.g. `https://llack.acme.com`).
    pub base_url: String,
    pub api_prefix: String,
    pub device: DeviceInfo,
}

impl ApiConfig {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            api_prefix: "/api/v1".into(),
            device: DeviceInfo {
                device_name: None,
                platform: Some(std::env::consts::OS.to_string()),
                app_version: Some(env!("CARGO_PKG_VERSION").to_string()),
            },
        }
    }

    pub fn with_device_name(mut self, name: impl Into<String>) -> Self {
        self.device.device_name = Some(name.into());
        self
    }

    pub fn api_root(&self) -> String {
        format!("{}{}", self.base_url, self.api_prefix)
    }

    /// The WebSocket URL, derived from the HTTP base so operators configure
    /// one address rather than two that can drift apart.
    pub fn websocket_url(&self, token: &str, workspace_id: Option<&str>) -> String {
        let scheme = if self.base_url.starts_with("https://") {
            "wss"
        } else {
            "ws"
        };
        let host = self
            .base_url
            .trim_start_matches("https://")
            .trim_start_matches("http://");
        let mut url = format!(
            "{scheme}://{host}{}/ws?token={}",
            self.api_prefix,
            urlencode(token)
        );
        if let Some(workspace_id) = workspace_id {
            url.push_str(&format!("&workspace_id={}", urlencode(workspace_id)));
        }
        url
    }

    /// Resolve a relative path returned by the API (`/files/<id>/download`)
    /// into an absolute URL.
    pub fn resolve(&self, path: &str) -> String {
        if path.starts_with("http://") || path.starts_with("https://") {
            return path.to_string();
        }
        format!("{}{}", self.api_root(), path)
    }
}

fn urlencode(value: &str) -> String {
    value
        .bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (b as char).to_string()
            }
            other => format!("%{other:02X}"),
        })
        .collect()
}

pub struct ApiClient {
    http: reqwest::Client,
    config: ApiConfig,
    session: Arc<Session>,
}

impl ApiClient {
    pub fn new(config: ApiConfig, session: Arc<Session>) -> Result<Self> {
        let http = reqwest::Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .connect_timeout(CONNECT_TIMEOUT)
            .user_agent(format!("Llack/{}", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| Error::Config(e.to_string()))?;
        Ok(Self {
            http,
            config,
            session,
        })
    }

    pub fn config(&self) -> &ApiConfig {
        &self.config
    }

    pub fn session(&self) -> &Arc<Session> {
        &self.session
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}", self.config.api_root(), path)
    }

    // ── Core request plumbing ───────────────────────────────────────────

    /// Send an authenticated request, refreshing the access token if needed.
    async fn send<B: Serialize + ?Sized, T: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<T> {
        // Proactive refresh: cheaper than provoking a 401 and retrying.
        if self.session.access_token_is_stale(REFRESH_SKEW_SECONDS) {
            self.refresh_access_token().await?;
        }

        let response = self.send_once(method.clone(), path, body).await?;
        if response.status() != StatusCode::UNAUTHORIZED {
            return decode(response).await;
        }

        // A 401 despite a fresh-looking token means the server rejected it
        // (rotated secret, revoked session). One refresh-and-retry, then give up.
        self.refresh_access_token().await?;
        let retried = self.send_once(method, path, body).await?;
        decode(retried).await
    }

    async fn send_once<B: Serialize + ?Sized>(
        &self,
        method: Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<reqwest::Response> {
        let mut request = self.http.request(method, self.url(path));
        if let Some(token) = self.session.access_token() {
            request = request.bearer_auth(token);
        }
        if let Some(body) = body {
            request = request.json(body);
        }
        request.send().await.map_err(Error::from)
    }

    /// Unauthenticated request, for login/register/refresh.
    async fn send_public<B: Serialize + ?Sized, T: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        body: Option<&B>,
    ) -> Result<T> {
        let mut request = self.http.request(method, self.url(path));
        if let Some(body) = body {
            request = request.json(body);
        }
        decode(request.send().await?).await
    }

    /// Exchange the refresh token for a new pair, once per burst.
    async fn refresh_access_token(&self) -> Result<()> {
        let _guard = self.session.refresh_guard().await;

        // Another task may have refreshed while we waited for the lock.
        if !self.session.access_token_is_stale(REFRESH_SKEW_SECONDS) {
            return Ok(());
        }

        let refresh_token = self.session.require_refresh_token()?;
        let tokens: TokenPair = self
            .send_public(
                Method::POST,
                "/auth/refresh",
                Some(&serde_json::json!({ "refresh_token": refresh_token })),
            )
            .await
            .map_err(|err| {
                if err.status() == Some(401) {
                    // The refresh token itself is dead: sign-in required.
                    Error::Unauthenticated(err.to_string())
                } else {
                    err
                }
            })?;
        self.session.adopt(&tokens, None)?;
        Ok(())
    }

    // ── Auth ────────────────────────────────────────────────────────────

    pub async fn login(&self, email: &str, password: &str) -> Result<AuthResponse> {
        let payload = serde_json::json!({
            "email": email,
            "password": password,
            "device": self.config.device,
        });
        let auth: AuthResponse = self
            .send_public(Method::POST, "/auth/login", Some(&payload))
            .await?;
        self.session.adopt(&auth.tokens, Some(auth.user.clone()))?;
        Ok(auth)
    }

    pub async fn register(
        &self,
        email: &str,
        password: &str,
        display_name: &str,
    ) -> Result<AuthResponse> {
        let payload = serde_json::json!({
            "email": email,
            "password": password,
            "display_name": display_name,
            "device": self.config.device,
        });
        let auth: AuthResponse = self
            .send_public(Method::POST, "/auth/register", Some(&payload))
            .await?;
        self.session.adopt(&auth.tokens, Some(auth.user.clone()))?;
        Ok(auth)
    }

    /// Sign out this device. Best-effort: local credentials are cleared even
    /// if the server call fails, so the user is never stuck signed in.
    pub async fn logout(&self) -> Result<()> {
        let server_result = self
            .send::<(), serde_json::Value>(Method::POST, "/auth/logout", None)
            .await;
        self.session.clear()?;
        server_result.map(|_| ())
    }

    pub async fn me(&self) -> Result<User> {
        let user: User = self.send::<(), _>(Method::GET, "/me", None).await?;
        self.session.set_user(user.clone());
        Ok(user)
    }

    /// Bring a restored session back to life by minting an access token.
    pub async fn resume(&self) -> Result<User> {
        self.refresh_access_token().await?;
        self.me().await
    }

    // ── Workspaces ──────────────────────────────────────────────────────

    pub async fn list_workspaces(&self) -> Result<Vec<Workspace>> {
        self.send::<(), _>(Method::GET, "/workspaces", None).await
    }

    pub async fn list_workspace_users(
        &self,
        workspace_id: &str,
        query: Option<&str>,
    ) -> Result<Vec<User>> {
        let mut path = format!("/workspaces/{workspace_id}/users?limit=200");
        if let Some(query) = query {
            path.push_str(&format!("&q={}", urlencode(query)));
        }
        self.send::<(), _>(Method::GET, &path, None).await
    }

    // ── Channels ────────────────────────────────────────────────────────

    pub async fn list_channels(&self, workspace_id: &str) -> Result<Vec<Channel>> {
        self.send::<(), _>(
            Method::GET,
            &format!("/workspaces/{workspace_id}/channels"),
            None,
        )
        .await
    }

    pub async fn browse_channels(
        &self,
        workspace_id: &str,
        query: Option<&str>,
    ) -> Result<Vec<Channel>> {
        let mut path = format!("/workspaces/{workspace_id}/channels/browse");
        if let Some(query) = query {
            path.push_str(&format!("?q={}", urlencode(query)));
        }
        self.send::<(), _>(Method::GET, &path, None).await
    }

    pub async fn get_channel(&self, channel_id: &str) -> Result<Channel> {
        self.send::<(), _>(Method::GET, &format!("/channels/{channel_id}"), None)
            .await
    }

    pub async fn create_channel(
        &self,
        workspace_id: &str,
        name: &str,
        kind: ChannelKind,
        member_ids: &[String],
    ) -> Result<Channel> {
        let payload = serde_json::json!({
            "name": name,
            "kind": kind,
            "member_ids": member_ids,
        });
        self.send(
            Method::POST,
            &format!("/workspaces/{workspace_id}/channels"),
            Some(&payload),
        )
        .await
    }

    /// Get-or-create a DM. Idempotent for the same set of people.
    pub async fn open_dm(&self, workspace_id: &str, user_ids: &[String]) -> Result<Channel> {
        let payload = serde_json::json!({ "user_ids": user_ids });
        self.send(
            Method::POST,
            &format!("/workspaces/{workspace_id}/channels/dm"),
            Some(&payload),
        )
        .await
    }

    /// Rename, retopic or archive a channel. `patch` carries only the fields
    /// to change (`name` / `topic` / `is_archived`) — the server enforces who
    /// may change what, so this stays a passthrough.
    pub async fn update_channel(
        &self,
        channel_id: &str,
        patch: serde_json::Value,
    ) -> Result<Channel> {
        self.send(
            Method::PATCH,
            &format!("/channels/{channel_id}"),
            Some(&patch),
        )
        .await
    }

    pub async fn channel_members(&self, channel_id: &str) -> Result<Vec<ChannelMemberEntry>> {
        self.send::<(), _>(
            Method::GET,
            &format!("/channels/{channel_id}/members"),
            None,
        )
        .await
    }

    /// Returns the ids actually added (already-present ids are skipped).
    pub async fn add_channel_members(
        &self,
        channel_id: &str,
        user_ids: &[String],
    ) -> Result<Vec<String>> {
        let payload = serde_json::json!({ "user_ids": user_ids });
        self.send(
            Method::POST,
            &format!("/channels/{channel_id}/members"),
            Some(&payload),
        )
        .await
    }

    pub async fn remove_channel_member(&self, channel_id: &str, user_id: &str) -> Result<()> {
        self.send::<(), serde_json::Value>(
            Method::DELETE,
            &format!("/channels/{channel_id}/members/{user_id}"),
            None,
        )
        .await
        .map(|_| ())
    }

    pub async fn join_channel(&self, channel_id: &str) -> Result<Channel> {
        self.send::<(), _>(Method::POST, &format!("/channels/{channel_id}/join"), None)
            .await
    }

    pub async fn leave_channel(&self, channel_id: &str) -> Result<()> {
        self.send::<(), serde_json::Value>(
            Method::POST,
            &format!("/channels/{channel_id}/leave"),
            None,
        )
        .await
        .map(|_| ())
    }

    pub async fn mark_read(
        &self,
        channel_id: &str,
        message_id: Option<&str>,
    ) -> Result<ChannelMembership> {
        let payload = serde_json::json!({ "message_id": message_id });
        self.send(
            Method::POST,
            &format!("/channels/{channel_id}/read"),
            Some(&payload),
        )
        .await
    }

    pub async fn update_membership(
        &self,
        channel_id: &str,
        patch: serde_json::Value,
    ) -> Result<ChannelMembership> {
        self.send(
            Method::PATCH,
            &format!("/channels/{channel_id}/membership"),
            Some(&patch),
        )
        .await
    }

    // ── Messages ────────────────────────────────────────────────────────

    pub async fn history(
        &self,
        channel_id: &str,
        limit: u32,
        before: Option<&str>,
    ) -> Result<CursorPage<Message>> {
        let mut path = format!("/channels/{channel_id}/messages?limit={limit}");
        if let Some(before) = before {
            path.push_str(&format!("&before={before}"));
        }
        self.send::<(), _>(Method::GET, &path, None).await
    }

    pub async fn thread_replies(&self, message_id: &str) -> Result<CursorPage<Message>> {
        self.send::<(), _>(
            Method::GET,
            &format!("/messages/{message_id}/replies?limit=200"),
            None,
        )
        .await
    }

    pub async fn post_message(&self, channel_id: &str, message: &NewMessage) -> Result<Message> {
        self.send(
            Method::POST,
            &format!("/channels/{channel_id}/messages"),
            Some(message),
        )
        .await
    }

    pub async fn edit_message(&self, message_id: &str, body: &str) -> Result<Message> {
        let payload = serde_json::json!({ "body": body });
        self.send(
            Method::PATCH,
            &format!("/messages/{message_id}"),
            Some(&payload),
        )
        .await
    }

    pub async fn delete_message(&self, message_id: &str) -> Result<()> {
        self.send::<(), serde_json::Value>(Method::DELETE, &format!("/messages/{message_id}"), None)
            .await
            .map(|_| ())
    }

    pub async fn add_reaction(&self, message_id: &str, emoji: &str) -> Result<()> {
        let payload = serde_json::json!({ "emoji": emoji });
        self.send::<_, serde_json::Value>(
            Method::PUT,
            &format!("/messages/{message_id}/reactions"),
            Some(&payload),
        )
        .await
        .map(|_| ())
    }

    pub async fn remove_reaction(&self, message_id: &str, emoji: &str) -> Result<()> {
        self.send::<(), serde_json::Value>(
            Method::DELETE,
            &format!(
                "/messages/{message_id}/reactions?emoji={}",
                urlencode(emoji)
            ),
            None,
        )
        .await
        .map(|_| ())
    }

    // ── Search ──────────────────────────────────────────────────────────

    pub async fn search_messages(&self, workspace_id: &str, query: &str) -> Result<SearchResponse> {
        self.send::<(), _>(
            Method::GET,
            &format!(
                "/workspaces/{workspace_id}/search/messages?q={}",
                urlencode(query)
            ),
            None,
        )
        .await
    }

    /// The command-palette query: channels, people, apps and messages at once.
    pub async fn search_everything(
        &self,
        workspace_id: &str,
        query: &str,
    ) -> Result<serde_json::Value> {
        self.send::<(), _>(
            Method::GET,
            &format!("/workspaces/{workspace_id}/search?q={}", urlencode(query)),
            None,
        )
        .await
    }

    // ── Files ───────────────────────────────────────────────────────────

    /// Two-step upload: reserve a row, then stream the bytes.
    pub async fn upload_file(
        &self,
        workspace_id: &str,
        filename: &str,
        mime_type: &str,
        bytes: Vec<u8>,
    ) -> Result<FileRef> {
        #[derive(serde::Deserialize)]
        struct Ticket {
            file_id: String,
            upload_url: String,
            #[serde(default)]
            headers: std::collections::HashMap<String, String>,
        }

        let ticket: Ticket = self
            .send(
                Method::POST,
                &format!("/workspaces/{workspace_id}/files"),
                Some(&serde_json::json!({
                    "filename": filename,
                    "mime_type": mime_type,
                    "size_bytes": bytes.len(),
                })),
            )
            .await?;

        // The ticket URL is either an API path (local storage) or an absolute
        // presigned URL (S3). Only the former takes our bearer token.
        let is_absolute = ticket.upload_url.starts_with("http");
        let url = if is_absolute {
            ticket.upload_url.clone()
        } else {
            format!("{}{}", self.config.base_url, ticket.upload_url)
        };

        let mut request = self.http.put(&url).body(bytes);
        for (key, value) in &ticket.headers {
            request = request.header(key, value);
        }
        if !is_absolute {
            if let Some(token) = self.session.access_token() {
                request = request.bearer_auth(token);
            }
        }
        let response = request.send().await?;

        if is_absolute {
            // S3 upload succeeded; tell the backend the object landed.
            check_status(response).await?;
            return self
                .send::<(), _>(
                    Method::POST,
                    &format!("/files/{}/complete", ticket.file_id),
                    None,
                )
                .await;
        }
        decode(response).await
    }

    pub async fn download_file(&self, file_id: &str) -> Result<Vec<u8>> {
        let mut request = self
            .http
            .get(self.url(&format!("/files/{file_id}/download")));
        if let Some(token) = self.session.access_token() {
            request = request.bearer_auth(token);
        }
        let response = check_status(request.send().await?).await?;
        Ok(response.bytes().await?.to_vec())
    }

    // ── Mini-apps ───────────────────────────────────────────────────────

    pub async fn list_installed_apps(&self, workspace_id: &str) -> Result<Vec<AppInstallation>> {
        self.send::<(), _>(
            Method::GET,
            &format!("/workspaces/{workspace_id}/apps"),
            None,
        )
        .await
    }

    pub async fn list_available_apps(&self, workspace_id: &str) -> Result<Vec<AppSummary>> {
        self.send::<(), _>(
            Method::GET,
            &format!("/workspaces/{workspace_id}/apps/available"),
            None,
        )
        .await
    }

    pub async fn install_app(
        &self,
        workspace_id: &str,
        app_id: &str,
        granted_scopes: Option<&[String]>,
    ) -> Result<AppInstallation> {
        let payload = serde_json::json!({
            "granted_scopes": granted_scopes,
            "pin_to_dock": true,
        });
        self.send(
            Method::POST,
            &format!("/workspaces/{workspace_id}/apps/{app_id}/install"),
            Some(&payload),
        )
        .await
    }

    pub async fn uninstall_app(&self, installation_id: &str) -> Result<()> {
        self.send::<(), serde_json::Value>(
            Method::DELETE,
            &format!("/app-installations/{installation_id}"),
            None,
        )
        .await
        .map(|_| ())
    }

    /// Mint a panel session. The bridge token it returns is what the host
    /// injects into the sandboxed webview — never the user's access token.
    pub async fn create_panel_session(
        &self,
        installation_id: &str,
        channel_id: Option<&str>,
    ) -> Result<PanelSession> {
        let mut path = format!("/app-installations/{installation_id}/panel-session");
        if let Some(channel_id) = channel_id {
            path.push_str(&format!("?channel_id={channel_id}"));
        }
        self.send::<(), _>(Method::POST, &path, None).await
    }
}

// ── Response decoding ───────────────────────────────────────────────────────

async fn check_status(response: reqwest::Response) -> Result<reqwest::Response> {
    let status = response.status();
    if status.is_success() {
        return Ok(response);
    }
    Err(error_from_response(status, response).await)
}

async fn decode<T: DeserializeOwned>(response: reqwest::Response) -> Result<T> {
    let status = response.status();
    if !status.is_success() {
        return Err(error_from_response(status, response).await);
    }

    let bytes = response.bytes().await?;
    // 204 and other empty bodies still have to satisfy `T`; `null` is what
    // serde accepts for unit and Option.
    if bytes.is_empty() {
        return serde_json::from_slice(b"null")
            .map_err(|e| Error::Network(format!("empty response body: {e}")));
    }
    serde_json::from_slice(&bytes).map_err(|e| {
        Error::Network(format!(
            "could not decode response: {e} (body starts: {})",
            String::from_utf8_lossy(&bytes[..bytes.len().min(200)])
        ))
    })
}

async fn error_from_response(status: StatusCode, response: reqwest::Response) -> Error {
    let bytes = response.bytes().await.unwrap_or_default();
    match serde_json::from_slice::<ApiErrorEnvelope>(&bytes) {
        Ok(envelope) => Error::Api {
            status: status.as_u16(),
            body: envelope.error,
        },
        // A response that is not our envelope means a proxy or gateway
        // answered, not the application.
        Err(_) => Error::Network(format!(
            "HTTP {status}: {}",
            String::from_utf8_lossy(&bytes[..bytes.len().min(200)])
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> ApiConfig {
        ApiConfig::new("https://llack.example.com/")
    }

    #[test]
    fn trailing_slashes_are_normalised() {
        assert_eq!(config().base_url, "https://llack.example.com");
        assert_eq!(config().api_root(), "https://llack.example.com/api/v1");
    }

    #[test]
    fn websocket_url_follows_the_http_scheme() {
        let secure = config();
        assert!(secure
            .websocket_url("tok", None)
            .starts_with("wss://llack.example.com/api/v1/ws?token=tok"));

        let plain = ApiConfig::new("http://localhost:8000");
        assert!(plain
            .websocket_url("tok", Some("01WS"))
            .starts_with("ws://localhost:8000/api/v1/ws?token=tok&workspace_id=01WS"));
    }

    #[test]
    fn websocket_url_escapes_the_token() {
        // A JWT contains '.' (safe) but a token with '+' or '/' must not
        // corrupt the query string.
        let url = config().websocket_url("a+b/c=d", None);
        assert!(url.contains("token=a%2Bb%2Fc%3Dd"), "got {url}");
    }

    #[test]
    fn resolve_handles_relative_and_absolute_paths() {
        let cfg = config();
        assert_eq!(
            cfg.resolve("/files/01F/download"),
            "https://llack.example.com/api/v1/files/01F/download"
        );
        assert_eq!(
            cfg.resolve("https://cdn.example.com/x.png"),
            "https://cdn.example.com/x.png"
        );
    }

    #[test]
    fn urlencode_leaves_unreserved_characters_alone() {
        assert_eq!(urlencode("abcXYZ019-_.~"), "abcXYZ019-_.~");
        assert_eq!(urlencode("a b"), "a%20b");
        // Multi-byte input is percent-encoded per UTF-8 byte.
        assert_eq!(urlencode("가"), "%EA%B0%80");
    }
}
