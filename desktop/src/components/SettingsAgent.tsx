/**
 * Agent v2 settings: MCP servers, memory, skills, and the native-dialog toggle.
 *
 * Everything here is *this device's* agent state, read and written through Rust.
 * None of it is a control the model can reach: an MCP server's credential lives
 * in the OS keychain and never returns to the webview, a saved memory is data
 * the gate still classifies, and the dialog toggle only chooses *where* an
 * approval is answered, never *whether* one is needed.
 *
 * Desktop only. A browser tab has no keychain, no child processes, and no OS
 * dialog, so the parent renders these sections only when `computerControl` is
 * true.
 */

import { useCallback, useEffect, useState } from "react";

import type { AgentMemory, AgentSkill, McpServerView } from "@/lib/agent/types";
import { asCommandError } from "@/lib/errors";
import { formatRelative } from "@/lib/format";
import { agentHost } from "@/lib/ipc";

function message(error: unknown, fallback: string): string {
  try {
    return asCommandError(error).message || fallback;
  } catch {
    return error instanceof Error ? error.message : fallback;
  }
}

/* ── MCP servers ──────────────────────────────────────────────────────── */

/**
 * Connected MCP servers and the tools they contribute.
 *
 * Adding a server performs the real handshake (`initialize` + `tools/list`)
 * before it is stored, so a bad URL or a rejected token fails here rather than
 * on the first tool call. Every MCP tool is class 3 — approved every time and
 * never remembered — so the count shown is a count of *prompts the model can
 * raise*, which is the number worth seeing.
 */
