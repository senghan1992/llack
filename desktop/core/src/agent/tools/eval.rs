//! `artifact.eval`: compute over a stored value, safely.
//!
//! The read side of the RLM seam let the model *slice* an artifact; this lets
//! it *compute* over one — sum a column, count matches, reshape lines — without
//! pulling the whole thing into context. The script runs in [`rhai`], which has
//! no file, network or process access of its own, under a hard operation cap
//! and size limits, so a runaway or hostile script fails as an error rather
//! than as a hang or an escape. That is why the policy classes this at 0: it is
//! a calculator, not a side effect.
//!
//! The script sees two variables: `lines` (an array of the artifact's lines)
//! and `text` (the whole body). Its return value is stringified and stored as a
//! new artifact, so a large computed result stays out of context too.

use super::{schema, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::error::Result;

/// The ceiling on script work. High enough for a scan over a big artifact,
/// low enough that an accidental infinite loop ends in well under a second.
const MAX_OPERATIONS: u64 = 200_000;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![ToolSpec {
        name: "artifact.eval".into(),
        description: "저장된 아티팩트를 Rhai 스크립트로 계산합니다. \
                      `lines`(줄 배열)와 `text`(전체 문자열)를 읽을 수 있고, \
                      반환값이 새 아티팩트로 저장됩니다. 파일·네트워크 접근은 없습니다."
            .into(),
        input_schema: schema(
            serde_json::json!({
                "handle": { "type": "string", "description": "art_ 로 시작하는 핸들" },
                "script": {
                    "type": "string",
                    "description": "Rhai 스크립트. 예: `lines.filter(|l| l.contains(\"ERROR\")).len()`",
                },
            }),
            &["handle", "script"],
        ),
        source: ToolSource::Builtin,
    }]
}

pub(super) fn eval(ctx: &ToolContext<'_>, handle: &str, script: &str) -> Result<ToolOutput> {
    // Pull the whole body via a count query, then a slice of everything — the
    // store has no "give me the body" verb by design, so this reads it in one
    // large slice.
    let count = ctx
        .store
        .query_artifact(handle, &crate::agent::store::ArtifactOp::Count, 1)?;
    let total = count.total_lines;
    let slice = ctx.store.query_artifact(
        handle,
        &crate::agent::store::ArtifactOp::Slice { from: 0, to: total },
        // The eval path is allowed the whole artifact — the cap that protects
        // the *context* does not apply to what the sandbox reads internally.
        usize::MAX,
    )?;

    let mut engine = rhai::Engine::new();
    engine.set_max_operations(MAX_OPERATIONS);
    engine.set_max_string_size(1_000_000);
    engine.set_max_array_size(200_000);
    engine.set_max_call_levels(32);
    engine.set_max_expr_depths(64, 64);
    // `eval` inside the script would let it grow its own operation budget by
    // re-entering; disable it outright.
    engine.disable_symbol("eval");

    let mut scope = rhai::Scope::new();
    let lines: rhai::Array = slice
        .lines
        .iter()
        .map(|l| rhai::Dynamic::from(l.clone()))
        .collect();
    scope.push("lines", lines);
    scope.push("text", slice.lines.join("\n"));

    let result = engine.eval_with_scope::<rhai::Dynamic>(&mut scope, script);
    let output = match result {
        Ok(value) => value.to_string(),
        // A script error is information for the model — a typo or a cap hit is
        // something it can fix on the next turn, not a dead turn.
        Err(err) => return Ok(ToolOutput::error(format!("스크립트 오류: {err}"))),
    };

    let (artifact_handle, bytes) = ctx
        .store
        .store_text(ctx.session_id, "eval_result", &output)?;
    // Small results inline; large ones become a handle to query further.
    if bytes as usize <= crate::agent::store::INLINE_BYTE_LIMIT {
        Ok(ToolOutput::with_artifact(
            serde_json::json!({ "result": output }),
            artifact_handle,
        ))
    } else {
        Ok(ToolOutput::with_artifact(
            serde_json::json!({
                "bytes": bytes,
                "note": "결과가 커서 아티팩트로 저장했습니다. artifact.query 로 확인하세요.",
            }),
            artifact_handle,
        ))
    }
}
