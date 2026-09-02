//! Reading back what a previous tool stored.
//!
//! The read side of the RLM seam. Fixed verbs, not code: v1 lets the model
//! slice and filter a stored value, but not compute over one. That distinction
//! is the honest boundary between this and a real recursive-language-model
//! harness, and it is stated here so nobody mistakes one for the other.

use super::{schema, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::agent::store::ArtifactOp;
use crate::error::Result;

/// The most lines one query may return, whatever the model asks for. The point
/// of the store is that a large value stays out of the context; a `grep` that
/// matched everything would undo it.
const MAX_LINES: usize = 200;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![ToolSpec {
        name: "artifact.query".into(),
        description: "이전 도구가 저장한 값을 잘라 봅니다. \
                      head/tail/slice 로 창을 열거나, grep 으로 걸러내거나, \
                      count 로 크기만 확인합니다."
            .into(),
        input_schema: schema(
            serde_json::json!({
                "handle": { "type": "string", "description": "art_ 로 시작하는 핸들" },
                "op": {
                    "type": "string",
                    "enum": ["head", "tail", "slice", "grep", "count"],
                },
                "lines": { "type": "integer", "description": "head/tail 에서 가져올 줄 수" },
                "from": { "type": "integer", "description": "slice 시작 줄 (0-based)" },
                "to": { "type": "integer", "description": "slice 끝 줄 (제외)" },
                "pattern": { "type": "string", "description": "grep 에서 찾을 문자열" },
            }),
            &["handle", "op"],
        ),
        source: ToolSource::Builtin,
    }]
}

pub(super) fn query(
    ctx: &ToolContext<'_>,
    handle: &str,
    op: &str,
    args: &serde_json::Value,
) -> Result<ToolOutput> {
    let count = |key: &str, default: usize| {
        args.get(key)
            .and_then(|v| v.as_u64())
            .map(|n| n as usize)
            .unwrap_or(default)
    };

    let parsed = match op {
        "head" => ArtifactOp::Head {
            lines: count("lines", 40),
        },
        "tail" => ArtifactOp::Tail {
            lines: count("lines", 40),
        },
        "count" => ArtifactOp::Count,
        "slice" => {
            let from = count("from", 0);
            ArtifactOp::Slice {
                from,
                to: count("to", from + 40),
            }
        }
        "grep" => match args.get("pattern").and_then(|v| v.as_str()) {
            Some(pattern) => ArtifactOp::Grep {
                pattern: pattern.to_string(),
                limit: count("lines", 40),
            },
            // Told to the model rather than raised: a missing argument is
            // something it can fix on the next turn.
            None => return Ok(ToolOutput::error("grep 에는 pattern 인자가 필요합니다.")),
        },
        _ => return Ok(ToolOutput::error("알 수 없는 op 입니다.")),
    };

    let slice = ctx.store.query_artifact(handle, &parsed, MAX_LINES)?;
    Ok(ToolOutput::ok(
        serde_json::to_value(&slice).unwrap_or(serde_json::Value::Null),
    ))
}
