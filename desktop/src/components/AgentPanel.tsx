/**
 * The agent, as a third docked sheet.
 *
 * It is a sheet rather than a window or a separate app because that is this
 * product's one structural promise: new work arrives *beside* the transcript
 * instead of covering it. An agent summarising `#개발` while `#개발` stays
 * readable next to it is the thing only this layout can show.
 *
 * It is first-party rather than a mini-app because a mini-app cannot hold a
 * provider credential, cannot invoke a Tauri command, and cannot receive
 * `llack://` events — and the panel needs all three. The extension point for
 * third parties is the tool catalog, not this panel.
 *
 * ## Two sheets, never three
 *
 * The Tauri window's minimum is 940px and the two-sheet stacking rule fires at
 * 960px, so a third simultaneous sheet would leave roughly a 200px transcript.
 * Opening the agent therefore closes the mini-app panel, and vice versa — see
 * `AppDock` and the `:has()` rules in `global.css`.
 */

import { useEffect, useRef, useState } from "react";

import { createDriver, type TurnDriver } from "@/lib/agent/driver";
import { agentHost, capabilities, events } from "@/lib/ipc";
import { renderMessage } from "@/lib/markdown";
import { useAgent } from "@/store/agent";
import { useApp } from "@/store/app";

import { AgentApprovalCard } from "./AgentApprovalCard";
import { IconClose, IconSend, IconStop } from "./Icon";

export function AgentPanel() {
  const open = useAgent((state) => state.open);
  const setOpen = useAgent((state) => state.setOpen);
  const phase = useAgent((state) => state.phase);
  const turns = useAgent((state) => state.turns);
  const provider = useAgent((state) => state.provider);
  const sessionId = useAgent((state) => state.sessionId);
  const banner = useAgent((state) => state.banner);
  const tainted = useAgent((state) => state.tainted);
  const startSession = useAgent((state) => state.startSession);
  const setProvider = useAgent((state) => state.setProvider);
  const showApproval = useAgent((state) => state.showApproval);
  const clearApproval = useAgent((state) => state.clearApproval);
  const setComputerControl = useAgent((state) => state.setComputerControl);
  const setBanner = useAgent((state) => state.setBanner);
  const activeChannelId = useApp((state) => state.activeChannelId);
  const openSettings = useApp((state) => state.setSettings);

  const [draft, setDraft] = useState("");
  const [auditOpen, setAuditOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  /**
   * One driver per session, holding the API-shaped message history.
   *
   * A ref rather than state: replacing it must not re-render, and re-rendering
   * must not replace it — a new driver mid-conversation would silently start
   * the history over and the only symptom would be the model losing the thread.
   */
  const driverRef = useRef<{ sessionId: string; driver: TurnDriver } | null>(null);

  // One subscription for the whole panel's life, not per turn.
  useEffect(() => {
    if (!open) return undefined;
    setComputerControl(capabilities.computerControl);

    let cancelled = false;
    void agentHost
      .agentProviderStatus()
      .then((status) => {
        if (!cancelled) setProvider(status);
      })
      .catch(() => {
        if (!cancelled) setProvider(null);
      });

    const unlisten = events.onAgent((event) => {
      switch (event.kind) {
        case "approval_pending":
          showApproval(event.request);
          break;
        case "approval_closed":
          clearApproval(event.request_id);
          break;
        case "provider_changed":
          setProvider(event.status);
          break;
        case "session_started":
          startSession(event.session_id);
          break;
      }
    });

    return () => {
      cancelled = true;
      void unlisten.then((stop) => stop()).catch(() => {});
    };
  }, [open, setComputerControl, setProvider, showApproval, clearApproval, startSession]);

  // Follow the stream: an agent answer that scrolls off the bottom while it is
  // being written is the same bug as a chat transcript that does not follow.
  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns]);

  if (!open) return null;

  const send = async () => {
    const text = draft.trim();
    if (!text || phase !== "idle") return;
    setDraft("");

    try {
      let session = sessionId;
      if (!session) {
        session = await agentHost.agentOpenSession(null);
        startSession(session);
      }

      if (driverRef.current?.sessionId !== session) {
        driverRef.current = {
          sessionId: session,
          driver: createDriver(session, provider),
        };
      }
      // The engine needs to know which channel "this channel" means, and the
      // user may have moved since the session opened.
      await agentHost.agentFocus(session, activeChannelId).catch(() => {});

      await driverRef.current.driver.send(text);
    } catch (error) {
      // The driver reports turn-level failures into the turn itself; this
      // catches the ones before a turn exists — opening a session, fetching the
      // catalog — which would otherwise vanish.
      setBanner(
        error instanceof Error ? error.message : "대화를 시작할 수 없습니다.",
      );
    }
  };

  const stop = () => {
    driverRef.current?.driver.stop();
  };

  const needsProvider = !provider?.connected;

  return (
    <aside className="agent-panel" aria-label="에이전트">
      <header className="agent-panel-header">
        <h2>
          에이전트
          {provider?.connected ? (
            // A button, because the model is a choice: it opens the settings
            // dialog where the account's model list lives.
            <button
              type="button"
              className="agent-model"
              onClick={() => openSettings(true)}
              title="설정에서 모델 변경"
            >
              {provider.model}
            </button>
          ) : null}
        </h2>
        {tainted ? (
          <span
            className="agent-taint"
            title="채널 내용을 읽었으므로 이 세션에서는 승인을 매번 다시 확인합니다."
          >
            채널 읽음
          </span>
        ) : null}
        {capabilities.computerControl ? (
          <button
            type="button"
            className="agent-audit-open"
            onClick={() => setAuditOpen(true)}
            title="에이전트가 실행한 도구의 감사 기록"
          >
            감사 기록
          </button>
        ) : null}
        <button type="button" onClick={() => setOpen(false)} aria-label="에이전트 닫기">
          <IconClose size={13} />
        </button>
      </header>

      {auditOpen ? <AgentAuditModal onClose={() => setAuditOpen(false)} /> : null}

      {banner ? <p className="agent-banner">{banner}</p> : null}

      <div className="agent-scroll" ref={scrollRef}>
        {needsProvider ? (
          <AgentNeedsProvider onOpenSettings={() => openSettings(true)} />
        ) : turns.length === 0 ? (
          <AgentEmptyState />
        ) : (
          turns.map((turn) => <AgentTurnView key={turn.id} turn={turn} />)
        )}
      </div>

      <AgentApprovalCard />

      <div className="agent-composer">
        <div className="agent-composer-box">
          <textarea
            value={draft}
            disabled={needsProvider || phase !== "idle"}
            placeholder={
              needsProvider
                ? "프로바이더를 연결하면 사용할 수 있습니다"
                : phase === "awaiting_approval"
                  ? "승인을 기다리는 중…"
                  : "무엇을 도와드릴까요?"
            }
            rows={Math.min(8, draft.split("\n").length)}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          {phase === "idle" ? (
            <button
              type="button"
              className="agent-send"
              onClick={() => void send()}
              disabled={needsProvider || !draft.trim()}
              aria-label="보내기"
            >
              <IconSend size={15} />
            </button>
          ) : (
            /* The same slot, so stop is where send was — a control that moves
               between states is a control people miss when they need it most. */
            <button
              type="button"
              className="agent-stop"
              onClick={stop}
              aria-label="중단"
              title="중단"
            >
              <IconStop size={13} />
            </button>
          )}
        </div>
        {!capabilities.computerControl ? (
          // Shown rather than hidden: a missing capability the user cannot see
          // becomes "why won't it do the thing".
          <p className="agent-composer-note">
            컴퓨터 제어는 데스크톱 앱에서만 사용할 수 있습니다.
          </p>
        ) : null}
      </div>
    </aside>
  );
}

