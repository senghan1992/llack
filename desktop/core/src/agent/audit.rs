//! An append-only record of everything the agent tried to do.
//!
//! ## Why append-only, specifically here
//!
//! The subject of this log can write files and run programs. A mutable log is
//! one approved `host.exec` away from being rewritten by the very actor it
//! exists to hold accountable — and the entry that would be erased is exactly
//! the one you would want to read. So: opens are append-only, and each line
//! carries `prev`, the SHA-256 of the line before it. Editing or truncating
//! the middle of the file breaks the chain at that point, and [`verify`] says
//! where.
//!
//! ## Why two records per call
//!
//! Every tool call writes an `intent` record *before* the executor runs and an
//! `outcome` record after. If the process is killed, the machine loses power,
//! or a command hangs until the user force-quits, a single post-hoc record
//! would leave nothing at all — and that is precisely the case worth
//! reconstructing. Two records cost one extra line and turn "we have no idea"
//! into "it started this and never finished".
//!
//! ## What is deliberately not recorded
//!
//! File contents, command stdout and stderr bodies, and message bodies. Only
//! sizes and hashes. An audit log that copies every secret the agent touched
//! into a second at-rest file is not a control, it is a liability — and this
//! file is not itself protected by the policy that guards the originals.
//!
//! ## The honest limit of the chain
//!
//! A hash chain stored next to the data it protects is tamper-*evident* only
//! while the head is anchored somewhere the writer cannot reach. The head goes
//! into the OS keychain when one is available. On macOS the keychain ACL is
//! per-signed-binary, so a child process the agent spawns cannot silently
//! overwrite it. On Linux Secret Service there is no per-binary ACL, so on
//! Linux the anchor raises the cost of tampering without making it impossible.
//! Stated here rather than implied, because an overstated guarantee is worse
//! than a modest one.

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use time::format_description::well_known::Rfc3339;
use time::macros::format_description;
use time::OffsetDateTime;

use crate::error::{Error, Result};
use crate::session::TokenStore;

/// The hash written as `prev` on the first line of a chain.
pub const CHAIN_GENESIS: &str = "genesis";

/// Which half of a tool call a record describes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    /// Written before the executor runs.
    Intent,
    /// Written after it finishes, fails, or is refused.
    Outcome,
}

/// What happened to a tool call.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    /// The policy allowed it without asking.
    Auto,
    /// The user approved it.
    Approved,
    /// The user declined it.
    Denied,
    /// The policy refused it; no approval could have helped.
    Refused,
    /// Nobody answered in time.
    Expired,
    /// The turn was cancelled before a decision.
    Cancelled,
}

/// Where an allow came from. Distinguishing these is what lets you answer
/// "did I actually approve that, or did something reuse an old approval".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecisionSource {
    PolicyAuto,
    SessionGrant,
    NativeDialog,
    InAppCard,
    Policy,
}

/// Who and where, for one agent session. Constant across a session's records.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditActor {
    pub session_id: String,
    pub user_id: Option<String>,
    pub server_url: Option<String>,
    pub workspace_id: Option<String>,
}

/// One line of the log.
///
/// `args` holds the canonical, already-sanitised description of the call — the
/// literal argv, the resolved absolute path, a byte count. Never the payload.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditRecord {
    pub ts: String,
    pub seq: u64,
    pub prev: String,
    pub phase: Phase,
    #[serde(flatten)]
    pub actor: AuditActor,
    pub tool: String,
    pub args: serde_json::Value,
    pub risk: String,
    pub tainted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verdict: Option<Verdict>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub decision_source: Option<DecisionSource>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub matched_rule: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exit_code: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_bytes: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
}

/// The parts of a record a caller supplies; the log fills in the rest.
#[derive(Debug, Clone)]
pub struct AuditEntry {
    pub phase: Phase,
    pub tool: String,
    pub args: serde_json::Value,
    pub risk: String,
    pub tainted: bool,
    pub verdict: Option<Verdict>,
    pub decision_source: Option<DecisionSource>,
    pub matched_rule: Option<String>,
    pub duration_ms: Option<u64>,
    pub exit_code: Option<i32>,
    pub output_bytes: Option<u64>,
    pub output_sha256: Option<String>,
    pub error_code: Option<String>,
}

