// Gate A rework -- real patch-based wood texture synthesis (image quilting
// with minimum-error-boundary cuts, Efros/Freeman-style) instead of a flat
// averaged tone. The flat-tone candidate was rejected: margins read as a
// uniform vertical band with a visible seam. This version builds the
// margins entirely out of real photographed wood-grain pixels (from two
// hand-verified prop-free desk patches in the source photo itself), so
// grain direction, brightness variation, and fine color deviation are
// continuous and non-uniform -- no generative model involved, this is
// classical texture synthesis over real pixel data.
const sharp = require("sharp");
const crypto = require("crypto");
const fs = require("fs");

const SRC = "public/brand/decor/v2/v2-reading-open-book-desktop-16x9.webp";
const PREP_DIR = "../references/mockups/reading-v3-prep";
const MARGIN = 188;
const CENTER_W = 1672;
const H = 941;
const CANVAS_W = CENTER_W + MARGIN * 2;

// Width and height are decoupled on purpose. A square patch tied to the
// source's narrow ~50px width forced ~40 horizontal seams to cover 941px
// of height; even jittered/staggered, that many roughly-horizontal min-cut
// lines read collectively as a fine horizontal ridge texture -- not the
// source's actual grain direction. Tall, narrow patches (most of the
// source's own height, modest width) need only ~4-5 vertical seams per
// column, so seam density stops reading as a texture of its own.
const PATCH_W = 60;
const OVERLAP_W = 44;
const STEP_W = PATCH_W - OVERLAP_W;
const PATCH_H = 260;
const OVERLAP_H = 70;
const STEP_H = PATCH_H - OVERLAP_H;
const CANDIDATES = 900; // random candidate offsets evaluated per cell
const RAND_SEED = 88172645;

function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(RAND_SEED);
const randInt = (n) => Math.floor(rand() * n);

function gridPositions(total, patch, step) {
  const positions = [0];
  let x = step;
  while (x < total - patch) {
    positions.push(x);
    x += step;
  }
  if (total > patch) positions.push(total - patch);
  return positions;
}

// A regular grid puts every horizontal seam at the same set of rows in
// every column, so even a well-matched min-cut can leave a faint but
// perfectly periodic ridge every STEP px -- a repeating pattern, which is
// exactly what's forbidden. Jittering each column's row spacing
// independently (own RNG draw per step) staggers seams brick-style so any
// residual seam reads as an isolated grain irregularity, not a rule.
function jitteredRowPositions(total, patch, step, jitterMax, rand) {
  const positions = [0];
  let y = 0;
  while (true) {
    const jitter = Math.round((rand() * 2 - 1) * jitterMax);
    const next = y + step + jitter;
    if (next >= total - patch) break;
    positions.push(next);
    y = next;
  }
  if (total > patch) positions.push(total - patch);
  return positions;
}

