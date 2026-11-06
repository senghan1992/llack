/** Avatar colour: the palette, and the maths that keeps initials legible. */

/**
 * The colours an avatar may wear. They are deep on purpose: the initials sit
 * on them in paper white, and small text has to stay readable.
 */
export const AVATAR_PALETTE = [
  "#126b47",
  "#8a4141",
  "#295e90",
  "#814d0e",
  "#644c8a",
  "#006b71",
  "#6a5a00",
] as const;

/**
 * The ink an avatar's initials are printed in: paper white, in both themes.
 * The tile under them is the person's own colour and may be any mid tone,
 * so the ink cannot be a grey that only reads on the darkest tiles.
 */
export const AVATAR_INK = "#fcfcfb";

/** How much contrast the initials must keep on their tile. */
export const AVATAR_MIN_CONTRAST = 5;

/** Parse `#rgb` or `#rrggbb` into its three channels. */
export function parseHex(value: string): [number, number, number] | null {
  const hex = value.trim().replace(/^#/, "");
  if (hex.length === 3) {
    const parts = hex.split("");
    if (parts.every((part) => /^[0-9a-f]$/i.test(part))) {
      return [
        parseInt(parts[0] + parts[0], 16),
        parseInt(parts[1] + parts[1], 16),
        parseInt(parts[2] + parts[2], 16),
      ];
    }
    return null;
  }
  if (hex.length !== 6 || !/^[0-9a-f]{6}$/i.test(hex)) return null;
  return [
    parseInt(hex.slice(0, 2), 16),
    parseInt(hex.slice(2, 4), 16),
    parseInt(hex.slice(4, 6), 16),
  ];
}

function toHex(rgb: [number, number, number]): string {
  return `#${rgb.map((part) => Math.round(part).toString(16).padStart(2, "0")).join("")}`;
}

function channel(value: number): number {
  const v = value / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function luminance(rgb: [number, number, number]): number {
  return (
    0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])
  );
}

/** The contrast between two colours, from 1 to 21. */
export function contrastRatio(a: string, b: string): number {
  const first = parseHex(a);
  const second = parseHex(b);
  if (!first || !second) return 1;
  const light = Math.max(luminance(first), luminance(second));
  const dark = Math.min(luminance(first), luminance(second));
  return (light + 0.05) / (dark + 0.05);
}

/**
 * Darken a colour until the ink on it is readable. The hue is
 * kept: only the lightness moves.
 */
export function readableOn(color: string, ink = AVATAR_INK, min = AVATAR_MIN_CONTRAST): string {
  const rgb = parseHex(color);
  if (!rgb) return color;
  if (contrastRatio(color, ink) >= min) return toHex(rgb);
  let current: [number, number, number] = rgb;
  for (let step = 0; step < 60; step += 1) {
    current = [current[0] * 0.94, current[1] * 0.94, current[2] * 0.94];
    if (contrastRatio(toHex(current), ink) >= min) break;
  }
  return toHex(current);
}
