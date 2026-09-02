/**
 * 환경설정 — the place things are *set up*, as opposed to used.
 *
 * The provider connection lives here rather than inside the agent panel: the
 * panel is where you talk to the model, and a form that appears where the
 * conversation should be reads as a broken conversation. The panel now points
 * here, and this dialog owns connect / model choice / disconnect.
 *
 * The key handling contract is unchanged from the old in-panel form: the key is
 * typed here, handed to Rust once, and kept only in the OS keychain. After
 * connecting, the model dropdown is repopulated from the *account's own*
 * `/v1/models` (fetched through the byte proxy, so the key stays in Rust) —
 * whatever the connected subscription can run is what the dropdown offers.
 */

import { useEffect, useState } from "react";

import {
  DEFAULT_MODELS,
  listProviderModels,
  type ProviderModel,
} from "@/lib/agent/models";
import { agentHost, capabilities } from "@/lib/ipc";
import { useAgent } from "@/store/agent";
import { useApp } from "@/store/app";

import { IconClose } from "./Icon";

export function Settings() {
  const open = useApp((state) => state.settingsOpen);
  const setSettings = useApp((state) => state.setSettings);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettings(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setSettings]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onClick={() => setSettings(false)}
      role="presentation"
    >
      <div
        className="modal settings"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="환경설정"
      >
        <header className="modal-header">
          <h2>환경설정</h2>
          <button type="button" onClick={() => setSettings(false)} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body settings-body">
          <section className="settings-section">
            <h3>기능 안내</h3>
            <p className="settings-hint">
              하고 싶은 일을 찾아 그대로 따라 하면 됩니다. 전부 지금 화면에서
              바로 됩니다.
            </p>
            <GuideList />
          </section>

          <section className="settings-section">
            <h3>에이전트 프로바이더</h3>
            <ProviderSection />
          </section>
        </div>
      </div>
    </div>
  );
}

/**
 * What-to-do → how-to-do-it, one line each.
 *
 * This exists because a feature nobody can find is a feature that does not
 * exist. Every row names the exact control ("컴포저의 클립", "채널 머리글의
 * 톱니") rather than a concept, so the reader can put the dialog down and go
 * press the thing.
 */
