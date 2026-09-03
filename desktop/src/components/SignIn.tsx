import { useState } from "react";

import { demoUser, isDemoBuild } from "@/lib/demo";
import { api } from "@/lib/ipc";
import { pendingInviteToken } from "@/lib/invite";
import { useApp } from "@/store/app";

export function SignIn({ defaultServerUrl }: { defaultServerUrl: string }) {
  const serverUrl = useApp((state) => state.serverUrl);
  const bootstrap = useApp((state) => state.bootstrap);
  const signIn = useApp((state) => state.signIn);
  const signUp = useApp((state) => state.signUp);
  const reportError = useApp((state) => state.reportError);

  const [mode, setMode] = useState<"signin" | "signup" | "forgot">("signin");
  // The forgot flow has two steps: ask for a code, then redeem it.
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
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
    mode === "forgot"
      ? email.trim().length > 0 &&
        (!codeSent || (code.trim().length >= 4 && password.length >= 10))
      : email.trim().length > 0 &&
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
      if (mode === "forgot") {
        if (!codeSent) {
          await api.forgotPassword(email.trim());
          setCodeSent(true);
          useApp.setState({
            banner: {
              kind: "info",
              message:
                "가입된 이메일이라면 재설정 코드를 보냈습니다. 받은 편지함을 확인해주세요.",
            },
          });
        } else {
          await api.resetPassword(email.trim(), code.trim(), password);
          setMode("signin");
          setCodeSent(false);
          setCode("");
          setPassword("");
          useApp.setState({
            banner: {
              kind: "info",
              message: "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요.",
            },
          });
        }
        return;
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
      const translations: Record<string, string> = {
        invalid_credentials: "이메일 또는 비밀번호가 올바르지 않습니다.",
        rate_limited: "시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
        email_taken: "이미 가입된 이메일입니다. 로그인해주세요.",
        invite_required:
          "이 서버는 초대로만 가입할 수 있습니다. 관리자에게 초대 링크를 요청해주세요.",
        invite_email_mismatch:
          "초대장이 다른 이메일로 발급되었습니다. 초대받은 주소로 가입해주세요.",
        invite_used: "이 초대 링크는 이미 사용되었습니다.",
        invite_expired: "초대 링크가 만료되었거나 회수되었습니다.",
        invite_invalid: "초대 링크가 올바르지 않습니다.",
        reset_code_invalid: "코드가 올바르지 않거나 만료되었습니다. 코드를 다시 요청해주세요.",
      };
      const message = translations[parsed.code];
      if (message) {
        useApp.setState({ banner: { kind: "error", message } });
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

        {mode === "forgot" && codeSent ? (
          <label>
            재설정 코드 (이메일로 받은 6자리)
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              placeholder="123456"
              autoComplete="one-time-code"
              maxLength={12}
              required
            />
          </label>
        ) : null}

        {mode !== "forgot" || codeSent ? (
          <label>
            {mode === "forgot" || mode === "signup" ? (
              mode === "forgot" ? "새 비밀번호" : "비밀번호"
            ) : (
              "비밀번호"
            )}
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              required
              minLength={mode === "signin" ? 1 : 10}
            />
            {mode !== "signin" ? (
              <small>10자 이상으로 설정해주세요.</small>
            ) : null}
          </label>
        ) : null}

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
          {busy
            ? "잠시만요…"
            : mode === "signin"
              ? "로그인"
              : mode === "signup"
                ? "계정 만들기"
                : codeSent
                  ? "비밀번호 재설정"
                  : "재설정 코드 보내기"}
        </button>

        <button
          type="button"
          className="signin-switch"
          onClick={() => {
            setCodeSent(false);
            setCode("");
            setMode(mode === "signin" ? "signup" : "signin");
          }}
        >
          {mode === "signin" ? "계정이 없으신가요? 만들기" : "이미 계정이 있습니다"}
        </button>

        {mode === "signin" && !demo ? (
          <button
            type="button"
            className="signin-switch"
            onClick={() => {
              setMode("forgot");
              setCodeSent(false);
              setCode("");
              setPassword("");
            }}
          >
            비밀번호를 잊으셨나요?
          </button>
        ) : null}

        {mode === "forgot" ? (
          <p className="signin-demo">
            가입한 이메일로 6자리 코드를 보내드립니다. 코드는 15분 동안
            유효합니다.{codeSent ? " 메일이 오지 않으면 관리자에게 임시 비밀번호 발급을 요청할 수도 있습니다." : ""}
          </p>
        ) : null}
      </form>
    </div>
  );
}
