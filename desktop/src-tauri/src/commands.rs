//! Tauri commands — the IPC surface the UI calls.
//!
//! Every command is a thin adapter: validate, delegate to `llack-core`, and
//! return a serialisable result. Business rules live in core so they can be
//! tested without a running window.
//!
//! Read paths return cached data immediately and refresh in the background
//! where it makes sense, so opening a channel never shows an empty pane while
//! a request is in flight.

use std::sync::Arc;

use llack_core::error::{Error, Result};
use llack_core::{
    Channel, ChannelKind, ChannelMembership, DrainReport, Message, NewMessage, PanelSession,
    RealtimeCommand, User, Workspace,
};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::state::AppState;

// ── Connection & auth ───────────────────────────────────────────────────────

#[derive(serde::Serialize)]
pub struct BootstrapResult {
    pub server_url: Option<String>,
    pub user: Option<User>,
    /// True when a stored refresh token was exchanged successfully, so the UI
    /// can go straight to the workspace instead of the sign-in screen.
    pub resumed: bool,
}

/// Point the app at a server and try to resume a stored session.
#[tauri::command]
pub async fn bootstrap(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    server_url: String,
) -> Result<BootstrapResult> {
    let device_name = hostname_label();
    let api = state.connect(&server_url, Some(device_name))?;

    if !api.session().is_authenticated() {
        return Ok(BootstrapResult {
            server_url: Some(server_url),
            user: None,
            resumed: false,
        });
    }

    match api.resume().await {
        Ok(user) => {
            state.install_sync(&user.id)?;
            crate::realtime_task::start(app, state.inner().clone(), None);
            Ok(BootstrapResult {
                server_url: Some(server_url),
                user: Some(user),
                resumed: true,
            })
        }
        Err(err) if err.requires_reauth() => {
            // The stored token is dead; clear it so the UI shows sign-in
            // rather than retrying forever.
            let _ = api.session().clear();
            Ok(BootstrapResult {
                server_url: Some(server_url),
                user: None,
                resumed: false,
            })
        }
        Err(err) => Err(err),
    }
}

#[tauri::command]
pub async fn login(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    email: String,
    password: String,
) -> Result<User> {
    let api = state.api()?;
    let auth = api.login(&email, &password).await?;
    state.install_sync(&auth.user.id)?;
    crate::realtime_task::start(app, state.inner().clone(), None);
    Ok(auth.user)
}

#[tauri::command]
pub async fn register(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    email: String,
    password: String,
    display_name: String,
    invite_token: Option<String>,
) -> Result<User> {
    let api = state.api()?;
    let auth = api
        .register(&email, &password, &display_name, invite_token.as_deref())
        .await?;
    state.install_sync(&auth.user.id)?;
    crate::realtime_task::start(app, state.inner().clone(), None);
    Ok(auth.user)
}

#[tauri::command]
pub async fn logout(state: State<'_, Arc<AppState>>) -> Result<()> {
    let api = state.api()?;
    // Best-effort server call; local state is cleared regardless so the user
    // is never left appearing signed in.
    let server_result = api.logout().await;
    state.reset()?;
    match server_result {
        Ok(()) => Ok(()),
        Err(err) if err.is_retryable() => Ok(()),
        Err(err) => Err(err),
    }
}

#[tauri::command]
pub async fn current_user(state: State<'_, Arc<AppState>>) -> Result<Option<User>> {
    Ok(state.session().ok().and_then(|s| s.user()))
}

#[tauri::command]
pub async fn update_me(state: State<'_, Arc<AppState>>, patch: serde_json::Value) -> Result<User> {
    state.api()?.update_me(patch).await
}

#[tauri::command]
pub async fn upload_avatar(state: State<'_, Arc<AppState>>, path: String) -> Result<User> {
    let file_path = std::fs::canonicalize(&path)
        .map_err(|e| Error::Other(format!("could not read {path}: {e}")))?;
    if let Some((rule, reason)) = llack_core::agent::policy::refuse_path(
        &file_path,
        llack_core::agent::policy::Access::Read,
        &state.path_context(),
    ) {
        tracing::warn!(rule, path = %file_path.display(), "avatar upload refused by path policy");
        return Err(Error::Other(reason.into()));
    }
    let mime = match file_path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
        .as_deref()
    {
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        _ => "image/png",
    };
    let bytes = std::fs::read(&file_path)
        .map_err(|e| Error::Other(format!("could not read {}: {e}", file_path.display())))?;
    state.api()?.upload_avatar(mime, bytes).await
}

#[tauri::command]
pub async fn remove_avatar(state: State<'_, Arc<AppState>>) -> Result<User> {
    state.api()?.remove_avatar().await
}

