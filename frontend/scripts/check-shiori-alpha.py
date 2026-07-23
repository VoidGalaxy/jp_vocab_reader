"""Diagnostic: report alpha-channel status of the 9 Shiori PNG assets.

Read-only -- does not modify any file. Run with:
    python frontend/scripts/check-shiori-alpha.py
"""

import os
from PIL import Image

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "brand", "shiori")

VARIANTS = [
    "default", "hero", "reading", "classify", "save",
    "review", "success", "empty", "loading",
]


def corner_samples(img):
    w, h = img.size
    pts = {
        "top-left": (0, 0),
        "top-right": (w - 1, 0),
        "bottom-left": (0, h - 1),
        "bottom-right": (w - 1, h - 1),
        "center": (w // 2, h // 2),
    }
    return {name: img.getpixel((x, y)) for name, (x, y) in pts.items()}


def alpha_stats(img):
    if img.mode != "RGBA":
        return None
    alpha = img.split()[-1]
    hist = alpha.histogram()
    total = sum(hist)
    fully_transparent = hist[0]
    fully_opaque = hist[255]
    partial = total - fully_transparent - fully_opaque
    return {
        "total": total,
        "fully_transparent": fully_transparent,
        "fully_opaque": fully_opaque,
        "partial": partial,
        "pct_transparent": round(100 * fully_transparent / total, 2),
    }


def main():
    for variant in VARIANTS:
        path = os.path.join(ASSET_DIR, f"shiori-{variant}.png")
        if not os.path.exists(path):
            print(f"[{variant}] MISSING: {path}")
            continue

        img = Image.open(path)
        print(f"\n=== shiori-{variant}.png ===")
        print(f"  mode: {img.mode}, size: {img.size}")

        stats = alpha_stats(img)
        if stats is None:
            print("  ALPHA: none (not RGBA) -- flat background baked in")
        else:
            print(
                f"  ALPHA: fully_transparent={stats['fully_transparent']} "
                f"({stats['pct_transparent']}%), fully_opaque={stats['fully_opaque']}, "
                f"partial(anti-aliased edges)={stats['partial']}"
            )

        rgba = img.convert("RGBA")
        corners = corner_samples(rgba)
        for name, px in corners.items():
            r, g, b, a = px
            print(f"  corner[{name}]: rgba({r},{g},{b},{a})")


if __name__ == "__main__":
    main()
