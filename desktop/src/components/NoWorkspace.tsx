/**
 * The screen for an account that belongs to no workspace yet.
 *
 * This used to be a dead pane ("채널을 선택하세요" over an empty sidebar) —
 * a fresh sign-up had nowhere to go and nothing telling them why. Two honest
 * ways forward: come back through an invite link, or found a workspace of
 * your own (the caller becomes owner, #general/#random are seeded).
 */

import { useState } from "react";

import { api } from "@/lib/ipc";
import { useApp } from "@/store/app";

/** ASCII slug from a (possibly Korean) name; random suffix keeps it unique. */
function slugFor(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const suffix = Math.random().toString(36).slice(2, 6);
  return base ? `${base}-${suffix}` : `ws-${suffix}`;
}

export function NoWorkspace() {
  const me = useApp((state) => state.me);
  const signOut = useApp((state) => state.signOut);
  const loadWorkspaces = useApp((state) => state.loadWorkspaces);
  const reportError = useApp((state) => state.reportError);

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await api.createWorkspace(trimmed, slugFor(trimmed));
      await loadWorkspaces();
    } catch (error) {
      reportError(error, "워크스페이스를 만들지 못했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="no-workspace">
      <div className="no-workspace-card">
        <h1>어서 오세요{me?.display_name ? `, ${me.display_name} 님` : ""}</h1>
        <p>
          아직 참여한 워크스페이스가 없습니다. 팀에 합류하려면 관리자에게
          <strong> 초대 링크</strong>를 요청해 그 링크로 다시 접속해주세요 —
          로그인만 하면 자동으로 참여됩니다.
        </p>

        <div className="no-workspace-divider">또는 직접 시작하기</div>

        <div className="linkapp-row">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="워크스페이스 이름 (예: 아크메 주식회사)"
            aria-label="워크스페이스 이름"
            maxLength={80}
            onKeyDown={(event) => {
              if (event.key === "Enter") void create();
            }}
          />
          <button
            type="button"
            className="settings-primary"
            onClick={() => void create()}
            disabled={busy || !name.trim()}
          >
            {busy ? "만드는 중…" : "워크스페이스 만들기"}
          </button>
        </div>
        <p className="no-workspace-hint">
          만드는 사람이 소유자가 되고, #general 과 #random 채널이 함께
          만들어집니다.
        </p>

        <button type="button" className="no-workspace-signout" onClick={() => void signOut()}>
          다른 계정으로 로그인
        </button>
      </div>
    </div>
  );
}
