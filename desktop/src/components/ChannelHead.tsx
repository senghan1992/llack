import { useState } from "react";
import {
  FolderKanban,
  Hash,
  Lock,
  Maximize2,
  Menu as MenuIcon,
  Pin,
  Search,
  SquareDashed,
  UserPlus,
  Users,
} from "lucide-react";
import { Avatar } from "./Avatar";
import { Menu } from "./Menu";
import type { Channel, Member, Presence, Project } from "../lib/types";

interface Props {
  channel: Channel | null;
  members: Member[];
  presence: Record<string, Presence>;
  /** The project this room belongs to, when it belongs to one. */
  project: Project | null;
  onOpenProject: () => void;
  onOpenSearch: () => void;
  onOpenPeople: () => void;
  onAddPeople: () => void;
  onOpenPins: () => void;
  onToggleRail: () => void;
  onOpenSettings: () => void;
  /** Leave the workspace with nothing selected. A room window is one
   *  conversation, so it has nothing to clear and gets no key. */
  onClearScreen?: () => void;
  /** The board sits beside this conversation — the conversation may take
   *  the whole window instead. */
  onExpandChat?: () => void;
  /** A narrow pane — the bar keeps only what it needs to. */
  compact?: boolean;
}

export function ChannelHead({
  channel,
  members,
  presence,
  project,
  onOpenProject,
  onOpenSearch,
  onOpenPeople,
  onAddPeople,
  onOpenPins,
  onToggleRail,
  onOpenSettings,
  onClearScreen,
  onExpandChat,
  compact = false,
}: Props) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const faces = members.slice(0, compact ? 2 : 5);

  return (
    <header className={`head${compact ? " head--compact" : ""}`}>
      <div className="head__inner">
      <button
        type="button"
        className="iconbtn head__menu"
        aria-label="채널 목록 열기"
        onClick={onToggleRail}
      >
        <MenuIcon size={17} aria-hidden="true" />
      </button>
      {channel?.is_private ? (
        <span className="head__glyph" aria-hidden="true">
          <Lock size={14} />
        </span>
      ) : (
        <span className="head__glyph" aria-hidden="true">
          <Hash size={15} />
        </span>
      )}

      <div className="head__id">
        <button type="button" className="head__name" onClick={onOpenSettings}>
          {channel?.name ?? "선택된 채널 없음"}
        </button>
      </div>

      {channel?.topic ? <span className="head__topic">{channel.topic}</span> : null}

      <div className="head__actions">
        <div className="head__tools">
          {project ? (
            <button
              type="button"
              className="head__project"
              onClick={onOpenProject}
              aria-label={`프로젝트 ${project.name} 열기`}
            >
              <FolderKanban size={13} aria-hidden="true" />
              <span>{project.name}</span>
            </button>
          ) : null}
          <button
            type="button"
            className="iconbtn"
            aria-label="메시지 검색"
            title="메시지 검색"
            onClick={onOpenSearch}
          >
            <Search size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="iconbtn"
            aria-label="고정된 메시지"
            onClick={onOpenPins}
          >
            <Pin size={16} aria-hidden="true" />
          </button>
          {onExpandChat ? (
            <button
              type="button"
              className="iconbtn"
              aria-label="대화를 전체 화면으로"
              title="대화를 전체 화면으로"
              onClick={onExpandChat}
            >
              <Maximize2 size={16} aria-hidden="true" />
            </button>
          ) : null}
          {onClearScreen ? (
            <button
              type="button"
              className="iconbtn"
              aria-label="화면 비우기"
              title="화면 비우기"
              onClick={onClearScreen}
            >
              <SquareDashed size={16} aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <button
          type="button"
          className="faces"
          aria-label={`멤버 ${members.length}명 보기`}
          onClick={(event) => setAnchor(event.currentTarget)}
        >
          {faces.map((member) => (
            <Avatar
              key={member.user.id}
              user={member.user}
              size="sm"
              presence={presence[member.user.id] ?? member.user.presence}
            />
          ))}
          <span className="faces__more">{members.length}명</span>
        </button>
      </div>

      {anchor ? (
        <Menu anchor={anchor} onClose={() => setAnchor(null)} align="right" width={248}>
          <div className="menu__label">멤버 {members.length}명</div>
          {members.map((member) => (
            <button
              key={member.user.id}
              type="button"
              className="menu__item"
              onClick={() => {
                setAnchor(null);
                onOpenPeople();
              }}
            >
              <Avatar
                user={member.user}
                size="sm"
                presence={presence[member.user.id] ?? member.user.presence}
              />
              <span className="u-grow u-truncate">{member.user.name}</span>
              <span className="u-tiny u-muted">{member.user.title}</span>
            </button>
          ))}
          <div className="menu__sep" />
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setAnchor(null);
              onAddPeople();
            }}
          >
            <UserPlus size={14} aria-hidden="true" />
            사람 추가
          </button>
          <button
            type="button"
            className="menu__item"
            onClick={() => {
              setAnchor(null);
              onOpenPeople();
            }}
          >
            <Users size={14} aria-hidden="true" />
            멤버 전체 보기
          </button>
        </Menu>
      ) : null}
      </div>
    </header>
  );
}
