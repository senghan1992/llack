//! Wire types mirroring the backend's schemas.
//!
//! Every struct uses `#[serde(default)]` on optional fields so adding a field
//! server-side never breaks an older client — important once the desktop app
//! is distributed and not everyone updates at once.

use serde::{Deserialize, Serialize};

pub type Id = String;

// ── Users ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Presence {
    Active,
    Away,
    Dnd,
    /// Default: a user we have heard nothing about is not online.
    #[default]
    Offline,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserBrief {
    pub id: Id,
    pub handle: String,
    pub display_name: String,
    #[serde(default)]
    pub avatar_url: Option<String>,
    #[serde(default)]
    pub is_bot: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct User {
    pub id: Id,
    pub email: String,
    pub handle: String,
    pub display_name: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub avatar_url: Option<String>,
    #[serde(default = "default_timezone")]
    pub timezone: String,
    #[serde(default = "default_locale")]
    pub locale: String,
    #[serde(default)]
    pub status_emoji: Option<String>,
    #[serde(default)]
    pub status_text: Option<String>,
    #[serde(default)]
    pub presence: Presence,
    #[serde(default)]
    pub is_bot: bool,
    #[serde(default = "default_true")]
    pub is_active: bool,
}

fn default_timezone() -> String {
    "Asia/Seoul".into()
}
fn default_locale() -> String {
    "ko-KR".into()
}
fn default_true() -> bool {
    true
}

// ── Auth ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenPair {
    pub access_token: String,
    pub refresh_token: String,
    #[serde(default)]
    pub token_type: String,
    /// RFC 3339 timestamp at which `access_token` stops being accepted.
    pub expires_at: String,
    pub expires_in: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthResponse {
    pub user: User,
    pub tokens: TokenPair,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub platform: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub app_version: Option<String>,
}

// ── Workspaces ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkspaceRole {
    Owner,
    Admin,
    Member,
    Guest,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub id: Id,
    pub slug: String,
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub icon_url: Option<String>,
    #[serde(default)]
    pub my_role: Option<WorkspaceRole>,
    #[serde(default)]
    pub member_count: i64,
}

// ── Channels ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChannelKind {
    Public,
    Private,
    Dm,
    GroupDm,
}

