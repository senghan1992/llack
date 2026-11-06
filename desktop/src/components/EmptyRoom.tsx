import { Menu as MenuIcon, MessageSquareDashed } from "lucide-react";

interface Props {
  /** The rail is an overlay on a narrow window, and the cleared screen has no
   *  header to open it from — the key stands in the pane's corner instead. */
  onOpenRail?: () => void;
}

/**
 * The main pane with nothing in it — the screen the reader cleared for a
 * meeting. It is a designed state, not a blank page: the same empty state
 * the app uses everywhere else, with the mark, the title and the sentence.
 */
export function EmptyRoom({ onOpenRail }: Props) {
  return (
    <div className="empty empty--room">
      {onOpenRail ? (
        <button
          type="button"
          className="iconbtn head__menu empty__rail"
          aria-label="채널 목록 열기"
          title="채널 목록 열기"
          onClick={onOpenRail}
        >
          <MenuIcon size={17} aria-hidden="true" />
        </button>
      ) : null}
      <span className="empty__mark" aria-hidden="true">
        <MessageSquareDashed size={20} />
      </span>
      <p className="empty__title">열린 대화가 없습니다</p>
      <p className="empty__text">
        회의나 화면 공유를 위해 비워 둔 화면입니다. 레일에서 방을 고르면 대화가 다시 열립니다.
      </p>
      <p className="empty__hint">
        <span className="kbd">⌘K</span>
        <span>로 방과 사람을 찾을 수 있습니다.</span>
      </p>
    </div>
  );
}
