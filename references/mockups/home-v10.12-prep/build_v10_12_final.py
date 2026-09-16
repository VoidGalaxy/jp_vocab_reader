from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v10.11/home-v10.11-scene-desktop.png"
REFERENCE = Path(__file__).with_name("home-v10.12-final-reference.png")
OUTPUT = Path(__file__).with_name("home-v10.12-scene-desktop-candidate.png")
CONTACT_SHEET = Path(__file__).with_name("home-v10.12-final-contact-sheet.png")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


source_image = Image.open(SOURCE).convert("RGB")
reference_image = Image.open(REFERENCE).convert("RGB")
if reference_image.size != source_image.size:
    reference_image = reference_image.resize(source_image.size, Image.Resampling.LANCZOS)

source = np.asarray(source_image, dtype=np.float32)
reference = np.asarray(reference_image, dtype=np.float32)
height, width = source.shape[:2]

# Three narrow physical zones only: page stack, tape/root contacts, tab paper.
# The green cover lip and both book corners remain sourced entirely from V10.11.
mask_image = Image.new("L", (width, height), 0)
draw = ImageDraw.Draw(mask_image)
draw.rounded_rectangle((548, 640, 1394, 686), radius=12, fill=225)
for box in ((813, 649, 960, 706), (971, 649, 1118, 706), (1129, 649, 1276, 706)):
    draw.rounded_rectangle(box, radius=10, fill=255)
for box in ((813, 680, 960, 756), (971, 680, 1118, 756), (1129, 680, 1276, 756)):
    draw.rounded_rectangle(box, radius=12, fill=220)
mask = np.asarray(mask_image.filter(ImageFilter.GaussianBlur(3.5)), dtype=np.float32) / 255.0

# Hard containment prevents generated pixels from reaching the cover, corners,
# desk, or unrelated scene elements.
scope = np.zeros((height, width), dtype=np.float32)
scope[635:761, 540:1401] = 1.0
mask *= scope

# Keep the generated treatment close to V10.11's local light balance.
roi = (slice(642, 682), slice(575, 1375))
valid = mask[roi] > 0.55
if np.any(valid):
    correction = np.clip(
        np.median(source[roi][valid], axis=0) - np.median(reference[roi][valid], axis=0),
        -4.0,
        4.0,
    )
    reference = np.clip(reference + correction, 0.0, 255.0)

result = np.rint(source * (1.0 - mask[..., None]) + reference * mask[..., None]).astype(np.uint8)
Image.fromarray(result, mode="RGB").save(OUTPUT, optimize=True)

changed = np.max(np.abs(result.astype(np.int16) - source.astype(np.int16)), axis=2) > 2
outside = changed.copy()
outside[635:761, 540:1401] = False
ys, xs = np.where(changed)

# Compact review sheet: full candidate, V10.11 native crop, V10.12 native crop,
# then a 3x nearest-neighbour crop for artifact inspection.
crop_box = (500, 610, 1435, 770)
old_crop = source_image.crop(crop_box)
new_image = Image.fromarray(result, mode="RGB")
new_crop = new_image.crop(crop_box)
sheet = Image.new("RGB", (1888, 833 + 160 + 160 + 324), (238, 231, 216))
sheet.paste(new_image, (0, 0))
sheet.paste(old_crop, (0, 833))
sheet.paste(new_crop, (0, 993))
sheet.paste(new_crop.resize((1888, 323), Image.Resampling.NEAREST), (0, 1153))
sheet.save(CONTACT_SHEET, optimize=True)

print(f"source_sha256={sha256(SOURCE)}")
print(f"reference_sha256={sha256(REFERENCE)}")
print(f"output_sha256={sha256(OUTPUT)}")
print(f"size={source_image.size} mode=RGB")
print(f"changed_gt2={int(changed.sum())}")
print(f"outside_envelope_changed={int(outside.sum())}")
if len(xs):
    print(f"bbox=({xs.min()},{ys.min()})..({xs.max()},{ys.max()})")