impl ChannelKind {
    pub fn is_conversation(self) -> bool {
        matches!(self, ChannelKind::Dm | ChannelKind::GroupDm)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotificationLevel {
    All,
    Mentions,
    Nothing,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelMembership {
    /// "admin" or "member". The UI uses it to decide which channel-settings
    /// controls to offer; the server re-checks every privileged change.
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub last_read_message_id: Option<Id>,
    #[serde(default)]
    pub unread_count: i64,
    #[serde(default)]
    pub mention_count: i64,
    #[serde(default)]
    pub notification_level: Option<NotificationLevel>,
    #[serde(default)]
    pub is_muted: bool,
    #[serde(default)]
    pub is_starred: bool,
    #[serde(default)]
    pub section: Option<String>,
    #[serde(default)]
    pub sort_order: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Channel {
    pub id: Id,
    pub workspace_id: Id,
    pub kind: ChannelKind,
    #[serde(default)]
    pub slug: Option<String>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub topic: Option<String>,
    #[serde(default)]
    pub purpose: Option<String>,
    #[serde(default)]
    pub is_archived: bool,
    #[serde(default)]
    pub last_message_at: Option<String>,
    #[serde(default)]
    pub message_count: i64,
    #[serde(default)]
    pub member_count: i64,
    #[serde(default)]
    pub peers: Vec<UserBrief>,
    #[serde(default)]
    pub membership: Option<ChannelMembership>,
}

impl Channel {
    /// What to show in the sidebar. DMs have no stored name, so the server
    /// derives one from the peers; fall back to that locally too.
    pub fn display_name(&self) -> String {
        if let Some(name) = &self.name {
            return name.clone();
        }
        if self.kind.is_conversation() && !self.peers.is_empty() {
            return self
                .peers
                .iter()
                .map(|p| p.display_name.as_str())
                .collect::<Vec<_>>()
                .join(", ");
        }
        self.slug.clone().unwrap_or_else(|| self.id.clone())
    }

    pub fn unread_count(&self) -> i64 {
        self.membership
            .as_ref()
            .map(|m| m.unread_count)
            .unwrap_or(0)
    }

    pub fn mention_count(&self) -> i64 {
        self.membership
            .as_ref()
            .map(|m| m.mention_count)
            .unwrap_or(0)
    }

    /// A muted channel still counts mentions but never contributes to the
    /// workspace badge from plain traffic.
    pub fn badge_count(&self) -> i64 {
        match &self.membership {
            Some(m) if m.is_muted => m.mention_count,
            Some(m) => m.unread_count,
            None => 0,
        }
    }
}

/// One row of `GET /channels/{id}/members`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelMemberEntry {
    pub id: Id,
    pub user: UserBrief,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub joined_at: Option<String>,
}

// ── Messages ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageKind {
    /// Default: an older server that omits `kind` only sent user messages.
    #[default]
    User,
    System,
    App,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Reaction {
    pub emoji: String,
    pub count: i64,
    #[serde(default)]
    pub user_ids: Vec<Id>,
    #[serde(default)]
    pub me: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileRef {
    pub id: Id,
    pub filename: String,
    pub mime_type: String,
    pub size_bytes: i64,
    #[serde(default)]
    pub download_url: Option<String>,
    #[serde(default)]
    pub thumbnail_url: Option<String>,
    #[serde(default)]
    pub uploader: Option<UserBrief>,
}

impl FileRef {
    pub fn is_image(&self) -> bool {
        self.mime_type.starts_with("image/")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: Id,
    pub channel_id: Id,
    #[serde(default)]
    pub kind: MessageKind,
    #[serde(default)]
    pub body: String,
    #[serde(default)]
    pub blocks: Option<serde_json::Value>,
    #[serde(default)]
    pub client_msg_id: Option<String>,
    #[serde(default)]
    pub author: Option<UserBrief>,
    #[serde(default)]
    pub app_id: Option<Id>,
    #[serde(default)]
    pub parent_id: Option<Id>,
    #[serde(default)]
    pub reply_count: i64,
    #[serde(default)]
    pub last_reply_at: Option<String>,
    #[serde(default)]
    pub also_sent_to_channel: bool,
    #[serde(default)]
    pub mentioned_user_ids: Vec<Id>,
    #[serde(default)]
    pub mentions_everyone: bool,
    #[serde(default)]
    pub attachments: Vec<FileRef>,
    #[serde(default)]
    pub reactions: Vec<Reaction>,
    #[serde(default)]
    pub is_pinned: bool,
    #[serde(default)]
    pub edited_at: Option<String>,
    #[serde(default)]
    pub deleted_at: Option<String>,
    pub created_at: String,
}

impl Message {
    pub fn is_deleted(&self) -> bool {
        self.deleted_at.is_some()
    }

    pub fn is_thread_reply(&self) -> bool {
        self.parent_id.is_some()
    }

    pub fn mentions(&self, user_id: &str) -> bool {
        self.mentions_everyone || self.mentioned_user_ids.iter().any(|id| id == user_id)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CursorPage<T> {
    pub items: Vec<T>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(default)]
    pub prev_cursor: Option<String>,
    #[serde(default)]
    pub has_more: bool,
}

// ── Mini-apps ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSummary {
    pub id: Id,
    pub slug: String,
    pub name: String,
    #[serde(default)]
    pub tagline: Option<String>,
    #[serde(default)]
    pub icon_url: Option<String>,
    #[serde(default)]
    pub accent_color: Option<String>,
    #[serde(default)]
    pub panel_url: Option<String>,
    #[serde(default)]
    pub sidebar_url: Option<String>,
    #[serde(default = "default_panel_width")]
    pub default_width: i64,
    #[serde(default)]
    pub requested_scopes: Vec<String>,
}

fn default_panel_width() -> i64 {
    420
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppInstallation {
    pub id: Id,
    pub workspace_id: Id,
    pub app: AppSummary,
    #[serde(default)]
    pub granted_scopes: Vec<String>,
    #[serde(default)]
    pub config: serde_json::Value,
    #[serde(default)]
    pub bot_user_id: Option<Id>,
    #[serde(default = "default_true")]
    pub is_enabled: bool,
    #[serde(default)]
    pub is_pinned: bool,
    #[serde(default)]
    pub sort_order: i64,
}

/// Everything the host needs to boot a mini-app webview.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PanelSession {
    pub installation_id: Id,
    pub app_id: Id,
    pub panel_url: String,
    pub bridge_token: String,
    pub expires_at: String,
    #[serde(default)]
    pub granted_scopes: Vec<String>,
    #[serde(default)]
    pub config: serde_json::Value,
    #[serde(default)]
    pub context: serde_json::Value,
}

// ── Composing ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct NewMessage {
    #[serde(default)]
    pub body: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blocks: Option<serde_json::Value>,
    /// Generated locally so a retry after a dropped response cannot double-post.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_msg_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<Id>,
    #[serde(default)]
    pub also_send_to_channel: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub file_ids: Vec<Id>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHit {
    pub message: Message,
    pub channel_id: Id,
    #[serde(default)]
    pub channel_name: Option<String>,
    #[serde(default)]
    pub highlight: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResponse {
    pub query: String,
    #[serde(default)]
    pub hits: Vec<SearchHit>,
    #[serde(default)]
    pub total: i64,
    #[serde(default)]
    pub took_ms: i64,
}
