//! Acting on the user's own machine.
//!
//! Every function here is reachable only through `super::execute`, which has
//! already classified and asked. Nothing in this file consults the policy, and
//! nothing in this file is `pub` — that separation is what makes "the gate
//! cannot be skipped" a property of the module structure rather than a habit.
//!
//! `exec` takes an argv vector. There is no shell anywhere in this path, so a
//! command's arguments can never be reinterpreted as syntax.

use std::path::Path;

use super::{schema, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::agent::policy::AUTO_READ_BYTE_CAP;
use crate::error::Result;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "host.exec".into(),
            description: "이 컴퓨터에서 프로그램을 실행합니다. 셸을 거치지 않으므로 \
                          argv 배열로 주세요 (파이프·리다이렉트는 쓸 수 없습니다). \
                          실행 전 사용자 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "argv": {
                        "type": "array",
                        "items": { "type": "string" },
                        "description": "실행 파일과 인자. 예: [\"git\", \"status\"]",
                        "minItems": 1,
                    },
                    "cwd": { "type": "string", "description": "작업 디렉터리 (절대 경로)" },
                }),
                &["argv", "cwd"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "host.read_file".into(),
            description: "이 컴퓨터의 파일을 읽습니다.".into(),
            input_schema: schema(
                serde_json::json!({
                    "path": { "type": "string", "description": "절대 경로" },
                }),
                &["path"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "host.list_dir".into(),
            description: "이 컴퓨터의 디렉터리 목록을 봅니다.".into(),
            input_schema: schema(
                serde_json::json!({
                    "path": { "type": "string", "description": "절대 경로" },
                }),
                &["path"],
            ),
            source: ToolSource::Builtin,
        },
    ]
}

pub(super) async fn exec(
    ctx: &ToolContext<'_>,
    argv: &[String],
    cwd: &Path,
) -> Result<ToolOutput> {
    let out = ctx.host.exec(argv, cwd).await?;

    // Build output goes to the artifact store like a channel history does: a
    // 10 MB log must not choose between truncation and ruining the context.
    let combined = if out.stderr.is_empty() {
        out.stdout.clone()
    } else {
        format!("{}\n--- stderr ---\n{}", out.stdout, out.stderr)
    };

    let (_, preview) = ctx.store.put_artifact(
        ctx.session_id,
        "exec_output",
        &combined,
        serde_json::json!({
            "argv": argv,
            "cwd": cwd.display().to_string(),
            "exit_code": out.exit_code,
            "timed_out": out.timed_out,
        }),
    )?;

    Ok(ToolOutput::with_artifact(
        serde_json::json!({
            "exit_code": out.exit_code,
            "timed_out": out.timed_out,
            "duration_ms": out.duration_ms,
            "output": preview,
        }),
        preview.handle.clone(),
    ))
}

pub(super) async fn read_file(ctx: &ToolContext<'_>, path: &Path) -> Result<ToolOutput> {
    let bytes = ctx.host.read_file(path, AUTO_READ_BYTE_CAP).await?;
    // Lossy on purpose: a binary file should come back as something the model
    // can reason about ("this is not text") rather than as an error that hides
    // what the file was.
    let text = String::from_utf8_lossy(&bytes).to_string();
    let (_, preview) = ctx.store.put_artifact(
        ctx.session_id,
        "file",
        &text,
        serde_json::json!({ "path": path.display().to_string(), "bytes": bytes.len() }),
    )?;
    let content = serde_json::to_value(&preview).unwrap_or(serde_json::Value::Null);
    Ok(ToolOutput::with_artifact(content, preview.handle))
}

pub(super) async fn list_dir(ctx: &ToolContext<'_>, path: &Path) -> Result<ToolOutput> {
    let names = ctx.host.list_dir(path).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "path": path.display().to_string(),
        "entries": names,
    })))
}
