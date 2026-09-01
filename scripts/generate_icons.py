#!/usr/bin/env python3
"""Generate the desktop app icon set.

Tauri's config references a fixed list of icon files; without them `tauri dev`
fails before it opens a window. This script produces all of them from code, so
the repo has no binary assets that nobody can regenerate.

    python3 scripts/generate_icons.py

Written against the standard library only (zlib + struct) because a build should
not need Pillow installed just to draw a rounded square.

To use a real logo instead, replace `draw_icon` or run Tauri's own tool:

    cd desktop && npm run tauri icon path/to/logo.png
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"

# Brand accent, matching --accent in the UI stylesheet.
TOP = (0x8F, 0x80, 0xFF)
BOTTOM = (0x63, 0x4E, 0xEE)
GLYPH = (0xFF, 0xFF, 0xFF)

# Anti-aliasing: draw at 4x and box-filter down.
SUPERSAMPLE = 4


# ── Geometry helpers ────────────────────────────────────────────────────────


def inside_rounded_rect(
    x: float, y: float, left: float, top: float, right: float, bottom: float, radius: float
) -> bool:
    if x < left or x > right or y < top or y > bottom:
        return False
    # Only the four corner boxes need the circle test.
    for corner_x, corner_y in (
        (left + radius, top + radius),
        (right - radius, top + radius),
        (left + radius, bottom - radius),
        (right - radius, bottom - radius),
    ):
        in_x = x < corner_x if corner_x == left + radius else x > corner_x
        in_y = y < corner_y if corner_y == top + radius else y > corner_y
        if in_x and in_y:
            return (x - corner_x) ** 2 + (y - corner_y) ** 2 <= radius * radius
    return True


def inside_triangle(
    x: float, y: float, a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> bool:
    def sign(p: tuple[float, float], q: tuple[float, float]) -> float:
        return (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1])

    d1, d2, d3 = sign(a, b), sign(b, c), sign(c, a)
    has_negative = d1 < 0 or d2 < 0 or d3 < 0
    has_positive = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_negative and has_positive)


# ── The icon itself ─────────────────────────────────────────────────────────


def draw_icon(size: int) -> bytearray:
    """RGBA pixel buffer for a `size` x `size` icon.

    A rounded square in the brand gradient with a white speech bubble — legible
    down to 16px, which is where a tray icon actually lives.
    """
    scale = SUPERSAMPLE
    big = size * scale
    # Accumulate coverage at high resolution, then average.
    accum = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]

    # Background plate: a squircle-ish rounded square with a small margin.
    margin = big * 0.045
    plate_radius = big * 0.225

    # Speech bubble, offset up slightly to leave room for the tail.
    bubble_left = big * 0.215
    bubble_right = big * 0.785
    bubble_top = big * 0.235
    bubble_bottom = big * 0.635
    bubble_radius = big * 0.105

    # Tail: a triangle hanging from the bubble's lower-left.
    tail = (
        (big * 0.315, big * 0.615),
        (big * 0.315, big * 0.815),
        (big * 0.505, big * 0.625),
    )

    for py in range(big):
        y = py + 0.5
        target_row = (py // scale) * size
        for px in range(big):
            x = px + 0.5

            if not inside_rounded_rect(
                x, y, margin, margin, big - margin, big - margin, plate_radius
            ):
                continue

            in_bubble = inside_rounded_rect(
                x, y, bubble_left, bubble_top, bubble_right, bubble_bottom, bubble_radius
            )
            in_tail = inside_triangle(x, y, *tail)

            if in_bubble or in_tail:
                colour = GLYPH
            else:
                # Vertical gradient across the plate.
                t = y / big
                colour = (
                    round(TOP[0] + (BOTTOM[0] - TOP[0]) * t),
                    round(TOP[1] + (BOTTOM[1] - TOP[1]) * t),
                    round(TOP[2] + (BOTTOM[2] - TOP[2]) * t),
                )

            cell = accum[target_row + (px // scale)]
            cell[0] += colour[0]
            cell[1] += colour[1]
            cell[2] += colour[2]
            cell[3] += 255.0

    samples = float(scale * scale)
    pixels = bytearray(size * size * 4)
    for index, (r, g, b, a) in enumerate(accum):
        alpha = a / samples
        pixels[index * 4 + 3] = round(alpha)
        if alpha <= 0:
            continue
        # Un-premultiply so partially covered edge pixels keep their hue.
        covered = a / 255.0
        pixels[index * 4 + 0] = min(255, round(r / covered))
        pixels[index * 4 + 1] = min(255, round(g / covered))
        pixels[index * 4 + 2] = min(255, round(b / covered))
    return pixels


# ── PNG encoding ────────────────────────────────────────────────────────────


def png_bytes(pixels: bytearray, size: int) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    # Each scanline is prefixed with its filter type (0 = none).
    raw = bytearray()
    stride = size * 4
    for row in range(size):
        raw.append(0)
        raw.extend(pixels[row * stride : (row + 1) * stride])

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# ── ICO / ICNS containers ───────────────────────────────────────────────────


def ico_bytes(images: list[tuple[int, bytes]]) -> bytes:
    """Windows .ico holding PNG payloads (supported since Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = bytearray()
    payloads = bytearray()
    for size, png in images:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # 0 means 256
            0 if size >= 256 else size,
            0,  # palette size
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(png),
            offset,
        )
        payloads += png
        offset += len(png)
    return header + bytes(entries) + bytes(payloads)


def icns_bytes(entries: list[tuple[bytes, bytes]]) -> bytes:
    """macOS .icns holding PNG payloads under typed chunks."""
    body = bytearray()
    for tag, png in entries:
        body += tag + struct.pack(">I", len(png) + 8) + png
    return b"icns" + struct.pack(">I", len(body) + 8) + bytes(body)


# ── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sizes Tauri's config asks for, plus the ones the containers need.
    wanted = [16, 32, 48, 64, 128, 256, 512]
    rendered: dict[int, bytes] = {}
    for size in wanted:
        rendered[size] = png_bytes(draw_icon(size), size)
        print(f"  rendered {size}x{size}")

    files: dict[str, bytes] = {
        "32x32.png": rendered[32],
        "128x128.png": rendered[128],
        # Tauri's naming: the @2x of 128 is a 256px image.
        "128x128@2x.png": rendered[256],
        "icon.png": rendered[512],
        "icon.ico": ico_bytes([(s, rendered[s]) for s in (16, 32, 48, 64, 128, 256)]),
        "icon.icns": icns_bytes(
            [(b"ic07", rendered[128]), (b"ic08", rendered[256]), (b"ic09", rendered[512])]
        ),
        # Windows Store / MSIX square logos Tauri references in some templates.
        "Square30x30Logo.png": rendered[32],
        "Square44x44Logo.png": rendered[48],
        "Square89x89Logo.png": rendered[128],
        "Square107x107Logo.png": rendered[128],
        "Square142x142Logo.png": rendered[256],
        "Square150x150Logo.png": rendered[256],
        "Square284x284Logo.png": rendered[512],
        "Square310x310Logo.png": rendered[512],
        "StoreLogo.png": rendered[64],
    }

    for name, payload in files.items():
        (OUT_DIR / name).write_bytes(payload)
        print(f"  wrote {name} ({len(payload):,} bytes)")

    print(f"\n{len(files)} files in {OUT_DIR}")


if __name__ == "__main__":
    main()