#[tauri::command]
pub async fn list_workspace_files(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    q: Option<String>,
    kind: Option<String>,
    mine: bool,
    cursor: Option<String>,
    limit: u32,
) -> Result<serde_json::Value> {
    state
        .api()?
        .list_workspace_files(
            &workspace_id,
            q.as_deref(),
            kind.as_deref(),
            mine,
            cursor.as_deref(),
            limit,
        )
        .await
}

#[tauri::command]
pub async fn activity_threads(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    before: Option<String>,
) -> Result<serde_json::Value> {
    state
        .api()?
        .activity_threads(&workspace_id, before.as_deref())
        .await
}

#[tauri::command]
pub async fn activity_mentions(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    before: Option<String>,
) -> Result<serde_json::Value> {
    state
        .api()?
        .activity_mentions(&workspace_id, before.as_deref())
        .await
}

#[tauri::command]
pub async fn list_sessions(state: State<'_, Arc<AppState>>) -> Result<serde_json::Value> {
    state.api()?.list_sessions().await
}

#[tauri::command]
pub async fn revoke_session(state: State<'_, Arc<AppState>>, session_id: String) -> Result<()> {
    state.api()?.revoke_session(&session_id).await
}

#[tauri::command]
pub async fn list_workspace_members(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state.api()?.list_workspace_members(&workspace_id).await
}

#[tauri::command]
pub async fn update_workspace_member_role(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    member_id: String,
    role: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .update_workspace_member_role(&workspace_id, &member_id, &role)
        .await
}

#[tauri::command]
pub async fn remove_workspace_member(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    member_id: String,
) -> Result<()> {
    state
        .api()?
        .remove_workspace_member(&workspace_id, &member_id)
        .await
}

#[tauri::command]
pub async fn update_installation(
    state: State<'_, Arc<AppState>>,
    installation_id: String,
    patch: serde_json::Value,
) -> Result<llack_core::AppInstallation> {
    state
        .api()?
        .update_installation(&installation_id, patch)
        .await
}

#[tauri::command]
pub async fn probe_link_app(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    url: String,
) -> Result<serde_json::Value> {
    state.api()?.probe_link_app(&workspace_id, &url).await
}

#[tauri::command]
pub async fn list_audit(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    before: Option<String>,
    action: Option<String>,
    actor_id: Option<String>,
) -> Result<serde_json::Value> {
    state
        .api()?
        .list_audit(
            &workspace_id,
            before.as_deref(),
            action.as_deref(),
            actor_id.as_deref(),
        )
        .await
}

