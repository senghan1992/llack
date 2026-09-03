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
 * Sites that refuse framing (X-Frame-Options / CSP) are caught when the app is
 * added — the server probes the URL — and stored with `open_mode: "external"`.
 * Those render a card with one big "브라우저에서 열기" instead of a blank frame.
 * The header still offers the same escape hatch for the ones the probe could
 * not judge, because a cross-origin frame never tells us it failed.
 */

import { useEffect, useState } from "react";

import { api } from "@/lib/ipc";
import type { AppInstallation } from "@/lib/types";
import { useApp } from "@/store/app";

import { IconClose, IconEdit, IconGlobe, IconRefresh, IconTrash } from "./Icon";

export function WebAppView({ installation }: { installation: AppInstallation }) {
  const openWebApp = useApp((state) => state.openWebApp);
  const loadInstallations = useApp((state) => state.loadInstallations);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);
  const me = useApp((state) => state.me);
  const workspace = useApp((state) =>
    state.workspaces.find((candidate) => candidate.id === state.activeWorkspaceId),
  );
  const url = installation.app.panel_url ?? "";
  const external = installation.config?.open_mode === "external";

  // Admins and whoever added the tile may rename or remove it (server-enforced).
  const canManage =
    workspace?.my_role === "owner" ||
    workspace?.my_role === "admin" ||
    (installation.installed_by != null && installation.installed_by === me?.id);

  // Remounting the iframe is the only reload a cross-origin frame allows.
  const [generation, setGeneration] = useState(0);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(installation.app.name);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);

  // A new app selection must not inherit the previous one's state.
  useEffect(() => {
    setGeneration(0);
    setRenaming(false);
    setName(installation.app.name);
    setConfirmRemove(false);
  }, [installation.id, installation.app.name]);

  let host = "";
  try {
    host = new URL(url).host;
  } catch {
    // A malformed URL renders with an empty host; the frame will simply fail.
  }

  const saveName = async () => {
    const next = name.trim();
    if (!next || next === installation.app.name) {
      setRenaming(false);
      setName(installation.app.name);
      return;
    }
    setBusy(true);
    try {
      await api.updateInstallation(installation.id, { name: next });
      await loadInstallations();
      setRenaming(false);
      showBanner("info", `이름을 "${next}" 으로 바꿨습니다.`);
    } catch (error) {
      reportError(error, "이름을 바꾸지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const setMode = async (mode: "embed" | "external") => {
    setBusy(true);
    try {
      await api.updateInstallation(installation.id, {
        config: { ...installation.config, open_mode: mode },
      });
      await loadInstallations();
    } catch (error) {
      reportError(error, "열기 방식을 바꾸지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.uninstallApp(installation.id);
      openWebApp(null);
      await loadInstallations();
      showBanner("info", `${installation.app.name} 을(를) 도크에서 뺐습니다.`);
    } catch (error) {
      reportError(error, "앱을 제거하지 못했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="webapp-view">
      <header className="webapp-header">
        {renaming ? (
          <form
            className="webapp-rename"
            onSubmit={(event) => {
              event.preventDefault();
              void saveName();
            }}
          >
            <IconGlobe size={15} />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              autoFocus
              aria-label="앱 이름"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setRenaming(false);
                  setName(installation.app.name);
                }
              }}
            />
            <button type="submit" className="settings-primary" disabled={busy || !name.trim()}>
              저장
            </button>
          </form>
        ) : (
          <h1>
            <IconGlobe size={15} />
            {installation.app.name}
          </h1>
        )}
        <span className="webapp-host">{host}</span>
        <div className="webapp-actions">
          {canManage && !renaming ? (
            <button
              type="button"
              className="header-button"
              onClick={() => setRenaming(true)}
              title="이름 바꾸기"
              aria-label="이름 바꾸기"
            >
              <IconEdit size={14} />
            </button>
          ) : null}
          {!external ? (
            <button
              type="button"
              className="header-button"
              onClick={() => setGeneration((n) => n + 1)}
              title="새로고침"
              aria-label="새로고침"
            >
              <IconRefresh size={14} />
            </button>
          ) : null}
          <a className="webapp-open" href={url} target="_blank" rel="noreferrer noopener">
            브라우저에서 열기
          </a>
          {canManage ? (
            confirmRemove ? (
              <>
                <button
                  type="button"
                  className="member-action is-destructive"
                  onClick={() => void remove()}
                  disabled={busy}
                >
                  도크에서 빼기
                </button>
                <button type="button" className="member-action" onClick={() => setConfirmRemove(false)}>
                  취소
                </button>
              </>
            ) : (
              <button
                type="button"
                className="header-button"
                onClick={() => setConfirmRemove(true)}
                title="도크에서 빼기"
                aria-label="도크에서 빼기"
              >
                <IconTrash size={14} />
              </button>
            )
          ) : null}
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

      {external ? (
        <div className="webapp-external">
          <IconGlobe size={28} />
          <h2>{installation.app.name}</h2>
          <p>
            {host} 은(는) 다른 앱 안에 띄우는 것을 허용하지 않아 새 탭으로 엽니다. 로그인
            상태와 즐겨찾기는 브라우저의 것을 그대로 씁니다.
          </p>
          <a className="settings-primary webapp-external-open" href={url} target="_blank" rel="noreferrer noopener">
            새 탭에서 {installation.app.name} 열기
          </a>
          {canManage ? (
            <button
              type="button"
              className="webapp-mode-toggle"
              onClick={() => void setMode("embed")}
              disabled={busy}
            >
              사이트 설정이 바뀌었다면: 창 안에 띄우기로 되돌리기
            </button>
          ) : null}
        </div>
      ) : (
        <>
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
            화면이 비어 보이면 이 사이트가 임베드를 허용하지 않는 것입니다 — 위의 "브라우저에서
            열기"를 눌러주세요
            {canManage ? (
              <>
                {" "}
                또는{" "}
                <button type="button" className="webapp-mode-toggle inline" onClick={() => void setMode("external")} disabled={busy}>
                  이 앱을 새 탭으로 여는 타일로 바꾸기
                </button>
              </>
            ) : null}
            . 로그인 등 입력은 Llack 이 아니라 {host || "해당 사이트"} 로 바로 전달됩니다.
          </footer>
        </>
      )}
    </div>
  );
}
