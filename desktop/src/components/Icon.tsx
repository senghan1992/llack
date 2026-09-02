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

/**
 * The agent.
 *
 * Not a robot head and not a chat bubble: the first is a cliché that promises
 * autonomy this agent does not have, and the second is already taken by the
 * transcript beside it. Two sparks — the same figure the rest of the industry
 * settled on for "a model did this" — drawn on this set's grid and stroke so it
 * belongs to the same hand as the bell and the paperclip.
 */
export function IconAgent(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6.6 2.1c.5 2.9 1.5 3.9 4.4 4.4-2.9.5-3.9 1.5-4.4 4.4-.5-2.9-1.5-3.9-4.4-4.4 2.9-.5 3.9-1.5 4.4-4.4Z" />
      <path d="M12.3 9.6c.25 1.5.75 2 2.2 2.25-1.45.25-1.95.75-2.2 2.2-.25-1.45-.75-1.95-2.2-2.2 1.45-.25 1.95-.75 2.2-2.25Z" />
    </Svg>
  );
}

/**
 * Stop.
 *
 * A filled square, not an ✕. The ✕ in this app means "close this"; stopping a
 * turn in flight is a different act, and the transport control everybody
 * already recognises costs nothing to reuse.
 */
export function IconStop(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="8" height="8" rx="0.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** A check. Two strokes, one joint, on the same grid as the rest. */
export function IconCheck(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.2 8.6 6.1 11.5 12.8 4.8" />
    </Svg>
  );
}

/** Settings. A gear reduced to hub and spokes, which is all 16px can carry. */
/**
 * A cogwheel: a toothed ring around a hub. The previous drawing was a circle
 * with eight detached rays — which is the sun, i.e. a light-theme toggle, and
 * it was read as exactly that. Teeth must touch the ring they turn.
 */
export function IconGear(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7.20 3.88L7.31 1.44L8.69 1.44L8.80 3.88L10.35 4.52L12.15 2.87L13.13 3.85L11.48 5.65L12.12 7.20L14.56 7.31L14.56 8.69L12.12 8.80L11.48 10.35L13.13 12.15L12.15 13.13L10.35 11.48L8.80 12.12L8.69 14.56L7.31 14.56L7.20 12.12L5.65 11.48L3.85 13.13L2.87 12.15L4.52 10.35L3.88 8.80L1.44 8.69L1.44 7.31L3.88 7.20L4.52 5.65L2.87 3.85L3.85 2.87L5.65 4.52Z" />
      <circle cx="8" cy="8" r="1.9" />
    </Svg>
  );
}

/** A globe: the meridian ellipse over the equator line, inside the circle. */
export function IconGlobe(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="5.9" />
      <ellipse cx="8" cy="8" rx="2.7" ry="5.9" />
      <path d="M2.3 8h11.4" />
    </Svg>
  );
}

/** Reload: a broken circle with an arrowhead at the break. */
export function IconRefresh(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13.4 8a5.4 5.4 0 1 1-1.6-3.8" />
      <path d="M13.6 1.9v2.5h-2.5" />
    </Svg>
  );
}

/**
 * Expand the rail. Two chevrons pointing at the space the labels will take;
 * the caller flips it with a transform when the rail is already expanded.
 */
export function IconChevrons(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4.2 4.4L7.8 8l-3.6 3.6M8.6 4.4L12.2 8l-3.6 3.6" />
    </Svg>
  );
}

/**
 * Share a message somewhere else: the box it lives in, and an arrow leaving it.
 * Not the reply arrow — replying stays in place, sharing goes elsewhere.
 */
export function IconShare(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12.8 8.8v3.4a1 1 0 0 1-1 1H4.2a1 1 0 0 1-1-1V4.6a1 1 0 0 1 1-1h3.4" />
      <path d="M10 2.9h3.1V6M13.1 2.9L8.4 7.6" />
    </Svg>
  );
}

/** A document with ruled lines: the composer's message templates. */
export function IconTemplate(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3.2" y="2.6" width="9.6" height="10.8" rx="1" />
      <path d="M5.6 6h4.8M5.6 8.4h4.8M5.6 10.8h2.8" />
    </Svg>
  );
}
