import { describe, expect, it } from "vitest";
import { isWriting } from "./keys";

/** The node the key was pressed in — the browser's shapes, faked. */
function node(tag: string, over: Partial<HTMLElement> = {}): EventTarget {
  return {
    tagName: tag.toUpperCase(),
    isContentEditable: false,
    closest: () => null,
    ...over,
  } as unknown as EventTarget;
}

describe("isWriting", () => {
  it("knows a field the reader is typing in", () => {
    expect(isWriting(node("input"))).toBe(true);
    expect(isWriting(node("textarea"))).toBe(true);
  });

  it("knows a rich text area the reader is typing in", () => {
    expect(isWriting(node("div", { isContentEditable: true }))).toBe(true);
  });

  it("knows the composer, field or key", () => {
    const inComposer = node("button", {
      closest: (selector: string) => (selector === ".composer" ? ({} as Element) : null),
    });
    expect(isWriting(inComposer)).toBe(true);
  });

  it("leaves the rest of the app alone", () => {
    expect(isWriting(node("div"))).toBe(false);
    expect(isWriting(node("button"))).toBe(false);
    // A target that is not an element at all — the window itself.
    expect(isWriting({} as EventTarget)).toBe(false);
    expect(isWriting(null)).toBe(false);
  });
});
