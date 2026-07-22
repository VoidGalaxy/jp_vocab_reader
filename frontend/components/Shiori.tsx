"use client";

// Shiori (시오리) character system -- the app's bookmark-guide brand face.
// Locked shape rules: reads as a bookmark first (rounded-top ribbon, clear
// V-notch tail, a small loop-and-tassel at the top), a small guide
// character second. Deep-teal face/line, cream paper body, amber/coral used
// only for small per-variant accents -- never a fourth color. No external
// image assets: every shape here is a plain SVG path/circle/line so the
// character renders identically everywhere it's used.
//
// Character pass 2: the face plate used to fill almost the entire straight
// top edge of the ribbon, so it read as "a rectangle icon with a face" --
// shrunk here to a smaller inset plate with visible cream border around it,
// plus a small set of per-variant eyebrow/eye/mouth shapes and (at md+
// sizes only) a pair of short arm stubs holding a tiny prop (a word card, a
// pencil-check, an empty card box, ...). "sm" size (inline marks/stamps)
// deliberately skips the arms/eyebrows -- at ~28px wide those would just be
// noise -- and keeps the plain face+eyes+mouth read.

export type ShioriVariant =
  | "default"
  | "reading"
  | "save"
  | "classify"
  | "review"
  | "success"
  | "empty"
  | "loading";

export type ShioriSize = "sm" | "md" | "lg" | "hero";

// "empty"/"loading" read as at-rest (closed eyes); "success" reads as
// beaming (upward happy-arc eyes); every other variant is alert (open dot
// eyes).
const restingEyeVariants = new Set<ShioriVariant>(["empty", "loading"]);
const happyEyeVariants = new Set<ShioriVariant>(["success"]);

const mouthByVariant: Record<ShioriVariant, string> = {
  default: "M26.5 33 Q32 36.5 37.5 33",
  reading: "M26 32.5 Q32 38 38 32.5",
  save: "M26.5 33 Q32 36.5 37.5 33",
  classify: "M26 33.5 Q33 37.5 38.5 32.5",
  review: "M26.5 33 Q32 36.5 37.5 33",
  success: "M25.5 31.5 Q32 41 38.5 31.5",
  empty: "M28 35 H36",
  loading: "M28 34.5 Q32 36 36 34.5",
};

// Small eyebrow flourish -- only on the three variants where it actually
// reads as an expression (curious/focused/sly) at a glance; every other
// variant stays brow-less rather than force an expression that doesn't fit.
const browsByVariant: Partial<Record<ShioriVariant, { left: string; right: string }>> = {
  reading: { left: "M24 24.5 Q26.5 22 29 23.5", right: "M35 23.5 Q37.5 22 40 24.5" },
  classify: { left: "M24 22.5 Q26.5 20 29.5 22", right: "M35.5 24 Q38 23.5 40 24.5" },
  review: { left: "M24.5 23 H29", right: "M35 23 H39.5" },
};

// The one shared silhouette every Shiori piece (character/mark/stamp) draws
// from -- rounded-top ribbon body, clear V-cut tail. Exported so ShioriMark
// can reuse the exact same path without duplicating the "d" string.
const bookmarkBodyPath =
  "M14 2 H50 A12 12 0 0 1 62 14 V84 L32 63 L2 84 V14 A12 12 0 0 1 14 2 Z";

// Shrunk, inset face plate -- leaves a visible cream border on every side
// instead of filling the ribbon's whole straight-edge top (the previous
// "rectangle with a face" look).
const facePlate = { x: 20, y: 18, width: 24, height: 22, rx: 11 };