impl AuditEntry {
    /// An intent record: what the agent is about to attempt.
    pub fn intent(tool: impl Into<String>, args: serde_json::Value, risk: impl Into<String>) -> Self {
        Self {
            phase: Phase::Intent,
            tool: tool.into(),
            args,
            risk: risk.into(),
            tainted: false,
            verdict: None,
            decision_source: None,
            matched_rule: None,
            duration_ms: None,
            exit_code: None,
            output_bytes: None,
            output_sha256: None,
            error_code: None,
        }
    }

    /// An outcome record: what happened.
    pub fn outcome(tool: impl Into<String>, verdict: Verdict) -> Self {
        Self {
            phase: Phase::Outcome,
            tool: tool.into(),
            args: serde_json::Value::Null,
            risk: String::new(),
            tainted: false,
            verdict: Some(verdict),
            decision_source: None,
            matched_rule: None,
            duration_ms: None,
            exit_code: None,
            output_bytes: None,
            output_sha256: None,
            error_code: None,
        }
    }

    pub fn tainted(mut self, tainted: bool) -> Self {
        self.tainted = tainted;
        self
    }

    pub fn rule(mut self, rule: impl Into<String>) -> Self {
        self.matched_rule = Some(rule.into());
        self
    }

    pub fn source(mut self, source: DecisionSource) -> Self {
        self.decision_source = Some(source);
        self
    }

    /// Record the *shape* of an output, never the output.
    pub fn output(mut self, bytes: &[u8]) -> Self {
        self.output_bytes = Some(bytes.len() as u64);
        self.output_sha256 = Some(hex(&Sha256::digest(bytes)));
        self
    }

    pub fn exit_code(mut self, code: i32) -> Self {
        self.exit_code = Some(code);
        self
    }

    pub fn duration_ms(mut self, ms: u64) -> Self {
        self.duration_ms = Some(ms);
        self
    }

    pub fn error_code(mut self, code: impl Into<String>) -> Self {
        self.error_code = Some(code.into());
        self
    }
}

struct Chain {
    seq: u64,
    prev: String,
}

/// The log. One per agent-capable process.
pub struct AuditLog {
    dir: PathBuf,
    actor: AuditActor,
    anchor: Option<Arc<dyn TokenStore>>,
    anchor_account: String,
    chain: Mutex<Chain>,
}

impl AuditLog {
    /// Open (or create) the log directory and pick up where the chain left off.
    ///
    /// `anchor` is the keychain, when one is available. When it is, the stored
    /// head is compared against what the files actually say and a mismatch is
    /// surfaced by [`AuditLog::anchor_matches`] rather than by refusing to
    /// start — an agent that will not run because its log was touched is a
    /// denial of service on the user, not a protection.
    pub fn open(
        dir: impl Into<PathBuf>,
        actor: AuditActor,
        anchor: Option<Arc<dyn TokenStore>>,
    ) -> Result<Self> {
        let dir = dir.into();
        std::fs::create_dir_all(&dir)
            .map_err(|e| Error::Other(format!("could not create the audit directory: {e}")))?;
        restrict(&dir);

        let (seq, prev) = tail_of_chain(&dir)?;
        let anchor_account = format!(
            "audit-head:{}",
            actor.user_id.as_deref().unwrap_or("anonymous")
        );

        Ok(Self {
            dir,
            actor,
            anchor,
            anchor_account,
            chain: Mutex::new(Chain { seq, prev }),
        })
    }

