import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  anchor: HTMLElement | null;
  /** Open at a point instead of at the anchor — a right-click menu. */
  at?: { x: number; y: number } | null;
  onClose: () => void;
  children: ReactNode;
  align?: "left" | "right";
  width?: number;
  className?: string;
}

interface SubProps {
  open: boolean;
  /** The parent item the submenu hangs off. */
  anchor: HTMLElement | null;
  children: ReactNode;
  width?: number;
}

/** A popover anchored to a trigger, positioned in a portal so no ancestor clips it. */
export function Menu({
  anchor,
  at,
  onClose,
  children,
  align = "left",
  width,
  className,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<{ top: number; left: number } | null>(null);
  const atX = at?.x;
  const atY = at?.y;

  useLayoutEffect(() => {
    if ((!anchor && atX === undefined) || !ref.current) return;
    const box = ref.current.getBoundingClientRect();
    const gap = 6;
    let left: number;
    let top: number;
    if (atX !== undefined && atY !== undefined) {
      left = atX;
      top = atY;
      if (top + box.height > window.innerHeight - 8) top = Math.max(8, top - box.height);
    } else {
      const rect = anchor!.getBoundingClientRect();
      left = align === "right" ? rect.right - box.width : rect.left;
      top = rect.bottom + gap;
      if (top + box.height > window.innerHeight - 8) {
        top = Math.max(8, rect.top - box.height - gap);
      }
    }
    left = Math.min(Math.max(8, left), window.innerWidth - box.width - 8);
    setStyle({ top, left });
  }, [anchor, align, atX, atY]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointer = (event: PointerEvent) => {
      if (!ref.current) return;
      if (ref.current.contains(event.target as Node)) return;
      if (anchor?.contains(event.target as Node)) return;
      onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div
      ref={ref}
      className={className ? `menu ${className}` : "menu"}
      role="menu"
      style={{
        top: style?.top ?? -9999,
        left: style?.left ?? -9999,
        width,
        visibility: style ? "visible" : "hidden",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

/**
 * A menu that opens beside its parent item, the way a status picker does.
 *
 * It lives inside the parent menu's own box — not in a portal of its own —
 * so a click on one of its rows is a click inside the menu, and the menu
 * stays open while you reach for it.
 */
export function MenuSub({ open, anchor, children, width }: SubProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !anchor || !ref.current) return;
    const parent = anchor.closest(".menu");
    if (!parent) return;
    const item = anchor.getBoundingClientRect();
    const parentBox = parent.getBoundingClientRect();
    const box = ref.current.getBoundingClientRect();
    // Beside the item, a hair to the right of the parent's edge.
    let left = item.right - parentBox.left + 2;
    if (left + box.width > window.innerWidth - 8) {
      left = item.left - parentBox.left - box.width - 2;
    }
    let top = item.top - parentBox.top;
    if (top + box.height > window.innerHeight - 8) {
      top = window.innerHeight - 8 - box.height - parentBox.top;
    }
    setStyle({ top, left });
  }, [open, anchor]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className="menu menu--sub"
      role="menu"
      style={{
        top: style?.top ?? 0,
        left: style?.left ?? 0,
        width,
        visibility: style ? "visible" : "hidden",
      }}
    >
      {children}
    </div>
  );
}
