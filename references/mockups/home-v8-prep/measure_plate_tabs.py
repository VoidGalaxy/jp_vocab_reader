from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import deque

from PIL import Image


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: measure_plate_tabs.py <plate.png>")
    path = Path(sys.argv[1])
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    boxes = {"yellow": [], "coral": [], "blue": []}
    for y in range(h):
        for x in range(w):
            r, g, b, a = im.getpixel((x, y))
            if a < 120:
                continue
            if y < h * 0.72:
                continue
            if r > 175 and g > 115 and b < 115 and r < g + 95:
                boxes["yellow"].append((x, y))
            elif r > 135 and r > g + 38 and r > b + 30 and g < 135 and b < 135:
                boxes["coral"].append((x, y))
            elif b > 135 and b > r + 35 and b > g + 12:
                boxes["blue"].append((x, y))

    out = {"size": [w, h], "tabs": {}}
    for name, pts in boxes.items():
        if not pts:
            out["tabs"][name] = None
            continue
        point_set = set(pts)
        components = []
        while point_set:
            start = point_set.pop()
            queue = deque([start])
            comp = [start]
            while queue:
                x, y = queue.popleft()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (nx, ny) in point_set:
                        point_set.remove((nx, ny))
                        queue.append((nx, ny))
                        comp.append((nx, ny))
            if len(comp) >= 100:
                xs = [pt[0] for pt in comp]
                ys = [pt[1] for pt in comp]
                components.append({
                    "count": len(comp),
                    "bbox_px": [min(xs), min(ys), max(xs), max(ys)],
                    "bbox_pct": [
                        round(min(xs) / w * 100, 2),
                        round(min(ys) / h * 100, 2),
                        round((max(xs) - min(xs)) / w * 100, 2),
                        round((max(ys) - min(ys)) / h * 100, 2),
                    ],
                })
        out["tabs"][name] = sorted(components, key=lambda item: item["count"], reverse=True)[:5]
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