#[tauri::command]
pub async fn download_audit_csv(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<()> {
    let bytes = state.api()?.download_audit_csv(&workspace_id).await?;
    let dir = app
        .path()
        .download_dir()
        .map_err(|e| Error::Other(format!("no download dir: {e}")))?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let name = format!("llack-audit-{stamp}.csv");
    std::fs::write(dir.join(name), bytes)
        .map_err(|e| Error::Other(format!("could not write csv: {e}")))?;
    Ok(())
}

#[tauri::command]
pub async fn get_retention(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state.api()?.get_retention(&workspace_id).await
}

#[tauri::command]
pub async fn update_retention(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    patch: serde_json::Value,
) -> Result<serde_json::Value> {
    state.api()?.update_retention(&workspace_id, patch).await
}

#[tauri::command]
pub async fn update_notifications(
    state: State<'_, Arc<AppState>>,
    patch: serde_json::Value,
) -> Result<User> {
    state.api()?.update_notifications(patch).await
}

#[tauri::command]
pub async fn save_message(
    state: State<'_, Arc<AppState>>,
    message_id: String,
    note: Option<String>,
    remind_at: Option<String>,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({ "note": note, "remind_at": remind_at });
    state.api()?.save_message(&message_id, payload).await
}

#[tauri::command]
pub async fn unsave_message(state: State<'_, Arc<AppState>>, message_id: String) -> Result<()> {
    state.api()?.unsave_message(&message_id).await
}

#[tauri::command]
pub async fn list_saved(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    done: bool,
    before: Option<String>,
) -> Result<serde_json::Value> {
    state
        .api()?
        .list_saved(&workspace_id, done, before.as_deref())
        .await
}

#[tauri::command]
pub async fn mark_saved_done(
    state: State<'_, Arc<AppState>>,
    saved_id: String,
) -> Result<serde_json::Value> {
    state.api()?.saved_action(&saved_id, "done").await
}

#[tauri::command]
pub async fn reopen_saved(
    state: State<'_, Arc<AppState>>,
    saved_id: String,
) -> Result<serde_json::Value> {
    state.api()?.saved_action(&saved_id, "reopen").await
}

#[tauri::command]
pub async fn resend_invite(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    invite_id: String,
) -> Result<serde_json::Value> {
    state.api()?.resend_invite(&workspace_id, &invite_id).await
}

#[tauri::command]
pub async fn file_thumbnail(state: State<'_, Arc<AppState>>, file_id: String) -> Result<String> {
    use base64::Engine as _;
    let bytes = state.api()?.file_thumbnail(&file_id).await?;
    let mime = if bytes.starts_with(&[0x89, b'P', b'N', b'G']) {
        "image/png"
    } else {
        "image/jpeg"
    };
    Ok(format!(
        "data:{mime};base64,{}",
        base64::engine::general_purpose::STANDARD.encode(bytes)
    ))
}

#[tauri::command]
pub async fn media_token(
    state: State<'_, Arc<AppState>>,
    file_id: String,
) -> Result<serde_json::Value> {
    state.api()?.media_token(&file_id).await
}

#[tauri::command]
pub async fn list_commands(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state.api()?.list_commands(&workspace_id).await
}

#[tauri::command]
pub async fn run_command(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    text: String,
) -> Result<serde_json::Value> {
    state.api()?.run_command(&channel_id, &text).await
}

#[tauri::command]
pub async fn message_action(
    state: State<'_, Arc<AppState>>,
    message_id: String,
    action_id: String,
    value: Option<String>,
) -> Result<serde_json::Value> {
    state
        .api()?
        .message_action(&message_id, &action_id, value.as_deref())
        .await
}

#[tauri::command]
pub async fn open_app_home(
    state: State<'_, Arc<AppState>>,
    installation_id: String,
) -> Result<PanelSession> {
    state.api()?.open_app_home(&installation_id).await
}

#[tauri::command]
pub async fn list_my_apps(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_get(&format!("/workspaces/{workspace_id}/apps/mine"))
        .await
}

#[tauri::command]
pub async fn register_app(
    state: State<'_, Arc<AppState>>,
    manifest: serde_json::Value,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_post(
            &format!("/apps?workspace_id={workspace_id}"),
            Some(manifest),
        )
        .await
}

#[tauri::command]
pub async fn update_manifest(
    state: State<'_, Arc<AppState>>,
    app_id: String,
    manifest: serde_json::Value,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_put(&format!("/apps/{app_id}/manifest"), manifest)
        .await
}

#[tauri::command]
pub async fn submit_app(
    state: State<'_, Arc<AppState>>,
    app_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_post(&format!("/apps/{app_id}/submit"), None)
        .await
}

#[tauri::command]
pub async fn review_app(
    state: State<'_, Arc<AppState>>,
    app_id: String,
    decision: String,
    note: Option<String>,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({ "decision": decision, "note": note });
    state
        .api()?
        .apps_post(&format!("/apps/{app_id}/review"), Some(payload))
        .await
}

#[tauri::command]
pub async fn list_pending_apps(state: State<'_, Arc<AppState>>) -> Result<serde_json::Value> {
    state.api()?.apps_get("/apps/pending").await
}

#[tauri::command]
pub async fn rotate_app_secret(
    state: State<'_, Arc<AppState>>,
    app_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_post(&format!("/apps/{app_id}/rotate-secret"), None)
        .await
}

#[tauri::command]
pub async fn test_webhook(
    state: State<'_, Arc<AppState>>,
    app_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_post(&format!("/apps/{app_id}/test-webhook"), None)
        .await
}

#[tauri::command]
pub async fn list_deliveries(
    state: State<'_, Arc<AppState>>,
    app_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_get(&format!("/apps/{app_id}/deliveries?limit=50"))
        .await
}

#[tauri::command]
pub async fn list_app_tokens(
    state: State<'_, Arc<AppState>>,
    app_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .apps_get(&format!("/apps/{app_id}/tokens"))
        .await
}

#[tauri::command]
pub async fn create_app_token(
    state: State<'_, Arc<AppState>>,
    app_id: String,
    name: String,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({ "name": name });
    state
        .api()?
        .apps_post(&format!("/apps/{app_id}/tokens"), Some(payload))
        .await
}

#[tauri::command]
pub async fn revoke_app_token(
    state: State<'_, Arc<AppState>>,
    app_id: String,
    token_id: String,
) -> Result<()> {
    state
        .api()?
        .apps_delete(&format!("/apps/{app_id}/tokens/{token_id}"))
        .await
}

#[tauri::command]
pub async fn update_my_status(
    state: State<'_, Arc<AppState>>,
    patch: serde_json::Value,
) -> Result<User> {
    state.api()?.update_my_status(patch).await
}

#[tauri::command]
pub async fn get_smtp_settings(state: State<'_, Arc<AppState>>) -> Result<serde_json::Value> {
    state.api()?.get_smtp_settings().await
}

#[tauri::command]
pub async fn update_smtp_settings(
    state: State<'_, Arc<AppState>>,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    state.api()?.update_smtp_settings(payload).await
}

#[tauri::command]
pub async fn test_smtp(
    state: State<'_, Arc<AppState>>,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    state.api()?.test_smtp(payload).await
}

#[tauri::command]
pub async fn forgot_password(state: State<'_, Arc<AppState>>, email: String) -> Result<()> {
    state.api()?.forgot_password(&email).await
}

#[tauri::command]
pub async fn reset_password(
    state: State<'_, Arc<AppState>>,
    email: String,
    code: String,
    new_password: String,
) -> Result<()> {
    state
        .api()?
        .reset_password(&email, &code, &new_password)
        .await
}

#[tauri::command]
pub async fn change_password(
    state: State<'_, Arc<AppState>>,
    current_password: String,
    new_password: String,
) -> Result<()> {
    state
        .api()?
        .change_password(&current_password, &new_password)
        .await
}

#[tauri::command]
pub async fn create_invites(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    emails: Vec<String>,
    role: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .create_invites(&workspace_id, &emails, &role)
        .await
}

#[tauri::command]
pub async fn accept_invite(state: State<'_, Arc<AppState>>, token: String) -> Result<Workspace> {
    state.api()?.accept_invite(&token).await
}

#[tauri::command]
pub async fn list_invites(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<serde_json::Value> {
    state.api()?.list_invites(&workspace_id).await
}

#[tauri::command]
pub async fn reset_member_password(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    user_id: String,
) -> Result<serde_json::Value> {
    state
        .api()?
        .reset_member_password(&workspace_id, &user_id)
        .await
}

#[tauri::command]
pub async fn revoke_invite(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    invite_id: String,
) -> Result<()> {
    state.api()?.revoke_invite(&workspace_id, &invite_id).await
}

#[tauri::command]
pub async fn create_workspace(
    state: State<'_, Arc<AppState>>,
    name: String,
    slug: String,
) -> Result<Workspace> {
    state.api()?.create_workspace(&name, &slug).await
}

// ── Workspaces ──────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn list_workspaces(state: State<'_, Arc<AppState>>) -> Result<Vec<Workspace>> {
    state.api()?.list_workspaces().await
}

#[tauri::command]
pub async fn select_workspace(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    workspace_id: String,
) -> Result<Vec<Channel>> {
    state.set_active_workspace(Some(workspace_id.clone()));

    // Resubscribe the socket to this workspace's channels.
    let channels = state.sync()?.refresh_channels(&workspace_id).await?;
    if let Ok(realtime) = state.realtime() {
        let _ = realtime.subscribe(channels.iter().map(|c| c.id.clone()).collect());
    }
    update_badge(&app, &state, &workspace_id);
    Ok(channels)
}

#[tauri::command]
pub async fn list_workspace_users(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    query: Option<String>,
) -> Result<Vec<User>> {
    state
        .api()?
        .list_workspace_users(&workspace_id, query.as_deref())
        .await
}

// ── Channels ────────────────────────────────────────────────────────────────

/// Cached channels, for an instant first paint.
#[tauri::command]
pub async fn cached_channels(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<Vec<Channel>> {
    state.cache.channels(&workspace_id)
}

#[tauri::command]
pub async fn refresh_channels(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    workspace_id: String,
) -> Result<Vec<Channel>> {
    let channels = state.sync()?.refresh_channels(&workspace_id).await?;
    update_badge(&app, &state, &workspace_id);
    Ok(channels)
}

#[tauri::command]
pub async fn browse_channels(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    query: Option<String>,
) -> Result<Vec<Channel>> {
    state
        .api()?
        .browse_channels(&workspace_id, query.as_deref())
        .await
}

#[tauri::command]
pub async fn create_channel(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    name: String,
    kind: ChannelKind,
    member_ids: Vec<String>,
) -> Result<Channel> {
    let channel = state
        .api()?
        .create_channel(&workspace_id, &name, kind, &member_ids)
        .await?;
    state.cache.put_channels(std::slice::from_ref(&channel))?;
    if let Ok(realtime) = state.realtime() {
        let _ = realtime.subscribe(vec![channel.id.clone()]);
    }
    Ok(channel)
}

#[tauri::command]
pub async fn open_dm(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    user_ids: Vec<String>,
) -> Result<Channel> {
    let channel = state.api()?.open_dm(&workspace_id, &user_ids).await?;
    state.cache.put_channels(std::slice::from_ref(&channel))?;
    if let Ok(realtime) = state.realtime() {
        let _ = realtime.subscribe(vec![channel.id.clone()]);
    }
    Ok(channel)
}

#[tauri::command]
pub async fn update_channel(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    patch: serde_json::Value,
) -> Result<Channel> {
    let channel = state.api()?.update_channel(&channel_id, patch).await?;
    state.cache.put_channels(std::slice::from_ref(&channel))?;
    Ok(channel)
}

#[tauri::command]
pub async fn channel_members(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
) -> Result<Vec<llack_core::ChannelMemberEntry>> {
    state.api()?.channel_members(&channel_id).await
}

#[tauri::command]
pub async fn add_channel_members(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    user_ids: Vec<String>,
) -> Result<Vec<String>> {
    state
        .api()?
        .add_channel_members(&channel_id, &user_ids)
        .await
}

#[tauri::command]
pub async fn set_channel_member_role(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    user_id: String,
    role: String,
) -> Result<llack_core::ChannelMemberEntry> {
    state
        .api()?
        .set_channel_member_role(&channel_id, &user_id, &role)
        .await
}

#[tauri::command]
pub async fn revoke_other_sessions(state: State<'_, Arc<AppState>>) -> Result<()> {
    state.api()?.revoke_other_sessions().await
}

#[tauri::command]
pub async fn delete_file(state: State<'_, Arc<AppState>>, file_id: String) -> Result<()> {
    state.api()?.delete_file(&file_id).await
}

#[tauri::command]
pub async fn remove_channel_member(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    user_id: String,
) -> Result<()> {
    state
        .api()?
        .remove_channel_member(&channel_id, &user_id)
        .await
}

#[tauri::command]
pub async fn join_channel(state: State<'_, Arc<AppState>>, channel_id: String) -> Result<Channel> {
    let channel = state.api()?.join_channel(&channel_id).await?;
    state.cache.put_channels(std::slice::from_ref(&channel))?;
    if let Ok(realtime) = state.realtime() {
        let _ = realtime.subscribe(vec![channel.id.clone()]);
    }
    Ok(channel)
}

#[tauri::command]
pub async fn leave_channel(state: State<'_, Arc<AppState>>, channel_id: String) -> Result<()> {
    state.api()?.leave_channel(&channel_id).await?;
    state.cache.remove_channel(&channel_id)?;
    if let Ok(realtime) = state.realtime() {
        let _ = realtime.send(RealtimeCommand::Unsubscribe {
            channel_ids: vec![channel_id],
        });
    }
    Ok(())
}

#[tauri::command]
pub async fn update_membership(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    patch: serde_json::Value,
) -> Result<ChannelMembership> {
    state.api()?.update_membership(&channel_id, patch).await
}

#[tauri::command]
pub async fn mark_read(
    state: State<'_, Arc<AppState>>,
    app: AppHandle,
    channel_id: String,
    message_id: Option<String>,
) -> Result<ChannelMembership> {
    let membership = state
        .api()?
        .mark_read(&channel_id, message_id.as_deref())
        .await?;
    if let Some(workspace_id) = state.active_workspace() {
        // The badge is derived from cached counters, so refresh them.
        let _ = state
            .sync()
            .and_then(|s| tauri::async_runtime::block_on(s.refresh_channels(&workspace_id)));
        update_badge(&app, &state, &workspace_id);
    }
    Ok(membership)
}

// ── Messages ────────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn cached_history(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    limit: Option<u32>,
) -> Result<Vec<Message>> {
    state
        .cache
        .channel_history(&channel_id, limit.unwrap_or(80))
}

#[tauri::command]
pub async fn refresh_history(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    limit: Option<u32>,
) -> Result<Vec<Message>> {
    state
        .sync()?
        .refresh_history(&channel_id, limit.unwrap_or(80))
        .await
}

#[tauri::command]
pub async fn load_older_messages(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    before: String,
    limit: Option<u32>,
) -> Result<Vec<Message>> {
    let page = state
        .api()?
        .history(&channel_id, limit.unwrap_or(50), Some(&before))
        .await?;
    state.cache.put_messages(&page.items)?;
    let mut items = page.items;
    items.reverse();
    Ok(items)
}

#[tauri::command]
pub async fn thread_replies(
    state: State<'_, Arc<AppState>>,
    message_id: String,
) -> Result<Vec<Message>> {
    let page = state.api()?.thread_replies(&message_id).await?;
    state.cache.put_messages(&page.items)?;
    Ok(page.items)
}

/// Send a message.
///
/// Always goes through the outbox: the message is queued with its
/// `client_msg_id` first, then sent. If the send fails for a network reason it
/// stays queued and is retried, and because the server treats
/// `client_msg_id` as an idempotency key, a retry can never double-post.
#[derive(serde::Serialize)]
pub struct SendResult {
    /// The server's message, when the send succeeded immediately.
    pub message: Option<Message>,
    /// The optimistic id to render while queued.
    pub client_msg_id: String,
    pub queued: bool,
    pub error: Option<String>,
}

#[tauri::command]
pub async fn send_message(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    body: String,
    parent_id: Option<String>,
    also_send_to_channel: Option<bool>,
    file_ids: Option<Vec<String>>,
) -> Result<SendResult> {
    let payload = NewMessage {
        body,
        blocks: None,
        client_msg_id: Some(llack_core::ids::new_ulid()),
        parent_id,
        also_send_to_channel: also_send_to_channel.unwrap_or(false),
        file_ids: file_ids.unwrap_or_default(),
    };

    let entry = state.cache.enqueue(&channel_id, payload)?;
    state.cache.mark_sending(&entry.id)?;

    match state.api()?.post_message(&channel_id, &entry.payload).await {
        Ok(message) => {
            state.cache.put_messages(std::slice::from_ref(&message))?;
            state.cache.dequeue(&entry.id)?;
            Ok(SendResult {
                message: Some(message),
                client_msg_id: entry.client_msg_id,
                queued: false,
                error: None,
            })
        }
        Err(err) => {
            let retryable = err.is_retryable();
            state
                .cache
                .mark_result(&entry.id, &err.to_string(), retryable)?;
            if retryable {
                // Queued for the drain loop; the UI shows a pending bubble.
                Ok(SendResult {
                    message: None,
                    client_msg_id: entry.client_msg_id,
                    queued: true,
                    error: Some(err.to_string()),
                })
            } else {
                Err(err)
            }
        }
    }
}

#[tauri::command]
pub async fn edit_message(
    state: State<'_, Arc<AppState>>,
    message_id: String,
    body: String,
) -> Result<Message> {
    let message = state.api()?.edit_message(&message_id, &body).await?;
    state.cache.put_messages(std::slice::from_ref(&message))?;
    Ok(message)
}

#[tauri::command]
pub async fn set_pinned(
    state: State<'_, Arc<AppState>>,
    message_id: String,
    pinned: bool,
) -> Result<Message> {
    state.api()?.set_pinned(&message_id, pinned).await
}

#[tauri::command]
pub async fn channel_pins(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
) -> Result<Vec<Message>> {
    state.api()?.channel_pins(&channel_id).await
}

#[tauri::command]
pub async fn delete_message(state: State<'_, Arc<AppState>>, message_id: String) -> Result<()> {
    state.api()?.delete_message(&message_id).await?;
    state.cache.remove_message(&message_id)?;
    Ok(())
}

#[tauri::command]
pub async fn toggle_reaction(
    state: State<'_, Arc<AppState>>,
    message_id: String,
    emoji: String,
    add: bool,
) -> Result<()> {
    let api = state.api()?;
    if add {
        api.add_reaction(&message_id, &emoji).await
    } else {
        api.remove_reaction(&message_id, &emoji).await
    }
}

#[tauri::command]
pub async fn typing(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
    parent_id: Option<String>,
) -> Result<()> {
    state.realtime()?.typing(channel_id, parent_id)
}

// ── Outbox ──────────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn pending_messages(
    state: State<'_, Arc<AppState>>,
    channel_id: String,
) -> Result<Vec<llack_core::OutboxEntry>> {
    state.cache.outbox_for_channel(&channel_id)
}