function ShioriFacePlate({ variant }: { variant: ShioriVariant }) {
  const isResting = restingEyeVariants.has(variant);
  const isHappy = happyEyeVariants.has(variant);
  return (
    <>
      <rect
        className="shiori-face"
        x={facePlate.x}
        y={facePlate.y}
        width={facePlate.width}
        height={facePlate.height}
        rx={facePlate.rx}
      />
      {isResting ? (
        <>
          <line className="shiori-eye-closed" x1="24.5" y1="28" x2="29" y2="28" />
          <line className="shiori-eye-closed" x1="35" y1="28" x2="39.5" y2="28" />
        </>
      ) : isHappy ? (
        <>
          <path className="shiori-eye-happy" d="M24.5 30 Q26.5 25.5 28.5 30" />
          <path className="shiori-eye-happy" d="M35.5 30 Q37.5 25.5 39.5 30" />
        </>
      ) : (
        <>
          <circle className="shiori-eye" cx="26.5" cy="28" r="2.1" />
          <circle className="shiori-eye" cx="37.5" cy="28" r="2.1" />
        </>
      )}
      <path className="shiori-mouth" d={mouthByVariant[variant]} />
    </>
  );
}

// Per-variant "pose" -- a pair of short arm stubs (never full articulated
// limbs, see .shiori-hand) plus at most one small held prop, so each
// variant reads as a different moment (flipping a card, hugging a card,
// raising a checked pencil, waiting by an empty box, ...) instead of the
// same icon in a different color. Only rendered at md/lg/hero sizes --
// see the isDetailed gate in ShioriCharacter below.
function ShioriPose({ variant }: { variant: ShioriVariant }) {
  switch (variant) {
    case "reading":
      return (
        <>
          <path className="shiori-hand" d="M14 48 Q10 54 13 60" />
          <path className="shiori-hand" d="M49 46 Q57 47 58 54" />
          <rect className="shiori-accent-page" x="49" y="54" width="13" height="9" rx="1.8" />
          <line className="shiori-accent-page-line" x1="52" y1="57.5" x2="59" y2="57.5" />
          <line className="shiori-accent-page-line" x1="52" y1="60.5" x2="57" y2="60.5" />
        </>
      );
    case "classify":
      return (
        <>
          <path className="shiori-hand" d="M14 48 Q10 54 13 60" />
          <path className="shiori-hand" d="M49 44 Q56 42 57 47" />
          <path className="shiori-accent-swoosh" d="M45 36 Q42 38 45 41" />
          <rect
            className="shiori-accent-card"
            x="49"
            y="31"
            width="10"
            height="13"
            rx="2"
            transform="rotate(20 54 37.5)"
          />
        </>
      );
    case "save":
      return (
        <>
          <path className="shiori-hand" d="M12 48 Q20 57 27 55" />
          <path className="shiori-hand" d="M52 48 Q44 57 37 55" />
          <rect className="shiori-accent-card" x="25" y="46" width="14" height="14" rx="2.5" />
          <path className="shiori-accent-check" d="M28 53 L30.5 55.5 L36 49.5" />
        </>
      );
    case "review":
      return (
        <>
          <path className="shiori-hand" d="M14 48 Q10 54 13 60" />
          <path className="shiori-hand" d="M50 46 Q57 40 55 33" />
          <path className="shiori-accent-check" d="M51 33 L54 36 L60 29" />
        </>
      );
    case "success":
      return (
        <>
          <path className="shiori-hand" d="M14 48 Q8 40 11 32" />
          <path className="shiori-hand" d="M50 48 Q56 40 53 32" />
          <path
            className="shiori-accent-sparkle"
            d="M46 8 L48 12 L52 13 L48 14 L46 18 L44 14 L40 13 L44 12 Z"
          />
        </>
      );
    case "empty":
      return (
        <>
          <path className="shiori-hand" d="M14 50 Q10 55 13 60" />
          <path className="shiori-hand" d="M50 50 Q54 55 51 60" />
          <rect className="shiori-empty-box" x="23" y="47" width="18" height="13" rx="2" />
        </>
      );
    case "loading":
      return (
        <>
          <path className="shiori-hand" d="M14 50 Q10 55 13 60" />
          <path className="shiori-hand" d="M50 48 Q56 46 55 52" />
          <path className="shiori-accent-page" d="M50 46 Q56 44 57 49 Q53 49 50 46 Z" />
          <g className="shiori-loading-dots">
            <circle cx="27" cy="47" r="1.8" />
            <circle cx="32" cy="47" r="1.8" />
            <circle cx="37" cy="47" r="1.8" />
          </g>
        </>
      );
    default:
      return (
        <>
          <path className="shiori-hand" d="M14 48 Q10 54 13 60" />
          <path className="shiori-hand" d="M50 48 Q54 54 51 60" />
        </>
      );
  }
}

