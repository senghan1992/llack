/**
 * Connecting a model provider.
 *
 * The key is typed here and immediately handed to Rust, which puts it in the
 * OS keychain. It is never stored in this component, never in the store, and
 * never sent to the Llack server — every later request is signed by the byte
 * proxy on the Rust side, so the webview holds the key for exactly as long as
 * this form is on screen.
 *
 * Connecting performs one real validation call, so an invalid key fails here
 * rather than halfway through the user's first question.
 */

import { useState } from "react";

import { agentHost, capabilities } from "@/lib/ipc";
import { useAgent } from "@/store/agent";

/** The models this build knows how to drive. */
const MODELS = [
  { id: "claude-opus-5", label: "Claude Opus 5" },
  { id: "claude-sonnet-5", label: "Claude Sonnet 5" },
];

export function AgentProviderSetup() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(MODELS[0]?.id ?? "claude-opus-5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const status = await agentHost.agentProviderConnect("anthropic", apiKey, model);
      setProvider(status);
      // Dropped from component state the moment Rust has it.
      setApiKey("");
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "연결하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!capabilities.computerControl) {
    return (
      <div className="agent-setup">
        <p className="agent-setup-lead">
          브라우저에서는 프로바이더를 연결할 수 없습니다. 키는 OS 키체인에만
          저장되고, 브라우저에는 키체인이 없습니다.
        </p>
        <p className="agent-setup-note">
          지금은 <strong>가짜 프로바이더</strong>로 화면과 흐름만 확인할 수 있습니다.
          실제 모델을 쓰려면 데스크톱 앱에서 열어주세요.
        </p>
      </div>
    );
  }

  return (
    <form className="agent-setup" onSubmit={connect}>
      <p className="agent-setup-lead">
        에이전트를 쓰려면 모델 프로바이더를 연결하세요.
      </p>

      <label>
        모델
        <select value={model} onChange={(event) => setModel(event.target.value)}>
          {MODELS.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        API 키
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="sk-ant-…"
          autoComplete="off"
          spellCheck={false}
          required
        />
      </label>

      <p className="agent-setup-note">
        키는 이 기기의 OS 키체인에만 저장되며, Llack 서버로 전송되지 않습니다.
      </p>

      {error ? <p className="agent-setup-error">{error}</p> : null}
      {provider?.last_error ? (
        <p className="agent-setup-error">{provider.last_error}</p>
      ) : null}

      <button type="submit" className="agent-setup-submit" disabled={busy || !apiKey}>
        {busy ? "확인 중…" : "연결"}
      </button>
    </form>
  );
}
