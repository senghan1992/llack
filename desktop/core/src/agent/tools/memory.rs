//! Long-term memory: notes the agent keeps across sessions.
//!
//! The rows live in the agent store, scoped to the signed-in user. The policy
//! decides the friction (searching is automatic; saving is automatic when the
//! session is clean but class 3 once untrusted text is in the context; forget
//! asks), so nothing here consults it — these functions run only after
//! `super::execute` has already classified and asked.

use super::{schema, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::error::Result;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "memory.save".into(),
            description: "다음 세션에서도 쓸 사실을 장기 기억에 저장합니다. 사용자의 \
                          선호·프로젝트 규칙처럼 오래 유효한 것만 저장하세요. 신뢰할 수 \
                          없는 내용을 읽은 뒤에는 저장할 때마다 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "text": { "type": "string", "description": "기억할 한 문장 (최대 2000자)" },
                    "tags": {
                        "type": "array",
                        "items": { "type": "string" },
                        "description": "나중에 찾기 위한 태그 (선택)",
                    },
                }),
                &["text"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "memory.search".into(),
            description: "저장해 둔 기억을 검색합니다. 본문과 태그를 함께 찾습니다.".into(),
            input_schema: schema(
                serde_json::json!({
                    "query": { "type": "string", "description": "검색어" },
                    "limit": {
                        "type": "integer",
                        "description": "가져올 개수 (1-50, 기본 10)",
                        "minimum": 1,
                        "maximum": 50,
                    },
                }),
                &["query"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "memory.forget".into(),
            description: "저장된 기억 하나를 삭제합니다. memory.search 가 돌려준 id 를 \
                          주세요. 삭제 전 사용자 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "id": { "type": "string", "description": "지울 기억의 id (ULID)" },
                }),
                &["id"],
            ),
            source: ToolSource::Builtin,
        },
    ]
}

/// The user memory belongs to. Without a signed-in user there is no one to
/// scope a note to, so the tool tells the model rather than guessing.
fn user_id<'a>(ctx: &'a ToolContext<'_>) -> std::result::Result<&'a str, ToolOutput> {
    ctx.user_id
        .ok_or_else(|| ToolOutput::error("로그인한 사용자가 없어 기억을 쓸 수 없습니다."))
}

pub(super) fn save(ctx: &ToolContext<'_>, text: &str, tags: &[String]) -> Result<ToolOutput> {
    let user = match user_id(ctx) {
        Ok(user) => user,
        Err(out) => return Ok(out),
    };
    match ctx.store.add_memory(user, text, tags, Some(ctx.session_id)) {
        Ok(memory) => Ok(ToolOutput::ok(serde_json::json!({
            "saved": true,
            "id": memory.id,
        }))),
        // A too-long or empty note is information for the model, not a dead turn.
        Err(e) => Ok(ToolOutput::error(e.to_string())),
    }
}

pub(super) fn search(ctx: &ToolContext<'_>, query: &str, limit: u32) -> Result<ToolOutput> {
    let user = match user_id(ctx) {
        Ok(user) => user,
        Err(out) => return Ok(out),
    };
    let hits = ctx.store.search_memories(user, query, limit)?;
    Ok(ToolOutput::ok(serde_json::json!({
        "count": hits.len(),
        "memories": hits,
    })))
}

pub(super) fn forget(ctx: &ToolContext<'_>, id: &str) -> Result<ToolOutput> {
    let user = match user_id(ctx) {
        Ok(user) => user,
        Err(out) => return Ok(out),
    };
    ctx.store.delete_memory(user, id)?;
    Ok(ToolOutput::ok(serde_json::json!({ "forgotten": id })))
}