function GuideList() {
  const rows: Array<{ want: string; how: string }> = [
    {
      want: "채널·사람·앱·메시지·파일을 한 번에 찾기",
      how: "⌘K (Windows/Linux 는 Ctrl+K) — 목록에서 Enter 로 바로 이동하거나 파일을 내려받습니다.",
    },
    {
      want: "파일 보내기",
      how: "컴포저의 클립 버튼을 누르거나, 파일을 창에 끌어다 놓습니다.",
    },
    {
      want: "이미지 크게 보기",
      how: "첨부한 이미지는 대화에 미리보기로 보입니다. 클릭하면 크게 열립니다.",
    },
    {
      want: "메시지를 다른 채널/DM 에 전하기",
      how: "메시지에 마우스를 올리고 공유 버튼 — 출처가 인용으로 함께 갑니다.",
    },
    {
      want: "일정·할 일·결정 공유하기",
      how: "컴포저의 서식 버튼 — 일시·담당·기한이 늘 같은 자리에 오는 서식을 넣어줍니다.",
    },
    {
      want: "대화를 가리지 않고 답글 달기",
      how: "메시지의 답글 버튼 — 스레드가 오른쪽 열에 나란히 열립니다.",
    },
    {
      want: "채널 관리 (이름·주제·구성원 추가/제거·보관)",
      how: "채널 머리글 오른쪽의 톱니 버튼. 이름 변경·보관은 채널 관리자만 할 수 있습니다.",
    },
    {
      want: "채널 알림 끄기/켜기",
      how: "채널 머리글의 종 버튼. 음소거해도 나를 부르는 멘션은 셉니다.",
    },
    {
      want: "AI 에이전트에게 일 시키기",
      how: "아래에서 프로바이더를 연결한 뒤, 왼쪽 도크의 에이전트 버튼을 누릅니다.",
    },
  ];
  return (
    <dl className="settings-guide">
      {rows.map((row) => (
        <div key={row.want}>
          <dt>{row.want}</dt>
          <dd>{row.how}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Connect, choose a model from the account, or disconnect. */
function ProviderSection() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  // The dialog can open before the agent panel ever has, so it fetches the
  // status itself rather than assuming the panel already did.
  useEffect(() => {
    if (!capabilities.computerControl) return;
    let cancelled = false;
    void agentHost
      .agentProviderStatus()
      .then((status) => {
        if (!cancelled) setProvider(status);
      })
      .catch(() => {
        if (!cancelled) setProvider(null);
      });
    return () => {
      cancelled = true;
    };
  }, [setProvider]);

  if (!capabilities.computerControl) {
    return (
      <div className="settings-note">
        <p>
          브라우저에서는 프로바이더를 연결할 수 없습니다. 키는 OS 키체인에만
          저장되고, 브라우저에는 키체인이 없습니다.
        </p>
        <p>
          지금은 <strong>가짜 프로바이더</strong>로 화면과 흐름만 확인할 수
          있습니다. 실제 모델을 쓰려면 데스크톱 앱에서 열어주세요.
        </p>
      </div>
    );
  }

  return provider?.connected ? (
    <ConnectedProvider />
  ) : (
    <ConnectForm />
  );
}

/** The state after a key is in the keychain: pick a model, or disconnect. */
function ConnectedProvider() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  const [models, setModels] = useState<ProviderModel[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ask the account which models it can run. Through the byte proxy, so this
  // is the same trust boundary as every agent request.
  useEffect(() => {
    let cancelled = false;
    void listProviderModels()
      .then((list) => {
        if (!cancelled) setModels(list);
      })
      .catch((caught) => {
        if (cancelled) return;
        setModelsError(
          caught instanceof Error ? caught.message : "모델 목록을 가져오지 못했습니다.",
        );
        setModels(DEFAULT_MODELS);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentModel = provider?.model ?? "";
  // The stored model is always choosable, even if the fetched list somehow
  // lacks it — a dropdown that silently switches your model is worse than one
  // with a stale entry.
  const options =
    models && models.some((entry) => entry.id === currentModel)
      ? models
      : [...(models ?? []), { id: currentModel, displayName: currentModel }].filter(
          (entry) => entry.id,
        );

  const changeModel = async (model: string) => {
    if (!model || model === currentModel) return;
    setBusy(true);
    setError(null);
    try {
      setProvider(await agentHost.agentProviderSetModel(model));
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "모델을 변경하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      setProvider(await agentHost.agentProviderDisconnect());
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "연결을 해제하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-provider">
      <div className="settings-provider-status">
        <strong>Anthropic</strong>
        <span>
          연결됨
          {provider?.key_fingerprint ? ` · 키 ····${provider.key_fingerprint}` : ""}
        </span>
        <button
          type="button"
          className="settings-disconnect"
          onClick={() => void disconnect()}
          disabled={busy}
        >
          연결 해제
        </button>
      </div>

      <label>
        모델
        <select
          value={currentModel}
          onChange={(event) => void changeModel(event.target.value)}
          disabled={busy || models === null}
        >
          {models === null ? (
            <option value={currentModel}>{currentModel || "불러오는 중…"}</option>
          ) : (
            options.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.displayName}
              </option>
            ))
          )}
        </select>
      </label>
      <p className="settings-hint">
        {modelsError
          ? `계정의 모델 목록을 가져오지 못해 기본 목록을 보여줍니다. (${modelsError})`
          : "연결된 계정에서 사용할 수 있는 모델 목록입니다."}
      </p>

      {error ? <p className="settings-error">{error}</p> : null}
      {provider?.last_error ? (
        <p className="settings-error">{provider.last_error}</p>
      ) : null}
    </div>
  );
}

/**
 * Connecting a model provider.
 *
 * The key is typed here and immediately handed to Rust, which puts it in the
 * OS keychain. It is never stored in this component, never in the store, and
 * never sent to the Llack server. Connecting performs one real validation
 * call, so an invalid key fails here rather than halfway through the user's
 * first question.
 */
function ConnectForm() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(DEFAULT_MODELS[0]?.id ?? "claude-opus-5");
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

  return (
    <form className="settings-provider" onSubmit={connect}>
      <ol className="settings-steps">
        <li>
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
            console.anthropic.com
          </a>
          에서 API 키를 만듭니다.
        </li>
        <li>아래에 키를 붙여넣고 연결을 누릅니다. 키가 맞는지 한 번 확인합니다.</li>
        <li>
          연결되면 계정에서 쓸 수 있는 모델 목록이 여기에 나타나고, 왼쪽 도크의
          에이전트 버튼으로 대화를 시작할 수 있습니다.
        </li>
      </ol>

      <label>
        모델
        <select value={model} onChange={(event) => setModel(event.target.value)}>
          {DEFAULT_MODELS.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.displayName}
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

      <p className="settings-hint">
        키는 이 기기의 OS 키체인에만 저장되며, Llack 서버로 전송되지 않습니다.
      </p>

      {error ? <p className="settings-error">{error}</p> : null}
      {provider?.last_error ? (
        <p className="settings-error">{provider.last_error}</p>
      ) : null}

      <button type="submit" className="settings-connect" disabled={busy || !apiKey}>
        {busy ? "확인 중…" : "연결"}
      </button>
    </form>
  );
}
