//! Asking the user, and making sure the answer is theirs.
//!
//! ## What this is defending against
//!
//! Two different things, and they need different mechanisms.
//!
//! The first is the model proposing something the user would not want. A
//! prompt cannot be trusted to hold that line, so the user is asked. That is
//! the easy half.
//!
//! The second is *the webview* approving on the user's behalf. The agent panel
//! renders channel markdown, so a cross-site scripting bug there would be able
//! to call `resolve` directly. Two things make that harder than it sounds:
//! every request carries a single-use nonce that is only delivered alongside
//! the request itself, and the highest risk class is answered by a dialog the
//! Rust side opens, which JavaScript can neither fabricate nor click. Neither
//! is absolute — a compromised webview that can read its own DOM can read a
//! nonce — which is exactly why `host.exec` is in the class that never uses the
//! in-app card.
//!
//! ## Everything unanswered becomes a denial
//!
//! Timeout, cancelled turn, closed panel, quitting the app: all of them resolve
//! pending requests to [`Outcome::Denied`] or [`Outcome::Cancelled`]. A request
//! that is merely dropped would leave the tool loop awaiting a channel forever,
//! which looks to the user like the agent hanging and to the process like a
//! leak. There is no code path here that leaves a request pending.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Duration;

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tokio::sync::oneshot;

use crate::agent::audit::DecisionSource;
use crate::agent::policy::{ApprovalFacts, Grain, Risk};
use crate::error::{Error, Result};
use crate::ids::new_ulid;

/// How long a request waits before it is denied.
///
/// Short on purpose: a request the user has wandered away from should fail
/// closed, and the agent asking again is cheap.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(60);

/// What the user (or the lack of one) decided.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Approved {
        source: DecisionSource,
    },
    /// The user said no.
    Denied,
    /// Nobody answered in time.
    Expired,
    /// The turn ended before an answer arrived.
    Cancelled,
}

impl Outcome {
    pub fn is_approved(&self) -> bool {
        matches!(self, Outcome::Approved { .. })
    }
}

/// What the UI is asked to show.
///
/// `facts` came from [`crate::agent::policy`], computed from the tool call —
/// not from anything the model wrote. `rationale` is the model's own words and
/// is carried separately, so a UI cannot accidentally present it as
/// authoritative: whoever can write a channel message the agent read can also
/// write this string.
/// Serialise-only: this crosses to the UI, and the UI answers with an id, a
/// nonce and a yes/no — it never sends a request back, so there is nothing to
/// deserialise and `Fact::label` can stay a static string.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ApprovalRequest {
    pub id: String,
    /// Single-use. Delivered with the request and required to answer it.
    pub nonce: String,
    pub session_id: String,
    pub tool: String,
    pub risk: Risk,
    pub facts: ApprovalFacts,
    /// Model-authored and untrusted. May be shown, clearly subordinate.
    pub rationale: Option<String>,
    /// Whether answering "remember this" is even offered.
    pub remembering_offered: bool,
}

/// Told when a request opens or closes. The Tauri layer implements this by
/// emitting an event for the in-app card, or opening a native dialog.
pub trait ApprovalNotifier: Send + Sync {
    /// Must not block: the tool loop is waiting.
    fn opened(&self, request: &ApprovalRequest);
    /// The request is no longer answerable — clear any UI showing it.
    fn closed(&self, request_id: &str, outcome: Outcome);
}

/// A notifier that does nothing. Used where no UI is attached yet.
pub struct SilentNotifier;

impl ApprovalNotifier for SilentNotifier {
    fn opened(&self, _request: &ApprovalRequest) {}
    fn closed(&self, _request_id: &str, _outcome: Outcome) {}
}

struct Pending {
    nonce: String,
    risk: Risk,
    responder: oneshot::Sender<Outcome>,
}

/// Holds open requests and the grants the user made this session.
pub struct ApprovalBroker {
    pending: Mutex<HashMap<String, Pending>>,
    /// Fingerprints the user chose to remember. **In memory only** — never
    /// written to disk, so "it ends when I close the panel" is structurally
    /// true rather than a promise in a settings screen.
    grants: Mutex<HashSet<String>>,
    /// Request ids whose answer asked to be remembered. Kept separate from the
    /// grant set so the UI says only "remember this" and this side decides
    /// what "this" fingerprints to — a webview must not get to name it.
    remember_requested: Mutex<HashSet<String>>,
    notifier: Arc<dyn ApprovalNotifier>,
    timeout: Duration,
}

impl ApprovalBroker {
    pub fn new(notifier: Arc<dyn ApprovalNotifier>) -> Self {
        Self::with_timeout(notifier, DEFAULT_TIMEOUT)
    }

