//! The byte proxy: the only thing on this machine that touches the API key.
//!
//! ## Why a proxy at all
//!
//! The conversation loop lives in TypeScript, because that is where the
//! official SDK is and where API drift — SSE framing, `input_json_delta`
//! accumulation, `stop_reason` values, `output_config` — is somebody else's
//! maintenance burden. The key cannot live there, because the same webview
//! renders untrusted markdown from a channel.
//!
//! Both are satisfiable at once. The SDK accepts a custom `fetch`. That `fetch`
//! calls into Rust, Rust vets the request, injects the key from the keychain,
//! and streams the raw response bytes back. Rust never parses SSE — it does not
//! know what a `content_block_delta` is, and it stays that way on purpose.
//!
//! What this buys, precisely: a webview XSS can *use* the key for as long as
//! the app is open, but cannot *read* it, cannot persist it, and cannot use it
//! after the window closes. That is a smaller prize than a key in
//! `localStorage`, which is exfiltrated once and used forever.
//!
//! ## What lives here rather than in `src-tauri`
//!
//! Everything that can be decided without a network socket: the host and path
//! allowlist, which client headers survive, which are forged, and what the key
//! must look like. That is the part worth testing, and `src-tauri` cannot be
//! compiled in every environment this repo is worked on. The streaming glue
//! there is deliberately thin.

use crate::error::{Error, ProviderErrorCode, Result};

use super::credential::CredentialStore;

/// The only host the proxy will talk to.
///
/// A single constant rather than configuration. The moment this is a setting,
/// "point the agent at my company's gateway" and "point the agent at the
/// attacker's collector" are the same feature — and the request carries a live
/// API key.
pub const ALLOWED_HOST: &str = "api.anthropic.com";

/// The API version pinned for outbound requests.
pub const ANTHROPIC_VERSION: &str = "2023-06-01";

/// Client headers the proxy will forward.
///
/// An allowlist, not a denylist. A denylist has to anticipate every header that
/// could redirect, authenticate, or split a request; this only has to name the
/// four the SDK actually needs.
const FORWARDABLE: &[&str] = &[
    "content-type",
    "accept",
    "anthropic-beta",
    "x-stainless-retry-count",
];

/// A request that has passed every check and is ready to send.
///
/// `headers` is final: it already contains the injected key, and nothing the
/// caller passed can still be in it unless it was on [`FORWARDABLE`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VettedRequest {
    pub url: String,
    pub method: &'static str,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl VettedRequest {
    /// The headers with the key replaced, for logging.
    pub fn redacted_headers(&self) -> Vec<(String, String)> {
        self.headers
            .iter()
            .map(|(name, value)| {
                if name == "x-api-key" {
                    (name.clone(), "***".into())
                } else {
                    (name.clone(), value.clone())
                }
            })
            .collect()
    }
}

/// Reject anything that cannot appear in an HTTP header value.
///
/// CR and LF are request splitting. NUL and the other C0 controls are how a
/// header value smuggles a second header past a lenient parser.
fn header_value_is_sane(value: &str) -> bool {
    !value.is_empty()
        && value.is_ascii()
        && !value
            .chars()
            .any(|c| c.is_control() || c == '\r' || c == '\n')
}

