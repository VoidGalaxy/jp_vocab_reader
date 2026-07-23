"""Diagnostic: how much of each (already-transparent) Shiori PNG's canvas
is actually opaque character vs. empty transparent padding.

Read-only. Run with:
    python frontend/scripts/check-shiori-padding.py
"""

import os
from PIL import Image

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "brand", "shiori")

VARIANTS = [
    "default", "hero", "reading", "classify", "save",
    "review", "success", "empty", "loading",
]


def main():
    for variant in VARIANTS:
        path = os.path.join(ASSET_DIR, f"shiori-{variant}.png")
        if not os.path.exists(path):
            print(f"[{variant}] MISSING")
            continue
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        alpha = img.split()[-1]
        bbox = alpha.getbbox()
        if bbox is None:
            print(f"[{variant}] fully transparent?! size={w}x{h}")
            continue
        bx0, by0, bx1, by1 = bbox
        bw, bh = bx1 - bx0, by1 - by0
        fill_w = bw / w
        fill_h = bh / h
        pad_left, pad_top = bx0, by0
        pad_right, pad_bottom = w - bx1, h - by1
        print(
            f"[{variant}] canvas={w}x{h}  content_bbox={bw}x{bh} "
            f"(fills {fill_w:.0%} x {fill_h:.0%})  "
            f"pad L/T/R/B = {pad_left}/{pad_top}/{pad_right}/{pad_bottom}"
        )


if __name__ == "__main__":
    main()
