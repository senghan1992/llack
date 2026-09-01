/**
 * Host for a mini-app's UI.
 *
 * The app runs in a sandboxed `<iframe>` and talks to the host over
 * `postMessage`. Three rules make that safe, and they are the whole point of
 * this component:
 *
 * 1. **The frame never gets the user's token.** The host mints a short-lived
 *    bridge token scoped to the installation and hands it to the frame; that
 *    token only opens the `/app-bridge/*` endpoints, and only within the
 *    scopes an admin granted at install time.
 * 2. **Every inbound message is origin-checked** against the app's own
 *    `panel_url` origin. A message from anywhere else is dropped.
 * 3. **`sandbox` withholds `allow-same-origin`**, so the frame cannot reach
 *    the host's storage, cookies or DOM.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/ipc";
import type { PanelSession } from "@/lib/types";
import { useApp } from "@/store/app";

/** Messages the frame may send to the host. */
type BridgeRequest =
  | { id: string; type: "llack:ready" }
  | { id: string; type: "llack:get-session" }
  | { id: string; type: "llack:resize"; height: number }
  | { id: string; type: "llack:set-title"; title: string }
  | { id: string; type: "llack:open-channel"; channelId: string }
  | { id: string; type: "llack:close" };

export function AppPanel() {
  const installationId = useApp((state) => state.openPanelInstallationId);
  const installation = useApp((state) =>
    state.installations.find((candidate) => candidate.id === state.openPanelInstallationId),
  );
  const activeChannelId = useApp((state) => state.activeChannelId);
  const openAppPanel = useApp((state) => state.openAppPanel);
  const openChannel = useApp((state) => state.openChannel);
  const reportError = useApp((state) => state.reportError);

  const [session, setSession] = useState<PanelSession | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  const panelOrigin = useMemo(() => {
    if (!session?.panel_url) return null;
    try {
      return new URL(session.panel_url).origin;
    } catch {
      return null;
    }
  }, [session?.panel_url]);

  // Mint a session whenever the panel or the channel context changes: the app
  // is told which channel the user is looking at, so a panel can be
  // channel-aware without asking for broader scopes.
  useEffect(() => {
    if (!installationId) {
      setSession(null);
      setError(null);
      setTitle(null);
      return;
    }
    let cancelled = false;
    setError(null);
    void api
      .openAppPanel(installationId, activeChannelId ?? undefined)
      .then((minted) => {
        if (!cancelled) setSession(minted);
      })
      .catch((caught) => {
        if (cancelled) return;
        const parsed = reportError(caught, "앱을 열지 못했습니다.");
        setError(parsed.message);
      });
    return () => {
      cancelled = true;
    };
  }, [installationId, activeChannelId, reportError]);

  const reply = useCallback(
    (id: string, payload: unknown) => {
      const frame = frameRef.current?.contentWindow;
      if (!frame || !panelOrigin) return;
      // Targeted origin, never "*": a wildcard would leak the bridge token to
      // whatever happens to be loaded in the frame.
      frame.postMessage({ id, type: "llack:response", payload }, panelOrigin);
    },
    [panelOrigin],
  );

  useEffect(() => {
    if (!session || !panelOrigin) return;

    const onMessage = (event: MessageEvent) => {
      // Rule 2: drop anything not from the app's own origin.
      if (event.origin !== panelOrigin) return;
      if (event.source !== frameRef.current?.contentWindow) return;

      const message = event.data as BridgeRequest | undefined;
      if (!message || typeof message !== "object" || typeof message.type !== "string") {
        return;
      }

      switch (message.type) {
        case "llack:ready":
        case "llack:get-session":
          reply(message.id, {
            bridge_token: session.bridge_token,
            expires_at: session.expires_at,
            granted_scopes: session.granted_scopes,
            config: session.config,
            context: session.context,
            api_base: "/api/v1/app-bridge",
          });
          break;

        case "llack:set-title":
          if (typeof message.title === "string") {
            setTitle(message.title.slice(0, 80));
          }
          break;

        case "llack:open-channel":
          // The app may only navigate to a channel the user is already in;
          // openChannel fails harmlessly otherwise.
          if (typeof message.channelId === "string") {
            void openChannel(message.channelId);
          }
          break;

        case "llack:close":
          openAppPanel(null);
          break;

        case "llack:resize":
          // The panel is a fixed-width column; height is the host's business.
          break;

        default:
          break;
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [session, panelOrigin, reply, openAppPanel, openChannel]);

  if (!installationId || !installation) return null;

  const width = installation.app.default_width || 420;

  return (
    <aside className="app-panel" style={{ width }} aria-label="앱 패널">
      <header className="app-panel-header">
        <h2>
          {title ?? installation.app.name}
          {installation.app.accent_color ? (
            <span
              className="app-panel-accent"
              style={{ background: installation.app.accent_color }}
            />
          ) : null}
        </h2>
        <button type="button" onClick={() => openAppPanel(null)} aria-label="앱 닫기">
          ×
        </button>
      </header>

      {error ? (
        <div className="app-panel-error">
          <p>{error}</p>
          <button type="button" onClick={() => openAppPanel(null)}>
            닫기
          </button>
        </div>
      ) : session ? (
        <iframe
          ref={frameRef}
          className="app-panel-frame"
          src={session.panel_url}
          title={installation.app.name}
          /*
           * Rule 3. `allow-same-origin` is deliberately absent: with it, the
           * frame would share this window's origin and could read the host's
           * storage. Without it the frame is fully isolated and can only reach
           * the host through the postMessage bridge above.
           */
          sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="no-referrer"
          allow=""
        />
      ) : (
        <div className="app-panel-loading">앱을 여는 중…</div>
      )}

      <footer className="app-panel-footer">
        <span title={installation.granted_scopes.join(", ")}>
          권한 {installation.granted_scopes.length}개
        </span>
      </footer>
    </aside>
  );
}
