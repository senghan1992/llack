//! Skills: reusable instructions the agent can pull in on demand.
//!
//! ## Why files, not rows
//!
//! A skill is a Markdown note — "how we cut a release", "the shape of our
//! webhook payloads" — that the user writes and the model reads verbatim.
//! Keeping each as a plain `.md` file under `{app_data}/agent-skills/` means a
//! user can edit one in their own editor, drop one in over a sync folder, or
//! read the whole set without this app running. A database would hide all of
//! that behind a tool this app alone can open.
//!
//! ## The split this module keeps
//!
//! Everything here is pure or touches only a directory it is handed: name
//! validation, the title/description parse, and the small set of filesystem
//! helpers. *Where* that directory lives — the OS-specific app-data path — is
//! resolved by the shell (`src-tauri`) and passed in. That keeps the parsing
//! rules unit-testable here and the platform path out of core.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};

/// The most characters a skill name may have. Names become filenames, so this
/// is a filesystem-friendliness cap as much as a UI one.
pub const NAME_MAX: usize = 40;

/// A skill as the picker lists it — never its body.
///
/// The body can be long; the list screen only needs enough to choose from, so
/// it carries the first-line title, the second-line description, and the size.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentSkill {
    /// The stem of the file, e.g. `release-checklist`. Also the tool argument.
    pub name: String,
    /// The first line, with a leading `# ` stripped. Empty if the file is.
    pub title: String,
    /// The second line, trimmed. Empty if the file has only one line.
    pub description: String,
    /// The body size in bytes on disk.
    pub bytes: u64,
}

/// Whether `name` is a legal skill name.
///
/// One to [`NAME_MAX`] characters, each an ASCII lowercase letter, digit, `-`,
/// or `_`. Deliberately narrow: the name is interpolated straight into a
/// filename, so anything that could climb out of the directory (`.`, `/`, `\`)
/// or surprise a filesystem (case, spaces, Unicode) is simply not a name.
pub fn valid_name(name: &str) -> bool {
    let len = name.len();
    (1..=NAME_MAX).contains(&len)
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
}

/// The path a skill of this name lives at, under `dir`.
///
/// Returns an error rather than a bad path when the name is illegal, so no
/// caller can turn an unchecked name into a write outside the directory.
pub fn skill_path(dir: &Path, name: &str) -> Result<PathBuf> {
    if !valid_name(name) {
        return Err(Error::Config(format!(
            "스킬 이름 '{name}' 은 소문자·숫자·'-'·'_' 만, 1~{NAME_MAX}자여야 합니다"
        )));
    }
    Ok(dir.join(format!("{name}.md")))
}

/// Parse a stored body into its list-view shape.
///
/// The contract, stated once so the tests and the docs agree: the title is the
/// first line with a single leading `# ` removed; the description is the second
/// line, trimmed. Both are best-effort — a malformed skill still lists, it just
/// shows what little it has.
pub fn parse(name: &str, body: &str, bytes: u64) -> AgentSkill {
    let mut lines = body.lines();
    let title = lines
        .next()
        .unwrap_or("")
        .trim_start_matches("# ")
        .trim_start_matches('#')
        .trim()
        .to_string();
    let description = lines.next().unwrap_or("").trim().to_string();
    AgentSkill {
        name: name.to_string(),
        title,
        description,
        bytes,
    }
}

/// List every skill in `dir`, sorted by name.
///
/// A missing directory is an empty list, not an error — a fresh install simply
/// has no skills yet. Files that are not `.md`, or whose stem is not a legal
/// name, are skipped so a stray file cannot break the screen.
pub fn list(dir: &Path) -> Result<Vec<AgentSkill>> {
    let mut skills = Vec::new();
    let entries = match std::fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(skills),
        Err(e) => return Err(Error::Other(format!("스킬 폴더를 읽지 못했습니다: {e}"))),
    };
    for entry in entries {
        let entry = entry.map_err(|e| Error::Other(format!("스킬 항목을 읽지 못했습니다: {e}")))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("md") {
            continue;
        }
        let Some(name) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        if !valid_name(name) {
            continue;
        }
        let body = std::fs::read_to_string(&path)
            .map_err(|e| Error::Other(format!("스킬 '{name}' 을 읽지 못했습니다: {e}")))?;
        skills.push(parse(name, &body, body.len() as u64));
    }
    skills.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(skills)
}