#[tauri::command]
pub async fn drain_outbox(state: State<'_, Arc<AppState>>) -> Result<DrainReport> {
    state.sync()?.drain_outbox().await
}

#[tauri::command]
pub async fn retry_failed_messages(state: State<'_, Arc<AppState>>) -> Result<usize> {
    state.cache.retry_failed()
}

#[tauri::command]
pub async fn discard_pending_message(
    state: State<'_, Arc<AppState>>,
    entry_id: String,
) -> Result<()> {
    state.cache.discard(&entry_id)
}

// ── Search ──────────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn search(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    query: String,
) -> Result<serde_json::Value> {
    if query.trim().is_empty() {
        return Ok(serde_json::json!({
            "query": query, "channels": [], "people": [], "apps": [], "messages": []
        }));
    }
    state.api()?.search_everything(&workspace_id, &query).await
}

#[tauri::command]
pub async fn search_messages(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    query: String,
) -> Result<llack_core::SearchResponse> {
    state.api()?.search_messages(&workspace_id, &query).await
}

// ── Files ───────────────────────────────────────────────────────────────────

/// Read a local file and attach it to the workspace.
///
/// The path comes from the webview. Before the agent existed that was merely
/// broad; now it is the cheapest way around the agent's file policy — a
/// prompt-injected model that is refused `~/.ssh/id_rsa` through `host.read_file`
/// could otherwise ask the panel to attach it to a message and the file leaves
/// the machine anyway. So this goes through the same deny list, and it
/// canonicalises first: the list is lexical, and `Downloads/link → ~/.ssh` is
/// one symlink away otherwise.
#[tauri::command]
pub async fn upload_file(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    path: String,
) -> Result<llack_core::FileRef> {
    let requested = std::path::PathBuf::from(&path);
    let file_path = std::fs::canonicalize(&requested)
        .map_err(|e| Error::Other(format!("could not read {path}: {e}")))?;

    if let Some((rule, reason)) = llack_core::agent::policy::refuse_path(
        &file_path,
        llack_core::agent::policy::Access::Read,
        &state.path_context(),
    ) {
        // The rule id goes to the log, the reason to the user. Naming the rule
        // in the message would teach a caller which name to avoid next time.
        tracing::warn!(rule, path = %file_path.display(), "upload refused by path policy");
        return Err(Error::Other(reason.into()));
    }

    let filename = file_path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| Error::Other("could not read the file name".into()))?
        .to_string();
    let bytes = std::fs::read(&file_path)
        .map_err(|e| Error::Other(format!("could not read {path}: {e}")))?;
    let mime_type = guess_mime(&filename);

    state
        .api()?
        .upload_file(&workspace_id, &filename, mime_type, bytes)
        .await
}

