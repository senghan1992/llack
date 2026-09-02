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
import { useAgent } from "@/store/agent";
import { useApp } from "@/store/app";
import { IconAgent, IconChevrons, IconClose } from "./Icon";

/**
 * Whether the rail shows names, remembered across launches.
 *
 * localStorage rather than the store or the server: it is a fact about this
 * window's width budget, not about the account, and it must be readable before
 * anything has signed in.
 */
const DOCK_EXPANDED_KEY = "llack.dock.expanded";

function loadExpanded(): boolean {
  try {
    return window.localStorage.getItem(DOCK_EXPANDED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppDock() {
  const workspaces = useApp((state) => state.workspaces);
  const activeWorkspaceId = useApp((state) => state.activeWorkspaceId);
  const selectWorkspace = useApp((state) => state.selectWorkspace);
  const installations = useApp((state) => state.installations);
  const openPanelInstallationId = useApp((state) => state.openPanelInstallationId);
  const openAppPanel = useApp((state) => state.openAppPanel);
  const badge = useApp((state) => state.badge);
  const agentOpen = useAgent((state) => state.open);
  const setAgentOpen = useAgent((state) => state.setOpen);

  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [expanded, setExpanded] = useState(loadExpanded);

  const toggleExpanded = () => {
    setExpanded((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(DOCK_EXPANDED_KEY, next ? "1" : "0");
      } catch {
        // Private browsing: the toggle still works, it just will not persist.
      }
      return next;
    });
  };

  const pinned = installations.filter(
    (installation) => installation.is_pinned && installation.app.panel_url,
  );

  return (
    <div className={`dock ${expanded ? "is-expanded" : ""}`}>
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
            <span className="dock-label">{workspace.name}</span>
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
              installation.id === openPanelInstallationId ? "is-open" : ""
            }`}
            onClick={() =>
              openAppPanel(
                installation.id === openPanelInstallationId ? null : installation.id,
              )
            }
            title={installation.app.tagline ?? installation.app.name}
          >
            {/*
              The app's own `accent_color` is deliberately ignored: on this
              surface one colour carries one meaning, and an installed app
              cannot spend it. The plate takes a neutral tint instead.
            */}
            {installation.app.icon_url ? (
              <img src={installation.app.icon_url} alt="" />
            ) : (
              <span style={{ background: colorForId(installation.app.id) }}>
                {initials(installation.app.name)}
              </span>
            )}
            <span className="dock-label">{installation.app.name}</span>
          </button>
        ))}

        {/*
          The agent sits with the apps rather than above the divider: it is one
          of the things you can dock beside a channel, not a place you go. The
          divider separates "where I am" from "what I can open here".
        */}
        {/*
          `is-open`, not `is-active`.
          
          `is-active` carries the signal underline, which means "where you
          are" — a location. The agent is a panel you open beside where you
          are, so borrowing that state put two red position markers on screen
          at once and made the one colour mean two things inside the first
          viewport. Open is a lifted card and nothing else.
        */}
        <button
          type="button"
          className={`dock-tile dock-agent ${agentOpen ? "is-open" : ""}`}
          onClick={() => setAgentOpen(!agentOpen)}
          title="에이전트"
          aria-label="에이전트"
          aria-pressed={agentOpen}
        >
          <IconAgent size={17} />
          <span className="dock-label">에이전트</span>
        </button>

        <button
          type="button"
          className="dock-tile dock-add"
          onClick={() => setDirectoryOpen(true)}
          title="앱 추가"
          aria-label="앱 추가"
        >
          <span className="dock-glyph" aria-hidden="true">
            +
          </span>
          <span className="dock-label">앱 추가</span>
        </button>
      </div>

      {/*
        The rail's tiles are initials by default, and initials are not names:
        "데" could be 데일리 스탠드업 or 데이터 대시보드. The toggle trades
        transcript width for the names, remembers the choice, and hides itself
        below the width where the trade stops being affordable (see the
        `.dock-toggle` media rule).
      */}
      <button
        type="button"
        className="dock-toggle"
        onClick={toggleExpanded}
        aria-label={expanded ? "아이콘만 보기" : "이름 표시"}
        title={expanded ? "아이콘만 보기" : "이름 표시"}
        aria-pressed={expanded}
      >
        <IconChevrons size={14} />
        <span className="dock-label">접기</span>
      </button>

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
            <IconClose size={13} />
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
