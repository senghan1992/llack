/**
 * 첫 진입 안내 — the one card a newcomer needed and never got.
 *
 * Someone who joins by invite lands in #general with no idea that #q3-런치
 * exists, that the kick-off is pinned, or that the file they were told about
 * is a click away. This says so once per workspace, offers the three doors
 * (browse channels, activity, files), and gets out of the way for good when
 * dismissed. It never shows to the person who created the workspace — they
 * know where everything is.
 */

import { useState } from "react";

import { useApp } from "@/store/app";

import { BrowseChannels } from "./BrowseChannels";
import { IconActivity, IconClose, IconFolder, IconSearch } from "./Icon";

function storageKey(workspaceId: string): string {
  return `llack.onboarded:${workspaceId}`;
}

export function FirstRunCard() {
  const workspace = useApp((state) =>
    state.workspaces.find((candidate) => candidate.id === state.activeWorkspaceId),
  );
  const channelCount = useApp((state) => state.channels.length);
  const setMainView = useApp((state) => state.setMainView);
  const setSettings = useApp((state) => state.setSettings);

  const [browsing, setBrowsing] = useState(false);
  // Re-read per workspace on every render: the workspace list arrives after
  // the first paint, and a flag computed once at mount would have been decided
  // before there was a workspace to decide about.
  const [dismissedNow, setDismissedNow] = useState<string | null>(null);
  const dismissed = (() => {
    if (!workspace) return true;
    if (dismissedNow === workspace.id) return true;
    try {
      return window.localStorage.getItem(storageKey(workspace.id)) === "1";
    } catch {
      return true;
    }
  })();

  if (!workspace || dismissed) return null;
  // The founder of a one-person workspace has nothing to be shown around.
  if (workspace.my_role === "owner" && workspace.member_count <= 1) return null;

  const dismiss = () => {
    setDismissedNow(workspace.id);
    try {
      window.localStorage.setItem(storageKey(workspace.id), "1");
    } catch {
      // Private browsing: the card returns next time, which is harmless.
    }
  };

  return (
    <div className="first-run" role="region" aria-label="시작 안내">
      <div className="first-run-text">
        <strong>{workspace.name} 에 오신 것을 환영합니다.</strong>
        <p>
          {channelCount <= 1
            ? "아직 팀 채널에 들어가 있지 않습니다. 먼저 채널을 둘러보고 참여하세요 — 지난 대화까지 모두 보입니다."
            : "채널 머리글의 📌 에 팀이 고정해 둔 것이 있고, 나를 부른 메시지는 '활동'에, 파일은 '파일'에 모입니다."}
        </p>
      </div>
      <div className="first-run-actions">
        <button type="button" className="settings-primary" onClick={() => setBrowsing(true)}>
          <IconSearch size={13} /> 채널 둘러보기
        </button>
        <button type="button" className="settings-secondary" onClick={() => setMainView("activity")}>
          <IconActivity size={13} /> 활동
        </button>
        <button type="button" className="settings-secondary" onClick={() => setMainView("files")}>
          <IconFolder size={13} /> 파일
        </button>
        <button type="button" className="settings-secondary" onClick={() => setSettings(true)}>
          프로필 사진 올리기
        </button>
      </div>
      <button type="button" className="first-run-close" onClick={dismiss} aria-label="안내 닫기" title="다시 보지 않기">
        <IconClose size={12} />
      </button>
      {browsing ? <BrowseChannels onClose={() => setBrowsing(false)} /> : null}
    </div>
  );
}