/// Vet a request from the webview and prepare it for sending.
///
/// The `url` is checked as a string rather than parsed with a URL library on
/// purpose: the checks below are the ones that matter (exact scheme, exact
/// host, `/v1/` path) and each is a prefix comparison whose failure mode is
/// "refuse", not "reinterpret". A parser's failure mode is "normalise into
/// something that passes".
pub fn vet_request(
    url: &str,
    method: &str,
    client_headers: &[(String, String)],
    body: Vec<u8>,
    credentials: &CredentialStore,
    provider_id: &str,
    user_id: &str,
) -> Result<VettedRequest> {
    // ── Method. Two verbs, because two are all the SDK needs.
    let method = match method.to_ascii_uppercase().as_str() {
        "POST" => "POST",
        "GET" => "GET",
        other => {
            return Err(Error::provider(
                ProviderErrorCode::RequestRefused,
                format!("허용되지 않은 메서드입니다: {other}"),
            ))
        }
    };

    // ── Origin. Exact scheme, exact host, and the host must be followed by
    //    `/` — `https://api.anthropic.com.evil.test/` starts with the allowed
    //    string and is a different site.
    let expected = format!("https://{ALLOWED_HOST}");
    let rest = url.strip_prefix(&expected).ok_or_else(|| {
        Error::provider(
            ProviderErrorCode::RequestRefused,
            format!("{ALLOWED_HOST} 외의 주소로는 요청할 수 없습니다."),
        )
    })?;
    if !rest.starts_with('/') {
        return Err(Error::provider(
            ProviderErrorCode::RequestRefused,
            format!("{ALLOWED_HOST} 외의 주소로는 요청할 수 없습니다."),
        ));
    }

    // ── Path. `/v1/` only, and no `..` or userinfo tricks in what follows.
    let path = rest.split(['?', '#']).next().unwrap_or(rest);
    if !path.starts_with("/v1/") {
        return Err(Error::provider(
            ProviderErrorCode::RequestRefused,
            "/v1/ 경로만 사용할 수 있습니다.",
        ));
    }
    if path.contains("..") || path.contains("//") || url.contains('@') || url.contains('\\') {
        return Err(Error::provider(
            ProviderErrorCode::RequestRefused,
            "경로에 사용할 수 없는 문자가 있습니다.",
        ));
    }
    if !url.is_ascii() || url.chars().any(|c| c.is_control()) {
        return Err(Error::provider(
            ProviderErrorCode::RequestRefused,
            "주소에 제어 문자가 있습니다.",
        ));
    }

    // ── Headers. Forward the allowlist, drop everything else silently — the
    //    SDK sends a handful of telemetry headers we have no reason to relay,
    //    and refusing the request over them would be a support ticket.
    let mut headers: Vec<(String, String)> = Vec::with_capacity(FORWARDABLE.len() + 2);
    for (name, value) in client_headers {
        let lower = name.to_ascii_lowercase();
        if !FORWARDABLE.contains(&lower.as_str()) {
            continue;
        }
        if !header_value_is_sane(value) {
            return Err(Error::provider(
                ProviderErrorCode::RequestRefused,
                format!("헤더 {lower} 의 값에 사용할 수 없는 문자가 있습니다."),
            ));
        }
        headers.push((lower, value.clone()));
    }

    // ── The two headers only we may set. Pushed last and never taken from the
    //    client, so `x-api-key` is not something the webview can influence and
    //    the version cannot be downgraded to one with different semantics.
    headers.push(("x-api-key".into(), credentials.key(provider_id, user_id)?));
    headers.push(("anthropic-version".into(), ANTHROPIC_VERSION.into()));

    Ok(VettedRequest {
        url: url.to_string(),
        method,
        headers,
        body,
    })
}

/// The request that proves a key without spending tokens.
///
/// A `GET` on the model, not a one-token `POST`: it needs no body, bills
/// nothing, and a 404 tells the user their key works but the model does not
/// exist — which is a different problem from a 401 and should read differently.
pub fn validation_request(model: &str) -> (String, &'static str) {
    (format!("https://{ALLOWED_HOST}/v1/models/{model}"), "GET")
}

/// Turn a provider status code into something worth showing a person.
pub fn describe_status(status: u16) -> Option<String> {
    let message = match status {
        200..=299 => return None,
        401 | 403 => "API 키가 거부되었습니다. 키를 다시 확인해주세요.",
        404 => "이 키로는 해당 모델을 사용할 수 없습니다.",
        429 => "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        500..=599 => "프로바이더 쪽 오류입니다. 잠시 후 다시 시도해주세요.",
        _ => "프로바이더가 요청을 거부했습니다.",
    };
    Some(format!("{message} (HTTP {status})"))
}

