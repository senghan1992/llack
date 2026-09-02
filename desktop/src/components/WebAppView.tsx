/**
 * A link app filling the main pane — the transcript's seat, borrowed.
 *
 * The team's deployed web tools (a dashboard, a wiki, an internal admin) get a
 * dock tile and open here in a frame, so "우리 도구 보러 가기" stops being a
 * browser-tab switch. The frame is all they get: a link app has no bridge, no
 * token and no scopes (the server refuses to mint a panel session for one), so
 * an arbitrary external site is exactly as powerful in here as in a tab —
 * minus what the sandbox withholds.
 *
 * Some sites refuse framing outright (X-Frame-Options / CSP), and a
 * cross-origin frame gives us no reliable way to *detect* that — the load
 * event fires either way. So the header always offers 브라우저에서 열기, and a
 * quiet hint below the frame names the escape hatch instead of pretending
 * detection works.
 */

import { useEffect, useState } from "react";

import type { AppInstallation } from "@/lib/types";
import { useApp } from "@/store/app";

import { IconClose, IconGlobe, IconRefresh } from "./Icon";

export function WebAppView({ installation }: { installation: AppInstallation }) {
  const openWebApp = useApp((state) => state.openWebApp);
  const url = installation.app.panel_url ?? "";

  // Remounting the iframe is the only reload a cross-origin frame allows.
  const [generation, setGeneration] = useState(0);

  // A new app selection must not inherit the previous one's reload counter.
  useEffect(() => setGeneration(0), [installation.id]);

  let host = "";
  try {
    host = new URL(url).host;
  } catch {
    // A malformed URL renders with an empty host; the frame will simply fail.
  }

  return (
    <div className="webapp-view">
      <header className="webapp-header">
        <h1>
          <IconGlobe size={15} />
          {installation.app.name}
        </h1>
        <span className="webapp-host">{host}</span>
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
          <a
            className="webapp-open"
            href={url}
            target="_blank"
            rel="noreferrer noopener"
          >
            브라우저에서 열기
          </a>
          <button
            type="button"
            className="header-button"
            onClick={() => openWebApp(null)}
            title="닫고 대화로 돌아가기"
            aria-label="닫기"
          >
            <IconClose size={13} />
          </button>
        </div>
      </header>

      <iframe
        key={`${installation.id}:${generation}`}
        className="webapp-frame"
        src={url}
        title={installation.app.name}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads allow-modals"
        referrerPolicy="no-referrer"
        allow="clipboard-write; fullscreen"
      />

      <footer className="webapp-footnote">
        화면이 비어 보이면 이 사이트가 임베드를 허용하지 않는 것입니다 — 위의
        "브라우저에서 열기"를 눌러주세요. 로그인 등 입력은 Llack 이 아니라{" "}
        {host || "해당 사이트"} 로 바로 전달됩니다.
      </footer>
    </div>
  );
}
