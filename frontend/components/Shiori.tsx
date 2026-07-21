"use client";

// Shiori (시오리) character system -- the app's bookmark-guide brand face.
// Locked shape rules (2026 brand-character pass): reads as a bookmark first
// (rounded-top ribbon, clear V-notch tail, a small loop-and-tassel at the
// top), a quiet guide character second (small paper-tone face plate, two
// dot eyes, one calm mouth). Deep-teal face/line, cream paper body, amber/
// coral used only for small per-variant accents -- never a fourth color.
// No chibi limbs, no external image assets: every shape here is a plain
// SVG path/circle/line so the character renders identically everywhere
// it's used.
//
// One shared geometry (tassel + body + face + eyes) with a small set of
// per-variant differences (mouth curve, one optional small accent mark, and
// -- for "classify" only -- a tiny pointer stub) is what keeps every variant
// reading as the same character instead of eight unrelated drawings.

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

// "empty"/"loading" both read as at-rest (half-closed eyes); every other
// variant is alert (open dot eyes) with a mouth of its own.
const restingEyeVariants = new Set<ShioriVariant>(["empty", "loading"]);

const mouthByVariant: Record<ShioriVariant, string> = {
  default: "M26 36 Q32 39.5 38 36",
  reading: "M25 35 Q32 42 39 35",
  save: "M26 36 Q32 39.5 38 36",
  classify: "M25.5 36.5 Q33 40 38.5 35",
  review: "M26 36 Q32 39.5 38 36",
  success: "M25 35.5 Q32 44.5 39 35.5",
  empty: "M28 37.5 H36",
  loading: "M28 37 Q32 38.5 36 37",
};

// The one shared silhouette every Shiori piece (character/mark/stamp) draws
// from -- rounded-top ribbon body, clear V-cut tail. Exported so ShioriMark
// can reuse the exact same path without duplicating the "d" string.
const bookmarkBodyPath =
  "M14 2 H50 A12 12 0 0 1 62 14 V84 L32 63 L2 84 V14 A12 12 0 0 1 14 2 Z";

export function ShioriCharacter({
  variant = "default",
  size = "sm",
  className,
}: {
  variant?: ShioriVariant;
  size?: ShioriSize;
  className?: string;
}) {
  const isResting = restingEyeVariants.has(variant);

  return (
    <span
      className={`shiori-character shiori-character-${size} shiori-character--${variant}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <svg viewBox="0 -14 64 102" className="shiori-character-svg">
        {/* Loop + tassel -- the one piece the previous bookmark-only
            silhouette was missing, drawn above the body so it always reads
            as "a bookmark with a tassel", not just a rounded ribbon. */}
        <g className="shiori-tassel">
          <circle cx="32" cy="-8" r="3.4" />
          <line x1="29" y1="-4.6" x2="26" y2="2" />
          <line x1="32" y1="-4.6" x2="32" y2="3" />
          <line x1="35" y1="-4.6" x2="38" y2="2" />
        </g>

        <path className="shiori-bookmark-body" d={bookmarkBodyPath} />
        <rect className="shiori-face" x="14" y="16" width="36" height="28" rx="10" />

        {isResting ? (
          <>
            <line className="shiori-eye-closed" x1="23" y1="30" x2="29" y2="30" />
            <line className="shiori-eye-closed" x1="35" y1="30" x2="41" y2="30" />
          </>
        ) : (
          <>
            <circle className="shiori-eye" cx="26" cy="30" r="2.2" />
            <circle className="shiori-eye" cx="38" cy="30" r="2.2" />
          </>
        )}

        <path className="shiori-mouth" d={mouthByVariant[variant]} />

        {variant === "success" ? (
          <path
            className="shiori-accent shiori-accent-sparkle"
            d="M46 8 L48 12 L52 13 L48 14 L46 18 L44 14 L40 13 L44 12 Z"
          />
        ) : null}
        {variant === "save" ? (
          <path className="shiori-accent shiori-accent-check" d="M44 10 L47 13 L53 6" />
        ) : null}
        {variant === "review" ? (
          <circle className="shiori-accent shiori-accent-dot" cx="48" cy="9" r="2.6" />
        ) : null}
        {variant === "classify" ? (
          <>
            <path className="shiori-hand" d="M47 41 Q52 41 53 45" />
            <rect
              className="shiori-accent shiori-accent-card"
              x="50"
              y="30"
              width="9"
              height="12"
              rx="2"
              transform="rotate(14 54 36)"
            />
          </>
        ) : null}
        {variant === "loading" ? (
          <g className="shiori-loading-dots">
            <circle cx="27" cy="52" r="2" />
            <circle cx="32" cy="52" r="2" />
            <circle cx="37" cy="52" r="2" />
          </g>
        ) : null}
      </svg>
    </span>
  );
}

// ShioriMark -- the compact inline "brand mark" form: same silhouette and
// face, always the calm default expression, no tassel/accessory detail (at
// icon size those would just be noise). Drop-in replacement anywhere a
// plain bookmark/section icon used to stand in for the character (e.g. the
// selected-word panel's title icon).
export function ShioriMark({ className }: { className?: string }) {
  return (
    <span className={`shiori-mark${className ? ` ${className}` : ""}`} aria-hidden="true">
      <svg viewBox="0 0 64 88" className="shiori-mark-svg">
        <path className="shiori-bookmark-body" d={bookmarkBodyPath} />
        <rect className="shiori-face" x="14" y="16" width="36" height="28" rx="10" />
        <circle className="shiori-eye" cx="26" cy="30" r="2.2" />
        <circle className="shiori-eye" cx="38" cy="30" r="2.2" />
        <path className="shiori-mouth" d={mouthByVariant.default} />
      </svg>
    </span>
  );
}

// ShioriStamp -- the "moment just completed" mark: a small Shiori face plus
// an optional short label, read as a postmark stamped in a notebook rather
// than a second illustration next to the real one. Without a label it's
// just the bare character (inline next to a message line); with one it
// picks up the dashed-pill "postmark" chrome.
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
  message,
  className,
}: {
  variant?: ShioriVariant;
  message: string;
  className?: string;
}) {
  return (
    <div className={`shiori-guide-card${className ? ` ${className}` : ""}`}>
      <ShioriCharacter variant={variant} size="sm" />
      <p className="shiori-guide-card-text">{message}</p>
    </div>
  );
}
