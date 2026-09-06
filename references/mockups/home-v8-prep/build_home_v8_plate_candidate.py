from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v7/home-v7-notebook-tabs-shadow-plate.png"
OUT = ROOT / "frontend/public/brand/decor/home-v8/home-v8-notebook-tabs-grounded-plate.png"


def is_border_matte(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a == 0:
        return True
    bright = (r + g + b) / 3
    low_sat = max(r, g, b) - min(r, g, b) < 44
    # The recurring failure is an opaque white/gray matte connected to the
    # image edge. Real tabs/tape are not border-connected in the source plate.
    return a > 110 and bright > 132 and low_sat


def remove_connected_matte(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size

    # Preserve bright real materials (page edges, tape, bookmark ribbon) when
    # they are physically attached to dark/saturated notebook pixels. The v8
    # first pass flood-filled every border-connected light pixel and cut a
    # visible vertical gap out of the cover near the ribbon.
    material = Image.new("L", (w, h), 0)
    material_px = material.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a <= 20:
                continue
            if not is_border_matte((r, g, b, a)):
                material_px[x, y] = 255

    preserve = material.filter(ImageFilter.MaxFilter(31))
    preserve_px = preserve.load()
    seen: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    for x in range(w):
      queue.append((x, 0))
      queue.append((x, h - 1))
    for y in range(h):
      queue.append((0, y))
      queue.append((w - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or x < 0 or y < 0 or x >= w or y >= h:
            continue
        seen.add((x, y))
        if not is_border_matte(pixels[x, y]):
            continue
        # The cream bookmark ribbon intentionally reaches the top edge. Its
        # center panel is bright and low-saturation, so a pure border flood
        # fill mistakes it for matte and punches a vertical transparent slit.
        if w * 0.77 < x < w * 0.88 and y < h * 0.22:
            continue
        if preserve_px[x, y] > 0:
            continue
        pixels[x, y] = (0, 0, 0, 0)
        queue.append((x + 1, y))
        queue.append((x - 1, y))
        queue.append((x, y + 1))
        queue.append((x, y - 1))

    return rgba


def offset_alpha(alpha: Image.Image, offset: tuple[int, int], size: tuple[int, int]) -> Image.Image:
    layer = Image.new("L", size, 0)
    layer.paste(alpha, offset)
    return layer


def contact_mask(alpha: Image.Image) -> Image.Image:
    w, h = alpha.size
    source = alpha.load()
    mask = Image.new("L", (w, h), 0)
    out = mask.load()

    # Trace only the edges that touch the desk. The rejected v8 candidate
    # blurred the whole lower half of the object, which produced a brown
    # support slab. A physical contact shadow starts from the bottom/right
    # contact edges and fades outward.
    for x in range(w):
        lowest = -1
        strongest = 0
        for y in range(h - 1, -1, -1):
            value = source[x, y]
            if value > 20:
                lowest = y
                strongest = value
                break
        if lowest < 0:
            continue
        for yy in range(max(0, lowest - 1), min(h, lowest + 1)):
            out[x, yy] = max(out[x, yy], strongest)

    for y in range(round(h * 0.14), h):
        rightmost = -1
        strongest = 0
        for x in range(w - 1, -1, -1):
            value = source[x, y]
            if value > 20:
                rightmost = x
                strongest = value
                break
        if rightmost < 0:
            continue
        for xx in range(max(0, rightmost - 1), min(w, rightmost + 1)):
            out[xx, y] = max(out[xx, y], strongest)
    return mask


def build_shadow(alpha: Image.Image, canvas_size: tuple[int, int], pad: int) -> Image.Image:
    contact = contact_mask(alpha)
    tight = offset_alpha(contact, (pad + 8, pad + 10), canvas_size).filter(ImageFilter.GaussianBlur(8))
    soft = offset_alpha(contact, (pad + 24, pad + 30), canvas_size).filter(ImageFilter.GaussianBlur(32))
    tab_soft = offset_alpha(contact, (pad + 14, pad + 18), canvas_size).filter(ImageFilter.GaussianBlur(16))

    tight = tight.point(lambda value: int(value * 0.30))
    soft = soft.point(lambda value: int(value * 0.11))
    tab_soft = tab_soft.point(lambda value: int(value * 0.16))
    merged = ImageChops.lighter(ImageChops.lighter(tight, soft), tab_soft)

    shadow = Image.new("RGBA", canvas_size, (31, 20, 9, 0))
    shadow.putalpha(merged)
    return shadow


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    clean = remove_connected_matte(source)
    alpha = clean.getchannel("A")

    pad = 120
    w, h = clean.size
    canvas_size = (w + pad * 2, h + pad * 2)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow = build_shadow(alpha, canvas_size, pad)
    canvas.alpha_composite(shadow, (0, 0))
    canvas.alpha_composite(clean, (pad, pad))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print(f"wrote {OUT} {canvas.size[0]}x{canvas.size[1]}")


if __name__ == "__main__":
    main()
