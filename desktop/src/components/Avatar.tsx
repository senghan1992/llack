import { colorFor, initials } from "../lib/format";
import { readableOn } from "../lib/color";
import { presenceLabel } from "../lib/presence";
import type { Presence, User } from "../lib/types";

interface Props {
  user: Pick<User, "id" | "name" | "avatar_color">;
  size?: "sm" | "md" | "lg";
  presence?: Presence | null;
  title?: string;
}

export function Avatar({ user, size = "md", presence, title }: Props) {
  // The tile may be any colour the person (or an older record) carries, so
  // it is darkened here until the initials on it are certainly readable.
  const color = readableOn(user.avatar_color || colorFor(user.id));
  const classes = ["avatar"];
  if (size === "sm") classes.push("avatar--sm");
  if (size === "lg") classes.push("avatar--lg");

  return (
    <span className="avatar-wrap u-row u-row--center" title={title ?? user.name}>
      <span className={classes.join(" ")} style={{ ["--avatar-bg" as string]: color }} aria-hidden="true">
        {initials(user.name)}
      </span>
      {presence ? (
        <span
          className={`presence presence--${presence}`}
          role="img"
          aria-label={presenceLabel(presence)}
        />
      ) : null}
    </span>
  );
}
