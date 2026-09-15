from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v10.10/home-v10.10-scene-desktop.png"
REFERENCE = Path(__file__).with_name("home-v10.11-lower-edge-reference.png")
OUTPUT = Path(__file__).with_name("home-v10.11-scene-desktop-candidate.png")
CONTACT_SHEET = Path(__file__).with_name("home-v10.11-lower-edge-contact-sheet.png")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


source_image = Image.open(SOURCE).convert("RGB")
reference_image = Image.open(REFERENCE).convert("RGB")
if reference_image.size != source_image.size:
    reference_image = reference_image.resize(source_image.size, Image.Resampling.LANCZOS)

source = np.asarray(source_image, dtype=np.float32)
reference = np.asarray(reference_image, dtype=np.float32)
height, width = source.shape[:2]

# Restrict the generated edit to the physical lower stack. The broad horizontal
# feather follows the notebook span; the soft vertical edge avoids a pasted band.
mask_image = Image.new("L", (width, height), 0)
draw = ImageDraw.Draw(mask_image)
draw.rounded_rectangle((505, 620, 1428, 724), radius=28, fill=255)
mask = np.asarray(mask_image.filter(ImageFilter.GaussianBlur(10)), dtype=np.float32) / 255.0
scope = np.zeros((height, width), dtype=np.float32)
scope[600:741, 490:1441] = 1.0
mask *= scope

# Preserve every visible colored tab pixel. Only tape and the hidden root/contact
# transition above the tab bodies may inherit the generated physical treatment.
body_boxes = ((810, 690, 964, 758), (969, 690, 1123, 758), (1128, 690, 1282, 758))
for x0, y0, x1, y1 in body_boxes:
    mask[y0 : y1 + 1, x0 : x1 + 1] = 0.0

# Generated imagery supplies microstructure only. Align its local color balance
# with V10.10 so the edit remains invisible outside the corrected geometry.
match_roi = (slice(632, 686), slice(560, 1388))
valid = mask[match_roi] > 0.82
if np.any(valid):
    source_median = np.median(source[match_roi][valid], axis=0)
    reference_median = np.median(reference[match_roi][valid], axis=0)
    correction = np.clip(source_median - reference_median, -5.0, 5.0)
    reference = np.clip(reference + correction, 0.0, 255.0)

result = np.rint(
    source * (1.0 - mask[..., None]) + reference * mask[..., None]
).astype(np.uint8)
Image.fromarray(result, mode="RGB").save(OUTPUT, optimize=True)

changed = np.max(np.abs(result.astype(np.int16) - source.astype(np.int16)), axis=2) > 2
outside = changed.copy()
outside[600:741, 490:1441] = False
ys, xs = np.where(changed)

# One compact review sheet: full scenes and native/4x lower-edge crops.
crop_box = (470, 580, 1460, 765)
source_crop = source_image.crop(crop_box)
result_image = Image.fromarray(result, mode="RGB")
result_crop = result_image.crop(crop_box)
sheet = Image.new("RGB", (1888, 833 + 185 + 370), (238, 231, 216))
sheet.paste(result_image, (0, 0))
sheet.paste(source_crop, (0, 833))
sheet.paste(result_crop.resize((1888, 352), Image.Resampling.NEAREST), (0, 1018))
sheet.save(CONTACT_SHEET, optimize=True)

print(f"source_sha256={sha256(SOURCE)}")
print(f"reference_sha256={sha256(REFERENCE)}")
print(f"output_sha256={sha256(OUTPUT)}")
print(f"size={source_image.size} mode=RGB")
print(f"changed_gt2={int(changed.sum())}")
print(f"outside_envelope_changed={int(outside.sum())}")
if len(xs):
    print(f"bbox=({xs.min()},{ys.min()})..({xs.max()},{ys.max()})")
for box in body_boxes:
    x0, y0, x1, y1 = box
    print(f"tab_body_changed[{box}]={int(changed[y0:y1+1, x0:x1+1].sum())}")