/// Where the relayed bytes go.
///
/// A trait rather than a closure so the head, the chunks, and the two ways a
/// relay can end are separate methods that the compiler makes you handle. The
/// implementation in `src-tauri` forwards each one to a Tauri `Channel`; tests
/// use a recorder.
///
/// Every method takes `&self`: the sink is shared with the task doing the
/// reading and must not need a lock to accept a chunk.
pub trait ByteSink: Send + Sync {
    /// The response line and headers, before any body byte.
    fn head(&self, status: u16, headers: Vec<(String, String)>) -> Result<()>;
    /// One chunk of the body, exactly as it arrived. Never buffered to a line
    /// or a frame boundary — this side does not know what a frame is.
    fn chunk(&self, bytes: &[u8]) -> Result<()>;
    /// The body ended normally.
    fn done(&self) -> Result<()>;
    /// The relay failed. Separate from `done` so the loop upstream can tell a
    /// truncated stream from a complete one; a stream that silently stops looks
    /// to the SDK like a message that simply ended.
    fn failed(&self, message: &str);
}

/// Send a vetted request and stream the response body into `sink`.
///
/// Deliberately dumb: it does not parse the body, does not retry, and does not
/// look at the status beyond passing it on. Retries belong to the SDK, which
/// knows which errors are retryable this month; status interpretation belongs
/// to the loop.
///
/// Not unit-tested here, and that is a deliberate trade: making it testable
/// would mean either accepting plain `http` for a local mock — which is the one
/// thing [`vet_request`] exists to prevent — or pulling a TLS test server into
/// the workspace. The logic worth testing was moved out into `vet_request`; what
/// is left is reqwest plumbing whose failure is loud and immediate.
pub async fn relay(
    client: &reqwest::Client,
    request: VettedRequest,
    sink: &dyn ByteSink,
) -> Result<()> {
    use futures_util::StreamExt;

    let mut builder = match request.method {
        "GET" => client.get(&request.url),
        _ => client.post(&request.url).body(request.body.clone()),
    };
    for (name, value) in &request.headers {
        builder = builder.header(name.as_str(), value.as_str());
    }

    let response = match builder.send().await {
        Ok(response) => response,
        Err(error) => {
            // The message is shaped for a person: a raw reqwest error names
            // TLS internals the user cannot act on.
            let message = if error.is_timeout() {
                "프로바이더 응답이 없습니다. 네트워크를 확인해주세요.".to_string()
            } else if error.is_connect() {
                "프로바이더에 연결할 수 없습니다. 네트워크를 확인해주세요.".to_string()
            } else {
                "프로바이더 요청이 실패했습니다.".to_string()
            };
            sink.failed(&message);
            return Err(Error::provider(ProviderErrorCode::Unavailable, message));
        }
    };

    let status = response.status().as_u16();
    let headers = response
        .headers()
        .iter()
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.as_str().to_string(), value.to_string()))
        })
        .collect();
    sink.head(status, headers)?;

    let mut stream = response.bytes_stream();
    while let Some(next) = stream.next().await {
        match next {
            Ok(bytes) => sink.chunk(&bytes)?,
            Err(_) => {
                let message = "응답이 중간에 끊겼습니다.".to_string();
                sink.failed(&message);
                return Err(Error::provider(ProviderErrorCode::Truncated, message));
            }
        }
    }
    sink.done()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::MemoryTokenStore;
    use std::sync::Arc;

    const KEY: &str = "sk-ant-api03-abcdefghijklmnop-XYZW";

    fn creds() -> CredentialStore {
        let store = CredentialStore::new(Arc::new(MemoryTokenStore::default()));
        store.put("anthropic", "u1", KEY).unwrap();
        store
    }

    fn vet(url: &str, headers: &[(&str, &str)]) -> Result<VettedRequest> {
        let owned: Vec<(String, String)> = headers
            .iter()
            .map(|(n, v)| (n.to_string(), v.to_string()))
            .collect();
        vet_request(
            url,
            "POST",
            &owned,
            b"{}".to_vec(),
            &creds(),
            "anthropic",
            "u1",
        )
    }

    fn header(request: &VettedRequest, name: &str) -> Option<String> {
        request
            .headers
            .iter()
            .find(|(n, _)| n == name)
            .map(|(_, v)| v.clone())
    }

    // ── The origin allowlist ─────────────────────────────────────────────

    #[test]
    fn the_messages_endpoint_passes() {
        let request = vet("https://api.anthropic.com/v1/messages", &[]).unwrap();
        assert_eq!(request.method, "POST");
        assert_eq!(header(&request, "x-api-key").as_deref(), Some(KEY));
        assert_eq!(
            header(&request, "anthropic-version").as_deref(),
            Some(ANTHROPIC_VERSION)
        );
    }

    #[test]
    fn nothing_but_the_allowed_origin_passes() {
        for url in [
            // Plain http would put the key on the wire in clear.
            "http://api.anthropic.com/v1/messages",
            // A prefix of the allowed host is a different site.
            "https://api.anthropic.com.evil.test/v1/messages",
            "https://api.anthropic.comx/v1/messages",
            // A subdomain is not the host.
            "https://evil.api.anthropic.com/v1/messages",
            // Userinfo puts the real host after an @.
            "https://api.anthropic.com@evil.test/v1/messages",
            // Backslash is a path separator to some parsers and not others.
            "https://api.anthropic.com\\@evil.test/v1/messages",
            // Anything at all that is not the allowlist.
            "https://collector.evil.test/v1/messages",
            "file:///etc/passwd",
            "",
        ] {
            assert!(vet(url, &[]).is_err(), "accepted {url:?}");
        }
    }

    #[test]
    fn only_v1_paths_pass() {
        for url in [
            "https://api.anthropic.com/",
            "https://api.anthropic.com/v2/messages",
            "https://api.anthropic.com/v1",
            "https://api.anthropic.com/v1/../internal",
            "https://api.anthropic.com//v1/messages",
        ] {
            assert!(vet(url, &[]).is_err(), "accepted {url:?}");
        }
    }

    #[test]
    fn a_query_string_is_allowed_and_does_not_defeat_the_path_check() {
        assert!(vet("https://api.anthropic.com/v1/models?limit=1", &[]).is_ok());
        // The path check must look before the `?`, not at the whole string.
        assert!(vet("https://api.anthropic.com/x?/v1/messages", &[]).is_err());
    }

    // ── Header handling ──────────────────────────────────────────────────

    #[test]
    fn the_client_cannot_supply_or_override_the_key() {
        let request = vet(
            "https://api.anthropic.com/v1/messages",
            &[
                ("x-api-key", "sk-ant-attacker-key"),
                ("authorization", "Bearer attacker"),
                ("X-Api-Key", "sk-ant-also-attacker"),
            ],
        )
        .unwrap();

        let keys: Vec<_> = request
            .headers
            .iter()
            .filter(|(n, _)| n == "x-api-key")
            .collect();
        assert_eq!(
            keys.len(),
            1,
            "exactly one key header: {:?}",
            request.headers
        );
        assert_eq!(keys[0].1, KEY);
        assert!(header(&request, "authorization").is_none());
    }

    #[test]
    fn the_client_cannot_downgrade_the_api_version() {
        let request = vet(
            "https://api.anthropic.com/v1/messages",
            &[("anthropic-version", "2000-01-01")],
        )
        .unwrap();
        let versions: Vec<_> = request
            .headers
            .iter()
            .filter(|(n, _)| n == "anthropic-version")
            .map(|(_, v)| v.as_str())
            .collect();
        assert_eq!(versions, vec![ANTHROPIC_VERSION]);
    }

    #[test]
    fn the_headers_the_sdk_needs_survive() {
        let request = vet(
            "https://api.anthropic.com/v1/messages",
            &[
                ("Content-Type", "application/json"),
                ("accept", "text/event-stream"),
                ("anthropic-beta", "tool-runner-2026-01-01"),
                ("x-stainless-lang", "js"),
            ],
        )
        .unwrap();
        assert_eq!(
            header(&request, "content-type").as_deref(),
            Some("application/json")
        );
        assert_eq!(
            header(&request, "accept").as_deref(),
            Some("text/event-stream")
        );
        assert!(header(&request, "anthropic-beta").is_some());
        // Not on the allowlist: dropped, not an error.
        assert!(header(&request, "x-stainless-lang").is_none());
    }

    #[test]
    fn a_header_value_that_could_split_the_request_is_refused() {
        for value in [
            "application/json\r\nX-Evil: 1",
            "application/json\nX-Evil: 1",
            "application/json\0",
            "",
        ] {
            assert!(
                vet(
                    "https://api.anthropic.com/v1/messages",
                    &[("content-type", value)]
                )
                .is_err(),
                "accepted {value:?}"
            );
        }
    }

    #[test]
    fn only_get_and_post_pass() {
        for method in ["PUT", "DELETE", "CONNECT", "TRACE", "PATCH", ""] {
            assert!(
                vet_request(
                    "https://api.anthropic.com/v1/messages",
                    method,
                    &[],
                    Vec::new(),
                    &creds(),
                    "anthropic",
                    "u1",
                )
                .is_err(),
                "accepted {method}"
            );
        }
        assert!(vet_request(
            "https://api.anthropic.com/v1/models",
            "get",
            &[],
            Vec::new(),
            &creds(),
            "anthropic",
            "u1",
        )
        .is_ok());
    }

    #[test]
    fn with_no_key_stored_there_is_nothing_to_send() {
        let empty = CredentialStore::new(Arc::new(MemoryTokenStore::default()));
        assert!(vet_request(
            "https://api.anthropic.com/v1/messages",
            "POST",
            &[],
            Vec::new(),
            &empty,
            "anthropic",
            "u1",
        )
        .is_err());
    }

    #[test]
    fn the_body_is_passed_through_untouched() {
        // The proxy does not know what a request body means, and must not.
        let body = b"{\"model\":\"claude-opus-5\",\"stream\":true}".to_vec();
        let request = vet_request(
            "https://api.anthropic.com/v1/messages",
            "POST",
            &[],
            body.clone(),
            &creds(),
            "anthropic",
            "u1",
        )
        .unwrap();
        assert_eq!(request.body, body);
    }

    // ── Logging and reporting ────────────────────────────────────────────

    #[test]
    fn redacted_headers_never_carry_the_key() {
        let request = vet("https://api.anthropic.com/v1/messages", &[]).unwrap();
        let redacted = request.redacted_headers();
        assert!(redacted.iter().any(|(n, v)| n == "x-api-key" && v == "***"));
        assert!(!format!("{redacted:?}").contains(KEY));
    }

    #[test]
    fn validation_uses_a_get_that_bills_nothing() {
        let (url, method) = validation_request("claude-opus-5");
        assert_eq!(method, "GET");
        assert_eq!(url, "https://api.anthropic.com/v1/models/claude-opus-5");
        // And it must survive its own vetting.
        assert!(vet_request(&url, method, &[], Vec::new(), &creds(), "anthropic", "u1").is_ok());
    }

    // ── The sink contract ────────────────────────────────────────────────

    #[derive(Default)]
    struct Recorder {
        events: parking_lot::Mutex<Vec<String>>,
    }

    impl ByteSink for Recorder {
        fn head(&self, status: u16, _headers: Vec<(String, String)>) -> Result<()> {
            self.events.lock().push(format!("head {status}"));
            Ok(())
        }
        fn chunk(&self, bytes: &[u8]) -> Result<()> {
            self.events.lock().push(format!("chunk {}", bytes.len()));
            Ok(())
        }
        fn done(&self) -> Result<()> {
            self.events.lock().push("done".into());
            Ok(())
        }
        fn failed(&self, message: &str) {
            self.events.lock().push(format!("failed {message}"));
        }
    }

    #[test]
    fn a_sink_can_distinguish_a_finished_stream_from_a_cut_one() {
        // The distinction is the whole point of `failed` existing next to
        // `done`: a truncated SSE stream is indistinguishable from a complete
        // one to the SDK, so the transport has to say which it was.
        let recorder = Recorder::default();
        recorder.head(200, Vec::new()).unwrap();
        recorder.chunk(b"data: {}").unwrap();
        recorder.failed("cut");
        assert_eq!(
            *recorder.events.lock(),
            vec!["head 200", "chunk 8", "failed cut"]
        );
    }

    #[test]
    fn a_rejected_key_and_a_missing_model_read_differently() {
        assert!(describe_status(200).is_none());
        assert!(describe_status(401).unwrap().contains("키"));
        assert!(describe_status(404).unwrap().contains("모델"));
        assert!(describe_status(429).unwrap().contains("잠시"));
        assert!(describe_status(503).unwrap().contains("프로바이더"));
        // The code is always shown: "something went wrong" is unactionable.
        assert!(describe_status(418).unwrap().contains("418"));
    }
}
