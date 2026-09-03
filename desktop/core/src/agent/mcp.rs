//! MCP: tools from servers the user connects.
//!
//! ## What an MCP server is to the gate
//!
//! A third party's code, reached over HTTP or as a child process, that
//! describes its own tools in prose. That prose arrives with more apparent
//! authority than a chat message and is exactly as trustworthy, so every MCP
//! call is class 3 — asked every time, never remembered — and every result
//! taints the session. This module does the plumbing; the policy does the
//! deciding, and nothing here can route around it because the only way to run
//! an MCP tool is still `tools::execute`.
//!
//! ## Two transports, one client
//!
//! Streamable HTTP (a JSON-RPC POST per message; the server may answer with
//! JSON or with a short `text/event-stream`) and stdio (a child process, one
//! JSON-RPC message per line). The rest of the engine sees one
//! [`McpClient`] and never learns which it is.
//!
//! Credentials for HTTP servers live in the keychain like provider keys and
//! are attached here, on the way out, and nowhere else. A server record that
//! crosses to the webview says only *whether* a credential exists.

use std::collections::HashMap;
use std::sync::atomic::{AtomicI64, Ordering};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::Mutex;

use crate::error::{Error, Result};

/// The protocol revision this client announces.
pub const PROTOCOL_VERSION: &str = "2025-06-18";

/// The `initialize` round trip has this long, including the process spawn.
pub const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);
/// One `tools/call` has this long. Long enough for a slow search, short
/// enough that a hung server does not hold an approval-granted turn forever.
pub const CALL_TIMEOUT: Duration = Duration::from_secs(60);

/// How a server is reached.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Transport {
    Http,
    Stdio,
}

impl Transport {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "http" => Some(Transport::Http),
            "stdio" => Some(Transport::Stdio),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Transport::Http => "http",
            Transport::Stdio => "stdio",
        }
    }
}

/// A registered server, as stored. Never carries the credential.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpServer {
    pub id: String,
    pub user_id: String,
    pub name: String,
    pub transport: Transport,
    pub url: Option<String>,
    pub command: Option<String>,
    pub args: Vec<String>,
    pub enabled: bool,
    pub created_at_ms: i64,
    pub last_ok_at_ms: Option<i64>,
    pub last_error: Option<String>,
}

impl McpServer {
    /// What the approval card shows as "where": the URL, or the command line.
    pub fn endpoint(&self) -> String {
        match self.transport {
            Transport::Http => self.url.clone().unwrap_or_default(),
            Transport::Stdio => {
                let mut parts = vec![self.command.clone().unwrap_or_default()];
                parts.extend(self.args.iter().cloned());
                parts.join(" ")
            }
        }
    }
}

/// One tool as the server describes it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpToolDef {
    pub name: String,
    #[serde(default)]
    pub description: String,
    /// The server's own JSON Schema, passed to the model unchanged.
    #[serde(rename = "inputSchema", default = "empty_schema")]
    pub input_schema: serde_json::Value,
}

fn empty_schema() -> serde_json::Value {
    serde_json::json!({ "type": "object", "properties": {} })
}

/// The part of a server's name that may appear in a tool name.
///
/// `mcp.{slug}.{tool}` has to survive being a JSON key, a prompt-cache prefix
/// and a stored session, so it is ASCII and lowercase; a Korean server name
/// becomes `server` and gets a numeric suffix on collision (see the catalog).
pub fn slugify(name: &str) -> String {
    let mut slug: String = name
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect();
    while slug.contains("--") {
        slug = slug.replace("--", "-");
    }
    let slug = slug.trim_matches('-').to_string();
    if slug.is_empty() {
        "server".into()
    } else {
        slug.chars().take(40).collect()
    }
}

/// The tool name the model sees for `tool` on `slug`.
pub fn tool_name(slug: &str, tool: &str) -> String {
    format!("mcp.{slug}.{tool}")
}