/**
 * The agent's output resolves no ids.
 *
 * A `<@id>` or `<#id>` the model emitted is not a real reference — it did not
 * come from the server's mention pipeline — so resolving it would let the model
 * fabricate a link that looks like the product's own. Unresolved, the renderer
 * leaves it as literal text.
 */
const AGENT_RENDER = {
  userName: () => undefined,
  channelName: () => undefined,
};

/**
 * No provider yet: point at settings rather than embedding the form here.
 *
 * The panel is where you talk to the model; setup is a different act and lives
 * in 환경설정 with the rest of what gets configured once. In a browser there is
 * nothing to configure, so the note says what stands in instead.
 */
function AgentNeedsProvider({ onOpenSettings }: { onOpenSettings: () => void }) {
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
    <div className="agent-setup">
      <p className="agent-setup-lead">
        에이전트를 쓰려면 모델 프로바이더를 연결하세요.
      </p>
      <p className="agent-setup-note">
        환경설정에서 API 키를 연결하면, 계정에서 사용할 수 있는 모델을 골라 쓸 수
        있습니다.
      </p>
      <button type="button" className="agent-setup-open" onClick={onOpenSettings}>
        설정에서 연결
      </button>
    </div>
  );
}

function AgentEmptyState() {
  const channel = useApp((state) =>
    state.channels.find((candidate) => candidate.id === state.activeChannelId),
  );
  const name = channel?.name ? `#${channel.name}` : "이 채널";

  /*
   * A named empty state, pinned to the bottom.
   *
   * It used to be a privacy disclaimer with no heading, centred in ~290px of
   * void — an unnamed region, which is the one thing the direction contract
   * says not to leave. It now says what this is, sits next to the composer the
   * examples are about, and puts the storage note where a footnote belongs.
   */
  return (
    <div className="agent-empty">
      <h3>무엇을 시켜볼까요</h3>
      <ul>
        <li>{name} 의 최근 논의를 요약해줘</li>
        <li>내 프로젝트에서 실패하는 테스트를 찾아줘</li>
        <li>어제 배포 로그에서 오류만 뽑아줘</li>
      </ul>
      <p>이 대화는 이 기기에만 저장됩니다.</p>
    </div>
  );
}

