"""One-off batch fix: strip the baked-in near-white canvas out of the 9
Shiori PNG assets so they render as true transparent-background sprites.

The source PNGs are flat RGB (no alpha) with a near-white paper-colored
canvas around the character. This script:

  1. Backs up every original file once, into ./_backup/ (never overwritten
     on re-runs, so re-running this script is always safe/idempotent
     against the true source).
  2. Flood-fills from the canvas border (not a global color-key) so only
     background pixels *connected* to the edge are ever touched -- the
     character's outline stroke is what stops the fill, so linework, the
     cream/ivory body, the leaf charm, book/card/box props are structurally
     unreachable and can't be eaten no matter the threshold.
  3. Inside that flood-connected region, alpha is a smooth function of each
     pixel's color distance from the sampled background color: pixels that
     are essentially pure white go fully transparent, while pixels that are
     clearly a soft cast shadow (noticeably grayer/darker than the paper)
     keep partial-to-full opacity -- so shadows fade out gracefully instead
     of vanishing with the paper.
  4. De-halos the soft edge band (removes the white bleed that anti-aliasing
     against the old white canvas would otherwise leave behind).
  5. Crops to the character's bounding box + padding (kept within 24-48px so
     nothing is cropped tight).
  6. Sanity-checks the result before writing (skips + warns instead of
     saving something obviously broken).

Run with:
    python frontend/scripts/remove-shiori-backgrounds.py
"""

import os
import sys

import cv2
import numpy as np
from PIL import Image

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "brand", "shiori")
BACKUP_DIR = os.path.join(ASSET_DIR, "_backup")

VARIANTS = [
    "default", "hero", "reading", "classify", "save",
    "review", "success", "empty", "loading",
]

# Distance-from-background-color band (0-441, euclidean over RGB) used to
# turn the flood-connected "background candidate" region into a soft alpha
# ramp: below LOW -> fully transparent (pure paper white), above HIGH ->
# fully opaque (clearly shadow/character, not paper). Between the two,
# alpha ramps smoothly so a faint cast shadow fades rather than vanishing.
LOW = 6
HIGH = 34

# How far the flood fill is allowed to travel from the sampled background
# color before it's considered "not background anymore" -- this is what
# actually protects the cream body/outline/props; keep it below the typical
# white-vs-cream gap seen in these assets (~20-30 in the blue channel) so a
# smooth white->cream gradient can't get eaten in the absence of a hard
# outline edge.
FLOOD_DIFF = 18

# Some silhouettes have small fully-enclosed gaps (e.g. the notch between the
# two leg/tail flaps) that show background peeking through but aren't
# reachable by the border flood fill since the outline stroke seals them off
# topologically. Those pixels are still essentially the same paper-white
# color, just disconnected -- so catch them with a tight, non-flood, global
# distance check (well below the white/cream gap of ~24, so the cream body
# itself can never match).
HOLE_DIST = 10

MIN_PADDING = 32
MAX_PADDING = 48