/// Only http(s), and never a credential in the URL: userinfo would put the
/// secret in every log line that prints the address.
pub fn vet_url(url: &str) -> Result<()> {
    let parsed = url::Url::parse(url)
        .map_err(|_| Error::Other("MCP 서버 주소를 해석할 수 없습니다.".into()))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(Error::Other(
            "MCP 서버 주소는 http(s) 만 가능합니다.".into(),
        ));
    }
    if parsed.host_str().is_none() {
        return Err(Error::Other("MCP 서버 주소에 호스트가 없습니다.".into()));
    }
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err(Error::Other(
            "주소에 자격증명을 넣지 마세요. 토큰 칸에 따로 입력합니다.".into(),
        ));
    }
    Ok(())
}

// ── JSON-RPC framing ────────────────────────────────────────────────────────

fn rpc_request(id: i64, method: &str, params: serde_json::Value) -> serde_json::Value {
    serde_json::json!({ "jsonrpc": "2.0", "id": id, "method": method, "params": params })
}

fn rpc_notification(method: &str, params: serde_json::Value) -> serde_json::Value {
    serde_json::json!({ "jsonrpc": "2.0", "method": method, "params": params })
}

/// Pull the `result` out of a response to `id`, or the server's error.
///
/// A response is a message with our `id` and either `result` or `error`.
/// Anything else on the wire — a notification, a server-to-client request, a
/// response to another id — is not ours and is skipped by the callers.
pub fn take_result(message: &serde_json::Value, id: i64) -> Option<Result<serde_json::Value>> {
    if message.get("id").and_then(|v| v.as_i64()) != Some(id) {
        return None;
    }
    if let Some(error) = message.get("error") {
        let text = error
            .get("message")
            .and_then(|m| m.as_str())
            .unwrap_or("알 수 없는 오류");
        return Some(Err(Error::Other(format!("MCP 서버 오류: {text}"))));
    }
    Some(Ok(message
        .get("result")
        .cloned()
        .unwrap_or(serde_json::Value::Null)))
}

/// The JSON payloads in a `text/event-stream` body, in order.
///
/// Only `data:` lines matter; `event:` and `id:` lines are transport
/// decoration. Multi-line data fields are joined with `\n` per the SSE spec.
pub fn sse_payloads(body: &str) -> Vec<serde_json::Value> {
    let mut out = Vec::new();
    let mut data = String::new();
    let flush = |data: &mut String, out: &mut Vec<serde_json::Value>| {
        if !data.is_empty() {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(data) {
                out.push(value);
            }
            data.clear();
        }
    };
    for line in body.lines() {
        if line.is_empty() {
            flush(&mut data, &mut out);
        } else if let Some(rest) = line.strip_prefix("data:") {
            if !data.is_empty() {
                data.push('\n');
            }
            data.push_str(rest.trim_start());
        }
    }
    flush(&mut data, &mut out);
    out
}

/// Flatten a `tools/call` result into text for the artifact store.
///
/// Text blocks are concatenated; anything the model could not read as text is
/// named rather than dropped, so it knows there was an image it did not see.
pub fn result_text(result: &serde_json::Value) -> (String, bool) {
    let is_error = result
        .get("isError")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let mut parts = Vec::new();
    if let Some(blocks) = result.get("content").and_then(|c| c.as_array()) {
        for block in blocks {
            match block.get("type").and_then(|t| t.as_str()) {
                Some("text") => parts.push(
                    block
                        .get("text")
                        .and_then(|t| t.as_str())
                        .unwrap_or("")
                        .to_string(),
                ),
                Some("image") => parts.push("[image]".into()),
                Some("audio") => parts.push("[audio]".into()),
                Some("resource") | Some("resource_link") => parts.push("[resource]".into()),
                _ => {}
            }
        }
    } else if let Some(structured) = result.get("structuredContent") {
        parts.push(structured.to_string());
    }
    (parts.join("\n"), is_error)
}

// ── The client ──────────────────────────────────────────────────────────────

/// A connected server. Cheap to share behind an `Arc`.
pub struct McpClient {
    server: McpServer,
    next_id: AtomicI64,
    inner: Inner,
}

