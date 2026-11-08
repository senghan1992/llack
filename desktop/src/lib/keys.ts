/**
 * Whether the key was pressed while the reader was writing something — in
 * a field, in a rich text area, or in the composer.
 *
 * The rooms do not move under a sentence that is being written: the
 * keyboard shortcuts that walk between the rooms keep out of the way while
 * a word is being written.
 */
export function isWriting(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || typeof element.tagName !== "string") return false;
  if (element.isContentEditable) return true;
  const tag = element.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea") return true;
  // The composer — its field, its keys, its emoji sheet.
  return Boolean(element.closest?.(".composer"));
}
