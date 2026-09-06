from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_home_v8_plate.py <plate.png>")

    path = Path(sys.argv[1])
    if not path.exists():
        fail(f"file does not exist: {path}")

    image = Image.open(path)
    if image.mode not in {"RGBA", "LA"}:
        fail(f"expected transparent PNG with alpha, got mode {image.mode}")

    rgba = image.convert("RGBA")
    w, h = rgba.size
    if w < 900 or h < 650:
        fail(f"asset is unexpectedly small: {w}x{h}")

    corners = [
        rgba.getpixel((0, 0)),
        rgba.getpixel((w - 1, 0)),
        rgba.getpixel((0, h - 1)),
        rgba.getpixel((w - 1, h - 1)),
    ]
    if any(pixel[3] != 0 for pixel in corners):
        fail(f"all corners must be transparent, got {corners}")

    alpha = rgba.getchannel("A")
    min_alpha, max_alpha = alpha.getextrema()
    if min_alpha != 0 or max_alpha == 0:
        fail(f"alpha channel looks wrong: extrema {(min_alpha, max_alpha)}")

    border = []
    for x in range(w):
        border.append(rgba.getpixel((x, 0)))
        border.append(rgba.getpixel((x, h - 1)))
    for y in range(h):
        border.append(rgba.getpixel((0, y)))
        border.append(rgba.getpixel((w - 1, y)))

    opaque_border = [p for p in border if p[3] > 12]
    if opaque_border:
        fail(f"border has non-transparent pixels: {len(opaque_border)}")

    # Detect the recurring white/gray matte residue problem near the outer edge.
    scan_margin = max(18, round(min(w, h) * 0.025))
    residue = 0
    scanned = 0
    for y in range(h):
        for x in range(w):
            if x > scan_margin and x < w - scan_margin and y > scan_margin and y < h - scan_margin:
                continue
            r, g, b, a = rgba.getpixel((x, y))
            if a <= 96:
                continue
            scanned += 1
            bright = (r + g + b) / 3
            low_sat = max(r, g, b) - min(r, g, b) < 36
            if bright > 145 and low_sat:
                residue += 1

    if residue > max(120, scanned * 0.015):
        fail(f"possible bright gray/white matte residue near edge: {residue} pixels")

    print(f"PASS: {path} {w}x{h}, alpha OK, no border matte residue detected")


if __name__ == "__main__":
    main()