enum Inner {
    Http {
        http: reqwest::Client,
        url: String,
        /// Attached as `Authorization: Bearer …`. Held here, never returned.
        token: Option<String>,
        /// The server's session, if it issued one on `initialize`.
        session_id: parking_lot::Mutex<Option<String>>,
    },
    Stdio {
        /// The child and both pipes behind one lock: a JSON-RPC request and
        /// its response are one exchange, and interleaving two would hand
        /// one caller the other's answer. Boxed so this variant does not make
        /// every `Inner` (usually the small `Http` one) as large as a child
        /// process handle plus two pipe buffers.
        io: Box<Mutex<StdioIo>>,
    },
}

struct StdioIo {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl Drop for StdioIo {
    fn drop(&mut self) {
        // `kill_on_drop` is set on the command too; this is belt and braces
        // for the case where the runtime is gone.
        let _ = self.child.start_kill();
    }
}

impl McpClient {
    /// Connect and complete the handshake. Nothing is stored about a server
    /// whose handshake fails — see `AgentEngine::mcp_add`.
    pub async fn connect(
        http: reqwest::Client,
        server: McpServer,
        token: Option<String>,
    ) -> Result<(Self, serde_json::Value)> {
        let inner = match server.transport {
            Transport::Http => {
                let url = server
                    .url
                    .clone()
                    .ok_or_else(|| Error::Other("HTTP MCP 서버에는 주소가 필요합니다.".into()))?;
                vet_url(&url)?;
                Inner::Http {
                    http,
                    url,
                    token,
                    session_id: parking_lot::Mutex::new(None),
                }
            }
            Transport::Stdio => {
                let command = server
                    .command
                    .clone()
                    .filter(|c| !c.trim().is_empty())
                    .ok_or_else(|| Error::Other("stdio MCP 서버에는 명령이 필요합니다.".into()))?;
                let mut child = Command::new(&command)
                    .args(&server.args)
                    .stdin(std::process::Stdio::piped())
                    .stdout(std::process::Stdio::piped())
                    .stderr(std::process::Stdio::null())
                    .kill_on_drop(true)
                    .spawn()
                    .map_err(|e| Error::Other(format!("{command} 을 실행할 수 없습니다: {e}")))?;
                let stdin = child
                    .stdin
                    .take()
                    .ok_or_else(|| Error::Other("stdin 을 열 수 없습니다.".into()))?;
                let stdout = child
                    .stdout
                    .take()
                    .ok_or_else(|| Error::Other("stdout 을 열 수 없습니다.".into()))?;
                Inner::Stdio {
                    io: Box::new(Mutex::new(StdioIo {
                        child,
                        stdin,
                        stdout: BufReader::new(stdout),
                    })),
                }
            }
        };

        let client = Self {
            server,
            next_id: AtomicI64::new(1),
            inner,
        };

        let info = tokio::time::timeout(HANDSHAKE_TIMEOUT, client.handshake())
            .await
            .map_err(|_| Error::Other("MCP 서버가 초기화에 응답하지 않습니다 (10초).".into()))??;
        Ok((client, info))
    }

    pub fn server(&self) -> &McpServer {
        &self.server
    }

    async fn handshake(&self) -> Result<serde_json::Value> {
        let info = self
            .request(
                "initialize",
                serde_json::json!({
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": { "name": "llack", "version": crate::VERSION },
                }),
            )
            .await?;
        self.notify("notifications/initialized", serde_json::json!({}))
            .await?;
        Ok(info)
    }

    /// Every tool the server offers, following `nextCursor` to the end.
    pub async fn list_tools(&self) -> Result<Vec<McpToolDef>> {
        let mut tools = Vec::new();
        let mut cursor: Option<String> = None;
        // A server that never ends its cursor chain would loop forever;
        // twenty pages of tools is already more than any model can use.
        for _ in 0..20 {
            let params = match &cursor {
                Some(c) => serde_json::json!({ "cursor": c }),
                None => serde_json::json!({}),
            };
            let result = tokio::time::timeout(CALL_TIMEOUT, self.request("tools/list", params))
                .await
                .map_err(|_| Error::Other("MCP 서버가 도구 목록에 응답하지 않습니다.".into()))??;
            if let Some(page) = result.get("tools").and_then(|t| t.as_array()) {
                for tool in page {
                    if let Ok(def) = serde_json::from_value::<McpToolDef>(tool.clone()) {
                        tools.push(def);
                    }
                }
            }
            cursor = result
                .get("nextCursor")
                .and_then(|c| c.as_str())
                .map(str::to_string);
            if cursor.is_none() {
                break;
            }
        }
        Ok(tools)
    }

