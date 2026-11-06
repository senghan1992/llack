import { useState } from "react";
import { useStore } from "../store/useStore";
import { ApiError, friendlyMessage } from "../lib/api";

type Mode = "signin" | "signup";

/** 초대 코드는 없는 코드일 때가 많다. */
function inviteMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return "초대 코드를 찾을 수 없습니다.";
  return `초대 코드를 받지 못했습니다: ${friendlyMessage(error, "초대 코드를 받지 못했습니다")}`;
}

export function Gate() {
  const signIn = useStore((s) => s.signIn);
  const signUp = useStore((s) => s.signUp);
  const acceptInvite = useStore((s) => s.acceptInvite);
  const bootError = useStore((s) => s.bootError);
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") {
        await signIn(email.trim(), password);
      } else {
        await signUp({
          email: email.trim(),
          password,
          name: name.trim(),
          workspace_name: workspace.trim(),
        });
      }
      if (invite.trim()) {
        try {
          await acceptInvite(invite);
        } catch (err) {
          setError(inviteMessage(err));
          return;
        }
      }
    } catch (err) {
      setError(friendlyMessage(err, "로그인하지 못했습니다"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gate">
      <main className="gate__form">
        <div className="gate__inner">
          <div className="gate__brand">
            <span className="gate__mark" aria-hidden="true">
              L
            </span>
            <span className="gate__wordmark">Llack</span>
          </div>

          <h1 className="gate__title">
            {mode === "signin" ? "다시 만나 반가워요" : "새 워크스페이스를 시작해요"}
          </h1>
          <p className="gate__lead">
            {mode === "signin"
              ? "이메일과 비밀번호로 들어가세요."
              : "팀 이름을 정하면 그 이름으로 워크스페이스가 열립니다."}
          </p>

          <form className="gate__form-fields u-mt-2" onSubmit={submit}>
            {bootError ? (
              <p className="banner banner--error" role="alert">
                {bootError}
              </p>
            ) : null}

            {error ? (
              <p className="banner banner--error" role="alert">
                {error}
              </p>
            ) : null}

            {mode === "signup" ? (
              <>
                <div className="field">
                  <label className="field__label" htmlFor="gate-name">
                    이름
                  </label>
                  <input
                    id="gate-name"
                    className="field__input"
                    value={name}
                    autoComplete="name"
                    placeholder="예: 김현진"
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="gate-workspace">
                    팀 이름
                  </label>
                  <input
                    id="gate-workspace"
                    className="field__input"
                    value={workspace}
                    autoComplete="organization"
                    placeholder="예: 한빛"
                    onChange={(event) => setWorkspace(event.target.value)}
                    required
                  />
                </div>
              </>
            ) : null}

            <div className="field">
              <label className="field__label" htmlFor="gate-email">
                이메일
              </label>
              <input
                id="gate-email"
                className="field__input"
                type="email"
                value={email}
                autoComplete="email"
                placeholder="name@company.com"
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="gate-password">
                비밀번호
              </label>
              <input
                id="gate-password"
                className="field__input"
                type="password"
                value={password}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                placeholder={mode === "signup" ? "8자 이상" : ""}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === "signup" ? 8 : undefined}
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor="gate-invite">
                초대 코드
              </label>
              <input
                id="gate-invite"
                className="field__input"
                value={invite}
                autoComplete="off"
                placeholder="있으면 입력하세요"
                onChange={(event) => setInvite(event.target.value)}
              />
              <p className="field__hint">이미 만들어진 팀에 초대장으로 들어갈 때만 필요합니다.</p>
            </div>

            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? "확인하는 중" : mode === "signin" ? "들어가기" : "워크스페이스 만들기"}
            </button>
          </form>

          <p className="gate__switch">
            {mode === "signin" ? "계정이 없나요?" : "이미 계정이 있나요?"}{" "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "signin" ? "signup" : "signin");
                setError(null);
              }}
            >
              {mode === "signin" ? "워크스페이스 만들기" : "들어가기"}
            </button>
          </p>
        </div>
      </main>

      <aside className="gate__aside" aria-hidden="true">
        <p className="gate__quote">팀의 하루가 모이는 한 곳.</p>
        <p className="gate__attrib">채널과 직접 메시지, 스레드를 한 화면에서.</p>
        <div className="u-mt-6 u-row u-gap-3">
          <span className="kbd kbd--on-ink">⌘K</span>
          <span className="u-small gate__note">채널과 사람으로 바로 이동</span>
        </div>
      </aside>
    </div>
  );
}