async function main() {
  const { data, info } = await sharp(SRC).raw().toBuffer({ resolveWithObject: true });
  const channels = info.channels;
  const px = (x, y, c) => data[(y * CENTER_W + x) * channels + c];

  // ---- Source texture patches (verified prop-free by visual crop check) --
  const srcLRect = { left: 0, top: 345, width: 65, height: 420 };
  const srcRRect = { left: 1605, top: 195, width: 60, height: 480 };

  function extractSource(rect) {
    const { left, top, width, height } = rect;
    const buf = new Float64Array(width * height * 3);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        for (let c = 0; c < 3; c++) {
          buf[(y * width + x) * 3 + c] = px(left + x, top + y, c);
        }
      }
    }
    return { buf, width, height };
  }
  const srcL = extractSource(srcLRect);
  const srcR = extractSource(srcRRect);

  // Local-mean map (15x15 box) per source, used to split each source patch
  // into a low-frequency base (its own local average) and a detail signal
  // (fine grain/color deviation). We keep the *detail* when placing a patch
  // and re-add the *target* location's own fitted lighting -- so grain
  // stays exactly as photographed, only its brightness baseline moves to
  // agree with where it lands. This is a luminance-transfer step performed
  // once per source pixel, not a blur applied to the rendered output: the
  // final image's high-frequency content is the original detail, untouched.
  function localMeanMap(src) {
    const { buf, width, height } = src;
    const R = 18; // wider box: pulls more of the patch-to-patch shading
                  // drift into the "low-frequency" side so detail-space
                  // matching compares fine grain only, not local shading

    const out = new Float64Array(width * height * 3);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        let rs = 0, gs = 0, bs = 0, n = 0;
        for (let dy = -R; dy <= R; dy++) {
          const yy = y + dy;
          if (yy < 0 || yy >= height) continue;
          for (let dx = -R; dx <= R; dx++) {
            const xx = x + dx;
            if (xx < 0 || xx >= width) continue;
            const i = (yy * width + xx) * 3;
            rs += buf[i]; gs += buf[i + 1]; bs += buf[i + 2]; n++;
          }
        }
        const o = (y * width + x) * 3;
        out[o] = rs / n; out[o + 1] = gs / n; out[o + 2] = bs / n;
      }
    }
    return out;
  }
  const meanL = localMeanMap(srcL);
  const meanR = localMeanMap(srcR);

  function detailAt(src, mean, sx, sy, c) {
    const i = (sy * src.width + sx) * 3 + c;
    return src.buf[i] - mean[i];
  }

  // ---- Low-frequency lighting trend per side --------------------------
  // A 2-point linear fit (top-half vs bottom-half average of the SAME
  // clean patch), extrapolated across the full 0..941 height. Sampling is
  // confined entirely to the verified prop-free rectangles, so there is
  // no risk of leaking mat/pebble/leaf color into the trend the way the
  // rejected candidate's per-row sampling did. Linear (not radial), so it
  // reads as directional room light continuing, not a vignette.
  function halfAverages(src) {
    const { buf, width, height } = src;
    const half = Math.floor(height / 2);
    function avg(y0, y1) {
      let rs = 0, gs = 0, bs = 0, n = 0;
      for (let y = y0; y < y1; y++) {
        for (let x = 0; x < width; x++) {
          const i = (y * width + x) * 3;
          rs += buf[i]; gs += buf[i + 1]; bs += buf[i + 2]; n++;
        }
      }
      return [rs / n, gs / n, bs / n];
    }
    return { top: avg(0, half), bottom: avg(half, height), topMidY: half / 2, bottomMidY: half + (height - half) / 2 };
  }
  const halfL = halfAverages(srcL);
  const halfR = halfAverages(srcR);

  function lightingField(rect, half) {
    const topMidYAbs = rect.top + half.topMidY;
    const bottomMidYAbs = rect.top + half.bottomMidY;
    const span = bottomMidYAbs - topMidYAbs;
    return function (yAbs) {
      const t = (yAbs - topMidYAbs) / span;
      return [
        half.top[0] + (half.bottom[0] - half.top[0]) * t,
        half.top[1] + (half.bottom[1] - half.top[1]) * t,
        half.top[2] + (half.bottom[2] - half.top[2]) * t,
      ];
    };
  }
  const lightL = lightingField(srcLRect, halfL);
  const lightR = lightingField(srcRRect, halfR);

  // ---- Quilting fill ----------------------------------------------------
  // seamPull (optional): biases candidate selection, for cells within
  // `zone` px of the TRUE photo edge, toward source offsets whose
  // reconstructed color resembles the real photo's own pixels just inside
  // that edge. There is no pixel overlap to cut through at that boundary
  // (the real photo isn't reproduced twice), so this is a selection bias
  // across a 60-100px band rather than a geometric seam -- it is what
  // makes the last few columns of quilted patches "lean toward" the real
  // edge instead of being chosen with no awareness of it at all.
  function quiltFill(src, mean, lightFn, canvasYOffset, seamPull) {
    const canvas = new Float64Array(MARGIN * H * 3).fill(NaN);
    const assign = new Array(MARGIN * H).fill(null); // {sx,sy} per pixel, for overlap SSD lookups

    function setPixel(cx, cy, sx, sy) {
      const yAbs = canvasYOffset + cy;
      const field = lightFn(yAbs);
      const o = (cy * MARGIN + cx) * 3;
      canvas[o] = field[0] + detailAt(src, mean, sx, sy, 0);
      canvas[o + 1] = field[1] + detailAt(src, mean, sx, sy, 1);
      canvas[o + 2] = field[2] + detailAt(src, mean, sx, sy, 2);
      assign[cy * MARGIN + cx] = [sx, sy];
    }

    const xs = gridPositions(MARGIN, PATCH_W, STEP_W);
    const maxSx = src.width - PATCH_W;
    const maxSy = src.height - PATCH_H;
    const JITTER_H = Math.max(15, Math.floor(STEP_H / 4));
    // Column-major: each column gets its own independently-jittered row
    // grid (see jitteredRowPositions) so horizontal seams stagger instead
    // of lining up into a periodic ridge across the full margin width.
    const ysByColumn = xs.map(() => jitteredRowPositions(H, PATCH_H, STEP_H, JITTER_H, rand));

    for (let gj = 0; gj < xs.length; gj++) {
      const ys = ysByColumn[gj];
      for (let gi = 0; gi < ys.length; gi++) {
        const tx = xs[gj], ty = ys[gi];
        const hasLeft = gj > 0;
        const hasTop = gi > 0;
        const leftOverlapW = hasLeft ? xs[gj - 1] + PATCH_W - tx : 0;
        const topOverlapH = hasTop ? ys[gi - 1] + PATCH_H - ty : 0;

        // ---- pick a candidate source offset ----
        let bestErr = Infinity, bestSx = 0, bestSy = 0;
        const tries = maxSx <= 0 || maxSy <= 0 ? 1 : CANDIDATES;
        for (let t = 0; t < tries; t++) {
          const sx = maxSx <= 0 ? 0 : randInt(maxSx + 1);
          const sy = maxSy <= 0 ? 0 : randInt(maxSy + 1);
          let err = 0;
          if (hasLeft) {
            for (let dy = 0; dy < PATCH_H; dy++) {
              const cy = ty + dy;
              if (cy >= H) continue;
              for (let dx = 0; dx < leftOverlapW; dx++) {
                const cx = tx + dx;
                const a = assign[cy * MARGIN + cx];
                if (!a) continue;
                for (let c = 0; c < 3; c++) {
                  const dA = detailAt(src, mean, a[0], a[1], c);
                  const dB = detailAt(src, mean, sx + dx, sy + dy, c);
                  const diff = dA - dB;
                  err += diff * diff;
                }
              }
            }
          }
          if (hasTop) {
            for (let dy = 0; dy < topOverlapH; dy++) {
              const cy = ty + dy;
              if (cy >= H) continue;
              for (let dx = 0; dx < PATCH_W; dx++) {
                const cx = tx + dx;
                if (cx >= MARGIN) continue;
                const a = assign[cy * MARGIN + cx];
                if (!a) continue;
                for (let c = 0; c < 3; c++) {
                  const dA = detailAt(src, mean, a[0], a[1], c);
                  const dB = detailAt(src, mean, sx + dx, sy + dy, c);
                  const diff = dA - dB;
                  err += diff * diff;
                }
              }
            }
          }
          if (seamPull) {
            const { seamAtRight, trueColorFor, zone, strength } = seamPull;
            const patchMinDist = seamAtRight
              ? Math.max(0, MARGIN - 1 - Math.min(MARGIN - 1, tx + PATCH_W - 1))
              : tx;
            if (patchMinDist < zone) {
              for (let dy = 0; dy < PATCH_H; dy++) {
                const cy = ty + dy;
                if (cy >= H) continue;
                const yAbs = canvasYOffset + cy;
                const field = lightFn(yAbs);
                for (let dx = 0; dx < PATCH_W; dx++) {
                  const cx = tx + dx;
                  if (cx >= MARGIN) continue;
                  const dist = seamAtRight ? MARGIN - 1 - cx : cx;
                  if (dist >= zone) continue;
                  const w = strength * (1 - dist / zone);
                  const trueColor = trueColorFor(dist, yAbs);
                  for (let c = 0; c < 3; c++) {
                    const cand = field[c] + detailAt(src, mean, sx + dx, sy + dy, c);
                    const diff = cand - trueColor[c];
                    err += w * diff * diff;
                  }
                }
              }
            }
          }
          if (err < bestErr) {
            bestErr = err; bestSx = sx; bestSy = sy;
          }
        }
        const sx = bestSx, sy = bestSy;

        // ---- decide, per pixel of this patch, old(neighbor) vs new(candidate) ----
        const keepOld = new Uint8Array(PATCH_W * PATCH_H); // 1 = keep whatever is already in canvas

        if (hasLeft && leftOverlapW > 0) {
          // vertical min-cut across the left overlap band (x: 0..leftOverlapW-1 local)
          const w = leftOverlapW;
          const hgt = Math.min(PATCH_H, H - ty);
          const cost = new Float64Array(w * hgt);
          for (let dy = 0; dy < hgt; dy++) {
            const cy = ty + dy;
            for (let dx = 0; dx < w; dx++) {
              const cx = tx + dx;
              const a = assign[cy * MARGIN + cx];
              let e = 0;
              if (a) {
                for (let c = 0; c < 3; c++) {
                  const dA = detailAt(src, mean, a[0], a[1], c);
                  const dB = detailAt(src, mean, sx + dx, sy + dy, c);
                  const diff = dA - dB;
                  e += diff * diff;
                }
              }
              cost[dy * w + dx] = e;
            }
          }
          // DP min-cost path top->bottom. A +-1/step DP can't follow a
          // strongly *horizontal* streak crossing the seam -- it needs
          // several columns of lateral travel per row to duck around one.
          // Widening the allowed step to +-STEP_RANGE lets the cut weave
          // along the streak boundary instead of slicing across it.
          const STEP_RANGE = 4;
          const dpCost = new Float64Array(w * hgt);
          const dpFrom = new Int8Array(w * hgt);
          for (let x = 0; x < w; x++) dpCost[x] = cost[x];
          for (let y = 1; y < hgt; y++) {
            for (let x = 0; x < w; x++) {
              let best = Infinity, from = 0;
              for (let k = -STEP_RANGE; k <= STEP_RANGE; k++) {
                const px2 = x + k;
                if (px2 < 0 || px2 >= w) continue;
                const v = dpCost[(y - 1) * w + px2];
                if (v < best) { best = v; from = k; }
              }
              dpCost[y * w + x] = best + cost[y * w + x];
              dpFrom[y * w + x] = from;
            }
          }
          let minX = 0, minV = dpCost[(hgt - 1) * w];
          for (let x = 1; x < w; x++) if (dpCost[(hgt - 1) * w + x] < minV) { minV = dpCost[(hgt - 1) * w + x]; minX = x; }
          const seamX = new Int32Array(hgt);
          seamX[hgt - 1] = minX;
          for (let y = hgt - 1; y > 0; y--) {
            seamX[y - 1] = seamX[y] + dpFrom[y * w + seamX[y]];
          }
          for (let dy = 0; dy < hgt; dy++) {
            for (let dx = 0; dx < w; dx++) {
              if (dx < seamX[dy]) keepOld[dy * PATCH_W + dx] = 1;
            }
          }
        }

        if (hasTop && topOverlapH > 0) {
          const hgt = topOverlapH;
          const w = Math.min(PATCH_W, MARGIN - tx);
          const cost = new Float64Array(w * hgt);
          for (let dx = 0; dx < w; dx++) {
            const cx = tx + dx;
            for (let dy = 0; dy < hgt; dy++) {
              const cy = ty + dy;
              const a = assign[cy * MARGIN + cx];
              let e = 0;
              if (a) {
                for (let c = 0; c < 3; c++) {
                  const dA = detailAt(src, mean, a[0], a[1], c);
                  const dB = detailAt(src, mean, sx + dx, sy + dy, c);
                  const diff = dA - dB;
                  e += diff * diff;
                }
              }
              cost[dx * hgt + dy] = e;
            }
          }
          // DP min-cost path left->right, step y by -1/0/+1
          const dpCost = new Float64Array(w * hgt);
          const dpFrom = new Int8Array(w * hgt);
          for (let y = 0; y < hgt; y++) dpCost[y] = cost[y];
          for (let x = 1; x < w; x++) {
            for (let y = 0; y < hgt; y++) {
              let best = dpCost[x * hgt - hgt + y], from = 0; // (x-1)*hgt + y
              const base = (x - 1) * hgt;
              best = dpCost[base + y];
              if (y > 0 && dpCost[base + y - 1] < best) { best = dpCost[base + y - 1]; from = -1; }
              if (y < hgt - 1 && dpCost[base + y + 1] < best) { best = dpCost[base + y + 1]; from = 1; }
              dpCost[x * hgt + y] = best + cost[x * hgt + y];
              dpFrom[x * hgt + y] = from;
            }
          }
          let minY = 0, minV = dpCost[(w - 1) * hgt];
          for (let y = 1; y < hgt; y++) if (dpCost[(w - 1) * hgt + y] < minV) { minV = dpCost[(w - 1) * hgt + y]; minY = y; }
          const seamY = new Int32Array(w);
          seamY[w - 1] = minY;
          for (let x = w - 1; x > 0; x--) {
            seamY[x - 1] = seamY[x] + dpFrom[x * hgt + seamY[x]];
          }
          for (let dx = 0; dx < w; dx++) {
            for (let dy = 0; dy < seamY[dx] && dy < hgt; dy++) {
              // only mark as "keep old" if not already claimed as new by the
              // vertical seam decision above (vertical seam takes priority
              // in the small L-shaped corner where both overlaps meet)
              if (!(hasLeft && dx < leftOverlapW && keepOld[dy * PATCH_W + dx] === 0)) {
                keepOld[dy * PATCH_W + dx] = 1;
              }
            }
          }
        }

        // ---- write the patch ----
        const hgt = Math.min(PATCH_H, H - ty);
        const w = Math.min(PATCH_W, MARGIN - tx);
        for (let dy = 0; dy < hgt; dy++) {
          const cy = ty + dy;
          for (let dx = 0; dx < w; dx++) {
            const cx = tx + dx;
            if (keepOld[dy * PATCH_W + dx] && assign[cy * MARGIN + cx]) continue;
            setPixel(cx, cy, sx + dx, sy + dy);
          }
        }
      }
    }

    // Any never-assigned pixel (shouldn't happen given grid coverage) --
    // fall back to the lighting field alone.
    for (let cy = 0; cy < H; cy++) {
      for (let cx = 0; cx < MARGIN; cx++) {
        if (!assign[cy * MARGIN + cx]) {
          const field = lightFn(canvasYOffset + cy);
          const o = (cy * MARGIN + cx) * 3;
          canvas[o] = field[0]; canvas[o + 1] = field[1]; canvas[o + 2] = field[2];
        }
      }
    }
    return canvas;
  }

  const SEAM_ZONE = 90; // 60-100px continuation band requested
  const SEAM_STRENGTH = 1; // modest bias toward the true edge, tuned so it nudges selection without overriding internal texture-match quality
  const seamPullL = {
    seamAtRight: true,
    trueColorFor: (k, y) => [px(k, y, 0), px(k, y, 1), px(k, y, 2)],
    zone: SEAM_ZONE,
    strength: SEAM_STRENGTH,
  };
  const seamPullR = {
    seamAtRight: false,
    trueColorFor: (k, y) => [px(CENTER_W - 1 - k, y, 0), px(CENTER_W - 1 - k, y, 1), px(CENTER_W - 1 - k, y, 2)],
    zone: SEAM_ZONE,
    strength: SEAM_STRENGTH,
  };

  console.log("quilting left margin...");
  const leftCanvas = quiltFill(srcL, meanL, lightL, 0, seamPullL);
  console.log("quilting right margin...");
  const rightCanvas = quiltFill(srcR, meanR, lightR, 0, seamPullR);

  function toBuf8(f64) {
    const out = Buffer.alloc(f64.length);
    for (let i = 0; i < f64.length; i++) out[i] = Math.max(0, Math.min(255, Math.round(f64[i])));
    return out;
  }
  const leftBuf = toBuf8(leftCanvas);
  const rightBuf = toBuf8(rightCanvas);

  // ---- Composite final canvas --------------------------------------------
  const canvasBuf = Buffer.alloc(CANVAS_W * H * 3);
  for (let y = 0; y < H; y++) {
    const srcRowStart = y * CENTER_W * 3;
    const dstRowStart = y * CANVAS_W * 3;
    leftBuf.copy(canvasBuf, dstRowStart, y * MARGIN * 3, (y + 1) * MARGIN * 3);
    data.copy(canvasBuf, dstRowStart + MARGIN * 3, srcRowStart, srcRowStart + CENTER_W * 3);
    rightBuf.copy(canvasBuf, dstRowStart + (MARGIN + CENTER_W) * 3, y * MARGIN * 3, (y + 1) * MARGIN * 3);
  }

  const candidate = sharp(canvasBuf, { raw: { width: CANVAS_W, height: H, channels: 3 } });
  await candidate.clone().webp({ lossless: true }).toFile(`${PREP_DIR}/reading-v3-scene-candidate-2048x941.webp`);

  // ---- Verification: center pixel-identical ------------------------------
  const { data: rtData, info: rtInfo } = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-2048x941.webp`).raw().toBuffer({ resolveWithObject: true });
  let maxDiff = 0, diffCount = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < CENTER_W; x++) {
      for (let c = 0; c < 3; c++) {
        const a = px(x, y, c);
        const b = rtData[(y * CANVAS_W + (x + MARGIN)) * rtInfo.channels + c];
        const d = Math.abs(a - b);
        if (d > maxDiff) maxDiff = d;
        if (d !== 0) diffCount++;
      }
    }
  }
  console.log("center verification: maxDiff=", maxDiff, "diffPixelChannels=", diffCount);

  const srcHash = crypto.createHash("sha256").update(fs.readFileSync(SRC)).digest("hex");
  const candHash = crypto.createHash("sha256").update(fs.readFileSync(`${PREP_DIR}/reading-v3-scene-candidate-2048x941.webp`)).digest("hex");
  console.log("source sha256:", srcHash);
  console.log("candidate sha256:", candHash);

  // ---- Previews -----------------------------------------------------------
  await candidate.clone().resize({ width: 1920 }).webp({ quality: 92 }).toFile(`${PREP_DIR}/reading-v3-scene-candidate-preview-1920.webp`);

  await sharp(canvasBuf, { raw: { width: CANVAS_W, height: H, channels: 3 } })
    .extract({ left: 0, top: 0, width: 300, height: H })
    .png()
    .toFile(`${PREP_DIR}/reading-v3-scene-candidate-seam-left-100.png`);
  await sharp(canvasBuf, { raw: { width: CANVAS_W, height: H, channels: 3 } })
    .extract({ left: CANVAS_W - 300, top: 0, width: 300, height: H })
    .png()
    .toFile(`${PREP_DIR}/reading-v3-scene-candidate-seam-right-100.png`);
  await sharp(canvasBuf, { raw: { width: CANVAS_W, height: H, channels: 3 } })
    .extract({ left: MARGIN - 90, top: 380, width: 180, height: 180 })
    .resize({ width: 720 })
    .png()
    .toFile(`${PREP_DIR}/reading-v3-scene-candidate-seam-left-4x.png`);
  await sharp(canvasBuf, { raw: { width: CANVAS_W, height: H, channels: 3 } })
    .extract({ left: CANVAS_W - MARGIN - 90, top: 380, width: 180, height: 180 })
    .resize({ width: 720 })
    .png()
    .toFile(`${PREP_DIR}/reading-v3-scene-candidate-seam-right-4x.png`);

  console.log("done");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
