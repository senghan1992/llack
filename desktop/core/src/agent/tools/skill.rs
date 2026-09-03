//! Skill tools: list and read the Markdown skill files.
//!
//! The parsing and filesystem rules live in [`crate::agent::skills`]; this
//! module only wires them to the catalog. The directory is handed in through
//! [`ToolContext::skills_dir`] so core never has to know the OS-specific
//! app-data path — the shell resolves it.
//!
//! Both tools are reads of the user's own notes, so the policy makes them
//! automatic. Writing a skill is not a tool the model can call: skills are
//! authored by the user, through a command, on purpose.

use super::{schema, ToolContext, ToolOutput, ToolSource, ToolSpec};
use crate::agent::skills;
use crate::error::Result;

pub(super) fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "skill.list".into(),
            description: "사용할 수 있는 스킬(재사용 가능한 지침 문서) 목록을 봅니다. \
                          각 항목은 이름·제목·한 줄 설명을 담습니다."
                .into(),
            input_schema: schema(serde_json::json!({}), &[]),
            source: ToolSource::Builtin,
        },
        ToolSpec {
            name: "skill.read".into(),
            description: "스킬 하나의 전체 내용을 읽습니다. skill.list 가 돌려준 이름을 \
                          주세요."
                .into(),
            input_schema: schema(
                serde_json::json!({
                    "name": { "type": "string", "description": "스킬 이름" },
                }),
                &["name"],
            ),
            source: ToolSource::Builtin,
        },
    ]
}

/// Where the skill files live. Without a directory (a headless context) there
/// are simply no skills, which the tool reports rather than erroring.
fn dir<'a>(ctx: &'a ToolContext<'_>) -> Option<&'a std::path::Path> {
    ctx.skills_dir.as_deref()
}

pub(super) fn list(ctx: &ToolContext<'_>) -> Result<ToolOutput> {
    let Some(dir) = dir(ctx) else {
        return Ok(ToolOutput::ok(serde_json::json!({ "skills": [] })));
    };
    let skills = skills::list(dir)?;
    Ok(ToolOutput::ok(serde_json::json!({ "skills": skills })))
}

pub(super) fn read(ctx: &ToolContext<'_>, name: &str) -> Result<ToolOutput> {
    let Some(dir) = dir(ctx) else {
        return Ok(ToolOutput::error("스킬 폴더가 없습니다."));
    };
    match skills::read(dir, name) {
        Ok(body) => Ok(ToolOutput::ok(serde_json::json!({
            "name": name,
            "body": body,
        }))),
        // A missing or ill-named skill is information for the model.
        Err(e) => Ok(ToolOutput::error(e.to_string())),
    }
}
