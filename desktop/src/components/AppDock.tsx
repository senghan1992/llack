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
  const openWebAppInstallationId = useApp((state) => state.openWebAppInstallationId);
  const openWebApp = useApp((state) => state.openWebApp);
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
              installation.id === openPanelInstallationId ||
              installation.id === openWebAppInstallationId
                ? "is-open"
                : ""
            }`}
            onClick={() => {
              // A link app takes the main pane; a mini-app docks beside it.
              // Same tile, different seat — the distinction is the app's
              // kind, not something the person has to know.
              if (installation.app.kind === "link") {
                openWebApp(
                  installation.id === openWebAppInstallationId
                    ? null
                    : installation.id,
                );
              } else {
                openAppPanel(
                  installation.id === openPanelInstallationId
                    ? null
                    : installation.id,
                );
              }
            }}
            title={
              installation.app.tagline
                ? `${installation.app.name} — ${installation.app.tagline}`
                : installation.app.name
            }
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

  const [linkName, setLinkName] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [addingLink, setAddingLink] = useState(false);
  /** Set when the probe says the site refuses framing; the person decides. */
  const [blocked, setBlocked] = useState<{ url: string; title: string | null } | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  // Every other modal closes on Escape; this one was the odd one out.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const removeInstallation = async (installationId: string) => {
    setRemoving(installationId);
    try {
      await api.uninstallApp(installationId);
      await loadInstallations();
    } catch (error) {
      reportError(error, "앱을 제거하지 못했습니다. 관리자 권한이 필요할 수 있습니다.");
    } finally {
      setRemoving(null);
    }
  };

  /**
   * Add the link app. First ask the server whether the site allows framing;
   * a refusing site (GitHub, most SaaS logins) used to become a tile that
   * opened a blank pane with no explanation. Now the person is told before
   * adding, and can add it as an "open in browser" tile instead.
   */
  const addLink = async (openMode: "embed" | "external" = "embed", skipProbe = false) => {
    if (!workspaceId || addingLink) return;
    setAddingLink(true);
    try {
      const url = linkUrl.trim();
      let title: string | null = null;
      if (!skipProbe && openMode === "embed") {
        try {
          const probe = await api.probeLinkApp(workspaceId, url);
          title = probe.title ?? null;
          if (probe.embeddable === false) {
            setBlocked({ url, title });
            return;
          }
        } catch {
          // The probe is advice, not a gate. An intranet tool on a private
          // address is exactly what a team embeds, and the server refuses to
          // probe those (SSRF guard) — so it is added unverified, like before.
        }
      }
      // The name falls back to the page title, then the host, so pasting a
      // URL alone is enough.
      const name = linkName.trim() || title?.slice(0, 120) || new URL(url).host;
      const installation = await api.addLinkApp(workspaceId, name, url);
      if (openMode === "external") {
        await api.updateInstallation(installation.id, {
          config: { ...installation.config, open_mode: "external" },
        });
      }
      await loadInstallations();
      setLinkName("");
      setLinkUrl("");
      setBlocked(null);
      onClose();
    } catch (error) {
      // One cause per sentence: a member being told to "check the URL" would
      // fix the wrong thing.
      const parsed = reportError(error);
      const message =
        parsed.code === "guest_cannot_add_apps"
          ? "게스트는 웹 앱을 추가할 수 없습니다."
          : parsed.status === 403
            ? "웹 앱을 추가할 권한이 없습니다."
            : parsed.status === 422
              ? "주소를 확인해주세요. http(s) 주소만 추가할 수 있습니다."
              : "웹 앱을 추가하지 못했습니다.";
      useApp.setState({ banner: { kind: "error", message } });
    } finally {
      setAddingLink(false);
    }
  };

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
        className="modal app-directory"
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
          {/*
            The URL form sits first: for most teams "우리가 이미 배포한 웹
            도구를 넣는다"가 매니페스트 앱 설치보다 훨씬 잦은 동작입니다.
          */}
          <section className="linkapp-form">
            <h3>웹 앱을 주소로 추가</h3>
            <p className="linkapp-hint">
              팀이 배포한 웹 도구의 주소를 넣으면 왼쪽 도크에 들어가고, 누르면
              이 창 안에서 열립니다. 구성원 누구나 추가할 수 있고, 추가한 사람과
              관리자가 이름을 바꾸거나 뺄 수 있습니다.
            </p>
            <div className="linkapp-fields">
              <input
                value={linkUrl}
                onChange={(event) => setLinkUrl(event.target.value)}
                placeholder="https://tool.example.com"
                aria-label="웹 앱 주소"
                inputMode="url"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && linkUrl.trim()) void addLink();
                }}
              />
              <div className="linkapp-row">
                <input
                  value={linkName}
                  onChange={(event) => setLinkName(event.target.value)}
                  placeholder="이름 (비우면 주소에서 가져옵니다)"
                  aria-label="웹 앱 이름"
                  maxLength={120}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && linkUrl.trim()) void addLink();
                  }}
                />
                <button
                  type="button"
                  className="settings-primary"
                  onClick={() => void addLink()}
                  disabled={!linkUrl.trim() || addingLink}
                >
                  {addingLink ? "확인 중…" : "추가"}
                </button>
              </div>
            </div>
            {blocked ? (
              <div className="linkapp-blocked" role="alert">
                <strong>{blocked.title ?? new URL(blocked.url).host} 은(는) 창 안에 띄우는 것을 거부합니다.</strong>
                <p>
                  이 사이트는 다른 앱 안에서 열리지 않도록 설정돼 있어(X-Frame-Options), 임베드하면 빈 화면만
                  보입니다. 대신 도크에서 누르면 새 탭으로 여는 타일로 추가할 수 있습니다.
                </p>
                <div className="linkapp-blocked-actions">
                  <button
                    type="button"
                    className="settings-primary"
                    onClick={() => void addLink("external", true)}
                    disabled={addingLink}
                  >
                    새 탭으로 여는 앱으로 추가
                  </button>
                  <button
                    type="button"
                    className="settings-secondary"
                    onClick={() => void addLink("embed", true)}
                    disabled={addingLink}
                  >
                    그래도 임베드
                  </button>
                  <button type="button" className="settings-secondary" onClick={() => setBlocked(null)}>
                    취소
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          {installations.length > 0 ? (
            <section className="directory-section installed-section">
              <h3>설치된 앱</h3>
              <ul className="app-list">
                {installations.map((installation) => (
                  <li key={installation.id}>
                    <div className="app-list-info">
                      <strong>{installation.app.name}</strong>
                      <span>
                        {installation.app.kind === "link"
                          ? `웹 앱 · ${installation.app.tagline ?? ""}`
                          : (installation.app.tagline ?? "미니앱")}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="app-remove"
                      onClick={() => void removeInstallation(installation.id)}
                      disabled={removing === installation.id}
                    >
                      {removing === installation.id ? "제거 중…" : "제거"}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="directory-section">
            <h3>미니앱</h3>
            {loading ? <p className="linkapp-hint">불러오는 중…</p> : null}
            {!loading && available.length === 0 ? (
              <p className="linkapp-hint">
                설치할 수 있는 미니앱이 없습니다. 사내 앱을 등록하면 여기에
                나타납니다.
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
          </section>
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