    /// Run one tool. The caller has already been through the gate.
    pub async fn call_tool(
        &self,
        tool: &str,
        args: &serde_json::Value,
    ) -> Result<serde_json::Value> {
        tokio::time::timeout(
            CALL_TIMEOUT,
            self.request(
                "tools/call",
                serde_json::json!({ "name": tool, "arguments": args }),
            ),
        )
        .await
        .map_err(|_| Error::Other("MCP 도구가 60초 안에 응답하지 않았습니다.".into()))?
    }

    async fn request(&self, method: &str, params: serde_json::Value) -> Result<serde_json::Value> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let message = rpc_request(id, method, params);
        match &self.inner {
            Inner::Http { .. } => self.http_exchange(&message, Some(id)).await.and_then(|r| {
                r.ok_or_else(|| Error::Other("MCP 서버가 응답 본문을 보내지 않았습니다.".into()))
            }),
            Inner::Stdio { io } => {
                let mut io = io.lock().await;
                let mut line = message.to_string();
                line.push('\n');
                io.stdin
                    .write_all(line.as_bytes())
                    .await
                    .map_err(|e| Error::Other(format!("MCP 서버에 쓸 수 없습니다: {e}")))?;
                io.stdin.flush().await.ok();
                loop {
                    let mut buf = String::new();
                    let read =
                        io.stdout.read_line(&mut buf).await.map_err(|e| {
                            Error::Other(format!("MCP 서버를 읽을 수 없습니다: {e}"))
                        })?;
                    if read == 0 {
                        return Err(Error::Other("MCP 서버가 연결을 끊었습니다.".into()));
                    }
                    let Ok(value) = serde_json::from_str::<serde_json::Value>(buf.trim()) else {
                        // Servers sometimes log to stdout. Skip what is not JSON.
                        continue;
                    };
                    if let Some(result) = take_result(&value, id) {
                        return result;
                    }
                }
            }
        }
    }

    async fn notify(&self, method: &str, params: serde_json::Value) -> Result<()> {
        let message = rpc_notification(method, params);
        match &self.inner {
            Inner::Http { .. } => {
                self.http_exchange(&message, None).await?;
                Ok(())
            }
            Inner::Stdio { io } => {
                let mut io = io.lock().await;
                let mut line = message.to_string();
                line.push('\n');
                io.stdin
                    .write_all(line.as_bytes())
                    .await
                    .map_err(|e| Error::Other(format!("MCP 서버에 쓸 수 없습니다: {e}")))?;
                io.stdin.flush().await.ok();
                Ok(())
            }
        }
    }

    /// One POST. `Some(id)` means "wait for the response to this id".
    async fn http_exchange(
        &self,
        message: &serde_json::Value,
        expect: Option<i64>,
    ) -> Result<Option<serde_json::Value>> {
        let Inner::Http {
            http,
            url,
            token,
            session_id,
        } = &self.inner
        else {
            unreachable!("http_exchange on a stdio client");
        };

        let mut builder = http
            .post(url)
            .header("content-type", "application/json")
            .header("accept", "application/json, text/event-stream")
            .header("mcp-protocol-version", PROTOCOL_VERSION)
            .json(message);
        if let Some(token) = token {
            builder = builder.header("authorization", format!("Bearer {token}"));
        }
        if let Some(session) = session_id.lock().clone() {
            builder = builder.header("mcp-session-id", session);
        }

        let response = builder
            .send()
            .await
            .map_err(|e| Error::Other(format!("MCP 서버에 연결할 수 없습니다: {e}")))?;

        if let Some(session) = response
            .headers()
            .get("mcp-session-id")
            .and_then(|v| v.to_str().ok())
        {
            *session_id.lock() = Some(session.to_string());
        }

        let status = response.status().as_u16();
        if status == 401 || status == 403 {
            return Err(Error::Other(
                "MCP 서버가 인증을 거부했습니다. 토큰을 확인해주세요.".into(),
            ));
        }
        if !(200..300).contains(&status) {
            return Err(Error::Other(format!(
                "MCP 서버가 HTTP {status} 로 응답했습니다."
            )));
        }

        let Some(id) = expect else {
            return Ok(None);
        };

        let content_type = response
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_ascii_lowercase();
        let body = response
            .text()
            .await
            .map_err(|e| Error::Other(format!("MCP 응답을 읽을 수 없습니다: {e}")))?;

        let candidates = if content_type.starts_with("text/event-stream") {
            sse_payloads(&body)
        } else {
            match serde_json::from_str::<serde_json::Value>(&body) {
                Ok(serde_json::Value::Array(items)) => items,
                Ok(single) => vec![single],
                Err(_) => Vec::new(),
            }
        };
        for candidate in &candidates {
            if let Some(result) = take_result(candidate, id) {
                return result.map(Some);
            }
        }
        Err(Error::Other(
            "MCP 서버 응답에 이 요청의 결과가 없습니다.".into(),
        ))
    }
}