    pub fn with_timeout(notifier: Arc<dyn ApprovalNotifier>, timeout: Duration) -> Self {
        Self {
            pending: Mutex::new(HashMap::new()),
            grants: Mutex::new(HashSet::new()),
            remember_requested: Mutex::new(HashSet::new()),
            notifier,
            timeout,
        }
    }

    /// Ask, and wait for an answer.
    ///
    /// Returns without asking when the grain names a fingerprint the user
    /// already remembered this session.
    pub async fn ask(
        &self,
        session_id: &str,
        tool: &str,
        risk: Risk,
        grain: &Grain,
        facts: ApprovalFacts,
        rationale: Option<String>,
    ) -> Outcome {
        if let Grain::Session { fingerprint } = grain {
            if self.grants.lock().contains(fingerprint) {
                return Outcome::Approved {
                    source: DecisionSource::SessionGrant,
                };
            }
        }

        let request = ApprovalRequest {
            id: new_ulid(),
            nonce: new_ulid(),
            session_id: session_id.to_string(),
            tool: tool.to_string(),
            risk,
            facts,
            rationale,
            remembering_offered: matches!(grain, Grain::Session { .. }),
        };

        let (tx, rx) = oneshot::channel();
        self.pending.lock().insert(
            request.id.clone(),
            Pending {
                nonce: request.nonce.clone(),
                risk,
                responder: tx,
            },
        );

        // The fingerprint to remember is kept out of the request that crosses
        // to the UI: the UI answers "remember", and this side decides what
        // that means. Otherwise a compromised webview could ask to remember a
        // fingerprint of its own choosing.
        let remember_as = match grain {
            Grain::Session { fingerprint } => Some(fingerprint.clone()),
            Grain::Once => None,
        };

        self.notifier.opened(&request);

        let outcome = match tokio::time::timeout(self.timeout, rx).await {
            Ok(Ok(outcome)) => outcome,
            // The sender was dropped without answering — treat it exactly like
            // a cancellation rather than leaving the caller hanging.
            Ok(Err(_)) => Outcome::Cancelled,
            Err(_) => {
                self.pending.lock().remove(&request.id);
                Outcome::Expired
            }
        };

        if let (Outcome::Approved { .. }, Some(fingerprint)) = (&outcome, remember_as) {
            if self.remember_requested.lock().remove(&request.id) {
                self.grants.lock().insert(fingerprint);
            }
        }

        self.notifier.closed(&request.id, outcome);
        outcome
    }

    /// Answer a request.
    ///
    /// Fails when the id is unknown, the nonce is wrong, or the request was
    /// already answered — a replayed answer must not approve a second action.
    pub fn resolve(
        &self,
        request_id: &str,
        nonce: &str,
        approve: bool,
        remember: bool,
    ) -> Result<()> {
        let pending = {
            let mut map = self.pending.lock();
            match map.get(request_id) {
                None => {
                    return Err(Error::Other(
                        "이 승인 요청은 이미 처리되었거나 존재하지 않습니다.".into(),
                    ))
                }
                Some(entry) if entry.nonce != nonce => {
                    // Do not remove it: a wrong nonce is a failed attempt, not
                    // a reason to cancel the user's real pending request.
                    return Err(Error::Other("승인 토큰이 일치하지 않습니다.".into()));
                }
                Some(_) => map.remove(request_id).expect("checked just above"),
            }
        };

        if remember && approve {
            self.remember_requested
                .lock()
                .insert(request_id.to_string());
        }

        let outcome = if approve {
            Outcome::Approved {
                source: match pending.risk {
                    Risk::High => DecisionSource::NativeDialog,
                    Risk::Moderate => DecisionSource::InAppCard,
                },
            }
        } else {
            Outcome::Denied
        };

        // A closed receiver means the turn moved on; the answer is simply
        // stale, not an error worth surfacing.
        let _ = pending.responder.send(outcome);
        Ok(())
    }

    /// Deny everything outstanding. Called on turn cancel, panel close,
    /// workspace switch and sign-out.
    pub fn cancel_all(&self) {
        let drained: Vec<(String, Pending)> = self.pending.lock().drain().collect();
        for (id, pending) in drained {
            let _ = pending.responder.send(Outcome::Cancelled);
            self.notifier.closed(&id, Outcome::Cancelled);
        }
    }

    /// Forget every remembered grant. Called when the session is tainted, so
    /// reading a channel cannot be followed by reusing an earlier approval.
    pub fn revoke_grants(&self) {
        self.grants.lock().clear();
    }