function AgentTurnView({ turn }: { turn: ReturnType<typeof useAgent.getState>["turns"][number] }) {
  return (
    <article className={`agent-turn agent-turn-${turn.role}`}>
      {turn.blocks.map((block, index) => {
        if (block.kind === "text") {
          return (
            <div
              key={index}
              className="agent-text"
              // The same renderer the transcript uses. It escapes before any
              // tag exists and emits no image element, so agent output cannot
              // become a zero-click exfiltration beacon — which a second,
              // hand-rolled markdown path in this file very easily could.
              // (Spelled out rather than written as a tag: the design detector
              // reads tag literals in comments as real markup, and a check
              // that is permanently red is a check people stop reading.)
              dangerouslySetInnerHTML={{ __html: renderMessage(block.text, AGENT_RENDER) }}
            />
          );
        }
        if (block.kind === "thinking") {
          return (
            <details key={index} className="agent-thinking">
              <summary>생각 중</summary>
              <p>{block.text}</p>
            </details>
          );
        }
        return <AgentToolCard key={index} run={block.run} />;
      })}

      {turn.streaming ? <span className="agent-cursor" aria-hidden="true" /> : null}
      {turn.error ? <p className="agent-turn-error">{turn.error}</p> : null}
    </article>
  );
}

function AgentToolCard({
  run,
}: {
  run: {
    id: string;
    name: string;
    state: string;
    artifact: string | null;
    summary: string | null;
    image?: string | null;
  };
}) {
  return (
    <div className={`agent-tool agent-tool-${run.state}`}>
      <div className="agent-tool-line">
        <code>{run.name}</code>
        {run.summary ? <span>{run.summary}</span> : null}
        {run.artifact ? (
          <span className="agent-tool-artifact" title={run.artifact}>
            저장됨
          </span>
        ) : null}
      </div>
      {run.image ? (
        <img className="agent-tool-image" src={run.image} alt={`${run.name} 결과 이미지`} />
      ) : null}
    </div>
  );
}

/**
 * The agent's audit log, read from Rust.
 *
 * Every gated call — approved, denied, or auto — is appended to a hash-chained
 * JSONL file per day; this is the window onto it. `verified` reflects whether
 * that chain still checks out, so a tampered or truncated log shows as
 * unverified rather than silently reading clean.
 */
function AgentAuditModal({ onClose }: { onClose: () => void }) {
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState<string | null>(null);
  const [entries, setEntries] = useState<Array<Record<string, unknown>>>([]);
  const [verified, setVerified] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void agentHost
      .agentAuditEntries(date, 200)
      .then((result) => {
        if (cancelled) return;
        setDates(result.dates);
        setEntries(result.entries);
        setVerified(result.verified);
        // On first load, pin the selector to the day the log actually returned.
        if (date === null && result.dates.length > 0) {
          setDate(result.dates[result.dates.length - 1] ?? null);
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "감사 기록을 읽지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal agent-audit"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="에이전트 감사 기록"
      >
        <header className="modal-header">
          <h2>감사 기록</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="agent-audit-controls">
          {dates.length > 0 ? (
            <label>
              날짜
              <select value={date ?? ""} onChange={(event) => setDate(event.target.value || null)}>
                {dates.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <span className={verified ? "agent-audit-ok" : "agent-audit-bad"}>
            {verified ? "체인 검증됨" : "체인 검증 실패 — 기록이 변조되었을 수 있습니다"}
          </span>
        </div>

        <div className="modal-body agent-audit-body">
          {error ? (
            <p className="settings-error">{error}</p>
          ) : loading ? (
            <p className="settings-hint">불러오는 중…</p>
          ) : entries.length === 0 ? (
            <p className="settings-empty">이 날짜의 기록이 없습니다.</p>
          ) : (
            <ul className="agent-audit-list">
              {entries.map((entry, index) => (
                <li key={index}>
                  <AgentAuditRow entry={entry} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

/** One audit entry, rendered from whatever fields the JSONL row carries. */
function AgentAuditRow({ entry }: { entry: Record<string, unknown> }) {
  const str = (key: string): string | null => {
    const value = entry[key];
    return typeof value === "string" && value ? value : null;
  };
  const tool = str("tool") ?? str("action") ?? "(도구)";
  const verdict = str("verdict");
  const at = str("at") ?? str("ts") ?? str("timestamp");
  return (
    <div className="agent-audit-row">
      <div className="agent-audit-line">
        <code>{tool}</code>
        {verdict ? <span className={`agent-audit-verdict agent-audit-${verdict}`}>{verdict}</span> : null}
        {at ? <span className="agent-audit-at">{at}</span> : null}
      </div>
      {str("detail") ? <span className="agent-audit-detail">{str("detail")}</span> : null}
    </div>
  );
}