    /// Append one record. Returns its sequence number.
    ///
    /// Flushed and `sync_data`'d before returning: a record that is still in a
    /// buffer when the machine loses power did not happen, and the whole point
    /// of the intent record is to survive exactly that.
    pub fn append(&self, entry: AuditEntry) -> Result<u64> {
        let now = OffsetDateTime::now_utc();
        let mut chain = self.chain.lock();

        let record = AuditRecord {
            ts: now.format(&Rfc3339).unwrap_or_else(|_| String::from("unknown")),
            seq: chain.seq + 1,
            prev: chain.prev.clone(),
            phase: entry.phase,
            actor: self.actor.clone(),
            tool: entry.tool,
            args: entry.args,
            risk: entry.risk,
            tainted: entry.tainted,
            verdict: entry.verdict,
            decision_source: entry.decision_source,
            matched_rule: entry.matched_rule,
            duration_ms: entry.duration_ms,
            exit_code: entry.exit_code,
            output_bytes: entry.output_bytes,
            output_sha256: entry.output_sha256,
            error_code: entry.error_code,
        };

        let line = serde_json::to_string(&record)
            .map_err(|e| Error::Other(format!("could not encode an audit record: {e}")))?;

        let path = self.dir.join(file_name_for(now));
        let mut file = OpenOptions::new()
            .append(true)
            .create(true)
            .open(&path)
            .map_err(|e| Error::Other(format!("could not open the audit log: {e}")))?;
        restrict(&path);

        file.write_all(line.as_bytes())
            .and_then(|_| file.write_all(b"\n"))
            .and_then(|_| file.flush())
            .and_then(|_| file.sync_data())
            .map_err(|e| Error::Other(format!("could not write an audit record: {e}")))?;

        chain.seq = record.seq;
        chain.prev = hex(&Sha256::digest(line.as_bytes()));

        // Best effort: a keychain that is unavailable must not stop the agent.
        if let Some(anchor) = &self.anchor {
            let head = format!("{}:{}", chain.seq, chain.prev);
            let _ = anchor.save(&self.anchor_account, &head);
        }

        Ok(record.seq)
    }

    /// Whether the keychain's head still matches the files.
    ///
    /// `Ok(None)` means there is no anchor to compare against.
    pub fn anchor_matches(&self) -> Result<Option<bool>> {
        let Some(anchor) = &self.anchor else {
            return Ok(None);
        };
        let Some(stored) = anchor.load(&self.anchor_account)? else {
            return Ok(None);
        };
        let chain = self.chain.lock();
        let expected = format!("{}:{}", chain.seq, chain.prev);
        Ok(Some(stored == expected))
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }
}

/// What a verification pass concluded.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifyReport {
    pub records: u64,
    /// The sequence number of the first record whose `prev` did not match, if
    /// any. `Some` means the file was edited, truncated, or reordered.
    pub broken_at: Option<u64>,
    pub head: String,
}

impl VerifyReport {
    pub fn is_intact(&self) -> bool {
        self.broken_at.is_none()
    }
}

/// Walk every log file in order and check the chain.
pub fn verify(dir: impl AsRef<Path>) -> Result<VerifyReport> {
    let mut prev = CHAIN_GENESIS.to_string();
    let mut records = 0u64;
    let mut broken_at = None;

    for path in log_files(dir.as_ref())? {
        let file = File::open(&path)
            .map_err(|e| Error::Other(format!("could not read {}: {e}", path.display())))?;
        for line in BufReader::new(file).lines() {
            let line =
                line.map_err(|e| Error::Other(format!("could not read an audit line: {e}")))?;
            if line.trim().is_empty() {
                continue;
            }
            records += 1;

            let parsed: AuditRecord = match serde_json::from_str(&line) {
                Ok(parsed) => parsed,
                Err(_) => {
                    broken_at.get_or_insert(records);
                    continue;
                }
            };
            if parsed.prev != prev {
                broken_at.get_or_insert(parsed.seq);
            }
            prev = hex(&Sha256::digest(line.as_bytes()));
        }
    }

    Ok(VerifyReport {
        records,
        broken_at,
        head: prev,
    })
}

/// Read every record, oldest first. For the "what did it do on my machine"
/// screen; not on any hot path.
pub fn read_all(dir: impl AsRef<Path>) -> Result<Vec<AuditRecord>> {
    let mut out = Vec::new();
    for path in log_files(dir.as_ref())? {
        let file = File::open(&path)
            .map_err(|e| Error::Other(format!("could not read {}: {e}", path.display())))?;
        for line in BufReader::new(file).lines() {
            let line =
                line.map_err(|e| Error::Other(format!("could not read an audit line: {e}")))?;
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(record) = serde_json::from_str::<AuditRecord>(&line) {
                out.push(record);
            }
        }
    }
    Ok(out)
}