#[tauri::command]
pub async fn download_file(
    state: State<'_, Arc<AppState>>,
    file_id: String,
    filename: String,
) -> Result<String> {
    let bytes = state.api()?.download_file(&file_id).await?;
    let downloads = state.data_dir.join("downloads");
    std::fs::create_dir_all(&downloads)
        .map_err(|e| Error::Other(format!("could not create the download folder: {e}")))?;
    let target = downloads.join(sanitise_download_name(&filename));
    std::fs::write(&target, bytes)
        .map_err(|e| Error::Other(format!("could not write {}: {e}", target.display())))?;
    Ok(target.to_string_lossy().to_string())
}

/// An image attachment as a data URL, for rendering inline in the transcript.
///
/// The preview channel, not the download channel: images only, capped, and
/// nothing touches the disk. The mime string goes into the URL, so anything
/// that could smuggle a second field past `data:` parsing is refused here —
/// the value came over IPC, not from a list this process built.
#[tauri::command]
pub async fn file_preview(
    state: State<'_, Arc<AppState>>,
    file_id: String,
    mime: String,
) -> Result<String> {
    const PREVIEW_BYTE_CAP: usize = 10 * 1024 * 1024;
    let clean_mime = mime
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '/' | '-' | '.' | '+'));
    if !mime.starts_with("image/") || !clean_mime {
        return Err(Error::Other("이미지만 미리 볼 수 있습니다.".into()));
    }
    let bytes = state.api()?.download_file(&file_id).await?;
    if bytes.len() > PREVIEW_BYTE_CAP {
        return Err(Error::Other("미리보기에는 너무 큰 파일입니다.".into()));
    }
    use base64::Engine as _;
    let encoded = base64::engine::general_purpose::STANDARD.encode(&bytes);
    Ok(format!("data:{mime};base64,{encoded}"))
}

