/**
 * 앱 홈 — an app's channel-independent screen, in the main pane.
 *
 * A mini-app panel is a column beside a channel and is told which channel you
 * are looking at. Some apps want a page of their own (a dashboard, a settings
 * screen, a list of everything): that is the home tab. Same sandbox, same
 * bridge, same scoped token — only the seat differs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/ipc";
import type { PanelSession } from "@/lib/types";
import { useApp } from "@/store/app";

import { IconClose, IconHome, IconRefresh } from "./Icon";

type BridgeRequest =
  | { id: string; type: "llack:ready" }
  | { id: string; type: "llack:get-session" }
  | { id: string; type: "llack:set-title"; title: string }
  | { id: string; type: "llack:open-channel"; channelId: string }
  | { id: string; type: "llack:close" }
  | { id: string; type: string };

export function AppHomeView() {
  const installationId = useApp((state) => state.appHomeInstallationId);
  const installation = useApp((state) =>
    state.installations.find((candidate) => candidate.id === state.appHomeInstallationId),
  );
  const serverUrl = useApp((state) => state.serverUrl);
  const setMainView = useApp((state) => state.setMainView);
  const openChannel = useApp((state) => state.openChannel);
  const reportError = useApp((state) => state.reportError);

  const [session, setSession] = useState<PanelSession | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const frameRef = useRef<HTMLIFrameElement>(null);

  const bridgeBase = useMemo(() => {
    try {
      return new URL("/api/v1/app-bridge", serverUrl || window.location.origin).toString();
    } catch {
      return "/api/v1/app-bridge";
    }
  }, [serverUrl]);

  const homeOrigin = useMemo(() => {
    if (!session?.panel_url) return null;
    try {
      return new URL(session.panel_url).origin;
    } catch {
      return null;
    }
  }, [session?.panel_url]);

  useEffect(() => {
    if (!installationId) return;
    let cancelled = false;
    setError(null);
    setTitle(null);
    void api
      .openAppHome(installationId)
      .then((minted) => {
        if (!cancelled) setSession(minted);
      })
      .catch((caught) => {
        if (cancelled) return;
        setError(reportError(caught, "앱 홈을 열지 못했습니다.").message);
      });
    return () => {
      cancelled = true;
    };
  }, [installationId, generation, reportError]);

  const sameOriginRefusal = homeOrigin !== null && homeOrigin === window.location.origin;

  const reply = useCallback(
    (id: string, payload: unknown) => {
      const frame = frameRef.current?.contentWindow;
      if (!frame || !homeOrigin) return;
      frame.postMessage({ id, type: "llack:response", payload }, homeOrigin);
    },
    [homeOrigin],
  );

  useEffect(() => {
    if (!session || !homeOrigin || sameOriginRefusal) return;
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.origin !== homeOrigin) return;
      const message = event.data as BridgeRequest | undefined;
      if (!message || typeof message !== "object" || typeof message.type !== "string") return;
      switch (message.type) {
        case "llack:ready":
        case "llack:get-session":
          reply(message.id, {
            bridge_token: session.bridge_token,
            expires_at: session.expires_at,
            granted_scopes: session.granted_scopes,
            config: session.config,
            context: { ...session.context, surface: "home" },
            api_base: bridgeBase,
          });
          break;
        case "llack:set-title":
          if ("title" in message && typeof message.title === "string") {
            setTitle(message.title.slice(0, 80));
          }
          break;
        case "llack:open-channel":
          if ("channelId" in message && typeof message.channelId === "string") {
            void openChannel(message.channelId);
          }
          break;
        case "llack:close":
          setMainView("channel");
          break;
        default:
          break;
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [session, homeOrigin, sameOriginRefusal, reply, bridgeBase, openChannel, setMainView]);

  if (!installationId || !installation) {
    return (
      <div className="webapp-external">
        <p>열 수 있는 앱 홈이 없습니다.</p>
        <button type="button" className="settings-secondary" onClick={() => setMainView("channel")}>
          대화로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <div className="webapp-view app-home">
      <header className="webapp-header">
        <h1>
          <IconHome size={15} />
          {title ?? installation.app.name}
          <span className="app-home-tag">홈</span>
        </h1>
        <div className="webapp-actions">
          <button
            type="button"
            className="header-button"
            onClick={() => setGeneration((n) => n + 1)}
            title="새로고침"
            aria-label="새로고침"
          >
            <IconRefresh size={14} />
          </button>
          <button
            type="button"
            className="header-button"
            onClick={() => setMainView("channel")}
            title="닫고 대화로 돌아가기"
            aria-label="닫기"
          >
            <IconClose size={13} />
          </button>
        </div>
      </header>
      {error ? (
        <div className="webapp-external">
          <p>{error}</p>
        </div>
      ) : sameOriginRefusal ? (
        <div className="webapp-external">
          <p>이 앱은 Llack 과 같은 주소에서 서비스되고 있어 열 수 없습니다. 앱은 자기 주소에서 서비스되어야 합니다.</p>
        </div>
      ) : session ? (
        <iframe
          key={`${installation.id}:${generation}`}
          ref={frameRef}
          className="webapp-frame"
          src={session.panel_url}
          title={`${installation.app.name} 홈`}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads allow-modals"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="webapp-external">
          <p>불러오는 중…</p>
        </div>
      )}
    </div>
  );
}