/// What the webview may know about a server.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct McpServerView {
    pub id: String,
    pub name: String,
    pub transport: Transport,
    pub url: Option<String>,
    pub command: Option<String>,
    pub args: Vec<String>,
    pub enabled: bool,
    pub tool_count: usize,
    pub last_ok_at_ms: Option<i64>,
    pub last_error: Option<String>,
    pub has_credential: bool,
}

impl McpServerView {
    pub fn from_server(server: &McpServer, tool_count: usize, has_credential: bool) -> Self {
        Self {
            id: server.id.clone(),
            name: server.name.clone(),
            transport: server.transport,
            url: server.url.clone(),
            command: server.command.clone(),
            args: server.args.clone(),
            enabled: server.enabled,
            tool_count,
            last_ok_at_ms: server.last_ok_at_ms,
            last_error: server.last_error.clone(),
            has_credential,
        }
    }
}

/// Tool names per connected server, kept by the engine so a call can be
/// routed back to the server that offered it.
pub type ToolIndex = HashMap<String, (String, String)>;

#[cfg(test)]
pub(crate) mod testing {
    //! A minimal MCP server over HTTP/1.1 on a loopback port, answering
    //! `initialize`, `tools/list` and `tools/call` from a script. Written on a
    //! raw `TcpListener` because pulling an HTTP server framework into the
    //! workspace for a test is not worth the supply chain.

    use std::sync::Arc;

    use parking_lot::Mutex;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    pub struct FakeMcpServer {
        pub url: String,
        pub seen: Arc<Mutex<Vec<serde_json::Value>>>,
        pub auth_headers: Arc<Mutex<Vec<String>>>,
    }