// ── Mini-apps ───────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn list_installed_apps(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<Vec<llack_core::AppInstallation>> {
    state.api()?.list_installed_apps(&workspace_id).await
}

#[tauri::command]
pub async fn list_available_apps(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
) -> Result<Vec<llack_core::AppSummary>> {
    state.api()?.list_available_apps(&workspace_id).await
}

#[tauri::command]
pub async fn install_app(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    app_id: String,
    granted_scopes: Option<Vec<String>>,
) -> Result<llack_core::AppInstallation> {
    state
        .api()?
        .install_app(&workspace_id, &app_id, granted_scopes.as_deref())
        .await
}

#[tauri::command]
pub async fn add_link_app(
    state: State<'_, Arc<AppState>>,
    workspace_id: String,
    name: String,
    url: String,
) -> Result<llack_core::AppInstallation> {
    state.api()?.add_link_app(&workspace_id, &name, &url).await
}

#[tauri::command]
pub async fn uninstall_app(state: State<'_, Arc<AppState>>, installation_id: String) -> Result<()> {
    state.api()?.uninstall_app(&installation_id).await
}

/// Mint a panel session for a mini-app webview.
///
/// The returned `bridge_token` is short-lived and scoped to the installation.
/// The panel never receives the signed-in user's access token.
#[tauri::command]
pub async fn open_app_panel(
    state: State<'_, Arc<AppState>>,
    installation_id: String,
    channel_id: Option<String>,
) -> Result<PanelSession> {
    state
        .api()?
        .create_panel_session(&installation_id, channel_id.as_deref())
        .await
}

