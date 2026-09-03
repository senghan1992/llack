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
            name: "host.write_file".into(),
            description: "이 컴퓨터에 파일을 씁니다. 이미 있으면 통째로 덮어씁니다. \
                          상위 디렉터리는 미리 존재해야 합니다. 매번 사용자 승인을 \
                          받으며, 승인 카드에 경로·크기·내용 미리보기가 보입니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "path": { "type": "string", "description": "절대 경로" },
                    "content": { "type": "string", "description": "파일 전체 내용 (UTF-8)" },
                }),
                &["path", "content"],
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
        ToolSpec {
            name: "host.screenshot".into(),
            description: "현재 화면을 캡처합니다. 다른 앱 창까지 모두 담기므로 승인을 \
                          받습니다. 원본 PNG 는 아티팩트로 저장하고, 축소한 이미지를 \
                          모델에게 함께 돌려줍니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "display": {
                        "type": "integer",
                        "description": "캡처할 디스플레이 번호 (생략 시 기본 화면)",
                        "minimum": 0,
                    },
                }),
                &[],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "host.click".into(),
            description: "화면의 한 지점을 클릭합니다. 지금 포커스된 창에 그대로 \
                          입력되므로 매번 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "x": { "type": "integer", "description": "화면 X 좌표" },
                    "y": { "type": "integer", "description": "화면 Y 좌표" },
                    "button": {
                        "type": "string",
                        "description": "left · right · middle (기본 left)",
                        "enum": ["left", "right", "middle"],
                    },
                }),
                &["x", "y"],
            ),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "host.type_text".into(),
            description: "키보드 입력을 흉내 내 글자를 칩니다. 포커스된 어떤 입력란에도 \
                          들어갈 수 있으므로 매번 승인을 받습니다."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "text": { "type": "string", "description": "입력할 텍스트" },
                }),
                &["text"],
            ),
            source: ToolSource::Builtin,
        },
    ]
}

pub(super) async fn exec(ctx: &ToolContext<'_>, argv: &[String], cwd: &Path) -> Result<ToolOutput> {
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

pub(super) async fn write_file(
    ctx: &ToolContext<'_>,
    path: &Path,
    content: &str,
) -> Result<ToolOutput> {
    ctx.host.write_file(path, content.as_bytes()).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "path": path.display().to_string(),
        "bytes_written": content.len(),
    })))
}

pub(super) async fn list_dir(ctx: &ToolContext<'_>, path: &Path) -> Result<ToolOutput> {
    let names = ctx.host.list_dir(path).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "path": path.display().to_string(),
        "entries": names,
    })))
}

pub(super) async fn screenshot(ctx: &ToolContext<'_>, display: Option<u32>) -> Result<ToolOutput> {
    let shot = ctx.host.screenshot(display).await?;
    // The full PNG is large, so it lands in the artifact store like a build log;
    // the model gets the downscaled image inline so it can actually look.
    let (_artifact, preview) = ctx.store.put_artifact(
        ctx.session_id,
        "screenshot",
        &shot.png_b64,
        serde_json::json!({ "display": display, "encoding": "base64", "mime": "image/png" }),
    )?;
    Ok(ToolOutput::with_artifact(
        serde_json::json!({
            "image_b64": shot.image_b64,
            "mime": shot.mime,
            "note": "원본 PNG 는 아티팩트로 저장했습니다.",
        }),
        preview.handle,
    ))
}

pub(super) async fn click(
    ctx: &ToolContext<'_>,
    x: i32,
    y: i32,
    button: &str,
) -> Result<ToolOutput> {
    ctx.host.click(x, y, button).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "clicked": { "x": x, "y": y, "button": button },
    })))
}

pub(super) async fn type_text(ctx: &ToolContext<'_>, text: &str) -> Result<ToolOutput> {
    ctx.host.type_text(text).await?;
    Ok(ToolOutput::ok(serde_json::json!({
        "typed_chars": text.chars().count(),
    })))
}
