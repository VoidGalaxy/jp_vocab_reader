from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v10.9/home-v10.9-scene-desktop.png"
REFERENCE = Path(__file__).with_name("home-v10.10-codex-lower-edge-reference.png")
OUTPUT = Path(__file__).with_name("home-v10.10-scene-desktop-candidate.png")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


source_image = Image.open(SOURCE).convert("RGB")
reference_image = Image.open(REFERENCE).convert("RGB").resize(
    source_image.size, Image.Resampling.LANCZOS
)
source = np.asarray(source_image, dtype=np.float32)
reference = np.asarray(reference_image, dtype=np.float32)
height, width = source.shape[:2]

# One continuous physical reconstruction envelope. Wide feathering prevents a
# rectangular patch while the opaque center replaces the complete failed stack.
mask_image = Image.new("L", (width, height), 0)
draw = ImageDraw.Draw(mask_image)
draw.rounded_rectangle((500, 608, 1435, 731), radius=34, fill=255)
mask = np.asarray(mask_image.filter(ImageFilter.GaussianBlur(12)), dtype=np.float32) / 255.0
scope = np.zeros((height, width), dtype=np.float32)
scope[570:751, 500:1436] = 1.0
mask *= scope

# Keep the approved visible tab bodies byte-identical. Tape and the hidden root
# transition remain editable, while the body protection begins below the tape.
protected = Image.new("L", (width, height), 0)
protected_draw = ImageDraw.Draw(protected)
body_boxes = ((813, 691, 962, 757), (971, 691, 1120, 757), (1129, 691, 1278, 757))
for box in body_boxes:
    protected_draw.rounded_rectangle(box, radius=10, fill=255)
protected_mask = np.asarray(protected.filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32) / 255.0
mask *= 1.0 - protected_mask
for x0, y0, x1, y1 in body_boxes:
    mask[y0 : y1 + 1, x0 : x1 + 1] = 0.0

# The generated reference supplies structure, not global tone. Match its local
# warm page/cover balance to the source before the bounded composite.
match_roi = (slice(620, 690), slice(560, 1390))
valid = mask[match_roi] > 0.85
if np.any(valid):
    source_mean = np.median(source[match_roi][valid], axis=0)
    reference_mean = np.median(reference[match_roi][valid], axis=0)
    correction = np.clip(source_mean - reference_mean, -6.0, 6.0)
    reference = np.clip(reference + correction, 0.0, 255.0)

result = np.rint(
    source * (1.0 - mask[..., None]) + reference * mask[..., None]
).astype(np.uint8)
Image.fromarray(result, mode="RGB").save(OUTPUT, optimize=True)

changed = np.max(np.abs(result.astype(np.int16) - source.astype(np.int16)), axis=2) > 2
ys, xs = np.where(changed)
outside = changed.copy()
outside[570:751, 500:1436] = False

print(f"source_sha256={sha256(SOURCE)}")
print(f"reference={REFERENCE}")
print(f"output={OUTPUT}")
print(f"output_sha256={sha256(OUTPUT)}")
print(f"size={source_image.size} mode=RGB")
print(f"changed_gt2={int(changed.sum())}")
print(f"outside_envelope_changed={int(outside.sum())}")
if len(xs):
    print(f"bbox=({xs.min()},{ys.min()})..({xs.max()},{ys.max()})")