// ── Window & shell ──────────────────────────────────────────────────────────

#[tauri::command]
pub async fn set_presence(state: State<'_, Arc<AppState>>, presence: String) -> Result<()> {
    state.realtime()?.set_presence(presence)
}

/// Force a reconnect — used when the window regains focus after a sleep, where
/// the socket is often dead without having reported an error yet.
#[tauri::command]
pub async fn reconnect(state: State<'_, Arc<AppState>>) -> Result<()> {
    state.realtime()?.reconnect()
}

#[tauri::command]
pub async fn cache_stats(state: State<'_, Arc<AppState>>) -> Result<serde_json::Value> {
    let workspace_id = state.active_workspace();
    Ok(serde_json::json!({
        "data_dir": state.data_dir.to_string_lossy(),
        "pending_sends": state.cache.pending(1000)?.len(),
        "cached_channels": workspace_id
            .as_deref()
            .map(|id| state.cache.channels(id).map(|c| c.len()).unwrap_or(0))
            .unwrap_or(0),
    }))
}

/// Trim the local cache. Exposed so a user with a huge history can reclaim
/// disk without reinstalling.
#[tauri::command]
pub async fn prune_cache(
    state: State<'_, Arc<AppState>>,
    keep_per_channel: Option<u32>,
) -> Result<usize> {
    state.cache.prune(keep_per_channel.unwrap_or(500))
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/// Recompute the dock/taskbar badge from cached unread counters.
fn update_badge(app: &AppHandle, state: &Arc<AppState>, workspace_id: &str) {
    let Ok(sync) = state.sync() else { return };
    let Ok(total) = sync.badge_count(workspace_id) else {
        return;
    };

    // The UI also renders its own in-window badges.
    let _ = app.emit("llack://badge", serde_json::json!({ "count": total }));

    if let Some(window) = app.get_webview_window("main") {
        let count = if total > 0 { Some(total as i64) } else { None };
        // Not every platform supports a badge; ignore failures rather than
        // surfacing an error the user cannot act on.
        let _ = window.set_badge_count(count);
    }
}

fn hostname_label() -> String {
    std::env::var("HOSTNAME")
        .or_else(|_| std::env::var("COMPUTERNAME"))
        .unwrap_or_else(|_| format!("{} desktop", std::env::consts::OS))
}

fn guess_mime(filename: &str) -> &'static str {
    let extension = filename
        .rsplit('.')
        .next()
        .map(str::to_ascii_lowercase)
        .unwrap_or_default();
    match extension.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "pdf" => "application/pdf",
        "txt" | "log" => "text/plain; charset=utf-8",
        "md" => "text/markdown; charset=utf-8",
        "csv" => "text/csv; charset=utf-8",
        "json" => "application/json",
        "zip" => "application/zip",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "mp4" => "video/mp4",
        "mov" => "video/quicktime",
        _ => "application/octet-stream",
    }
}

