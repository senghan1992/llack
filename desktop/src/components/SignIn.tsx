import { useState } from "react";

import { demoUser, isDemoBuild } from "@/lib/demo";
import { pendingInviteToken } from "@/lib/invite";
import { useApp } from "@/store/app";

export function SignIn({ defaultServerUrl }: { defaultServerUrl: string }) {
  const serverUrl = useApp((state) => state.serverUrl);
  const bootstrap = useApp((state) => state.bootstrap);
  const signIn = useApp((state) => state.signIn);
  const signUp = useApp((state) => state.signUp);
  const reportError = useApp((state) => state.reportError);

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [server, setServer] = useState(serverUrl || defaultServerUrl);
  /*
   * The demo build prefills and accepts anything.
   *
   * The screen is still shown rather than skipped: it is part of the product,
   * and a walkthrough that starts already signed in hides the first thing a
   * reviewer sees on their own machine. One click gets past it.
   */
  const demo = isDemoBuild();
  const [email, setEmail] = useState(demo ? demoUser.email : "");
  const [password, setPassword] = useState(demo ? "demo" : "");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);

  const canSubmit =
    email.trim().length > 0 &&
    password.length > 0 &&
    (mode === "signin" || displayName.trim().length > 0);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      // Re-point at the server first: the user may have edited the address.
      if (server.trim() !== serverUrl) {
        await bootstrap(server.trim());
      }
      if (mode === "signin") {
        await signIn(email.trim(), password);
      } else {
        await signUp(email.trim(), password, displayName.trim());
      }
    } catch (error) {
      // The server's auth messages are English; the person reading them is
      // not. Translate by code, and keep not disclosing which field was wrong.
      const parsed = reportError(error);
      if (parsed.code === "invalid_credentials") {
        useApp.setState({
          banner: {
            kind: "error",
            message: "이메일 또는 비밀번호가 올바르지 않습니다.",
          },
        });
      } else if (parsed.code === "rate_limited") {
        useApp.setState({
          banner: {
            kind: "error",
            message: "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
          },
        });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="signin">
      <form className="signin-plate" onSubmit={submit}>
        <header className="signin-masthead">
          <h1 className="signin-title">Llack</h1>
          <p className="signin-subtitle">사내 협업 OS</p>
        </header>

        {pendingInviteToken() ? (
          <p className="signin-demo">
            워크스페이스 초대 링크로 오셨습니다. 로그인하거나 계정을 만들면
            초대가 자동으로 수락됩니다.
          </p>
        ) : null}

        {demo ? (
          <p className="signin-demo">
            둘러보기용 데모입니다. 서버 없이 이 페이지 안에서 동작하고, 아무
            비밀번호나 넣어도 들어갑니다. 입력한 내용은 어디에도 저장되지
            않습니다.
          </p>
        ) : (
          <label>
            서버 주소
            <input
              value={server}
              onChange={(event) => setServer(event.target.value)}
              placeholder="https://llack.example.com"
              autoComplete="url"
              required
            />
          </label>
        )}

        {mode === "signup" ? (
          <label>
            이름
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="김앨리스"
              autoComplete="name"
              required
              maxLength={120}
            />
          </label>
        ) : null}

        <label>
          이메일
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
        </label>

        <label>
          비밀번호
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            required
            minLength={mode === "signup" ? 10 : 1}
          />
          {mode === "signup" ? (
            <small>10자 이상으로 설정해주세요.</small>
          ) : null}
        </label>

        {/*
          Disabled until the form can actually be submitted.
          
          It was only disabled while a request was in flight, so with an empty
          email it rendered as a live primary action that did nothing when
          clicked — the browser's `required` check blocks the submit silently.
          A primary button that looks available and is not is the single most
          common place an interface loses a person's trust.
        */}
        <button
          type="submit"
          className="signin-submit"
          disabled={busy || !canSubmit}
        >
          {busy ? "잠시만요…" : mode === "signin" ? "로그인" : "계정 만들기"}
        </button>

        <button
          type="button"
          className="signin-switch"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
        >
          {mode === "signin" ? "계정이 없으신가요? 만들기" : "이미 계정이 있습니다"}
        </button>
      </form>
    </div>
  );
}
