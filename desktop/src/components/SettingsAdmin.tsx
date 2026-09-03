/**
 * 환경설정의 운영 섹션들: 알림 스케줄, 감사 로그, 보관 정책, 개발자 콘솔, 앱 심사.
 *
 * Split from Settings.tsx so the everyday dialog stays readable. Each section
 * loads its own data when the dialog opens, says plainly who may do what, and
 * never invents a control the server would refuse.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { formatRelative } from "@/lib/format";
import { api } from "@/lib/ipc";
import type {
  AppToken,
  AuditEvent,
  DeveloperApp,
  RetentionSettings,
  WebhookDelivery,
} from "@/lib/types";
import { useApp } from "@/store/app";

import { Avatar } from "./Avatar";

// ── 알림 스케줄 (방해 금지) ───────────────────────────────────────────────────

const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"];

export function NotificationScheduleSection() {
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const [start, setStart] = useState(me?.dnd_start ?? "");
  const [end, setEnd] = useState(me?.dnd_end ?? "");
  const [days, setDays] = useState<number[]>(me?.dnd_days ?? [0, 1, 2, 3, 4]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setStart(me?.dnd_start ?? "");
    setEnd(me?.dnd_end ?? "");
    setDays(me?.dnd_days ?? [0, 1, 2, 3, 4]);
  }, [me?.dnd_start, me?.dnd_end, me?.dnd_days]);

  const apply = async (patch: Parameters<typeof api.updateNotifications>[0], done: string) => {
    setBusy(true);
    try {
      const updated = await api.updateNotifications(patch);
      useApp.setState({ me: updated });
      showBanner("info", done);
    } catch (error) {
      reportError(error, "알림 설정을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const pausedUntil = me?.notify_paused_until ? new Date(me.notify_paused_until) : null;
  const paused = pausedUntil !== null && pausedUntil.getTime() > Date.now();

  const pauseFor = (minutes: number) =>
    apply(
      { paused_until: new Date(Date.now() + minutes * 60_000).toISOString() },
      `${minutes >= 60 ? `${minutes / 60}시간` : `${minutes}분`} 동안 알림을 멈춥니다.`,
    );

  const pauseUntilTomorrow = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return apply({ paused_until: d.toISOString() }, "내일 오전 9시까지 알림을 멈춥니다.");
  };

  const dirty =
    (start || null) !== (me?.dnd_start ?? null) ||
    (end || null) !== (me?.dnd_end ?? null) ||
    JSON.stringify([...days].sort()) !== JSON.stringify([...(me?.dnd_days ?? [0, 1, 2, 3, 4])].sort());

  return (
    <div className="settings-provider">
      <div className="settings-danger-row">
        <div>
          <strong>{paused ? "알림 일시 중지 중" : me?.in_dnd ? "방해 금지 시간" : "알림 켜짐"}</strong>
          <p>
            {paused
              ? `${pausedUntil.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} 까지 토스트·브라우저 알림이 오지 않습니다. 배지는 그대로 셉니다.`
              : "잠깐 집중할 때 씁니다. 멈춘 동안에도 안 읽음·멘션 배지는 그대로 쌓입니다."}
          </p>
        </div>
        {paused ? (
          <button type="button" onClick={() => void apply({ paused_until: null }, "알림을 다시 켰습니다.")} disabled={busy}>
            다시 켜기
          </button>
        ) : (
          <div className="dnd-pause-actions">
            <button type="button" onClick={() => void pauseFor(30)} disabled={busy}>30분</button>
            <button type="button" onClick={() => void pauseFor(60)} disabled={busy}>1시간</button>
            <button type="button" onClick={() => void pauseFor(120)} disabled={busy}>2시간</button>
            <button type="button" onClick={() => void pauseUntilTomorrow()} disabled={busy}>내일까지</button>
          </div>
        )}
      </div>

      <p className="settings-hint">
        매일 반복되는 방해 금지 시간입니다. 이 시간에는 멘션·DM 포함 모든 알림이 조용하고, 아침에 배지로 확인합니다.
        시간대는 프로필의 {me?.timezone ?? "Asia/Seoul"} 기준입니다.
      </p>
      <div className="settings-status-row">
        <label className="settings-field settings-status-emoji">
          <span>시작</span>
          <input type="time" value={start} onChange={(event) => setStart(event.target.value)} aria-label="방해 금지 시작" />
        </label>
        <label className="settings-field settings-status-emoji">
          <span>끝</span>
          <input type="time" value={end} onChange={(event) => setEnd(event.target.value)} aria-label="방해 금지 끝" />
        </label>
        <div className="settings-field">
          <span>요일</span>
          <div className="dnd-days" role="group" aria-label="방해 금지 요일">
            {WEEKDAYS.map((label, index) => (
              <button
                key={label}
                type="button"
                className={days.includes(index) ? "is-on" : ""}
                aria-pressed={days.includes(index)}
                onClick={() =>
                  setDays((current) =>
                    current.includes(index) ? current.filter((d) => d !== index) : [...current, index],
                  )
                }
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="settings-actions">
        <button
          type="button"
          className="settings-primary"
          onClick={() =>
            void apply(
              { dnd_start: start || null, dnd_end: end || null, dnd_days: days },
              start && end ? `매일 ${start}–${end} 에 알림이 조용합니다.` : "방해 금지 시간을 해제했습니다.",
            )
          }
          disabled={busy || !dirty || (Boolean(start) !== Boolean(end))}
        >
          저장
        </button>
        {start && end ? (
          <button
            type="button"
            className="settings-secondary"
            onClick={() => void apply({ dnd_start: null, dnd_end: null }, "방해 금지 시간을 해제했습니다.")}
            disabled={busy}
          >
            해제
          </button>
        ) : null}
      </div>
    </div>
  );
}

// ── 감사 로그 ────────────────────────────────────────────────────────────────

const ACTION_LABEL: Record<string, string> = {
  "member.role_changed": "구성원 역할 변경",
  "member.removed": "구성원 내보내기",
  "member.password_reset": "임시 비밀번호 발급",
  "invite.created": "초대 발급",
  "invite.revoked": "초대 회수",
  "channel.archived": "채널 보관",
  "channel.renamed": "채널 이름 변경",
  "channel.member_role_changed": "채널 관리자 변경",
  "channel.member_removed": "채널 구성원 제거",
  "app.installed": "앱 설치",
  "app.uninstalled": "앱 제거",
  "app.updated": "앱 변경",
  "app.review_decided": "앱 심사",
  "smtp.updated": "메일 서버 설정 변경",
  "retention.updated": "보관 정책 변경",
  "file.quarantined": "첨부 파일 차단",
};

export function AuditSection() {
  const workspace = useApp((state) =>
    state.workspaces.find((candidate) => candidate.id === state.activeWorkspaceId),
  );
  const reportError = useApp((state) => state.reportError);
  const canSee = workspace?.my_role === "owner" || workspace?.my_role === "admin";

  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [next, setNext] = useState<string | null>(null);
  const [action, setAction] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (before: string | null) => {
      if (!workspace || !canSee) return;
      setBusy(true);
      try {
        const page = await api.listAudit(workspace.id, { before, action: action || null });
        setEvents((current) => (before ? [...(current ?? []), ...page.items] : page.items));
        setHasMore(page.has_more);
        setNext(page.next_before ?? page.items[page.items.length - 1]?.id ?? null);
      } catch (error) {
        setEvents((current) => current ?? []);
        reportError(error, "감사 로그를 불러오지 못했습니다.");
      } finally {
        setBusy(false);
      }
    },
    [workspace, canSee, action, reportError],
  );

  useEffect(() => {
    setEvents(null);
    void load(null);
  }, [load]);

  if (!workspace) return null;
  if (!canSee) {
    return <p className="settings-hint">감사 로그는 워크스페이스 관리자만 볼 수 있습니다.</p>;
  }

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        누가 언제 무엇을 바꿨는지 — 역할, 초대, 채널 보관, 앱 설치, 메일·보관 설정. 규정 대응용 CSV 로 내려받을 수
        있습니다.
      </p>
      <div className="linkapp-row">
        <select
          className="member-role-select"
          value={action}
          onChange={(event) => setAction(event.target.value)}
          aria-label="행위 종류"
        >
          <option value="">모든 행위</option>
          {Object.entries(ACTION_LABEL).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="settings-secondary"
          onClick={() => void api.downloadAuditCsv(workspace.id).catch((error) => reportError(error, "CSV 를 내려받지 못했습니다."))}
        >
          CSV 내려받기
        </button>
      </div>
      <ul className="audit-list">
        {events === null ? (
          <li className="modal-empty">불러오는 중…</li>
        ) : events.length === 0 ? (
          <li className="modal-empty">기록이 없습니다.</li>
        ) : (
          events.map((event) => (
            <li key={event.id}>
              {event.actor ? (
                <Avatar id={event.actor.id} name={event.actor.display_name} avatarUrl={event.actor.avatar_url} size={20} />
              ) : (
                <span className="audit-system">시스템</span>
              )}
              <div className="audit-text">
                <strong>
                  {event.actor?.display_name ?? "시스템"} · {ACTION_LABEL[event.action] ?? event.action}
                </strong>
                <span>
                  {event.target_label ?? event.target_id ?? ""}
                  {event.details && Object.keys(event.details).length > 0
                    ? ` · ${Object.entries(event.details)
                        .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
                        .join(", ")}`
                    : ""}
                </span>
              </div>
              <time dateTime={event.created_at} title={new Date(event.created_at).toLocaleString("ko-KR")}>
                {formatRelative(event.created_at)}
              </time>
            </li>
          ))
        )}
      </ul>
      {hasMore ? (
        <button type="button" className="file-more" onClick={() => void load(next)} disabled={busy}>
          더 보기
        </button>
      ) : null}
    </div>
  );
}

// ── 보관 정책 ────────────────────────────────────────────────────────────────

export function RetentionSection() {
  const workspace = useApp((state) =>
    state.workspaces.find((candidate) => candidate.id === state.activeWorkspaceId),
  );
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);
  const canEdit = workspace?.my_role === "owner" || workspace?.my_role === "admin";

  const [settings, setSettings] = useState<RetentionSettings | null>(null);
  const [messages, setMessages] = useState("");
  const [files, setFiles] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!workspace) return;
    let alive = true;
    api
      .getRetention(workspace.id)
      .then((value) => {
        if (!alive) return;
        setSettings(value);
        setMessages(value.retention_days_messages != null ? String(value.retention_days_messages) : "");
        setFiles(value.retention_days_files != null ? String(value.retention_days_files) : "");
      })
      .catch(() => {
        if (alive) setSettings({ retention_days_messages: null, retention_days_files: null });
      });
    return () => {
      alive = false;
    };
  }, [workspace]);

  if (!workspace) return null;

  const save = async () => {
    setBusy(true);
    try {
      const updated = await api.updateRetention(workspace.id, {
        retention_days_messages: messages.trim() === "" ? null : Math.max(1, Number(messages)),
        retention_days_files: files.trim() === "" ? null : Math.max(1, Number(files)),
      });
      setSettings(updated);
      showBanner(
        "info",
        updated.retention_days_messages == null && updated.retention_days_files == null
          ? "보관 정책을 해제했습니다. 아무것도 자동 삭제되지 않습니다."
          : "보관 정책을 저장했습니다. 기한이 지난 항목은 매시간 정리됩니다.",
      );
    } catch (error) {
      reportError(error, "보관 정책을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        {settings === null
          ? "불러오는 중…"
          : settings.retention_days_messages == null && settings.retention_days_files == null
            ? "지금은 아무것도 자동 삭제되지 않습니다."
            : `메시지 ${settings.retention_days_messages ?? "무기한"}일 · 파일 ${settings.retention_days_files ?? "무기한"}일 뒤 자동 삭제.`}{" "}
        채널마다 다른 기간이 필요하면 채널 설정에서 따로 정할 수 있습니다(채널 값이 우선). 삭제는 되돌릴 수 없습니다.
      </p>
      {canEdit ? (
        <>
          <div className="settings-status-row">
            <label className="settings-field settings-status-text">
              <span>메시지 보관 기간(일)</span>
              <input type="number" min={1} max={3650} value={messages} onChange={(event) => setMessages(event.target.value)} placeholder="비우면 무기한" />
            </label>
            <label className="settings-field settings-status-text">
              <span>파일 보관 기간(일)</span>
              <input type="number" min={1} max={3650} value={files} onChange={(event) => setFiles(event.target.value)} placeholder="비우면 무기한" />
            </label>
          </div>
          <div className="settings-actions">
            <button type="button" className="settings-primary" onClick={() => void save()} disabled={busy || settings === null}>
              {busy ? "저장 중…" : "저장"}
            </button>
          </div>
        </>
      ) : (
        <p className="settings-hint">변경은 워크스페이스 관리자만 할 수 있습니다.</p>
      )}
    </div>
  );
}

// ── 개발자 콘솔 ──────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<DeveloperApp["status"], string> = {
  draft: "초안 (이 워크스페이스에서만)",
  pending_review: "심사 대기",
  published: "게시됨 (모든 워크스페이스)",
  rejected: "반려됨",
  disabled: "사용 중지",
};

const MANIFEST_TEMPLATE = `{
  "slug": "my-tool",
  "name": "우리 도구",
  "version": "1.0.0",
  "tagline": "한 줄 설명",
  "kind": "panel",
  "panel_url": "https://tool.example.com/panel",
  "home_url": "https://tool.example.com/home",
  "command_url": "https://tool.example.com/llack/command",
  "interaction_url": "https://tool.example.com/llack/interact",
  "event_webhook_url": "https://tool.example.com/llack/events",
  "event_subscriptions": ["message.created"],
  "slash_commands": [{ "command": "/tool", "description": "도구 열기", "usage": "/tool [검색어]" }],
  "scopes": ["channels:read", "messages:write"]
}`;

export function DeveloperSection() {
  const workspace = useApp((state) =>
    state.workspaces.find((candidate) => candidate.id === state.activeWorkspaceId),
  );
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);
  const loadInstallations = useApp((state) => state.loadInstallations);
  const canDevelop = workspace?.my_role === "owner" || workspace?.my_role === "admin";

  const [apps, setApps] = useState<DeveloperApp[] | null>(null);
  const [manifest, setManifest] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ appId: string; value: string } | null>(null);
  const [tokens, setTokens] = useState<Record<string, AppToken[]>>({});
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({});
  const [tokenName, setTokenName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!workspace || !canDevelop) return;
    try {
      setApps(await api.listMyApps(workspace.id));
    } catch (error) {
      setApps([]);
      reportError(error, "내 앱 목록을 불러오지 못했습니다.");
    }
  }, [workspace, canDevelop, reportError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!workspace) return null;
  if (!canDevelop) {
    return <p className="settings-hint">앱 등록은 워크스페이스 관리자만 할 수 있습니다. 만들고 싶은 앱이 있으면 관리자에게 매니페스트를 전달하세요.</p>;
  }

  const submitManifest = async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(manifest) as Record<string, unknown>;
    } catch {
      showBanner("error", "매니페스트가 올바른 JSON 이 아닙니다.");
      return;
    }
    setBusy(true);
    try {
      if (editing) {
        await api.updateManifest(editing, parsed);
        showBanner("info", "매니페스트를 갱신했습니다.");
      } else {
        const created = await api.registerApp(parsed, workspace.id);
        if (created.secret) setSecret({ appId: created.id, value: created.secret });
        showBanner("info", `${created.name} 을(를) 등록했습니다. 이 워크스페이스의 앱 디렉터리에서 설치할 수 있습니다.`);
      }
      setManifest("");
      setEditing(null);
      await load();
    } catch (error) {
      const parsedError = reportError(error);
      showBanner("error", parsedError.status === 422 ? `매니페스트 오류: ${parsedError.message}` : "등록하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const withApp = async (_appId: string, work: () => Promise<void>, done?: string) => {
    setBusy(true);
    try {
      await work();
      if (done) showBanner("info", done);
      await load();
      await loadInstallations();
      window.dispatchEvent(new CustomEvent("llack:apps-changed"));
    } catch (error) {
      reportError(error, "처리하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const loadTokens = async (appId: string) => {
    try {
      setTokens((current) => ({ ...current, [appId]: [] }));
      const rows = await api.listAppTokens(appId);
      setTokens((current) => ({ ...current, [appId]: rows }));
    } catch {
      // Older server without token routes: the list simply stays empty.
    }
  };
  const loadDeliveries = async (appId: string) => {
    try {
      const rows = await api.listDeliveries(appId);
      setDeliveries((current) => ({ ...current, [appId]: rows }));
    } catch {
      setDeliveries((current) => ({ ...current, [appId]: [] }));
    }
  };

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        매니페스트 JSON 하나로 앱을 등록합니다. 등록 직후에는 이 워크스페이스에서만 보이고(초안), 다른
        워크스페이스에도 내놓으려면 심사를 신청합니다. 서명 비밀은 등록 때 한 번만 보여줍니다.
      </p>

      <textarea
        className="manifest-editor"
        value={manifest}
        onChange={(event) => setManifest(event.target.value)}
        placeholder={MANIFEST_TEMPLATE}
        rows={manifest ? Math.min(24, manifest.split("\n").length + 1) : 6}
        spellCheck={false}
        aria-label="앱 매니페스트 JSON"
      />
      <div className="settings-actions">
        <button type="button" className="settings-primary" onClick={() => void submitManifest()} disabled={busy || !manifest.trim()}>
          {editing ? "매니페스트 갱신" : "앱 등록"}
        </button>
        <button type="button" className="settings-secondary" onClick={() => setManifest(MANIFEST_TEMPLATE)} disabled={busy}>
          예시 채우기
        </button>
        {editing ? (
          <button type="button" className="settings-secondary" onClick={() => { setEditing(null); setManifest(""); }}>
            새 앱으로 전환
          </button>
        ) : null}
      </div>

      {secret ? (
        <div className="linkapp-blocked" role="alert">
          <strong>서명 비밀 — 지금 복사해두세요. 다시 보여주지 않습니다.</strong>
          <p>
            <code className="secret-code">{secret.value}</code>
          </p>
          <div className="linkapp-blocked-actions">
            <button type="button" className="settings-secondary" onClick={() => void navigator.clipboard?.writeText(secret.value)}>
              복사
            </button>
            <button type="button" className="settings-secondary" onClick={() => setSecret(null)}>
              확인했습니다
            </button>
          </div>
        </div>
      ) : null}

      <ul className="dev-app-list">
        {apps === null ? (
          <li className="modal-empty">불러오는 중…</li>
        ) : apps.length === 0 ? (
          <li className="modal-empty">아직 등록한 앱이 없습니다.</li>
        ) : (
          apps.map((app) => {
            const open = expanded === app.id;
            return (
              <li key={app.id} className={open ? "is-open" : ""}>
                <button
                  type="button"
                  className="dev-app-head"
                  onClick={() => {
                    setExpanded(open ? null : app.id);
                    if (!open) {
                      void loadTokens(app.id);
                      void loadDeliveries(app.id);
                    }
                  }}
                  aria-expanded={open}
                >
                  <strong>{app.name}</strong>
                  <span className={`dev-status is-${app.status}`}>{STATUS_LABEL[app.status] ?? app.status}</span>
                  <span className="dev-app-meta">
                    {app.slug} · v{app.version ?? "1.0.0"}
                    {app.slash_commands && app.slash_commands.length > 0 ? ` · ${app.slash_commands.map((c) => c.command).join(" ")}` : ""}
                  </span>
                </button>
                {open ? (
                  <div className="dev-app-body">
                    {app.review_note ? <p className="settings-hint">심사 메모: {app.review_note}</p> : null}
                    <div className="linkapp-blocked-actions">
                      <button
                        type="button"
                        className="settings-secondary"
                        onClick={() => {
                          setEditing(app.id);
                          setManifest(
                            JSON.stringify(
                              {
                                slug: app.slug,
                                name: app.name,
                                version: app.version ?? "1.0.0",
                                tagline: app.tagline ?? undefined,
                                description: app.description ?? undefined,
                                kind: app.kind ?? "panel",
                                icon_url: app.icon_url ?? undefined,
                                panel_url: app.panel_url ?? undefined,
                                sidebar_url: app.sidebar_url ?? undefined,
                                home_url: app.home_url ?? undefined,
                                command_url: app.command_url ?? undefined,
                                interaction_url: app.interaction_url ?? undefined,
                                event_webhook_url: app.event_webhook_url ?? undefined,
                                event_subscriptions: app.event_subscriptions ?? [],
                                slash_commands: app.slash_commands ?? [],
                                scopes: app.requested_scopes ?? [],
                              },
                              null,
                              2,
                            ),
                          );
                        }}
                      >
                        매니페스트 수정
                      </button>
                      {app.status === "draft" || app.status === "rejected" ? (
                        <button
                          type="button"
                          className="settings-primary"
                          onClick={() => void withApp(app.id, () => api.submitApp(app.id).then(() => undefined), "심사를 신청했습니다. 서비스 관리자가 승인하면 모든 워크스페이스에 게시됩니다.")}
                          disabled={busy}
                        >
                          심사 신청
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="settings-secondary"
                        onClick={() =>
                          void withApp(app.id, async () => {
                            const rotated = await api.rotateAppSecret(app.id);
                            setSecret({ appId: app.id, value: rotated.secret });
                          })
                        }
                        disabled={busy}
                      >
                        서명 비밀 재발급
                      </button>
                      {app.event_webhook_url ? (
                        <button
                          type="button"
                          className="settings-secondary"
                          onClick={() =>
                            void withApp(app.id, async () => {
                              const delivery = await api.testWebhook(app.id);
                              showBanner(
                                delivery.status === "ok" ? "info" : "error",
                                delivery.status === "ok"
                                  ? `테스트 이벤트를 보냈습니다 (HTTP ${delivery.last_status_code ?? "?"}).`
                                  : `웹훅이 응답하지 않았습니다: ${delivery.last_error ?? "알 수 없음"}`,
                              );
                              await loadDeliveries(app.id);
                            })
                          }
                          disabled={busy}
                        >
                          웹훅 테스트
                        </button>
                      ) : null}
                    </div>

                    <div className="dev-sub">
                      <strong>API 토큰</strong>
                      <p className="settings-hint">봇으로 메시지를 게시하거나 브릿지 밖에서 API 를 부를 때 씁니다. 평문은 발급 응답에서만 보입니다.</p>
                      <ul className="session-list">
                        {(tokens[app.id] ?? []).map((token) => (
                          <li key={token.id}>
                            <div className="session-info">
                              <strong>
                                {token.name} <code>{token.token_prefix}…</code>
                              </strong>
                              <span>
                                {token.created_at ? `발급 ${formatRelative(token.created_at)}` : ""}
                                {token.last_used_at ? ` · 마지막 사용 ${formatRelative(token.last_used_at)}` : ""}
                                {token.expires_at ? ` · 만료 ${new Date(token.expires_at).toLocaleDateString("ko-KR")}` : ""}
                              </span>
                            </div>
                            <button
                              type="button"
                              className="member-action is-destructive"
                              onClick={() => void withApp(app.id, () => api.revokeAppToken(app.id, token.id).then(() => loadTokens(app.id)), "토큰을 폐기했습니다.")}
                              disabled={busy}
                            >
                              폐기
                            </button>
                          </li>
                        ))}
                      </ul>
                      <div className="linkapp-row">
                        <input
                          className="settings-invite-input"
                          value={tokenName}
                          onChange={(event) => setTokenName(event.target.value)}
                          placeholder="토큰 이름 (예: CI 봇)"
                          maxLength={80}
                          aria-label="토큰 이름"
                        />
                        <button
                          type="button"
                          className="settings-primary"
                          onClick={() =>
                            void withApp(app.id, async () => {
                              const created = await api.createAppToken(app.id, tokenName.trim() || "토큰");
                              if (created.token) setSecret({ appId: app.id, value: created.token });
                              setTokenName("");
                              await loadTokens(app.id);
                            })
                          }
                          disabled={busy}
                        >
                          토큰 발급
                        </button>
                      </div>
                    </div>

                    <div className="dev-sub">
                      <strong>웹훅 전달 기록</strong>
                      <ul className="audit-list">
                        {(deliveries[app.id] ?? []).length === 0 ? (
                          <li className="modal-empty">전달 기록이 없습니다.</li>
                        ) : (
                          (deliveries[app.id] ?? []).map((delivery) => (
                            <li key={delivery.id}>
                              <span className={`dev-status is-${delivery.status}`}>{delivery.status}</span>
                              <div className="audit-text">
                                <strong>{delivery.event}</strong>
                                <span>
                                  시도 {delivery.attempts}회
                                  {delivery.last_status_code ? ` · HTTP ${delivery.last_status_code}` : ""}
                                  {delivery.last_error ? ` · ${delivery.last_error}` : ""}
                                </span>
                              </div>
                              <time dateTime={delivery.created_at}>{formatRelative(delivery.created_at)}</time>
                            </li>
                          ))
                        )}
                      </ul>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}

// ── 앱 심사 (서비스 관리자) ──────────────────────────────────────────────────

export function ReviewSection() {
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);
  const [pending, setPending] = useState<DeveloperApp[] | null>(null);
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!me?.is_service_admin) return;
    try {
      setPending(await api.listPendingApps());
    } catch (error) {
      setPending([]);
      reportError(error, "심사 대기 목록을 불러오지 못했습니다.");
    }
  }, [me?.is_service_admin, reportError]);

  useEffect(() => {
    void load();
    // The developer console (same dialog) submits apps for review; it
    // announces that so this queue does not go stale until reopened.
    const onChanged = () => void load();
    window.addEventListener("llack:apps-changed", onChanged);
    return () => window.removeEventListener("llack:apps-changed", onChanged);
  }, [load]);

  const count = useMemo(() => pending?.length ?? 0, [pending]);
  if (!me?.is_service_admin) return null;

  const decide = async (app: DeveloperApp, decision: "approve" | "reject") => {
    setBusy(app.id);
    try {
      await api.reviewApp(app.id, decision, note[app.id]?.trim() || null);
      showBanner("info", decision === "approve" ? `${app.name} 을(를) 게시했습니다.` : `${app.name} 을(를) 반려했습니다.`);
      await load();
    } catch (error) {
      reportError(error, "심사 결정을 저장하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        {count === 0 ? "심사를 기다리는 앱이 없습니다." : `${count}개의 앱이 게시 승인을 기다립니다. 승인하면 모든 워크스페이스의 앱 디렉터리에 보입니다.`}
      </p>
      <ul className="dev-app-list">
        {(pending ?? []).map((app) => (
          <li key={app.id} className="is-open">
            <div className="dev-app-head">
              <strong>{app.name}</strong>
              <span className="dev-app-meta">
                {app.slug} · v{app.version ?? "1.0.0"} · {app.kind ?? "panel"}
                {app.panel_url ? ` · ${app.panel_url}` : ""}
              </span>
            </div>
            <div className="dev-app-body">
              {app.tagline ? <p>{app.tagline}</p> : null}
              {app.requested_scopes?.length ? <p className="settings-hint">요청 권한: {app.requested_scopes.join(", ")}</p> : null}
              <input
                className="settings-invite-input"
                value={note[app.id] ?? ""}
                onChange={(event) => setNote((current) => ({ ...current, [app.id]: event.target.value }))}
                placeholder="작성자에게 남길 메모 (선택)"
                maxLength={500}
                aria-label="심사 메모"
              />
              <div className="linkapp-blocked-actions">
                <button type="button" className="settings-primary" onClick={() => void decide(app, "approve")} disabled={busy === app.id}>
                  승인·게시
                </button>
                <button type="button" className="member-action is-destructive" onClick={() => void decide(app, "reject")} disabled={busy === app.id}>
                  반려
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