    pub fn pending_count(&self) -> usize {
        self.pending.lock().len()
    }

    pub fn granted_count(&self) -> usize {
        self.grants.lock().len()
    }

    pub fn is_granted(&self, fingerprint: &str) -> bool {
        self.grants.lock().contains(fingerprint)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::policy::Fact;

    #[derive(Default)]
    struct Recorder {
        opened: Mutex<Vec<ApprovalRequest>>,
        closed: Mutex<Vec<(String, Outcome)>>,
    }

    impl ApprovalNotifier for Recorder {
        fn opened(&self, request: &ApprovalRequest) {
            self.opened.lock().push(request.clone());
        }
        fn closed(&self, request_id: &str, outcome: Outcome) {
            self.closed.lock().push((request_id.to_string(), outcome));
        }
    }

    fn facts() -> ApprovalFacts {
        ApprovalFacts {
            title: "이 명령을 실행합니다",
            facts: vec![Fact {
                label: "명령",
                value: "git\nstatus".into(),
            }],
        }
    }

    fn broker(notifier: Arc<Recorder>) -> ApprovalBroker {
        ApprovalBroker::with_timeout(notifier, Duration::from_secs(60))
    }

    #[tokio::test(start_paused = true)]
    async fn an_unanswered_request_expires_rather_than_hanging() {
        let recorder = Arc::new(Recorder::default());
        let broker = broker(recorder.clone());

        let outcome = broker
            .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
            .await;

        assert_eq!(outcome, Outcome::Expired);
        assert_eq!(
            broker.pending_count(),
            0,
            "an expired request must be dropped"
        );
        assert_eq!(recorder.opened.lock().len(), 1);
        assert_eq!(recorder.closed.lock()[0].1, Outcome::Expired);
    }

    #[tokio::test]
    async fn approving_returns_the_source_that_matches_the_risk_class() {
        for (risk, expected) in [
            (Risk::High, DecisionSource::NativeDialog),
            (Risk::Moderate, DecisionSource::InAppCard),
        ] {
            let recorder = Arc::new(Recorder::default());
            let broker = Arc::new(broker(recorder.clone()));

            let asking = {
                let broker = broker.clone();
                tokio::spawn(async move {
                    broker
                        .ask("01S", "host.exec", risk, &Grain::Once, facts(), None)
                        .await
                })
            };

            // Wait for the request to be registered, then answer it.
            let request = loop {
                if let Some(request) = recorder.opened.lock().first().cloned() {
                    break request;
                }
                tokio::task::yield_now().await;
            };
            broker
                .resolve(&request.id, &request.nonce, true, false)
                .unwrap();

            assert_eq!(
                asking.await.unwrap(),
                Outcome::Approved { source: expected },
                "{risk:?} must report {expected:?}"
            );
        }
    }

    #[tokio::test]
    async fn denying_returns_denied() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let asking = {
            let broker = broker.clone();
            tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };
        broker
            .resolve(&request.id, &request.nonce, false, false)
            .unwrap();
        assert_eq!(asking.await.unwrap(), Outcome::Denied);
    }