    impl FakeMcpServer {
        pub async fn start(sse: bool, require_token: Option<&str>) -> Self {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let port = listener.local_addr().unwrap().port();
            let seen = Arc::new(Mutex::new(Vec::new()));
            let auth_headers = Arc::new(Mutex::new(Vec::new()));
            let seen_task = seen.clone();
            let auth_task = auth_headers.clone();
            let required = require_token.map(str::to_string);
            tokio::spawn(async move {
                loop {
                    let Ok((mut socket, _)) = listener.accept().await else {
                        break;
                    };
                    let seen = seen_task.clone();
                    let auth = auth_task.clone();
                    let required = required.clone();
                    tokio::spawn(async move {
                        // Handle every request on this connection, not just the
                        // first: reqwest keeps the socket alive and sends the
                        // `initialized` notification and `tools/list` on it, and
                        // closing after one reply made the client reconnect —
                        // occasionally surfacing as a failure under load.
                        let mut buf = Vec::new();
                        let mut chunk = [0u8; 4096];
                        loop {
                            // Read until a full head+body is buffered, keeping
                            // any surplus bytes for the next request.
                            let (head_end, head_len, body_len) = loop {
                                if let Some(pos) = find(&buf, b"\r\n\r\n") {
                                    let head = String::from_utf8_lossy(&buf[..pos]).to_string();
                                    let len = head
                                        .lines()
                                        .find_map(|l| {
                                            l.to_ascii_lowercase()
                                                .strip_prefix("content-length:")
                                                .map(|v| v.trim().parse::<usize>().unwrap_or(0))
                                        })
                                        .unwrap_or(0);
                                    if buf.len() >= pos + 4 + len {
                                        break (head, pos + 4, len);
                                    }
                                }
                                let n = socket.read(&mut chunk).await.unwrap_or(0);
                                if n == 0 {
                                    return;
                                }
                                buf.extend_from_slice(&chunk[..n]);
                            };
                            let body = buf[head_len..head_len + body_len].to_vec();
                            buf.drain(..head_len + body_len);

                            let authorization = head_end.lines().find_map(|l| {
                                l.to_ascii_lowercase()
                                    .strip_prefix("authorization:")
                                    .map(|v| v.trim().to_string())
                            });
                            if let Some(a) = &authorization {
                                auth.lock().push(a.clone());
                            }
                            if let Some(required) = &required {
                                if authorization.as_deref() != Some(&format!("bearer {required}")) {
                                    let _ = socket
                                        .write_all(
                                            b"HTTP/1.1 401 Unauthorized\r\ncontent-length: 0\r\n\r\n",
                                        )
                                        .await;
                                    return;
                                }
                            }
                            let message: serde_json::Value =
                                serde_json::from_slice(&body).unwrap_or(serde_json::Value::Null);
                            seen.lock().push(message.clone());
                            let reply = respond(&message);
                            let response = match reply {
                                None => {
                                    "HTTP/1.1 202 Accepted\r\ncontent-length: 0\r\n\r\n".to_string()
                                }
                                Some(value) if sse => {
                                    let data = format!("event: message\ndata: {value}\n\n");
                                    format!(
                                        "HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\nmcp-session-id: s-1\r\ncontent-length: {}\r\n\r\n{}",
                                        data.len(),
                                        data
                                    )
                                }
                                Some(value) => {
                                    let data = value.to_string();
                                    format!(
                                        "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\nmcp-session-id: s-1\r\ncontent-length: {}\r\n\r\n{}",
                                        data.len(),
                                        data
                                    )
                                }
                            };
                            if socket.write_all(response.as_bytes()).await.is_err() {
                                return;
                            }
                        }
                    });
                }
            });
            Self {
                url: format!("http://127.0.0.1:{port}/mcp"),
                seen,
                auth_headers,
            }
        }
    }

    fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
        haystack
            .windows(needle.len())
            .position(|window| window == needle)
    }

    /// The scripted answers. `echo` returns its `text` argument; `boom`
    /// reports a tool-level error.
    fn respond(message: &serde_json::Value) -> Option<serde_json::Value> {
        let id = message.get("id")?.clone();
        let method = message.get("method")?.as_str()?;
        let result = match method {
            "initialize" => serde_json::json!({
                "protocolVersion": super::PROTOCOL_VERSION,
                "capabilities": { "tools": {} },
                "serverInfo": { "name": "fake", "version": "0.1" },
            }),
            "tools/list" => serde_json::json!({
                "tools": [
                    {
                        "name": "echo",
                        "description": "돌려줍니다",
                        "inputSchema": { "type": "object", "properties": { "text": { "type": "string" } }, "required": ["text"] }
                    },
                    {
                        "name": "boom",
                        "description": "실패합니다",
                        "inputSchema": { "type": "object", "properties": {} }
                    }
                ]
            }),
            "tools/call" => {
                let name = message["params"]["name"].as_str().unwrap_or("");
                if name == "boom" {
                    serde_json::json!({ "content": [{ "type": "text", "text": "터졌습니다" }], "isError": true })
                } else {
                    let text = message["params"]["arguments"]["text"]
                        .as_str()
                        .unwrap_or("");
                    serde_json::json!({ "content": [
                        { "type": "text", "text": format!("echo: {text}") },
                        { "type": "image", "data": "AAAA", "mimeType": "image/png" }
                    ] })
                }
            }
            _ => {
                return Some(serde_json::json!({
                    "jsonrpc": "2.0", "id": id,
                    "error": { "code": -32601, "message": "Method not found" }
                }))
            }
        };
        Some(serde_json::json!({ "jsonrpc": "2.0", "id": id, "result": result }))
    }
}

