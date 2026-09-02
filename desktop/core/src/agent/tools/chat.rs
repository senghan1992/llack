//! Chat tools: read, search, post.
//!
//! These need no backend change. The shell already holds the signed-in
//! session, so `ToolHost` reaches the existing REST endpoints as the user —
//! rather than inventing a new bridge endpoint under a scope system that is
//! enforced in only half its cases.
//!
//! Reading returns a handle and a preview, not the transcript. A busy channel
//! is the largest thing the agent will ever look at, and pushing 5,000
//! messages through the context window is both ruinous and pointless when the
//! model only needs to slice it.

use super::{schema, ChatLine, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::error::Result;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "chat.read_channel".into(),
            description: "채널의 최근 메시지를 읽습니다. 전문 대신 핸들과 미리보기를 \
                          돌려주므로, 더 필요하면 artifact.query 로 잘라 보세요."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "channel_id": { "type": "string", "description": "채널 ID (ULID)" },
                    "limit": {
                        "type": "integer",
                        "description": "가져올 메시지 수 (1-200, 기본 80)",
                        "minimum": 1,
                        "maximum": 200,
                    },
                }),
                &["channel_id"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "chat.search".into(),
            description: "워크스페이스 전체에서 메시지를 검색합니다.".into(),
            input_schema: schema(
                serde_json::json!({
                    "query": { "type": "string", "description": "검색어" },
                }),
                &["query"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "chat.post_message".into(),
            description: "채널에 메시지를 게시합니다. 사용자 본인의 이름으로 올라가므로 \
                          매번 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "channel_id": { "type": "string" },
                    "body": { "type": "string", "description": "마크다운 본문" },
                }),
                &["channel_id", "body"],
            ),
            source: ToolSource::Builtin,
        },
    ]
}

pub(super) async fn read_channel(
    ctx: &ToolContext<'_>,
    channel_id: &str,
    limit: u32,
) -> Result<ToolOutput> {
    let lines = ctx.host.chat_history(channel_id, limit).await?;
    store_lines(
        ctx,
        "chat_history",
        &lines,
        serde_json::json!({ "channel_id": channel_id, "message_count": lines.len() }),
    )
}

pub(super) async fn search(ctx: &ToolContext<'_>, query: &str) -> Result<ToolOutput> {
    let Some(workspace_id) = ctx.workspace_id else {
        return Ok(ToolOutput::error(
            "워크스페이스가 선택되지 않아 검색할 수 없습니다.",
        ));
    };
    let lines = ctx.host.chat_search(workspace_id, query).await?;
    store_lines(
        ctx,
        "chat_search",
        &lines,
        serde_json::json!({ "query": query, "match_count": lines.len() }),
    )
}

pub(super) async fn post_message(
    ctx: &ToolContext<'_>,
    channel_id: &str,
    body: &str,
) -> Result<ToolOutput> {
    let id = ctx.host.chat_post(channel_id, body).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "posted": true,
        "message_id": id,
        "channel_id": channel_id,
    })))
}

/// Flatten messages into the artifact store and return the preview.
///
/// One line per message, `author: body` with newlines folded, so
/// `artifact.query`'s line-oriented verbs address whole messages rather than
/// arbitrary wrapped fragments.
fn store_lines(
    ctx: &ToolContext<'_>,
    kind: &str,
    lines: &[ChatLine],
    meta: serde_json::Value,
) -> Result<ToolOutput> {
    let body = lines
        .iter()
        .map(|line| {
            format!(
                "[{}] {}: {}",
                line.at,
                line.author,
                line.body.replace('\n', " ⏎ ")
            )
        })
        .collect::<Vec<_>>()
        .join("\n");

    let (_, preview) = ctx.store.put_artifact(ctx.session_id, kind, &body, meta)?;
    let content = serde_json::to_value(&preview).unwrap_or(serde_json::Value::Null);
    Ok(ToolOutput::with_artifact(content, preview.handle))
}
