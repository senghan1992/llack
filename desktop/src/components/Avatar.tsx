import { colorForId, initials } from "@/lib/format";
import type { Presence } from "@/lib/types";

interface AvatarProps {
  id: string;
  name: string;
  avatarUrl?: string | null;
  size?: number;
  presence?: Presence;
  isBot?: boolean;
}

export function Avatar({ id, name, avatarUrl, size = 36, presence, isBot }: AvatarProps) {
  return (
    <span className="avatar" style={{ width: size, height: size }}>
      {avatarUrl ? (
        <img src={avatarUrl} alt="" width={size} height={size} />
      ) : (
        <span
          className="avatar-fallback"
          style={{
            background: colorForId(id),
            fontSize: Math.max(11, size * 0.4),
            borderRadius: isBot ? size * 0.25 : size * 0.28,
          }}
        >
          {initials(name)}
        </span>
      )}
      {presence && presence !== "offline" ? (
        <span
          className={`presence-dot presence-${presence}`}
          title={presenceLabel(presence)}
          aria-label={presenceLabel(presence)}
        />
      ) : null}
    </span>
  );
}

function presenceLabel(presence: Presence): string {
  switch (presence) {
    case "active":
      return "온라인";
    case "away":
      return "자리 비움";
    case "dnd":
      return "방해 금지";
    default:
      return "오프라인";
  }
}