/// Keep a downloaded file inside the downloads folder regardless of what the
/// server called it.
fn sanitise_download_name(filename: &str) -> String {
    let basename = filename.replace('\\', "/");
    let basename = basename.rsplit('/').next().unwrap_or("download");
    let cleaned: String = basename
        .chars()
        .filter(|c| !matches!(c, '\0' | ':' | '*' | '?' | '"' | '<' | '>' | '|'))
        .collect();
    let trimmed = cleaned.trim_matches('.').trim();
    if trimmed.is_empty() {
        "download".into()
    } else {
        trimmed.chars().take(200).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mime_guessing_covers_the_common_office_and_image_types() {
        assert_eq!(guess_mime("보고서.pdf"), "application/pdf");
        assert_eq!(guess_mime("screenshot.PNG"), "image/png");
        assert_eq!(
            guess_mime("매출.xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        );
        assert_eq!(guess_mime("no-extension"), "application/octet-stream");
    }

    #[test]
    fn download_names_cannot_escape_the_folder() {
        assert_eq!(sanitise_download_name("../../etc/passwd"), "passwd");
        assert_eq!(sanitise_download_name("..\\..\\win.ini"), "win.ini");
        assert_eq!(sanitise_download_name("보고서.pdf"), "보고서.pdf");
        assert_eq!(sanitise_download_name(".."), "download");
        assert_eq!(sanitise_download_name(""), "download");
        assert_eq!(sanitise_download_name("a:b?c*.txt"), "abc.txt");
    }
}