/// Log files, sorted by name — which is date order, because of the filename.
fn log_files(dir: &Path) -> Result<Vec<PathBuf>> {
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .map_err(|e| Error::Other(format!("could not list the audit directory: {e}")))?
        .filter_map(|entry| entry.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|ext| ext == "jsonl"))
        .collect();
    files.sort();
    Ok(files)
}

/// The last sequence number and chain hash on disk.
fn tail_of_chain(dir: &Path) -> Result<(u64, String)> {
    let report = verify(dir)?;
    // `records` is the count; the last record's own seq is what we continue
    // from, so read it rather than assuming they agree — a log that was
    // truncated at the front would make them differ.
    let last_seq = read_all(dir)?.last().map(|r| r.seq).unwrap_or(0);
    Ok((last_seq, report.head))
}

fn file_name_for(now: OffsetDateTime) -> String {
    let format = format_description!("[year]-[month]-[day]");
    let date = now
        .date()
        .format(&format)
        .unwrap_or_else(|_| String::from("unknown"));
    format!("{date}.jsonl")
}

fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write;
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// Owner-only, where the platform has a notion of that.
#[cfg(unix)]
fn restrict(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    if let Ok(meta) = std::fs::metadata(path) {
        let mut perms = meta.permissions();
        perms.set_mode(if meta.is_dir() { 0o700 } else { 0o600 });
        let _ = std::fs::set_permissions(path, perms);
    }
}