export function McpSection() {
  const [servers, setServers] = useState<McpServerView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      setServers(await agentHost.agentMcpList());
    } catch (caught) {
      setError(message(caught, "MCP 서버 목록을 가져오지 못했습니다."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setBusy(true);
    setError(null);
    try {
      setServers(await agentHost.agentMcpRefresh());
    } catch (caught) {
      setError(message(caught, "새로고침에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (server: McpServerView) => {
    setError(null);
    try {
      const updated = await agentHost.agentMcpSetEnabled(server.id, !server.enabled);
      setServers((list) => (list ?? []).map((s) => (s.id === updated.id ? updated : s)));
    } catch (caught) {
      setError(message(caught, "상태를 바꾸지 못했습니다."));
    }
  };

  const remove = async (server: McpServerView) => {
    setError(null);
    try {
      await agentHost.agentMcpRemove(server.id);
      setServers((list) => (list ?? []).filter((s) => s.id !== server.id));
    } catch (caught) {
      setError(message(caught, "삭제하지 못했습니다."));
    }
  };

  return (
    <div className="settings-mcp">
      <p className="settings-hint">
        MCP 서버의 도구는 에이전트 카탈로그에 <code>mcp.서버.도구</code> 이름으로 들어옵니다.
        MCP 호출은 <strong>매번 사용자 승인</strong>이 필요하고, 결과는 신뢰할 수 없는
        데이터로 다뤄집니다.
      </p>

      {servers === null ? (
        <p className="settings-hint">불러오는 중…</p>
      ) : servers.length === 0 ? (
        <p className="settings-empty">연결된 MCP 서버가 없습니다.</p>
      ) : (
        <ul className="settings-mcp-list">
          {servers.map((server) => (
            <li key={server.id} className="settings-mcp-row">
              <div className="settings-mcp-main">
                <strong>{server.name}</strong>
                <span className="settings-mcp-meta">
                  {server.transport === "http"
                    ? (server.url ?? "HTTP")
                    : [server.command, ...(server.args ?? [])].filter(Boolean).join(" ") || "stdio"}
                </span>
                <span className="settings-mcp-meta">
                  도구 {server.tool_count}개
                  {server.has_credential ? " · 자격증명 저장됨" : ""}
                  {typeof server.last_ok_at_ms === "number"
                    ? ` · 최근 연결 ${formatRelative(new Date(server.last_ok_at_ms).toISOString())}`
                    : ""}
                </span>
                {server.last_error ? (
                  <span className="settings-error">{server.last_error}</span>
                ) : null}
              </div>
              <div className="settings-mcp-actions">
                <label className="settings-switch">
                  <input
                    type="checkbox"
                    checked={server.enabled}
                    onChange={() => void toggle(server)}
                  />
                  <span>사용</span>
                </label>
                <button type="button" className="settings-disconnect" onClick={() => void remove(server)}>
                  삭제
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {error ? <p className="settings-error">{error}</p> : null}

      <div className="settings-mcp-buttons">
        <button type="button" onClick={() => setAdding((v) => !v)}>
          {adding ? "취소" : "서버 추가"}
        </button>
        <button type="button" onClick={() => void refresh()} disabled={busy}>
          {busy ? "새로고침 중…" : "새로고침"}
        </button>
      </div>

      {adding ? (
        <McpAddForm
          onAdded={(server) => {
            setServers((list) => [...(list ?? []), server]);
            setAdding(false);
          }}
        />
      ) : null}
    </div>
  );
}

function McpAddForm({ onAdded }: { onAdded: (server: McpServerView) => void }) {
  const [transport, setTransport] = useState<"http" | "stdio">("http");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const server = await agentHost.agentMcpAdd({
        name: name.trim(),
        transport,
        url: transport === "http" ? url.trim() : null,
        command: transport === "stdio" ? command.trim() : null,
        args:
          transport === "stdio"
            ? args.split(/\s+/).map((a) => a.trim()).filter(Boolean)
            : [],
        token: token.trim() || null,
      });
      onAdded(server);
    } catch (caught) {
      setError(message(caught, "서버를 추가하지 못했습니다. 연결을 확인하세요."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="settings-mcp-add" onSubmit={submit}>
      <label>
        전송 방식
        <select value={transport} onChange={(e) => setTransport(e.target.value as "http" | "stdio")}>
          <option value="http">HTTP (Streamable)</option>
          <option value="stdio">stdio (로컬 프로세스)</option>
        </select>
      </label>
      <label>
        이름
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 사내 위키" required />
      </label>
      {transport === "http" ? (
        <>
          <label>
            URL
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://mcp.example.com/rpc"
              required
            />
          </label>
          <label>
            토큰 (선택)
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Bearer 토큰"
              autoComplete="off"
            />
          </label>
        </>
      ) : (
        <>
          <label>
            명령
            <input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="예: npx"
              required
            />
          </label>
          <label>
            인수 (공백 구분)
            <input value={args} onChange={(e) => setArgs(e.target.value)} placeholder="-y @modelcontextprotocol/server-foo" />
          </label>
        </>
      )}
      <p className="settings-hint">
        추가 시 서버에 실제로 연결해 도구 목록을 가져옵니다. 토큰은 OS 키체인에만 저장됩니다.
      </p>
      {error ? <p className="settings-error">{error}</p> : null}
      <button type="submit" className="settings-connect" disabled={busy || !name.trim()}>
        {busy ? "연결 중…" : "추가"}
      </button>
    </form>
  );
}

/* ── Memory ───────────────────────────────────────────────────────────── */

/**
 * What the agent has been told to remember.
 *
 * Memories are prepended to the system prompt each turn, so this list is the
 * one place to see — and forget — what colours the agent's answers. A memory
 * saved during a tainted session is class 3 to write, because a channel message
 * hardening into a durable instruction is exactly the injection-persistence
 * path; forgetting one is always allowed here.
 */
export function AgentMemorySection() {
  const [memories, setMemories] = useState<AgentMemory[] | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setMemories(await agentHost.agentMemoriesList(100));
    } catch (caught) {
      setError(message(caught, "기억을 가져오지 못했습니다."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await agentHost.agentMemoryAdd(trimmed, []);
      setMemories((list) => [saved, ...(list ?? [])]);
      setText("");
    } catch (caught) {
      setError(message(caught, "저장하지 못했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const forget = async (memory: AgentMemory) => {
    setError(null);
    try {
      await agentHost.agentMemoryDelete(memory.id);
      setMemories((list) => (list ?? []).filter((m) => m.id !== memory.id));
    } catch (caught) {
      setError(message(caught, "삭제하지 못했습니다."));
    }
  };

  return (
    <div className="settings-memory">
      <p className="settings-hint">
        에이전트가 다음 세션에도 기억할 사실입니다. 매 턴 시스템 프롬프트 앞에 붙습니다.
        여기서 지우면 더 이상 참고하지 않습니다.
      </p>

      <form className="settings-memory-add" onSubmit={add}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="예: 배포는 항상 스테이징 먼저 확인"
          maxLength={2000}
        />
        <button type="submit" className="settings-connect" disabled={busy || !text.trim()}>
          추가
        </button>
      </form>

      {error ? <p className="settings-error">{error}</p> : null}

      {memories === null ? (
        <p className="settings-hint">불러오는 중…</p>
      ) : memories.length === 0 ? (
        <p className="settings-empty">저장된 기억이 없습니다.</p>
      ) : (
        <ul className="settings-memory-list">
          {memories.map((memory) => (
            <li key={memory.id}>
              <div className="settings-memory-body">
                <span>{memory.text}</span>
                {memory.tags.length > 0 ? (
                  <span className="settings-memory-tags">{memory.tags.join(", ")}</span>
                ) : null}
              </div>
              <button type="button" className="settings-disconnect" onClick={() => void forget(memory)}>
                잊기
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── Skills ───────────────────────────────────────────────────────────── */

/**
 * Reusable procedures the agent can read on its own.
 *
 * A skill is a Markdown file with a `# 제목` first line and a one-line
 * description; the agent sees the titles in its prompt and reads the body with
 * `skill.read` when a task matches. Editing one here is editing a file under
 * the app's data directory — nothing more magical than that.
 */
export function AgentSkillsSection() {
  const [skills, setSkills] = useState<AgentSkill[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSkills(await agentHost.agentSkillsList());
    } catch (caught) {
      setError(message(caught, "스킬을 가져오지 못했습니다."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openNew = () => {
    setEditing("");
    setNameInput("");
    setBody("# 제목\n한 줄 설명\n\n절차를 여기에 적습니다.");
    setError(null);
  };

  const openExisting = async (skill: AgentSkill) => {
    setError(null);
    try {
      const text = await agentHost.agentSkillRead(skill.name);
      setEditing(skill.name);
      setNameInput(skill.name);
      setBody(text);
    } catch (caught) {
      setError(message(caught, "스킬을 열지 못했습니다."));
    }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = nameInput.trim();
    if (!name || !/^[a-z0-9_-]{1,40}$/.test(name)) {
      setError("이름은 소문자·숫자·- _ 만, 40자 이내여야 합니다.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await agentHost.agentSkillSave(name, body);
      await load();
      setEditing(null);
    } catch (caught) {
      setError(message(caught, "저장하지 못했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (skill: AgentSkill) => {
    setError(null);
    try {
      await agentHost.agentSkillDelete(skill.name);
      setSkills((list) => (list ?? []).filter((s) => s.name !== skill.name));
    } catch (caught) {
      setError(message(caught, "삭제하지 못했습니다."));
    }
  };

  return (
    <div className="settings-skills">
      <p className="settings-hint">
        스킬은 절차서입니다. 첫 줄 <code># 제목</code>, 둘째 줄 한 줄 설명으로 시작합니다.
        에이전트는 제목을 보고 관련 작업일 때 본문을 읽어 그대로 따릅니다.
      </p>

      {skills === null ? (
        <p className="settings-hint">불러오는 중…</p>
      ) : skills.length === 0 ? (
        <p className="settings-empty">저장된 스킬이 없습니다.</p>
      ) : (
        <ul className="settings-skill-list">
          {skills.map((skill) => (
            <li key={skill.name}>
              <button type="button" className="settings-skill-open" onClick={() => void openExisting(skill)}>
                <strong>{skill.title || skill.name}</strong>
                {skill.description ? <span>{skill.description}</span> : null}
                <span className="settings-mcp-meta">{skill.name}.md · {skill.bytes}B</span>
              </button>
              <button type="button" className="settings-disconnect" onClick={() => void remove(skill)}>
                삭제
              </button>
            </li>
          ))}
        </ul>
      )}

      {error ? <p className="settings-error">{error}</p> : null}

      {editing === null ? (
        <button type="button" onClick={openNew}>
          스킬 추가
        </button>
      ) : (
        <form className="settings-skill-edit" onSubmit={save}>
          <label>
            파일 이름
            <input
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              placeholder="deploy-checklist"
              disabled={busy}
            />
          </label>
          <label>
            내용
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} disabled={busy} />
          </label>
          <div className="settings-mcp-buttons">
            <button type="submit" className="settings-connect" disabled={busy || !nameInput.trim()}>
              {busy ? "저장 중…" : "저장"}
            </button>
            <button type="button" onClick={() => setEditing(null)} disabled={busy}>
              취소
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

/* ── Native dialogs ───────────────────────────────────────────────────── */

/**
 * Whether class-3 approvals are answered in an OS dialog.
 *
 * On, the highest-risk approvals (host writes, MCP calls, typing) surface as a
 * native window the webview cannot forge or auto-dismiss; the in-app card shows
 * a waiting state. Off is for headless and test environments where no dialog
 * can appear. Either way the approval is still required — this only moves it.
 */
export function NativeDialogSection() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void agentHost
      .agentNativeDialogs(null)
      .then(setEnabled)
      .catch((caught) => setError(message(caught, "설정을 가져오지 못했습니다.")));
  }, []);

  const toggle = async () => {
    setError(null);
    try {
      setEnabled(await agentHost.agentNativeDialogs(!enabled));
    } catch (caught) {
      setError(message(caught, "설정을 바꾸지 못했습니다."));
    }
  };

  return (
    <div className="settings-native-dialog">
      <label className="settings-switch">
        <input type="checkbox" checked={enabled === true} onChange={() => void toggle()} disabled={enabled === null} />
        <span>높은 위험 승인을 운영체제 대화상자로 받기</span>
      </label>
      <p className="settings-hint">
        켜면 host 쓰기·MCP 호출·입력 같은 3등급 승인이 웹뷰가 위조하거나 자동으로 닫을 수
        없는 네이티브 창으로 뜹니다. 어느 쪽이든 승인 자체는 그대로 필요합니다.
      </p>
      {error ? <p className="settings-error">{error}</p> : null}
    </div>
  );
}