#[cfg(test)]
mod tests {
    use super::testing::FakeMcpServer;
    use super::*;

    fn server(url: &str) -> McpServer {
        McpServer {
            id: "01SRV".into(),
            user_id: "u1".into(),
            name: "가짜 서버".into(),
            transport: Transport::Http,
            url: Some(url.to_string()),
            command: None,
            args: Vec::new(),
            enabled: true,
            created_at_ms: 0,
            last_ok_at_ms: None,
            last_error: None,
        }
    }

    // ── Naming ──────────────────────────────────────────────────────────

    #[test]
    fn slugs_are_ascii_lowercase_and_never_empty() {
        assert_eq!(slugify("Notion Search"), "notion-search");
        assert_eq!(slugify("노션"), "server");
        assert_eq!(slugify("  My--Tool!! "), "my-tool");
        assert_eq!(tool_name("notion", "search"), "mcp.notion.search");
    }

    #[test]
    fn a_credential_in_the_url_is_refused() {
        assert!(vet_url("https://user:pw@mcp.example.com/").is_err());
        assert!(vet_url("ftp://mcp.example.com/").is_err());
        assert!(vet_url("not a url").is_err());
        assert!(vet_url("http://localhost:3000/mcp").is_ok());
        assert!(vet_url("https://mcp.example.com/v1").is_ok());
    }

    // ── Framing ─────────────────────────────────────────────────────────

    #[test]
    fn sse_bodies_yield_their_json_payloads_in_order() {
        let body = "event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n: keepalive\n\ndata: {\"a\":\ndata: 1}\n\n";
        let payloads = sse_payloads(body);
        assert_eq!(payloads.len(), 2);
        assert_eq!(payloads[0]["id"], 1);
        assert_eq!(payloads[1]["a"], 1, "multi-line data joins with a newline");
    }

    #[test]
    fn only_the_response_to_our_id_is_taken() {
        let ours = serde_json::json!({ "jsonrpc": "2.0", "id": 7, "result": { "ok": true } });
        let theirs = serde_json::json!({ "jsonrpc": "2.0", "id": 8, "result": {} });
        let notice = serde_json::json!({ "jsonrpc": "2.0", "method": "notifications/progress" });
        assert!(take_result(&ours, 7).unwrap().unwrap()["ok"]
            .as_bool()
            .unwrap());
        assert!(take_result(&theirs, 7).is_none());
        assert!(take_result(&notice, 7).is_none());
        let failed =
            serde_json::json!({ "jsonrpc": "2.0", "id": 7, "error": { "message": "nope" } });
        assert!(take_result(&failed, 7).unwrap().is_err());
    }

    #[test]
    fn results_flatten_to_text_and_name_what_was_not_text() {
        let result = serde_json::json!({ "content": [
            { "type": "text", "text": "hello" },
            { "type": "image", "data": "x" },
            { "type": "text", "text": "world" }
        ] });
        let (text, is_error) = result_text(&result);
        assert_eq!(text, "hello\n[image]\nworld");
        assert!(!is_error);
        let (_, is_error) = result_text(&serde_json::json!({ "content": [], "isError": true }));
        assert!(is_error);
    }

    // ── The HTTP transport against a scripted server ────────────────────

