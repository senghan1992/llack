/**
 * 환경설정 — the place things are *set up*, as opposed to used.
 *
 * The provider connection lives here rather than inside the agent panel: the
 * panel is where you talk to the model, and a form that appears where the
 * conversation should be reads as a broken conversation. The panel now points
 * here, and this dialog owns connect / model choice / disconnect.
 *
 * The key handling contract is unchanged from the old in-panel form: the key is
 * typed here, handed to Rust once, and kept only in the OS keychain. After
 * connecting, the model dropdown is repopulated from the *account's own*
 * `/v1/models` (fetched through the byte proxy, so the key stays in Rust) —
 * whatever the connected subscription can run is what the dropdown offers.
 */

import { useCallback, useEffect, useState } from "react";

import {
  DEFAULT_MODELS,
  listProviderModels,
  type ProviderModel,
} from "@/lib/agent/models";
import { webInviteUrl } from "@/lib/invite";
import { agentHost, api, capabilities, isDesktopShell } from "@/lib/ipc";
import type { InviteOut, SmtpSettings } from "@/lib/types";
import { useAgent } from "@/store/agent";
import { useApp } from "@/store/app";

import { IconClose } from "./Icon";

export function Settings() {
  const open = useApp((state) => state.settingsOpen);
  const setSettings = useApp((state) => state.setSettings);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettings(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setSettings]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      onClick={() => setSettings(false)}
      role="presentation"
    >
      <div
        className="modal settings"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="환경설정"
      >
        <header className="modal-header">
          <h2>환경설정</h2>
          <button type="button" onClick={() => setSettings(false)} aria-label="닫기">
            <IconClose size={13} />
          </button>
        </header>

        <div className="modal-body settings-body">
          <section className="settings-section">
            <h3>내 프로필</h3>
            <ProfileSection />
          </section>

          <section className="settings-section">
            <h3>구성원 초대</h3>
            <InviteSection />
          </section>

          <section className="settings-section">
            <h3>메일 (SMTP)</h3>
            <SmtpSection />
          </section>

          <section className="settings-section">
            <h3>에이전트 프로바이더</h3>
            <ProviderSection />
          </section>

          <section className="settings-section">
            <h3>계정</h3>
            <AccountSection />
          </section>

          <section className="settings-section">
            <h3>기능 안내</h3>
            <p className="settings-hint">
              하고 싶은 일을 찾아 그대로 따라 하면 됩니다. 전부 지금 화면에서
              바로 됩니다.
            </p>
            <GuideList />
          </section>
        </div>
      </div>
    </div>
  );
}

/**
 * My name, title and status — the API existed all along; this is the door.
 *
 * Saved with `exclude_unset` semantics: only the fields that changed travel.
 * The realtime `user.updated` event carries the change to everyone who shares
 * a workspace, so no local map surgery is needed beyond `me`.
 */
