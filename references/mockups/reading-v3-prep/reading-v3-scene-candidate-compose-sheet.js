const sharp = require("sharp");
const PREP_DIR = "../references/mockups/reading-v3-prep";
const SRC = "public/brand/decor/v2/v2-reading-open-book-desktop-16x9.webp";
const MARGIN = 188, CENTER_W = 1672, H = 941, CANVAS_W = CENTER_W + MARGIN * 2;

async function main() {
  // ---- center-preservation diff (secondary evidence only) ----
  const { data: srcData } = await sharp(SRC).raw().toBuffer({ resolveWithObject: true });
  const { data: candData, info: candInfo } = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-2048x941.webp`).raw().toBuffer({ resolveWithObject: true });
  const diffBuf = Buffer.alloc(CENTER_W * H * 3);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < CENTER_W; x++) {
      for (let c = 0; c < 3; c++) {
        const a = srcData[(y * CENTER_W + x) * 3 + c];
        const b = candData[(y * CANVAS_W + (x + MARGIN)) * candInfo.channels + c];
        diffBuf[(y * CENTER_W + x) * 3 + c] = Math.min(255, Math.abs(a - b) * 40);
      }
    }
  }
  const diffSmall = await sharp(diffBuf, { raw: { width: CENTER_W, height: H, channels: 3 } }).resize({ width: 700 }).png().toBuffer();
  const diffMeta = await sharp(diffSmall).metadata();

  const full = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-preview-1920.webp`).resize({ width: 1400 }).png().toBuffer();
  const fullMeta = await sharp(full).metadata();

  const seamL100 = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-seam-left-100.png`).png().toBuffer();
  const seamR100 = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-seam-right-100.png`).png().toBuffer();
  const l100Meta = await sharp(seamL100).metadata();
  const r100Meta = await sharp(seamR100).metadata();

  const seamL4x = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-seam-left-4x.png`).png().toBuffer();
  const seamR4x = await sharp(`${PREP_DIR}/reading-v3-scene-candidate-seam-right-4x.png`).png().toBuffer();
  const l4xMeta = await sharp(seamL4x).metadata();
  const r4xMeta = await sharp(seamR4x).metadata();

  const PAD = 24;
  const row2H = Math.max(l100Meta.height, r100Meta.height);
  const row3H = Math.max(l4xMeta.height, r4xMeta.height);
  const row2W = l100Meta.width + PAD + r100Meta.width;
  const row3W = l4xMeta.width + PAD + r4xMeta.width;
  const row4Top = PAD * 3 + fullMeta.height + row2H + row3H + PAD * 2;
  const sheetW = Math.max(fullMeta.width, row2W, row3W, diffMeta.width) + PAD * 2;
  const sheetH = row4Top + diffMeta.height + PAD;

  const bg = { r: 232, g: 230, b: 224 };
  const composites = [
    { input: full, left: PAD, top: PAD },
    { input: seamL100, left: PAD, top: PAD * 2 + fullMeta.height + PAD },
    { input: seamR100, left: PAD + l100Meta.width + PAD, top: PAD * 2 + fullMeta.height + PAD },
    { input: seamL4x, left: PAD, top: PAD * 3 + fullMeta.height + row2H + PAD },
    { input: seamR4x, left: PAD + l4xMeta.width + PAD, top: PAD * 3 + fullMeta.height + row2H + PAD },
    { input: diffSmall, left: PAD, top: row4Top },
  ];

  await sharp({ create: { width: sheetW, height: sheetH, channels: 3, background: bg } })
    .composite(composites)
    .png()
    .toFile(`${PREP_DIR}/reading-v3-scene-candidate-contact-sheet.png`);

  console.log("contact sheet:", sheetW, "x", sheetH);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
