/**
 * The left-most rail: workspaces on top, installed mini-apps below.
 *
 * This is the "사내 OS" surface — the apps a team builds sit at the same level
 * as the workspace itself, one click away from any channel, rather than buried
 * in a menu.
 */

import { useEffect, useState } from "react";

import { colorForId, initials } from "@/lib/format";
import { api } from "@/lib/ipc";
import { useApp } from "@/store/app";

export function AppDock() {
  const workspaces = useApp((state) => state.workspaces);
  const activeWorkspaceId = useApp((state) => state.activeWorkspaceId);
  const selectWorkspace = useApp((state) => state.selectWorkspace);
  const installations = useApp((state) => state.installations);
  const openPanelInstallationId = useApp((state) => state.openPanelInstallationId);
  const openAppPanel = useApp((state) => state.openAppPanel);
  const badge = useApp((state) => state.badge);

  const [directoryOpen, setDirectoryOpen] = useState(false);

  const pinned = installations.filter(
    (installation) => installation.is_pinned && installation.app.panel_url,
  );

  return (
    <div className="dock">
      <div className="dock-workspaces">
        {workspaces.map((workspace) => (
          <button
            key={workspace.id}
            type="button"
            className={`dock-tile ${
              workspace.id === activeWorkspaceId ? "is-active" : ""
            }`}
            onClick={() => void selectWorkspace(workspace.id)}
            title={workspace.name}
          >
            {workspace.icon_url ? (
              <img src={workspace.icon_url} alt="" />
            ) : (
              <span style={{ background: colorForId(workspace.id) }}>
                {initials(workspace.name)}
              </span>
            )}
            {workspace.id === activeWorkspaceId && badge > 0 ? (
              <em className="dock-badge">{badge > 99 ? "99+" : badge}</em>
            ) : null}
          </button>
        ))}
      </div>

      <div className="dock-divider" />

      <div className="dock-apps">
        {pinned.map((installation) => (
          <button
            key={installation.id}
            type="button"
            className={`dock-tile dock-app ${
              installation.id === openPanelInstallationId ? "is-active" : ""
            }`}
            onClick={() =>
              openAppPanel(
                installation.id === openPanelInstallationId ? null : installation.id,
              )
            }
            title={installation.app.tagline ?? installation.app.name}
          >
            {installation.app.icon_url ? (
              <img src={installation.app.icon_url} alt="" />
            ) : (
              <span
                style={{
                  background:
                    installation.app.accent_color ?? colorForId(installation.app.id),
                }}
              >
                {initials(installation.app.name)}
              </span>
            )}
          </button>
        ))}

        <button
          type="button"
          className="dock-tile dock-add"
          onClick={() => setDirectoryOpen(true)}
          title="앱 추가"
          aria-label="앱 추가"
        >
          +
        </button>
      </div>

      {directoryOpen ? <AppDirectory onClose={() => setDirectoryOpen(false)} /> : null}
    </div>
  );
}

/** The install dialog. Shows the scopes an app is asking for before granting. */
function AppDirectory({ onClose }: { onClose: () => void }) {
  const workspaceId = useApp((state) => state.activeWorkspaceId);
  const installations = useApp((state) => state.installations);
  const loadInstallations = useApp((state) => state.loadInstallations);
  const reportError = useApp((state) => state.reportError);

  const [available, setAvailable] = useState<
    Array<{ id: string; name: string; tagline?: string | null; requested_scopes: string[] }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    void api
      .listAvailableApps(workspaceId)
      .then((apps) => {
        if (!cancelled) setAvailable(apps);
      })
      .catch((error) => {
        if (!cancelled) reportError(error, "앱 목록을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, reportError]);

  const installedIds = new Set(installations.map((installation) => installation.app.id));

  const install = async (appId: string) => {
    if (!workspaceId) return;
    setInstalling(appId);
    try {
      await api.installApp(workspaceId, appId);
      await loadInstallations();
    } catch (error) {
      reportError(error, "앱을 설치하지 못했습니다. 관리자 권한이 필요할 수 있습니다.");
    } finally {
      setInstalling(null);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="앱 디렉터리"
      >
        <header className="modal-header">
          <h2>앱 추가</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </header>

        <div className="modal-body">
          {loading ? <p>불러오는 중…</p> : null}
          {!loading && available.length === 0 ? (
            <p className="modal-empty">
              설치할 수 있는 앱이 없습니다. 사내 앱을 등록하면 여기에 나타납니다.
            </p>
          ) : null}

          <ul className="app-list">
            {available.map((app) => (
              <li key={app.id}>
                <div className="app-list-info">
                  <strong>{app.name}</strong>
                  {app.tagline ? <span>{app.tagline}</span> : null}
                  {app.requested_scopes.length > 0 ? (
                    <ul className="scope-list">
                      {app.requested_scopes.map((scope) => (
                        <li key={scope} title={describeScope(scope)}>
                          {describeScope(scope)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                {installedIds.has(app.id) ? (
                  <span className="app-installed">설치됨</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => void install(app.id)}
                    disabled={installing === app.id}
                  >
                    {installing === app.id ? "설치 중…" : "설치"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/** Plain-language descriptions, so granting a scope is an informed decision. */
function describeScope(scope: string): string {
  const labels: Record<string, string> = {
    "identity:read": "내 이름과 프로필 확인",
    "channels:read": "채널 목록 확인",
    "messages:read": "메시지 읽기",
    "messages:write": "메시지 보내기",
    "files:read": "파일 읽기",
    "files:write": "파일 올리기",
    "users:read": "구성원 목록 확인",
    notify: "알림 보내기",
    storage: "앱 데이터 저장",
    "panel:ui": "패널 화면 표시",
  };
  return labels[scope] ?? scope;
}