function ProfileSection() {
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const [displayName, setDisplayName] = useState(me?.display_name ?? "");
  const [title, setTitle] = useState(me?.title ?? "");
  const [statusEmoji, setStatusEmoji] = useState(me?.status_emoji ?? "");
  const [statusText, setStatusText] = useState(me?.status_text ?? "");
  const [busy, setBusy] = useState(false);

  // The dialog may open before `me` resolves on a cold start.
  useEffect(() => {
    setDisplayName(me?.display_name ?? "");
    setTitle(me?.title ?? "");
    setStatusEmoji(me?.status_emoji ?? "");
    setStatusText(me?.status_text ?? "");
  }, [me]);

  const dirtyProfile =
    displayName !== (me?.display_name ?? "") || title !== (me?.title ?? "");
  const dirtyStatus =
    statusEmoji !== (me?.status_emoji ?? "") || statusText !== (me?.status_text ?? "");

  const save = async () => {
    if ((!dirtyProfile && !dirtyStatus) || busy || !displayName.trim()) return;
    setBusy(true);
    try {
      let updated = me;
      if (dirtyProfile) {
        updated = await api.updateProfile({
          ...(displayName !== (me?.display_name ?? "")
            ? { display_name: displayName.trim() }
            : {}),
          ...(title !== (me?.title ?? "") ? { title: title.trim() } : {}),
        });
      }
      if (dirtyStatus) {
        updated = await api.updateStatus({
          status_emoji: statusEmoji.trim() || null,
          status_text: statusText.trim() || null,
        });
      }
      if (updated) useApp.setState({ me: updated });
      showBanner("info", "프로필을 저장했습니다.");
    } catch (error) {
      reportError(error, "프로필을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-provider">
      <label className="settings-field">
        <span>이름</span>
        <input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={120}
        />
      </label>
      <label className="settings-field">
        <span>직함</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="예: 백엔드 엔지니어"
          maxLength={160}
        />
      </label>
      <div className="settings-status-row">
        <label className="settings-field settings-status-emoji">
          <span>상태 이모지</span>
          <input
            value={statusEmoji}
            onChange={(event) => setStatusEmoji(event.target.value)}
            placeholder="🍜"
            maxLength={8}
          />
        </label>
        <label className="settings-field settings-status-text">
          <span>상태 문구</span>
          <input
            value={statusText}
            onChange={(event) => setStatusText(event.target.value)}
            placeholder="예: 점심 식사 중, 1시에 돌아옵니다"
            maxLength={200}
          />
        </label>
      </div>
      <div className="settings-actions">
        <button
          type="button"
          className="settings-primary"
          onClick={() => void save()}
          disabled={busy || (!dirtyProfile && !dirtyStatus) || !displayName.trim()}
        >
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}

/**
 * Issue invite links from inside the product.
 *
 * The server's URL is a `llack://` deep link for the desktop; a browser needs
 * a clickable https address, so each row shows the web form
 * (`{origin}/?invite=token`) with a copy button. Links appear exactly once —
 * the raw token is never stored — which the UI says out loud.
 */
function InviteSection() {
  const workspace = useApp((state) =>
    state.workspaces.find((entry) => entry.id === state.activeWorkspaceId),
  );
  const reportError = useApp((state) => state.reportError);
  const showBanner = useApp((state) => state.showBanner);

  const [emails, setEmails] = useState("");
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<
    Array<{ email: string; link: string; expires_at?: string | null }>
  >([]);
  const [outstanding, setOutstanding] = useState<InviteOut[]>([]);

  const isAdmin = workspace?.my_role === "admin" || workspace?.my_role === "owner";

  const refreshOutstanding = useCallback(async () => {
    if (!workspace) return;
    try {
      const rows = await api.listInvites(workspace.id);
      setOutstanding(rows.filter((row) => !row.accepted_at));
    } catch {
      // Not an admin, or the endpoint is unreachable: the section below
      // simply shows nothing outstanding.
      setOutstanding([]);
    }
  }, [workspace]);

  useEffect(() => {
    if (isAdmin) void refreshOutstanding();
  }, [isAdmin, refreshOutstanding]);

  const revoke = async (inviteId: string | undefined) => {
    if (!workspace || !inviteId) return;
    try {
      await api.revokeInvite(workspace.id, inviteId);
      await refreshOutstanding();
      showBanner("info", "초대를 회수했습니다. 그 링크는 더 이상 동작하지 않습니다.");
    } catch (error) {
      reportError(error, "초대를 회수하지 못했습니다.");
    }
  };

  const invite = async () => {
    if (!workspace || busy) return;
    const list = emails
      .split(/[\s,;]+/)
      .map((entry) => entry.trim())
      .filter(Boolean);
    if (list.length === 0) return;
    setBusy(true);
    try {
      const created = await api.createInvites(workspace.id, list);
      setIssued(
        created.map((row) => ({
          email: row.email,
          link:
            webInviteUrl(row.invite_url) ??
            row.invite_url ??
            "링크를 만들지 못했습니다",
          expires_at: row.expires_at,
        })),
      );
      setEmails("");
      await refreshOutstanding();
    } catch (error) {
      reportError(error, "초대를 만들지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link);
      showBanner("info", "초대 링크를 복사했습니다.");
    } catch {
      showBanner("error", "복사하지 못했습니다. 링크를 직접 선택해 복사해주세요.");
    }
  };

  if (!workspace) {
    return <p className="settings-hint">워크스페이스에 들어간 뒤 초대할 수 있습니다.</p>;
  }
  if (!isAdmin) {
    return (
      <p className="settings-hint">
        구성원 초대는 워크스페이스 관리자만 할 수 있습니다. 관리자에게 초대
        링크를 요청해주세요.
      </p>
    );
  }

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        이메일을 쉼표나 줄바꿈으로 구분해 넣으세요. 사람마다 초대 링크가
        만들어지며, 링크는 지금 한 번만 표시됩니다 — 복사해서 직접
        전달해주세요.
      </p>
      <div className="linkapp-row">
        <input
          className="settings-invite-input"
          value={emails}
          onChange={(event) => setEmails(event.target.value)}
          placeholder="jinny@acme.com, minho@acme.com"
          aria-label="초대할 이메일"
          onKeyDown={(event) => {
            if (event.key === "Enter" && emails.trim()) void invite();
          }}
        />
        <button
          type="button"
          className="settings-primary"
          onClick={() => void invite()}
          disabled={busy || !emails.trim()}
        >
          {busy ? "만드는 중…" : "초대 링크 만들기"}
        </button>
      </div>

      {issued.length > 0 ? (
        <ul className="invite-list">
          {issued.map((row) => (
            <li key={row.email}>
              <div className="invite-info">
                <strong>{row.email}</strong>
                <span>{row.link}</span>
              </div>
              <button type="button" onClick={() => void copy(row.link)}>
                복사
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <ResetPasswordRow workspaceId={workspace.id} />

      {outstanding.length > 0 ? (
        <>
          <p className="settings-hint">
            수락되지 않은 초대입니다. 회수하면 그 링크는 즉시 무효가 됩니다.
          </p>
          <ul className="invite-list">
            {outstanding.map((row) => (
              <li key={row.id ?? row.email}>
                <div className="invite-info">
                  <strong>{row.email}</strong>
                  <span>
                    {row.expires_at
                      ? `만료: ${new Date(row.expires_at).toLocaleDateString("ko-KR")}`
                      : "대기 중"}
                  </span>
                </div>
                <button type="button" onClick={() => void revoke(row.id)}>
                  회수
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

/**
 * The recovery path for "비밀번호를 잊었습니다" on a server with no email.
 *
 * The admin picks a member by email; the server issues a one-time temporary
 * password (shown once, copy it now) and kills the member's sessions. The
 * server enforces the role rules — only downward, never yourself.
 */
function ResetPasswordRow({ workspaceId }: { workspaceId: string }) {
  const people = useApp((state) => state.people);
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<{ email: string; password: string } | null>(null);

  const reset = async () => {
    const needle = email.trim().toLowerCase();
    if (!needle || busy) return;
    const target = [...people.values()].find(
      (person) => person.email?.toLowerCase() === needle,
    );
    if (!target) {
      showBanner("error", "그 이메일의 구성원을 찾지 못했습니다.");
      return;
    }
    if (target.id === me?.id) {
      showBanner("error", "내 비밀번호는 아래 계정 섹션에서 바꿀 수 있습니다.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.resetMemberPassword(workspaceId, target.id);
      setIssued({ email: needle, password: result.temp_password });
      setEmail("");
    } catch (error) {
      reportError(error, "비밀번호를 재설정하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <p className="settings-hint" style={{ marginTop: 14 }}>
        비밀번호를 잊은 구성원이 있다면 임시 비밀번호를 발급해 직접
        전달해주세요. 기존 비밀번호와 모든 로그인 세션은 즉시 무효가 됩니다.
      </p>
      <div className="linkapp-row">
        <input
          className="settings-invite-input"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="구성원 이메일"
          aria-label="비밀번호를 재설정할 구성원 이메일"
          onKeyDown={(event) => {
            if (event.key === "Enter" && email.trim()) void reset();
          }}
        />
        <button
          type="button"
          className="settings-primary"
          onClick={() => void reset()}
          disabled={busy || !email.trim()}
        >
          {busy ? "발급 중…" : "임시 비밀번호 발급"}
        </button>
      </div>
      {issued ? (
        <ul className="invite-list">
          <li>
            <div className="invite-info">
              <strong>{issued.email}</strong>
              <span>임시 비밀번호: {issued.password} — 지금만 표시됩니다</span>
            </div>
            <button
              type="button"
              onClick={() =>
                void navigator.clipboard
                  .writeText(issued.password)
                  .then(() => showBanner("info", "임시 비밀번호를 복사했습니다."))
                  .catch(() => showBanner("error", "복사하지 못했습니다."))
              }
            >
              복사
            </button>
          </li>
        </ul>
      ) : null}
    </>
  );
}

/**
 * The server's outbound mail relay, editable from here.
 *
 * Each company points this at its own SMTP (사내 릴레이, Gmail/Workspace,
 * SES, …) — no env editing, no redeploy. Owner-only: this decides where
 * everyone's reset codes go, which is exactly the kind of thing a lower role
 * must not be able to re-point. The password is write-only — the server
 * returns `password_set`, never the secret — and "테스트 메일 보내기" tries
 * the values as typed before anything is saved.
 */
function SmtpSection() {
  const workspace = useApp((state) =>
    state.workspaces.find((entry) => entry.id === state.activeWorkspaceId),
  );
  const me = useApp((state) => state.me);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const isOwner = workspace?.my_role === "owner" || Boolean(me?.is_service_admin);

  const [loaded, setLoaded] = useState<SmtpSettings | null>(null);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [starttls, setStarttls] = useState(true);
  const [mailFrom, setMailFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    if (!isOwner) return;
    let alive = true;
    api
      .getSmtpSettings()
      .then((settings) => {
        if (!alive) return;
        setLoaded(settings);
        setHost(settings.host);
        setPort(String(settings.port || 587));
        setUsername(settings.username);
        setStarttls(settings.starttls);
        setMailFrom(settings.mail_from);
      })
      .catch(() => {
        if (alive) setLoaded(null);
      });
    return () => {
      alive = false;
    };
  }, [isOwner]);

  if (!isOwner) {
    return (
      <p className="settings-hint">
        메일 서버 설정은 워크스페이스 소유자만 볼 수 있습니다. 비밀번호
        재설정 메일이 오지 않으면 소유자에게 이 설정을 요청해주세요.
      </p>
    );
  }

  const payload = () => ({
    host: host.trim(),
    port: Number(port) || 587,
    username: username.trim(),
    // Empty input = keep the stored secret; the server treats null as "keep".
    password: password ? password : null,
    starttls,
    mail_from: mailFrom.trim() || "llack@localhost",
  });

  const save = async () => {
    if (busy) return;
    setBusy(true);
    setTestResult(null);
    try {
      const settings = await api.updateSmtpSettings(payload());
      setLoaded(settings);
      setPassword("");
      showBanner(
        "info",
        settings.source === "database"
          ? "메일 서버 설정을 저장했습니다. 이제 재설정 코드가 이 서버로 발송됩니다."
          : "메일 서버 설정을 비웠습니다. 환경 변수 또는 서버 로그(콘솔)로 돌아갑니다.",
      );
    } catch (error) {
      reportError(error, "메일 서버 설정을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    if (testing || !host.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testSmtp(payload());
      setTestResult(
        result.ok
          ? `테스트 메일을 보냈습니다 → ${result.sent_to}. 받은 편지함을 확인해주세요.`
          : `연결 실패: ${result.error}`,
      );
    } catch (error) {
      reportError(error, "테스트를 실행하지 못했습니다.");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="settings-provider">
      <p className="settings-hint">
        회사 메일 서버(SMTP) 정보를 넣으면 비밀번호 재설정 코드가 그 서버로
        발송됩니다. 비워두면 코드가 서버 로그에만 남습니다.
        {loaded ? (
          <>
            {" "}
            현재:{" "}
            <strong>
              {loaded.source === "database"
                ? "이 화면에서 저장한 설정 사용 중"
                : loaded.source === "env"
                  ? "서버 환경 변수 사용 중"
                  : "미설정 (콘솔 로그)"}
            </strong>
          </>
        ) : null}
      </p>

      <div className="settings-status-row">
        <label className="settings-field settings-status-text">
          <span>SMTP 호스트</span>
          <input
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="smtp.company.com"
          />
        </label>
        <label className="settings-field settings-status-emoji">
          <span>포트</span>
          <input
            value={port}
            onChange={(event) => setPort(event.target.value)}
            inputMode="numeric"
            placeholder="587"
          />
        </label>
      </div>

      <div className="settings-status-row">
        <label className="settings-field settings-status-text">
          <span>사용자 이름 (없으면 비움)</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="mailer@company.com"
            autoComplete="off"
          />
        </label>
        <label className="settings-field settings-status-text">
          <span>비밀번호</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={loaded?.password_set ? "저장됨 — 바꿀 때만 입력" : ""}
            autoComplete="new-password"
          />
        </label>
      </div>

      <label className="settings-field">
        <span>보내는 주소 (From)</span>
        <input
          value={mailFrom}
          onChange={(event) => setMailFrom(event.target.value)}
          placeholder="llack@company.com"
        />
      </label>

      <label className="sidebar-new-private">
        <input
          type="checkbox"
          checked={starttls}
          onChange={(event) => setStarttls(event.target.checked)}
        />
        STARTTLS 사용 (대부분의 587 포트 릴레이)
      </label>

      {testResult ? (
        <p className={testResult.startsWith("연결 실패") ? "settings-error" : "settings-hint"}>
          {testResult}
        </p>
      ) : null}

      <div className="settings-actions settings-smtp-actions">
        <button
          type="button"
          onClick={() => void test()}
          disabled={testing || !host.trim()}
          className="settings-secondary"
        >
          {testing ? "보내는 중…" : "테스트 메일 보내기"}
        </button>
        <button
          type="button"
          className="settings-primary"
          onClick={() => void save()}
          disabled={busy}
        >
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}

/** Password change and the way out. */
function AccountSection() {
  const me = useApp((state) => state.me);
  const signOut = useApp((state) => state.signOut);
  const showBanner = useApp((state) => state.showBanner);
  const reportError = useApp((state) => state.reportError);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [revoking, setRevoking] = useState(false);

  /** Every other device out, this one stays. Sessions accumulated silently
   *  (22 on one test account) with no way to see or end them. */
  const revokeOthers = async () => {
    if (revoking) return;
    setRevoking(true);
    try {
      await api.revokeOtherSessions();
      showBanner("info", "다른 기기의 세션을 모두 종료했습니다. 이 기기는 그대로 로그인 상태입니다.");
    } catch (error) {
      reportError(error, "다른 기기를 로그아웃하지 못했습니다.");
    } finally {
      setRevoking(false);
    }
  };

  const changePassword = async () => {
    if (busy || !current || next.length < 10) return;
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      showBanner("info", "비밀번호를 변경했습니다.");
    } catch (error) {
      reportError(error, "비밀번호를 변경하지 못했습니다. 현재 비밀번호를 확인해주세요.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-provider">
      <div className="settings-status-row">
        <label className="settings-field settings-status-text">
          <span>현재 비밀번호</span>
          <input
            type="password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        <label className="settings-field settings-status-text">
          <span>새 비밀번호 (10자 이상)</span>
          <input
            type="password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            autoComplete="new-password"
          />
        </label>
      </div>
      <div className="settings-actions">
        <button
          type="button"
          className="settings-primary"
          onClick={() => void changePassword()}
          disabled={busy || !current || next.length < 10}
        >
          비밀번호 변경
        </button>
      </div>

      <NotificationPermissionRow />

      <div className="settings-danger-row">
        <div>
          <strong>다른 기기 모두 로그아웃</strong>
          <p>잃어버린 노트북, 공용 PC 에 남긴 로그인을 여기서 끊습니다. 이 기기는 유지됩니다.</p>
        </div>
        <button type="button" onClick={() => void revokeOthers()} disabled={revoking}>
          {revoking ? "종료 중…" : "다른 기기 로그아웃"}
        </button>
      </div>

      <div className="settings-danger-row">
        <div>
          <strong>로그아웃</strong>
          <p>{me?.email ?? ""} 계정에서 이 기기의 세션을 종료합니다.</p>
        </div>
        <button type="button" onClick={() => void signOut()}>
          로그아웃
        </button>
      </div>
    </div>
  );
}

/**
 * Browser notification state, said out loud. The permission prompt fired once
 * at first sign-in with no context; someone who clicked "차단" then had no way
 * to know why nothing ever popped up, or how to turn it back on.
 */
function NotificationPermissionRow() {
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(() =>
    isDesktopShell() || typeof Notification === "undefined"
      ? "unsupported"
      : Notification.permission,
  );
  if (permission === "unsupported") return null;

  const ask = async () => {
    try {
      const result = await Notification.requestPermission();
      setPermission(result);
    } catch {
      // Some browsers throw instead of resolving; the row keeps its state.
    }
  };

  return (
    <div className="settings-danger-row settings-notify-row">
      <div>
        <strong>브라우저 알림</strong>
        <p>
          {permission === "granted"
            ? "켜져 있습니다. 탭이 뒤에 있을 때 멘션·DM·새 메시지를 알려드립니다. 채널별로는 머리글의 종 버튼으로 조절하세요."
            : permission === "denied"
              ? "브라우저에서 차단되어 있습니다. 주소창 왼쪽의 사이트 정보(🔒) → 알림 → 허용으로 바꾸면 다시 켜집니다."
              : "아직 허용하지 않았습니다. 허용하면 탭이 뒤에 있을 때 멘션과 DM 을 놓치지 않습니다."}
        </p>
      </div>
      {permission === "default" ? (
        <button type="button" onClick={() => void ask()}>
          알림 허용
        </button>
      ) : null}
    </div>
  );
}

/**
 * What-to-do → how-to-do-it, one line each.
 *
 * This exists because a feature nobody can find is a feature that does not
 * exist. Every row names the exact control ("컴포저의 클립", "채널 머리글의
 * 톱니") rather than a concept, so the reader can put the dialog down and go
 * press the thing.
 */
function GuideList() {
  const rows: Array<{ want: string; how: string }> = [
    {
      want: "팀 채널에 들어가기",
      how: "사이드바 '채널' 옆의 돋보기(채널 둘러보기) — 공개 채널을 보고 '참여'를 누르면 지난 대화까지 모두 보입니다.",
    },
    {
      want: "누군가에게 바로 말하기 (DM)",
      how: "사이드바 '다이렉트 메시지' 옆의 + — 여러 명을 고르면 그룹 대화가 됩니다.",
    },
    {
      want: "사람 부르기 (멘션)",
      how: "@ 뒤에 이름이나 아이디를 치면 목록이 뜹니다. @김앨리스 처럼 이름 그대로 써도 멘션됩니다.",
    },
    {
      want: "채널·사람·앱·메시지·파일을 한 번에 찾기",
      how: "⌘K (Windows/Linux 는 Ctrl+K) — 목록에서 Enter 로 바로 이동하거나 파일을 내려받습니다.",
    },
    {
      want: "파일·스크린샷 보내기",
      how: "컴포저의 클립 버튼, 파일을 창에 끌어다 놓기, 또는 이미지를 복사해 ⌘V 로 붙여넣기.",
    },
    {
      want: "이미지 크게 보기",
      how: "첨부한 이미지는 대화에 미리보기로 보입니다. 클릭하면 크게 열립니다.",
    },
    {
      want: "메시지를 다른 채널/DM 에 전하기",
      how: "메시지에 마우스를 올리고 공유 버튼 — 출처가 인용으로 함께 갑니다.",
    },
    {
      want: "일정·할 일·결정 공유하기",
      how: "컴포저의 서식 버튼 — 일시·담당·기한이 늘 같은 자리에 오는 서식을 넣어줍니다.",
    },
    {
      want: "대화를 가리지 않고 답글 달기",
      how: "메시지의 답글 버튼 — 스레드가 오른쪽 열에 나란히 열립니다.",
    },
    {
      want: "채널 관리 (이름·주제·구성원·보관)",
      how: "채널 머리글 오른쪽의 톱니 버튼. 구성원 추가는 누구나, 이름 변경·제거·보관은 채널 관리자만 — 관리자는 같은 화면에서 '관리자로' 버튼으로 다른 사람에게 넘길 수 있습니다.",
    },
    {
      want: "채널 알림 끄기/켜기",
      how: "채널 머리글의 종 버튼. 음소거해도 나를 부르는 멘션은 셉니다.",
    },
    {
      want: "비밀번호 바꾸기 / 잊었을 때",
      how: "여기 계정 섹션에서 언제든 변경. 잊었다면 로그인 화면의 \"비밀번호를 잊으셨나요?\" — 이메일로 6자리 코드가 갑니다.",
    },
    {
      want: "AI 에이전트에게 일 시키기",
      how: "아래에서 프로바이더를 연결한 뒤, 왼쪽 도크의 에이전트 버튼을 누릅니다.",
    },
  ];
  return (
    <dl className="settings-guide">
      {rows.map((row) => (
        <div key={row.want}>
          <dt>{row.want}</dt>
          <dd>{row.how}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Connect, choose a model from the account, or disconnect. */
function ProviderSection() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  // The dialog can open before the agent panel ever has, so it fetches the
  // status itself rather than assuming the panel already did.
  useEffect(() => {
    if (!capabilities.computerControl) return;
    let cancelled = false;
    void agentHost
      .agentProviderStatus()
      .then((status) => {
        if (!cancelled) setProvider(status);
      })
      .catch(() => {
        if (!cancelled) setProvider(null);
      });
    return () => {
      cancelled = true;
    };
  }, [setProvider]);

  if (!capabilities.computerControl) {
    return (
      <div className="settings-note">
        <p>
          브라우저에서는 프로바이더를 연결할 수 없습니다. 키는 OS 키체인에만
          저장되고, 브라우저에는 키체인이 없습니다.
        </p>
        <p>
          지금은 <strong>가짜 프로바이더</strong>로 화면과 흐름만 확인할 수
          있습니다. 실제 모델을 쓰려면 데스크톱 앱에서 열어주세요.
        </p>
      </div>
    );
  }

  return provider?.connected ? (
    <ConnectedProvider />
  ) : (
    <ConnectForm />
  );
}

/** The state after a key is in the keychain: pick a model, or disconnect. */
function ConnectedProvider() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  const [models, setModels] = useState<ProviderModel[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ask the account which models it can run. Through the byte proxy, so this
  // is the same trust boundary as every agent request.
  useEffect(() => {
    let cancelled = false;
    void listProviderModels()
      .then((list) => {
        if (!cancelled) setModels(list);
      })
      .catch((caught) => {
        if (cancelled) return;
        setModelsError(
          caught instanceof Error ? caught.message : "모델 목록을 가져오지 못했습니다.",
        );
        setModels(DEFAULT_MODELS);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentModel = provider?.model ?? "";
  // The stored model is always choosable, even if the fetched list somehow
  // lacks it — a dropdown that silently switches your model is worse than one
  // with a stale entry.
  const options =
    models && models.some((entry) => entry.id === currentModel)
      ? models
      : [...(models ?? []), { id: currentModel, displayName: currentModel }].filter(
          (entry) => entry.id,
        );

  const changeModel = async (model: string) => {
    if (!model || model === currentModel) return;
    setBusy(true);
    setError(null);
    try {
      setProvider(await agentHost.agentProviderSetModel(model));
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "모델을 변경하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      setProvider(await agentHost.agentProviderDisconnect());
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "연결을 해제하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-provider">
      <div className="settings-provider-status">
        <strong>Anthropic</strong>
        <span>
          연결됨
          {provider?.key_fingerprint ? ` · 키 ····${provider.key_fingerprint}` : ""}
        </span>
        <button
          type="button"
          className="settings-disconnect"
          onClick={() => void disconnect()}
          disabled={busy}
        >
          연결 해제
        </button>
      </div>

      <label>
        모델
        <select
          value={currentModel}
          onChange={(event) => void changeModel(event.target.value)}
          disabled={busy || models === null}
        >
          {models === null ? (
            <option value={currentModel}>{currentModel || "불러오는 중…"}</option>
          ) : (
            options.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.displayName}
              </option>
            ))
          )}
        </select>
      </label>
      <p className="settings-hint">
        {modelsError
          ? `계정의 모델 목록을 가져오지 못해 기본 목록을 보여줍니다. (${modelsError})`
          : "연결된 계정에서 사용할 수 있는 모델 목록입니다."}
      </p>

      {error ? <p className="settings-error">{error}</p> : null}
      {provider?.last_error ? (
        <p className="settings-error">{provider.last_error}</p>
      ) : null}
    </div>
  );
}

/**
 * Connecting a model provider.
 *
 * The key is typed here and immediately handed to Rust, which puts it in the
 * OS keychain. It is never stored in this component, never in the store, and
 * never sent to the Llack server. Connecting performs one real validation
 * call, so an invalid key fails here rather than halfway through the user's
 * first question.
 */
function ConnectForm() {
  const provider = useAgent((state) => state.provider);
  const setProvider = useAgent((state) => state.setProvider);

  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(DEFAULT_MODELS[0]?.id ?? "claude-opus-5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const status = await agentHost.agentProviderConnect("anthropic", apiKey, model);
      setProvider(status);
      // Dropped from component state the moment Rust has it.
      setApiKey("");
    } catch (caught) {
      setError(
        caught && typeof caught === "object" && "message" in caught
          ? String((caught as { message: unknown }).message)
          : "연결하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="settings-provider" onSubmit={connect}>
      <ol className="settings-steps">
        <li>
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
            console.anthropic.com
          </a>
          에서 API 키를 만듭니다.
        </li>
        <li>아래에 키를 붙여넣고 연결을 누릅니다. 키가 맞는지 한 번 확인합니다.</li>
        <li>
          연결되면 계정에서 쓸 수 있는 모델 목록이 여기에 나타나고, 왼쪽 도크의
          에이전트 버튼으로 대화를 시작할 수 있습니다.
        </li>
      </ol>

      <label>
        모델
        <select value={model} onChange={(event) => setModel(event.target.value)}>
          {DEFAULT_MODELS.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.displayName}
            </option>
          ))}
        </select>
      </label>

      <label>
        API 키
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="sk-ant-…"
          autoComplete="off"
          spellCheck={false}
          required
        />
      </label>

      <p className="settings-hint">
        키는 이 기기의 OS 키체인에만 저장되며, Llack 서버로 전송되지 않습니다.
      </p>

      {error ? <p className="settings-error">{error}</p> : null}
      {provider?.last_error ? (
        <p className="settings-error">{provider.last_error}</p>
      ) : null}

      <button type="submit" className="settings-connect" disabled={busy || !apiKey}>
        {busy ? "확인 중…" : "연결"}
      </button>
    </form>
  );
}
