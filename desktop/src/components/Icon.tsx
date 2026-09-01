/**
 * The icon set, drawn rather than borrowed from the emoji table.
 *
 * One 16-unit grid, one 1.5-unit stroke, round caps and joins, `currentColor`
 * throughout, so an icon inherits the ink of whatever row it sits in and the
 * whole set reads as one hand. Emoji were the previous stand-in; they carry
 * their own colour and their own weight, and on a surface where one colour has
 * one meaning that is a palette leak.
 *
 * A reaction is not in here: the emoji a person picked is content, not
 * iconography, and it keeps its own glyph.
 */

interface IconProps {
  /** Matches the surrounding text size by default. */
  size?: number;
  className?: string;
}

const base = {
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

function Svg({ size = 16, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg {...base} width={size} height={size} className={className}>
      {children}
    </svg>
  );
}

export function IconBell(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4.2 6.6a3.8 3.8 0 0 1 7.6 0v2.5l1.1 2.1H3.1l1.1-2.1V6.6Z" />
      <path d="M6.4 13.2a1.7 1.7 0 0 0 3.2 0" />
    </Svg>
  );
}

export function IconBellOff(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4.2 6.6a3.8 3.8 0 0 1 7.6 0v2.5l1.1 2.1H3.1l1.1-2.1V6.6Z" />
      <path d="M6.4 13.2a1.7 1.7 0 0 0 3.2 0" />
      <path d="M2.4 2.4l11.2 11.2" />
    </Svg>
  );
}

export function IconLock(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3.4" y="7" width="9.2" height="6.4" rx="1" />
      <path d="M5.7 7V5.2a2.3 2.3 0 0 1 4.6 0V7" />
    </Svg>
  );
}

export function IconPaperclip(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M11.6 7.3l-4.3 4.3a2.1 2.1 0 0 1-3-3l5-5a3.2 3.2 0 0 1 4.5 4.5l-5 5" />
    </Svg>
  );
}

export function IconPin(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 9.6V14" />
      <path d="M4.6 6.2h6.8l-.9 3.4H5.5L4.6 6.2Z" />
      <path d="M6.1 6.2V2.6h3.8v3.6" />
    </Svg>
  );
}

export function IconClose(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </Svg>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 3.4v9.2M3.4 8h9.2" />
    </Svg>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7.2" cy="7.2" r="3.8" />
      <path d="M10.1 10.1l3 3" />
    </Svg>
  );
}

export function IconFile(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 2.6h4.6L12 6v7.4H4V2.6Z" />
      <path d="M8.4 2.6V6H12" />
    </Svg>
  );
}

export function IconImage(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.8" y="3.4" width="10.4" height="9.2" rx="1" />
      <path d="M2.8 10.4l2.9-2.5 3 2.4 1.9-1.6 2.6 2.1" />
      <circle cx="6" cy="6.4" r="0.9" />
    </Svg>
  );
}

export function IconArrowDown(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 3.2v9.6M4.4 9.2L8 12.8l3.6-3.6" />
    </Svg>
  );
}

export function IconSend(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.6 8h10.8M9.4 4l4 4-4 4" />
    </Svg>
  );
}

export function IconReply(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.8 12.4V10a3.2 3.2 0 0 1 3.2-3.2h6.4" />
      <path d="M9.8 3.8l2.9 3-2.9 3" />
    </Svg>
  );
}

export function IconEdit(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8.4 3.9l3.7 3.7-5.5 5.5H2.9V9.4l5.5-5.5Z" />
      <path d="M7.2 5.1l3.7 3.7" />
    </Svg>
  );
}

export function IconTrash(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.2 5h9.6" />
      <path d="M4.5 5v7.6c0 .5.4.9.9.9h5.2c.5 0 .9-.4.9-.9V5" />
      <path d="M6.4 5V3.4h3.2V5" />
    </Svg>
  );
}

/**
 * The mark before a channel name.
 *
 * `#` sets as a character with the label so it shares its metrics; a private
 * channel takes the drawn lock, because no character reads as "private" at
 * 13px. Both occupy the same fixed cell so the label column never shifts.
 */
export function ChannelMark({ kind }: { kind: string }) {
  if (kind === "private") {
    return (
      <span className="channel-mark" aria-label="비공개 채널">
        <IconLock size={12} />
      </span>
    );
  }
  if (kind === "dm" || kind === "group_dm") {
    return null;
  }
  return (
    <span className="channel-mark" aria-hidden="true">
      #
    </span>
  );
}
