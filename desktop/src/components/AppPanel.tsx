/**
 * Host for a mini-app's UI.
 *
 * The app runs in a sandboxed `<iframe>` and talks to the host over
 * `postMessage`. Three rules make that safe:
 *
 * 1. **The frame never gets the user's token.** The host mints a short-lived
 *    bridge token scoped to the installation and hands it to the frame; that
 *    token only opens the `/app-bridge/*` endpoints, and only within the
 *    scopes an admin granted at install time.
 * 2. **Every inbound message is checked twice** — `event.source` must be this
 *    frame's own `contentWindow` (unforgeable), and `event.origin` must be the
 *    app's `panel_url` origin.
 * 3. **The panel must be cross-origin from the host.** That, not the sandbox,
 *    is what keeps the app out of the host's storage and DOM. The panel is
 *    rendered only when its origin differs from ours; see `sameOriginRefusal`.
 *
 * The sandbox therefore *keeps* `allow-same-origin`. Withholding it gives the
 * frame an opaque origin, and an opaque origin breaks all three rules at once:
 * the app's own subresources become cross-origin requests its server does not
 * answer with CORS headers (so the panel's scripts never run), `event.origin`
 * arrives as the string "null" so rule 2 can never match, and there is no
 * origin left to address a reply to. `allow-same-origin` does not hand the
 * frame *our* origin — it lets the frame keep *its own*, which is a different
 * origin and therefore still isolated.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/ipc";
import type { PanelSession } from "@/lib/types";
import { useApp } from "@/store/app";
import { IconClose } from "./Icon";

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
  const serverUrl = useApp((state) => state.serverUrl);
  const openAppPanel = useApp((state) => state.openAppPanel);
  const openChannel = useApp((state) => state.openChannel);
  const reportError = useApp((state) => state.reportError);

  const [session, setSession] = useState<PanelSession | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  /** Absolute bridge root, so a frame on another origin can reach it. */
  const bridgeBase = useMemo(() => {
    try {
      return new URL("/api/v1/app-bridge", serverUrl || window.location.origin).toString();
    } catch {
      return "/api/v1/app-bridge";
    }
  }, [serverUrl]);

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

  /**
   * A panel served from our own origin would, with `allow-same-origin` and
   * `allow-scripts`, be able to reach into this document and drop its own
   * sandbox. Apps are meant to live on their own host, so refuse rather than
   * quietly widen what an app can touch.
   */
  const sameOriginRefusal =
    panelOrigin !== null && panelOrigin === window.location.origin;

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
    if (!session || !panelOrigin || sameOriginRefusal) return;

    const onMessage = (event: MessageEvent) => {
      // Rule 2, unforgeable half first: only this frame's own window.
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.origin !== panelOrigin) return;

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
            // Absolute: a relative path would resolve against the *app's*
            // origin inside the frame, not the Llack server's.
            api_base: bridgeBase,
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
          {/* Neutral marker: the app is identified by its name, not its brand hue. */}
          {installation.app.accent_color ? <span className="app-panel-accent" /> : null}
        </h2>
        <button type="button" onClick={() => openAppPanel(null)} aria-label="앱 닫기">
          <IconClose size={13} />
        </button>
      </header>

      {error ? (
        <div className="app-panel-error">
          <p>{error}</p>
          <button type="button" onClick={() => openAppPanel(null)}>
            닫기
          </button>
        </div>
      ) : sameOriginRefusal ? (
        <div className="app-panel-error">
          <p>
            이 앱은 Llack 과 같은 주소에서 서비스되고 있어 열 수 없습니다. 앱은
            별도의 호스트에서 서비스해야 합니다.
          </p>
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
           * `allow-same-origin` keeps the frame on its *own* origin, which is
           * what makes the bridge and the app's own asset loads work. Safe
           * only because the panel is cross-origin from us — enforced above.
           */
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
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