#[cfg(not(unix))]
fn restrict(_path: &Path) {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::MemoryTokenStore;

    fn actor() -> AuditActor {
        AuditActor {
            session_id: "01SESSION".into(),
            user_id: Some("01ALICE".into()),
            server_url: Some("http://localhost:8000".into()),
            workspace_id: Some("01WS".into()),
        }
    }

    fn temp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "llack-audit-{tag}-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        dir
    }

    fn exec_args() -> serde_json::Value {
        serde_json::json!({ "argv": ["git", "status"], "cwd": "/home/me/app" })
    }

    #[test]
    fn a_call_writes_an_intent_before_an_outcome() {
        let dir = temp_dir("order");
        let log = AuditLog::open(&dir, actor(), None).unwrap();

        log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
            .unwrap();
        log.append(
            AuditEntry::outcome("host.exec", Verdict::Approved)
                .source(DecisionSource::NativeDialog)
                .exit_code(0)
                .output(b"nothing to commit\n")
                .duration_ms(12),
        )
        .unwrap();

        let records = read_all(&dir).unwrap();
        assert_eq!(records.len(), 2);
        assert_eq!(records[0].phase, Phase::Intent);
        assert_eq!(records[1].phase, Phase::Outcome);
        assert_eq!(records[0].seq, 1);
        assert_eq!(records[1].seq, 2);

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn the_chain_links_and_verifies() {
        let dir = temp_dir("chain");
        let log = AuditLog::open(&dir, actor(), None).unwrap();
        for _ in 0..5 {
            log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
                .unwrap();
        }

        let report = verify(&dir).unwrap();
        assert_eq!(report.records, 5);
        assert!(report.is_intact());

        let records = read_all(&dir).unwrap();
        assert_eq!(records[0].prev, CHAIN_GENESIS);
        assert_ne!(records[1].prev, CHAIN_GENESIS);

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn editing_a_line_breaks_the_chain_at_that_line() {
        let dir = temp_dir("tamper");
        {
            let log = AuditLog::open(&dir, actor(), None).unwrap();
            for _ in 0..4 {
                log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
                    .unwrap();
            }
        }

        // Rewrite record 2 to hide what was run — the classic move.
        let path = log_files(&dir).unwrap().remove(0);
        let text = std::fs::read_to_string(&path).unwrap();
        let mut lines: Vec<String> = text.lines().map(String::from).collect();
        lines[1] = lines[1].replace("git", "innocent");
        std::fs::write(&path, lines.join("\n") + "\n").unwrap();

        let report = verify(&dir).unwrap();
        assert!(!report.is_intact());
        // Line 2 still claims the right `prev`, so the break surfaces on the
        // line that follows it.
        assert_eq!(report.broken_at, Some(3));

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn truncating_the_tail_is_detected_by_the_anchor_not_by_the_chain() {
        let dir = temp_dir("truncate");
        let store: Arc<dyn TokenStore> = Arc::new(MemoryTokenStore::default());
        let log = AuditLog::open(&dir, actor(), Some(store.clone())).unwrap();
        for _ in 0..3 {
            log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
                .unwrap();
        }
        assert_eq!(log.anchor_matches().unwrap(), Some(true));

        // Chop the last record. The remaining chain is internally consistent —
        // which is exactly why the head has to live somewhere else.
        let path = log_files(&dir).unwrap().remove(0);
        let text = std::fs::read_to_string(&path).unwrap();
        let kept: Vec<&str> = text.lines().take(2).collect();
        std::fs::write(&path, kept.join("\n") + "\n").unwrap();

        assert!(
            verify(&dir).unwrap().is_intact(),
            "a truncated chain still verifies internally"
        );

        let reopened = AuditLog::open(&dir, actor(), Some(store)).unwrap();
        assert_eq!(
            reopened.anchor_matches().unwrap(),
            Some(false),
            "the anchor must not match a truncated file"
        );

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn reopening_continues_the_chain_instead_of_restarting_it() {
        let dir = temp_dir("reopen");
        {
            let log = AuditLog::open(&dir, actor(), None).unwrap();
            log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
                .unwrap();
            log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
                .unwrap();
        }
        let log = AuditLog::open(&dir, actor(), None).unwrap();
        let seq = log
            .append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
            .unwrap();
        assert_eq!(seq, 3, "a reopened log must not reuse sequence numbers");
        assert!(verify(&dir).unwrap().is_intact());

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn output_is_recorded_as_a_size_and_a_hash_never_as_content() {
        let dir = temp_dir("noleak");
        let log = AuditLog::open(&dir, actor(), None).unwrap();
        let secret = b"AKIAIOSFODNN7EXAMPLE super secret token";
        log.append(AuditEntry::outcome("host.exec", Verdict::Approved).output(secret))
            .unwrap();

        let raw = std::fs::read_to_string(log_files(&dir).unwrap().remove(0)).unwrap();
        assert!(
            !raw.contains("AKIAIOSFODNN7EXAMPLE"),
            "the log must never contain the output itself"
        );
        let record = &read_all(&dir).unwrap()[0];
        assert_eq!(record.output_bytes, Some(secret.len() as u64));
        assert_eq!(record.output_sha256.as_ref().unwrap().len(), 64);

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_refusal_records_the_rule_that_refused_it() {
        let dir = temp_dir("refusal");
        let log = AuditLog::open(&dir, actor(), None).unwrap();
        log.append(
            AuditEntry::outcome("host.exec", Verdict::Refused)
                .rule("exec_privilege_elevation")
                .source(DecisionSource::Policy),
        )
        .unwrap();

        let record = &read_all(&dir).unwrap()[0];
        assert_eq!(record.verdict, Some(Verdict::Refused));
        assert_eq!(
            record.matched_rule.as_deref(),
            Some("exec_privilege_elevation")
        );

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn an_empty_directory_verifies_as_intact_with_no_records() {
        let dir = temp_dir("empty");
        let report = verify(&dir).unwrap();
        assert_eq!(report.records, 0);
        assert!(report.is_intact());
        assert_eq!(report.head, CHAIN_GENESIS);
    }

    #[cfg(unix)]
    #[test]
    fn the_log_is_owner_only() {
        use std::os::unix::fs::PermissionsExt;
        let dir = temp_dir("perms");
        let log = AuditLog::open(&dir, actor(), None).unwrap();
        log.append(AuditEntry::intent("host.exec", exec_args(), "approve_high"))
            .unwrap();

        let dir_mode = std::fs::metadata(&dir).unwrap().permissions().mode() & 0o777;
        assert_eq!(dir_mode, 0o700, "got {dir_mode:o}");
        let file = log_files(&dir).unwrap().remove(0);
        let file_mode = std::fs::metadata(&file).unwrap().permissions().mode() & 0o777;
        assert_eq!(file_mode, 0o600, "got {file_mode:o}");

        std::fs::remove_dir_all(&dir).ok();
    }
}
