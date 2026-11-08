import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  /** The mark the tip belongs to — the element under the pointer. */
  anchor: HTMLElement | null;
  children: ReactNode;
}

/** How close to the top of the window the tip turns over. */
const EDGE = 120;

/** The gutter the tip keeps from the edge of the window. */
const GUTTER = 8;

/**
 * The card that names a mark on the chart.
 *
 * It is the ink band — the same strip the names of a reaction ride on —
 * drawn in a portal so the dialog's own scroll never cuts it. It sits
 * above the mark it belongs to, and turns below when the mark stands too
 * near the top of the window for there to be room above it.
 *
 * It is a hover tip, not a menu: it takes no pointer of its own, so the
 * pointer can travel from the mark to the card without losing either.
 */
export function ChartTip({ anchor, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<{ top: number; left: number; below: boolean } | null>(
    null,
  );

  useLayoutEffect(() => {
    if (!anchor || !ref.current) return;
    const rect = anchor.getBoundingClientRect();
    const box = ref.current.getBoundingClientRect();

    // Near the top of the window there is no room above the mark.
    let below = rect.top < EDGE;
    let top = below ? rect.bottom + 8 : rect.top - 8;
    if (below && top + box.height > window.innerHeight - GUTTER) {
      // No room below either — the tip turns back over the mark.
      below = false;
      top = rect.top - 8;
    }

    // The tip stands over the middle of the mark, but it never leaves
    // the window: it is clamped to the gutter on both sides.
    const half = box.width / 2;
    const middle = rect.left + rect.width / 2;
    const left = Math.min(
      Math.max(middle, GUTTER + half),
      Math.max(GUTTER + half, window.innerWidth - GUTTER - half),
    );

    setStyle((prev) =>
      prev && prev.top === top && prev.left === left && prev.below === below
        ? prev
        : { top, left, below },
    );
  }, [anchor, children]);

  if (!anchor) return null;

  return createPortal(
    <div
      ref={ref}
      id="charttip"
      className={`charttip${style?.below ? " charttip--below" : ""}`}
      role="tooltip"
      style={{
        top: style?.top ?? -9999,
        left: style?.left ?? -9999,
        visibility: style ? "visible" : "hidden",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