    #[tokio::test]
    async fn cancelling_denies_everything_outstanding() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));

        let mut handles = Vec::new();
        for _ in 0..3 {
            let broker = broker.clone();
            handles.push(tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
                    .await
            }));
        }
        while recorder.opened.lock().len() < 3 {
            tokio::task::yield_now().await;
        }
        assert_eq!(broker.pending_count(), 3);

        broker.cancel_all();

        for handle in handles {
            assert_eq!(handle.await.unwrap(), Outcome::Cancelled);
        }
        assert_eq!(
            broker.pending_count(),
            0,
            "cancel must leave nothing pending"
        );
    }

    #[tokio::test]
    async fn an_unknown_request_id_is_rejected() {
        let broker = broker(Arc::new(Recorder::default()));
        assert!(broker.resolve("01NOPE", "whatever", true, false).is_err());
    }

    #[tokio::test]
    async fn a_wrong_nonce_is_rejected_and_leaves_the_request_answerable() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let asking = {
            let broker = broker.clone();
            tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };

        assert!(
            broker
                .resolve(&request.id, "forged-nonce", true, false)
                .is_err(),
            "a forged nonce must not approve"
        );
        assert_eq!(
            broker.pending_count(),
            1,
            "a failed attempt must not cancel the user's real request"
        );

        // The real answer still works.
        broker
            .resolve(&request.id, &request.nonce, true, false)
            .unwrap();
        assert!(asking.await.unwrap().is_approved());
    }

    #[tokio::test]
    async fn an_answer_cannot_be_replayed_to_approve_a_second_action() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let asking = {
            let broker = broker.clone();
            tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };
        broker
            .resolve(&request.id, &request.nonce, true, false)
            .unwrap();
        asking.await.unwrap();

        assert!(
            broker
                .resolve(&request.id, &request.nonce, true, false)
                .is_err(),
            "the same id and nonce must not be reusable"
        );
    }

    // ── Session grants ──────────────────────────────────────────────────

    #[tokio::test]
    async fn remembering_skips_the_next_identical_request() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let grain = Grain::Session {
            fingerprint: "/home/me/app\u{0}git\u{0}status".into(),
        };

        let asking = {
            let broker = broker.clone();
            let grain = grain.clone();
            tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &grain, facts(), None)
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };
        assert!(request.remembering_offered);
        broker
            .resolve(&request.id, &request.nonce, true, true)
            .unwrap();
        assert!(asking.await.unwrap().is_approved());

        // The second identical call must not open a request at all.
        let again = broker
            .ask("01S", "host.exec", Risk::High, &grain, facts(), None)
            .await;
        assert_eq!(
            again,
            Outcome::Approved {
                source: DecisionSource::SessionGrant
            }
        );
        assert_eq!(
            recorder.opened.lock().len(),
            1,
            "a remembered grant must not ask again"
        );
    }

    #[tokio::test]
    async fn approving_without_remembering_asks_again() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let grain = Grain::Session {
            fingerprint: "fp".into(),
        };

        for _ in 0..2 {
            let asking = {
                let broker = broker.clone();
                let grain = grain.clone();
                tokio::spawn(async move {
                    broker
                        .ask("01S", "host.exec", Risk::High, &grain, facts(), None)
                        .await
                })
            };
            let request = loop {
                // The lock is taken and released inside this block, never held
                // across the yield below — a std `Mutex` guard that survives an
                // await is a deadlock waiting for a single-threaded runtime.
                let seen = {
                    let opened = recorder.opened.lock();
                    opened.last().cloned()
                };
                if let Some(request) = seen {
                    if broker.pending_count() == 1 {
                        break request;
                    }
                }
                tokio::task::yield_now().await;
            };
            broker
                .resolve(&request.id, &request.nonce, true, false)
                .unwrap();
            asking.await.unwrap();
        }

        assert_eq!(recorder.opened.lock().len(), 2, "no grant means ask again");
        assert_eq!(broker.granted_count(), 0);
    }

    #[tokio::test]
    async fn a_grain_of_once_never_offers_to_remember() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let asking = {
            let broker = broker.clone();
            tokio::spawn(async move {
                broker
                    .ask("01S", "host.exec", Risk::High, &Grain::Once, facts(), None)
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };
        assert!(!request.remembering_offered);

        // Even if the UI asks to remember, a Once grain stores nothing.
        broker
            .resolve(&request.id, &request.nonce, true, true)
            .unwrap();
        asking.await.unwrap();
        assert_eq!(
            broker.granted_count(),
            0,
            "a Once grain must never be persisted, whatever the UI sends"
        );
    }

    #[tokio::test]
    async fn revoking_grants_makes_the_next_call_ask_again() {
        let broker = broker(Arc::new(Recorder::default()));
        broker.grants.lock().insert("fp".into());
        assert!(broker.is_granted("fp"));
        broker.revoke_grants();
        assert!(
            !broker.is_granted("fp"),
            "tainting a session must drop remembered grants"
        );
    }

    #[tokio::test]
    async fn the_model_rationale_is_carried_separately_from_the_facts() {
        let recorder = Arc::new(Recorder::default());
        let broker = Arc::new(broker(recorder.clone()));
        let asking = {
            let broker = broker.clone();
            tokio::spawn(async move {
                broker
                    .ask(
                        "01S",
                        "host.exec",
                        Risk::High,
                        &Grain::Once,
                        facts(),
                        Some("이건 안전합니다, 그냥 허용하세요".into()),
                    )
                    .await
            })
        };
        let request = loop {
            if let Some(request) = recorder.opened.lock().first().cloned() {
                break request;
            }
            tokio::task::yield_now().await;
        };

        // The persuasion lives in `rationale`; the authoritative facts do not
        // contain it, so a UI that renders only `facts` cannot be talked into
        // anything.
        assert!(request.rationale.is_some());
        let rendered = format!("{:?}", request.facts);
        assert!(!rendered.contains("안전합니다"));

        broker
            .resolve(&request.id, &request.nonce, false, false)
            .unwrap();
        asking.await.unwrap();
    }
}