/// Read one skill's full body.
pub fn read(dir: &Path, name: &str) -> Result<String> {
    let path = skill_path(dir, name)?;
    std::fs::read_to_string(&path)
        .map_err(|e| Error::Other(format!("스킬 '{name}' 을 읽지 못했습니다: {e}")))
}

/// Write a skill, creating the directory if needed, and return its list shape.
pub fn save(dir: &Path, name: &str, body: &str) -> Result<AgentSkill> {
    let path = skill_path(dir, name)?;
    std::fs::create_dir_all(dir)
        .map_err(|e| Error::Other(format!("스킬 폴더를 만들지 못했습니다: {e}")))?;
    std::fs::write(&path, body)
        .map_err(|e| Error::Other(format!("스킬 '{name}' 을 저장하지 못했습니다: {e}")))?;
    Ok(parse(name, body, body.len() as u64))
}

/// Remove a skill. A skill that is already gone is not an error.
pub fn delete(dir: &Path, name: &str) -> Result<()> {
    let path = skill_path(dir, name)?;
    match std::fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(Error::Other(format!(
            "스킬 '{name}' 을 지우지 못했습니다: {e}"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(tag: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "llack-skills-{tag}-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn a_name_is_lowercase_alnum_dash_underscore_and_bounded() {
        assert!(valid_name("release-checklist"));
        assert!(valid_name("a"));
        assert!(valid_name("web_hook_2"));
        assert!(!valid_name(""), "empty is not a name");
        assert!(!valid_name("Release"), "uppercase is rejected");
        assert!(!valid_name("has space"));
        assert!(!valid_name("dots.bad"));
        assert!(!valid_name("../escape"), "no path climbing");
        assert!(!valid_name(&"x".repeat(NAME_MAX + 1)), "over the cap");
        assert!(valid_name(&"x".repeat(NAME_MAX)), "at the cap");
    }

    #[test]
    fn a_bad_name_never_produces_a_path() {
        let dir = Path::new("/tmp/skills");
        assert!(skill_path(dir, "../etc/passwd").is_err());
        assert!(skill_path(dir, "ok-name").is_ok());
    }

    #[test]
    fn parsing_pulls_the_title_off_the_first_line_and_the_description_off_the_second() {
        let s = parse(
            "rel",
            "# 릴리스 절차\n분기마다 한 번 수행합니다\n본문...",
            40,
        );
        assert_eq!(s.title, "릴리스 절차");
        assert_eq!(s.description, "분기마다 한 번 수행합니다");
        assert_eq!(s.name, "rel");
        assert_eq!(s.bytes, 40);
    }

    #[test]
    fn parsing_tolerates_a_missing_heading_marker_and_a_missing_second_line() {
        let bare = parse("x", "제목만 있고 마커 없음", 10);
        assert_eq!(bare.title, "제목만 있고 마커 없음");
        assert_eq!(bare.description, "");

        let empty = parse("x", "", 0);
        assert_eq!(empty.title, "");
        assert_eq!(empty.description, "");
    }

    #[test]
    fn save_then_list_and_read_round_trip_and_delete_removes() {
        let dir = temp_dir("round");
        let saved = save(&dir, "notes", "# 메모\n짧은 설명\n내용").unwrap();
        assert_eq!(saved.title, "메모");
        assert_eq!(saved.description, "짧은 설명");

        let listed = list(&dir).unwrap();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].name, "notes");

        assert_eq!(read(&dir, "notes").unwrap(), "# 메모\n짧은 설명\n내용");

        delete(&dir, "notes").unwrap();
        assert!(list(&dir).unwrap().is_empty());
        // Deleting again is a no-op, not an error.
        delete(&dir, "notes").unwrap();

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn listing_a_missing_directory_is_empty_and_skips_stray_files() {
        let dir = temp_dir("stray");
        assert!(
            list(&dir).unwrap().is_empty(),
            "no directory means no skills"
        );

        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("good.md"), "# 좋음\n설명").unwrap();
        std::fs::write(dir.join("notes.txt"), "무시됨").unwrap();
        std::fs::write(dir.join("Bad Name.md"), "무시됨").unwrap();

        let listed = list(&dir).unwrap();
        assert_eq!(listed.len(), 1, "only the legal .md is listed");
        assert_eq!(listed[0].name, "good");

        std::fs::remove_dir_all(&dir).ok();
    }
}
