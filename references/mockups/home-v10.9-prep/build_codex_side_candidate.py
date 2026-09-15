from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v10.8/home-v10.8-scene-desktop.png"
REFERENCE = Path(__file__).with_name("home-v10.9-side-reference.png")
OUTPUT = ROOT / "frontend/public/brand/decor/home-v10.9/home-v10.9-scene-desktop.png"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


source_image = Image.open(SOURCE).convert("RGB")
reference_image = Image.open(REFERENCE).convert("RGB").resize(
    source_image.size, Image.Resampling.LANCZOS
)

source = np.asarray(source_image, dtype=np.float32)
reference = np.asarray(reference_image, dtype=np.float32)
height, width = source.shape[:2]

# These three envelopes come directly from the user's blue-marked screenshot.
# They cover only the two left spine recesses and the right fore-edge recess.
region_layer = Image.new("L", (width, height), 0)
draw = ImageDraw.Draw(region_layer)
draw.rounded_rectangle((528, 105, 602, 215), radius=28, fill=255)
draw.rounded_rectangle((514, 470, 608, 686), radius=32, fill=255)
draw.rounded_rectangle((1364, 98, 1434, 694), radius=30, fill=255)
region = np.asarray(region_layer.filter(ImageFilter.GaussianBlur(7)), dtype=np.float32) / 255.0

# Keep the blend on dark green/neutral notebook material. Warm desk, cream
# paper, tape, and colored tabs are excluded even inside the broad envelopes.
r, g, b = np.moveaxis(source, -1, 0)
luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
notebook_material = (
    (g >= r - 10)
    & (g >= b - 10)
    & (luma < 118)
    & (np.indices((height, width))[0] >= 98)
    & (np.indices((height, width))[0] <= 695)
)

# Feather the material clip slightly inward without allowing the generated
# reference to spill across the physical notebook silhouette.
material_image = Image.fromarray((notebook_material * 255).astype(np.uint8), mode="L")
material_soft = np.asarray(material_image.filter(ImageFilter.GaussianBlur(1.6)), dtype=np.float32) / 255.0
alpha = np.clip(region * material_soft, 0.0, 1.0)

# Match each side repair to the adjacent V10.8 cloth luminance so the generated
# structure contributes geometry and texture without introducing a new tone.
for x0, y0, x1, y1 in ((528, 105, 602, 215), (514, 470, 608, 686), (1364, 98, 1434, 694)):
    roi = (slice(y0, y1 + 1), slice(x0, x1 + 1))
    valid = alpha[roi] > 0.55
    if np.any(valid):
        src_luma = np.mean(source[roi], axis=2)
        ref_luma = np.mean(reference[roi], axis=2)
        delta = float(np.median(src_luma[valid]) - np.median(ref_luma[valid]))
        reference[roi] = np.clip(reference[roi] + np.clip(delta, -7.0, 7.0), 0.0, 255.0)

result = np.rint(
    source * (1.0 - alpha[..., None]) + reference * alpha[..., None]
).astype(np.uint8)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(result, mode="RGB").save(OUTPUT, optimize=True)

changed = np.max(np.abs(result.astype(np.int16) - source.astype(np.int16)), axis=2) > 2
ys, xs = np.where(changed)
print(f"source_sha256={sha256(SOURCE)}")
print(f"reference={REFERENCE}")
print(f"output={OUTPUT}")
print(f"output_sha256={sha256(OUTPUT)}")
print(f"size={source_image.size} mode=RGB")
print(f"changed_gt2={int(changed.sum())}")
print(f"changed_fraction={changed.mean() * 100:.6f}%")
if len(xs):
    print(f"bbox=({xs.min()},{ys.min()})..({xs.max()},{ys.max()})")