export function ShioriCharacter({
  variant = "default",
  size = "sm",
  className,
}: {
  variant?: ShioriVariant;
  size?: ShioriSize;
  className?: string;
}) {
  // At icon scale (~28px wide) arm stubs/eyebrows read as stray pixels, not
  // detail -- only md/lg/hero (the sizes actually meant to carry a "this is
  // a character, not a mark" moment) get the full pose.
  const isDetailed = size !== "sm";
  const brows = isDetailed ? browsByVariant[variant] : undefined;

  return (
    <span
      className={`shiori-character shiori-character-${size} shiori-character--${variant}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <svg viewBox="0 -14 64 102" className="shiori-character-svg">
        {/* Loop + tassel -- reads as "a bookmark with a tassel", not just a
            rounded ribbon. */}
        <g className="shiori-tassel">
          <circle cx="32" cy="-8" r="3.4" />
          <line x1="29" y1="-4.6" x2="26" y2="2" />
          <line x1="32" y1="-4.6" x2="32" y2="3" />
          <line x1="35" y1="-4.6" x2="38" y2="2" />
        </g>

        <path className="shiori-bookmark-body" d={bookmarkBodyPath} />

        {brows ? (
          <>
            <path className="shiori-brow" d={brows.left} />
            <path className="shiori-brow" d={brows.right} />
          </>
        ) : null}

        <ShioriFacePlate variant={variant} />

        {isDetailed ? <ShioriPose variant={variant} /> : null}
      </svg>
    </span>
  );
}

// ShioriMark -- the compact inline "brand mark" form: same shrunk face
// plate/eyes/mouth, no tassel/eyebrow/arm detail (at icon size those would
// just be noise). Drop-in replacement anywhere a plain bookmark/section
// icon used to stand in for the character (e.g. the selected-word panel's
// title icon).
export function ShioriMark({
  variant = "default",
  className,
}: {
  variant?: ShioriVariant;
  className?: string;
}) {
  return (
    <span className={`shiori-mark${className ? ` ${className}` : ""}`} aria-hidden="true">
      <svg viewBox="0 0 64 88" className="shiori-mark-svg">
        <path className="shiori-bookmark-body" d={bookmarkBodyPath} />
        <ShioriFacePlate variant={variant} />
      </svg>
    </span>
  );
}

// ShioriStamp -- the "moment just completed" mark: a small Shiori face plus
// an optional short label, read as a postmark stamped in a notebook rather
// than a second illustration next to the real one. Without a label it's
// just the bare character (inline next to a message line); with one it
// picks up the dashed-pill "postmark" chrome. Always renders at "sm" (via
// ShioriCharacter) -- a stamp is a small aside, never a second big
// character next to the real one.
export function ShioriStamp({
  variant = "success",
  label,
  className,
}: {
  variant?: ShioriVariant;
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={`shiori-stamp shiori-stamp--${variant}${label ? " shiori-stamp--labeled" : ""}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <ShioriCharacter variant={variant} size="sm" className="shiori-stamp-character" />
      {label ? <span className="shiori-stamp-label">{label}</span> : null}
    </span>
  );
}

// ShioriGuideCard -- a slim horizontal "Shiori says one quiet line" card
// (icon left, one short message right). Distinct from AppEmptyState's
// fuller icon-top/title/description/actions layout on purpose: this is for
// a single inline hint (e.g. the reading word-inspector's idle state), not
// a full empty-state card with its own actions.
export function ShioriGuideCard({
  variant = "reading",
  size = "md",
  message,
  className,
}: {
  variant?: ShioriVariant;
  size?: ShioriSize;
  message: string;
  className?: string;
}) {
  return (
    <div className={`shiori-guide-card${className ? ` ${className}` : ""}`}>
      <ShioriCharacter variant={variant} size={size} />
      <p className="shiori-guide-card-text">{message}</p>
    </div>
  );
}
