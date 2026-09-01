import { useState } from "react";

import { useApp } from "@/store/app";

export function SignIn({ defaultServerUrl }: { defaultServerUrl: string }) {
  const serverUrl = useApp((state) => state.serverUrl);
  const bootstrap = useApp((state) => state.bootstrap);
  const signIn = useApp((state) => state.signIn);
  const signUp = useApp((state) => state.signUp);
  const reportError = useApp((state) => state.reportError);

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [server, setServer] = useState(serverUrl || defaultServerUrl);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);

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
      reportError(error);
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

        <button type="submit" className="signin-submit" disabled={busy}>
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