def sample_background_color(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    ring = 4
    border_pixels = np.concatenate([
        rgb[:ring, :, :].reshape(-1, 3),
        rgb[-ring:, :, :].reshape(-1, 3),
        rgb[:, :ring, :].reshape(-1, 3),
        rgb[:, -ring:, :].reshape(-1, 3),
    ])
    return np.median(border_pixels, axis=0)


def flood_background_mask(rgb: np.ndarray, bg_color: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    # Pad by 2px with the sampled bg color so every border pixel is
    # guaranteed connected to one seed point, regardless of noise in the
    # original canvas edge.
    padded = np.pad(rgb, ((2, 2), (2, 2), (0, 0)), mode="constant")
    padded[:2, :, :] = bg_color
    padded[-2:, :, :] = bg_color
    padded[:, :2, :] = bg_color
    padded[:, -2:, :] = bg_color
    padded = padded.astype(np.uint8).copy()

    # cv2.floodFill requires mask.shape == (padded.rows + 2, padded.cols + 2).
    mask = np.zeros((h + 6, w + 6), dtype=np.uint8)
    diff = (float(FLOOD_DIFF),) * 3
    cv2.floodFill(
        padded,
        mask,
        seedPoint=(0, 0),
        newVal=(0, 0, 0),
        loDiff=diff,
        upDiff=diff,
        flags=cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | 8 | (255 << 8),
    )
    # cv2's flood mask is padded by 1px beyond even our own padding.
    inner = mask[3:-3, 3:-3]
    return inner.astype(bool)


def build_alpha(rgb: np.ndarray, bg_color: np.ndarray, candidate_bg: np.ndarray) -> np.ndarray:
    dist = np.linalg.norm(rgb.astype(np.float32) - bg_color.astype(np.float32), axis=2)
    enclosed_hole = dist < HOLE_DIST
    candidate = candidate_bg | enclosed_hole
    ramp = np.clip((dist - LOW) / (HIGH - LOW), 0.0, 1.0)
    alpha = np.where(candidate, ramp, 1.0)
    # Soften the transition band by 1px so the cut doesn't look jagged.
    alpha = cv2.GaussianBlur(alpha.astype(np.float32), (3, 3), sigmaX=0.6)
    return np.clip(alpha, 0.0, 1.0)


def decontaminate(rgb: np.ndarray, alpha: np.ndarray, bg_color: np.ndarray) -> np.ndarray:
    rgb_f = rgb.astype(np.float32)
    a = alpha[..., None]
    safe_a = np.clip(a, 0.08, 1.0)
    unmixed = (rgb_f - (1.0 - a) * bg_color) / safe_a
    out = np.where(a > 0.08, unmixed, rgb_f)
    return np.clip(out, 0, 255)


def crop_with_padding(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3]
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0 or len(ys) == 0:
        return rgba
    h, w = alpha.shape
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    pad = MIN_PADDING
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad + 1)
    y1 = min(h, y1 + pad + 1)
    return rgba[y0:y1, x0:x1, :]


def process_one(variant: str) -> str:
    path = os.path.join(ASSET_DIR, f"shiori-{variant}.png")
    if not os.path.exists(path):
        return f"[{variant}] SKIP -- file missing"

    img = Image.open(path).convert("RGB")
    rgb = np.array(img)
    total_px = rgb.shape[0] * rgb.shape[1]

    if img.mode == "RGBA":
        pass  # handled by convert("RGB") above intentionally for a clean re-derive

    bg_color = sample_background_color(rgb)
    candidate_bg = flood_background_mask(rgb, bg_color)
    candidate_px = int(candidate_bg.sum())

    if candidate_px < total_px * 0.02:
        return (
            f"[{variant}] SKIP -- flood fill only reached {candidate_px / total_px:.1%} "
            "of the canvas, suspiciously small; left original untouched"
        )
    if candidate_px > total_px * 0.97:
        return (
            f"[{variant}] SKIP -- flood fill reached {candidate_px / total_px:.1%} "
            "of the canvas, suspiciously large (risk of eating the character); "
            "left original untouched"
        )

    alpha = build_alpha(rgb, bg_color, candidate_bg)
    decontaminated_rgb = decontaminate(rgb, alpha, bg_color)

    rgba = np.dstack([decontaminated_rgb, alpha * 255.0]).astype(np.uint8)
    cropped = crop_with_padding(rgba)

    fg_px = int((cropped[..., 3] > 10).sum())
    if fg_px < 500:
        return f"[{variant}] SKIP -- resulting foreground is basically empty; left original untouched"

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"shiori-{variant}.png")
    if not os.path.exists(backup_path):
        img.save(backup_path)

    out_img = Image.fromarray(cropped, mode="RGBA")
    out_img.save(path)

    made_transparent_pct = 100.0 * (1.0 - alpha.mean())
    return (
        f"[{variant}] OK -- {rgb.shape[1]}x{rgb.shape[0]} -> {cropped.shape[1]}x{cropped.shape[0]}, "
        f"~{made_transparent_pct:.1f}% of original canvas made transparent"
    )


def main():
    for variant in VARIANTS:
        print(process_one(variant))


if __name__ == "__main__":
    sys.exit(main())
