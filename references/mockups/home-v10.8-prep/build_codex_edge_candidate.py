from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png"
REFERENCE = Path(__file__).with_name("home-v10.8-generated-edge-reference.png")
OUTPUT = (
    ROOT
    / "frontend/public/brand/decor/home-v10.8/home-v10.8-scene-desktop.png"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


source_image = Image.open(SOURCE).convert("RGB")
reference_image = Image.open(REFERENCE).convert("RGB").resize(
    source_image.size, Image.Resampling.LANCZOS
)

source = np.asarray(source_image, dtype=np.float32)
reference = np.asarray(reference_image, dtype=np.float32)
height, width = source.shape[:2]

# The reference is used only inside this hand-shaped notebook-edge envelope.
# Vertical ramps blend into the untouched cover above and untouched desk below.
mask = np.zeros((height, width), dtype=np.float32)
x1, x2 = 516, 1428
y1, y2 = 612, 692
mask[y1:y2, x1:x2] = 1.0

top_ramp = np.linspace(0.0, 1.0, 18, dtype=np.float32)
bottom_ramp = np.linspace(1.0, 0.0, 14, dtype=np.float32)
mask[y1 : y1 + len(top_ramp), x1:x2] *= top_ramp[:, None]
mask[y2 - len(bottom_ramp) : y2, x1:x2] *= bottom_ramp[:, None]

# Taper the envelope around the two rounded corner returns.
for x in range(x1, x1 + 30):
    mask[:, x] *= (x - x1) / 30.0
for x in range(x2 - 30, x2):
    mask[:, x] *= (x2 - 1 - x) / 30.0

# Preserve the three approved tab and tape objects from V10.4. Masks are
# feathered so the restored originals do not create rectangular seams.
preserve = Image.new("L", source_image.size, 0)
preserve_pixels = np.asarray(preserve, dtype=np.uint8).copy()
for left, top, right, bottom in (
    (808, 638, 965, 765),
    (966, 638, 1122, 765),
    (1124, 638, 1284, 765),
):
    preserve_pixels[top:bottom, left:right] = 255
preserve = Image.fromarray(preserve_pixels, mode="L").filter(
    ImageFilter.GaussianBlur(radius=3)
)
preserve_weight = np.asarray(preserve, dtype=np.float32) / 255.0
mask *= 1.0 - preserve_weight

# A mild luminance match keeps the inserted structure in V10.4's lighting
# family without flattening the generated cloth and paper texture.
roi = (slice(620, 686), slice(540, 1408))
src_luma = np.mean(source[roi], axis=2)
ref_luma = np.mean(reference[roi], axis=2)
valid = mask[roi] > 0.45
if np.any(valid):
    delta = float(np.median(src_luma[valid]) - np.median(ref_luma[valid]))
    reference = np.clip(reference + np.clip(delta, -8.0, 8.0), 0.0, 255.0)

alpha = mask[..., None]
result = np.rint(source * (1.0 - alpha) + reference * alpha).astype(np.uint8)

# Remove the residual marker-like seam without painting another continuous
# strip. Crushed pixels immediately above the page inherit the real woven
# texture from the cover just above them. The two rounded returns use a darker
# version of the same local cloth so they retain depth without reading black.
result_float = result.astype(np.float32)
luma = (
    0.2126 * result_float[..., 0]
    + 0.7152 * result_float[..., 1]
    + 0.0722 * result_float[..., 2]
)

front_zone = np.zeros((height, width), dtype=bool)
front_zone[636:654, 530:1416] = True
front_weight = np.clip((30.0 - luma) / 24.0, 0.0, 1.0) * front_zone
for y in range(636, 654):
    sample_y = max(612, y - 16)
    target = result_float[sample_y, :, :] * 0.82
    w = front_weight[y, :, None] * 0.92
    result_float[y, :, :] = result_float[y, :, :] * (1.0 - w) + target * w

luma = (
    0.2126 * result_float[..., 0]
    + 0.7152 * result_float[..., 1]
    + 0.0722 * result_float[..., 2]
)
corner_zone = np.zeros((height, width), dtype=bool)
corner_zone[628:681, 520:590] = True
corner_zone[620:681, 1370:1425] = True
corner_weight = (
    np.clip((34.0 - luma) / 26.0, 0.0, 1.0)
    * corner_zone
)
for y in range(620, 681):
    sample_y = max(596, y - 34)
    left_sample = result_float[sample_y, 566:586, :].mean(axis=0)
    right_sample = result_float[sample_y, 1348:1368, :].mean(axis=0)
    left_target = left_sample * 0.55 + np.array([8.0, 5.0, 2.0])
    right_target = right_sample * 0.55 + np.array([8.0, 5.0, 2.0])
    left_w = corner_weight[y, 520:590, None] * 0.9
    right_w = corner_weight[y, 1370:1425, None] * 0.9
    result_float[y, 520:590, :] = (
        result_float[y, 520:590, :] * (1.0 - left_w) + left_target * left_w
    )
    result_float[y, 1370:1425, :] = (
        result_float[y, 1370:1425, :] * (1.0 - right_w) + right_target * right_w
    )

result = np.clip(np.rint(result_float), 0, 255).astype(np.uint8)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(result, mode="RGB").save(OUTPUT, optimize=True)

diff = np.max(np.abs(result.astype(np.int16) - source.astype(np.int16)), axis=2)
changed = diff > 2
ys, xs = np.where(changed)
print(f"source_sha256={sha256(SOURCE)}")
print(f"reference={REFERENCE}")
print(f"output={OUTPUT}")
print(f"output_sha256={sha256(OUTPUT)}")
print(f"size={source_image.size} mode=RGB")
print(f"changed_gt2={int(changed.sum())}")
print(f"changed_fraction={float(changed.mean()):.6%}")
print(f"bbox=({xs.min()},{ys.min()})..({xs.max()},{ys.max()})")