    #[tokio::test]
    async fn the_handshake_lists_tools_and_calls_one() {
        let fake = FakeMcpServer::start(false, None).await;
        let (client, info) = McpClient::connect(reqwest::Client::new(), server(&fake.url), None)
            .await
            .unwrap();
        assert_eq!(info["serverInfo"]["name"], "fake");

        let tools = client.list_tools().await.unwrap();
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].name, "echo");
        assert_eq!(tools[0].input_schema["required"][0], "text");

        let result = client
            .call_tool("echo", &serde_json::json!({ "text": "안녕" }))
            .await
            .unwrap();
        let (text, is_error) = result_text(&result);
        assert_eq!(text, "echo: 안녕\n[image]");
        assert!(!is_error);

        // The handshake sent initialize, then the initialized notification.
        let seen = fake.seen.lock();
        assert_eq!(seen[0]["method"], "initialize");
        assert_eq!(seen[1]["method"], "notifications/initialized");
        assert!(seen[1].get("id").is_none(), "a notification has no id");
    }

    #[tokio::test]
    async fn an_event_stream_response_is_understood() {
        let fake = FakeMcpServer::start(true, None).await;
        let (client, _) = McpClient::connect(reqwest::Client::new(), server(&fake.url), None)
            .await
            .unwrap();
        let tools = client.list_tools().await.unwrap();
        assert_eq!(tools.len(), 2);
    }

    #[tokio::test]
    async fn the_token_is_attached_as_a_bearer_and_a_wrong_one_is_reported() {
        let fake = FakeMcpServer::start(false, Some("secret-token")).await;
        let ok = McpClient::connect(
            reqwest::Client::new(),
            server(&fake.url),
            Some("secret-token".into()),
        )
        .await;
        assert!(ok.is_ok());
        assert!(fake
            .auth_headers
            .lock()
            .iter()
            .all(|h| h == "bearer secret-token"));

        let bad = McpClient::connect(
            reqwest::Client::new(),
            server(&fake.url),
            Some("wrong".into()),
        )
        .await;
        let err = match bad {
            Err(err) => err,
            Ok(_) => panic!("a rejected token must not connect"),
        };
        assert!(err.to_string().contains("토큰"), "{err}");
    }

    #[tokio::test]
    async fn a_tool_level_error_comes_back_as_is_error_not_as_a_transport_failure() {
        let fake = FakeMcpServer::start(false, None).await;
        let (client, _) = McpClient::connect(reqwest::Client::new(), server(&fake.url), None)
            .await
            .unwrap();
        let result = client
            .call_tool("boom", &serde_json::json!({}))
            .await
            .unwrap();
        let (text, is_error) = result_text(&result);
        assert!(is_error);
        assert_eq!(text, "터졌습니다");
    }

    #[tokio::test]
    async fn a_server_that_is_not_there_fails_the_handshake_quickly() {
        let unreachable = server("http://127.0.0.1:9/mcp");
        let started = std::time::Instant::now();
        let result = McpClient::connect(reqwest::Client::new(), unreachable, None).await;
        assert!(result.is_err());
        assert!(started.elapsed() < HANDSHAKE_TIMEOUT + Duration::from_secs(2));
    }

    // ── The stdio transport against a scripted child ─────────────────────

    const FAKE_STDIO: &str = r#"
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method = msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "py", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "upper", "description": "대문자", "inputSchema": {"type": "object", "properties": {"s": {"type": "string"}}}}]}
    elif method == "tools/call":
        s = msg["params"]["arguments"].get("s", "")
        print("log line that is not json", flush=True)
        result = {"content": [{"type": "text", "text": s.upper()}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "nope"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
"#;

    #[tokio::test]
    async fn a_stdio_server_speaks_one_json_per_line_and_noise_is_skipped() {
        if std::process::Command::new("python3")
            .arg("--version")
            .output()
            .is_err()
        {
            eprintln!("python3 not available; skipping stdio transport test");
            return;
        }
        let server = McpServer {
            id: "01STD".into(),
            user_id: "u1".into(),
            name: "py".into(),
            transport: Transport::Stdio,
            url: None,
            command: Some("python3".into()),
            args: vec!["-c".into(), FAKE_STDIO.into()],
            enabled: true,
            created_at_ms: 0,
            last_ok_at_ms: None,
            last_error: None,
        };
        let (client, info) = McpClient::connect(reqwest::Client::new(), server, None)
            .await
            .unwrap();
        assert_eq!(info["serverInfo"]["name"], "py");
        let tools = client.list_tools().await.unwrap();
        assert_eq!(tools[0].name, "upper");
        let result = client
            .call_tool("upper", &serde_json::json!({ "s": "abc" }))
            .await
            .unwrap();
        assert_eq!(result_text(&result).0, "ABC");
    }
}
