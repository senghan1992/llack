/**
 * The one place in this product where a wrong click runs a command.
 *
 * Three rules follow from that, and they are the whole design:
 *
 * 1. **Only Rust-computed facts are authoritative.** Every row in the table
 *    below came from `policy::classify`, derived from the tool call itself.
 *    The model's own explanation is rendered separately, visually subordinate,
 *    and labelled unreliable — because whoever can write a channel message the
 *    agent read can also write that explanation, and "this is safe, just allow
 *    it" next to an Allow button is the whole attack.
 * 2. **No default action.** Neither button is focused on mount and neither is
 *    styled as the obvious one. A card that appears under a cursor already
 *    moving toward Enter should not be able to approve anything.
 * 3. **The argv is shown one argument per line.** Space-joining invites the
 *    reader to parse it as a shell command, and a reader who thinks they are
 *    looking at shell will mis-read `--author=a b` as two arguments.
 */

import { useEffect, useRef } from "react";

import { agentHost } from "@/lib/ipc";
import { useAgent } from "@/store/agent";

import { IconClose } from "./Icon";

export function AgentApprovalCard() {
  const request = useAgent((state) => state.pending);
  const clearApproval = useAgent((state) => state.clearApproval);
  const setBanner = useAgent((state) => state.setBanner);

  const cardRef = useRef<HTMLDivElement>(null);
  const rememberRef = useRef<HTMLInputElement>(null);

  // Move focus to the card so a keyboard user is not left typing into the
  // composer while a decision is waiting — but focus the *card*, not a button,
  // so no key press is an answer.
  useEffect(() => {
    if (request) cardRef.current?.focus();
  }, [request]);

  if (!request) return null;

  // A class-3 call answered in a native OS dialog: the webview cannot resolve
  // it, so the card is informational and both buttons are inert. Only the OS
  // dialog's own buttons close the request.
  const native = request.native === true;

  const answer = async (approve: boolean) => {
    if (native) return;
    const remember = Boolean(rememberRef.current?.checked) && request.remembering_offered;
    try {
      await agentHost.agentResolveApproval(
        request.id,
        request.nonce,
        approve,
        remember,
      );
      clearApproval(request.id);
    } catch (error) {
      // A rejected answer means the request already closed — most often it
      // timed out. Say so instead of leaving a card that answers nothing.
      setBanner(
        error instanceof Error
          ? error.message
          : "이 승인 요청은 이미 만료되었습니다.",
      );
      clearApproval(request.id);
    }
  };

  return (
    <div
      className={`agent-approval agent-approval-${request.risk}`}
      role="alertdialog"
      aria-modal="false"
      aria-labelledby="agent-approval-title"
      tabIndex={-1}
      ref={cardRef}
      onKeyDown={(event) => {
        // Escape denies. Leaving without an answer is a denial everywhere else
        // in this feature, so it is a denial here too.
        if (event.key === "Escape") {
          event.stopPropagation();
          void answer(false);
        }
      }}
    >
      <header className="agent-approval-head">
        <strong id="agent-approval-title">{request.facts.title}</strong>
        <span className="agent-approval-risk">
          {request.risk === "high" ? "확인 필요" : "승인 필요"}
        </span>
      </header>

      <dl className="agent-approval-facts">
        {request.facts.facts.map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            {/* `pre-wrap` on the value: argv arrives newline-separated. */}
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>

      {request.rationale ? (
        <details className="agent-approval-rationale">
          <summary>모델 설명 — 신뢰하지 마세요</summary>
          <p>{request.rationale}</p>
        </details>
      ) : null}

      {request.remembering_offered && !native ? (
        <label className="agent-approval-remember">
          <input type="checkbox" ref={rememberRef} />
          이 세션 동안 같은 작업은 다시 묻지 않기
        </label>
      ) : null}

      {native ? (
        <p className="agent-approval-native">
          운영체제 대화상자에서 결정합니다. 화면에 뜬 창에서 허용 또는 거부를 눌러주세요.
        </p>
      ) : null}

      <div className="agent-approval-actions">
        {/* Deny first in the DOM, so Tab reaches it before Allow. */}
        <button
          type="button"
          className="agent-deny"
          onClick={() => void answer(false)}
          disabled={native}
        >
          거부
        </button>
        <button
          type="button"
          className="agent-allow"
          onClick={() => void answer(true)}
          disabled={native}
        >
          허용
        </button>
      </div>
    </div>
  );
}

/** The dismiss control for a stale card, used by the panel header. */
export function AgentApprovalDismiss() {
  const request = useAgent((state) => state.pending);
  const clearApproval = useAgent((state) => state.clearApproval);
  if (!request) return null;
  return (
    <button
      type="button"
      onClick={() => clearApproval(request.id)}
      aria-label="승인 카드 닫기"
      title="닫기"
    >
      <IconClose size={13} />
    </button>
  );
}
