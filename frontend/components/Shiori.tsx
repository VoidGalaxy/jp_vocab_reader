"use client";

import { useEffect, useState } from "react";

// Shiori (시오리) -- the app's bookmark-spirit brand character. As of this
// pass she is no longer hand-drawn in SVG/CSS: she's a set of pre-made
// illustrated PNGs (frontend/public/brand/shiori/shiori-<variant>.png --
// see docs/design/shiori-design-spec.md for the art direction those were
// produced from) and every component in this file is just picking the
// right local asset for a given variant/size and displaying it. No
// character geometry lives in this file anymore -- if the art needs to
// change, edit the PNGs, not this file. No external image URLs, ever.

export type ShioriVariant =
  | "default"
  | "hero"
  | "reading"
  | "classify"
  | "save"
  | "review"
  | "success"
  | "empty"
  | "loading";

export type ShioriSize = "sm" | "md" | "lg" | "xl" | "hero";

// Every variant is expected to eventually have its own PNG, but while art
// is still being delivered (or if a specific file 404s for any reason)
// everything falls back to this one -- "default" is the one variant
// that's always assumed to exist.
const FALLBACK_VARIANT: ShioriVariant = "default";

// variant -> asset path. One place to confirm against the 9 delivered PNGs
// (frontend/public/brand/shiori/) -- nothing here draws or edits the art,
// it only points at the finished file for each situation.
export const SHIORI_ASSET_MAP: Record<ShioriVariant, string> = {
  default: "/brand/shiori/shiori-default.png",
  hero: "/brand/shiori/shiori-hero.png",
  reading: "/brand/shiori/shiori-reading.png",
  classify: "/brand/shiori/shiori-classify.png",
  save: "/brand/shiori/shiori-save.png",
  review: "/brand/shiori/shiori-review.png",
  success: "/brand/shiori/shiori-success.png",
  empty: "/brand/shiori/shiori-empty.png",
  loading: "/brand/shiori/shiori-loading.png",
};

// size -> wrapper box class (globals.css defines the actual px/clamp values).
// Kept as a lookup rather than a template string so an invalid size can
// never silently produce a class that doesn't exist in CSS.
export const SHIORI_SIZE_MAP: Record<ShioriSize, string> = {
  sm: "shiori-asset--sm",
  md: "shiori-asset--md",
  lg: "shiori-asset--lg",
  xl: "shiori-asset--xl",
  hero: "shiori-asset--hero",
};

// Shared image renderer every export below is built from -- resolves the
// variant's PNG, and if it fails to load falls back to the default PNG;
// if even that fails (assets not delivered yet at all), renders nothing
// rather than a browser's broken-image glyph so the surrounding layout
// stays clean.
function ShioriImage({
  variant,
  size,
  className,
  alt = "",
}: {
  variant: ShioriVariant;
  size: ShioriSize;
  className?: string;
  alt?: string;
}) {
  const [src, setSrc] = useState(() => SHIORI_ASSET_MAP[variant]);
  const [isHidden, setIsHidden] = useState(false);

  // Re-resolve whenever the requested variant actually changes (e.g. a
  // card moving from "empty" to "review") instead of getting stuck on a
  // fallback picked for a previous variant.
  useEffect(() => {
    setSrc(SHIORI_ASSET_MAP[variant]);
    setIsHidden(false);
  }, [variant]);

  if (isHidden) {
    return null;
  }

  return (
    <span
      className={`shiori-asset ${SHIORI_SIZE_MAP[size]}${className ? ` ${className}` : ""}`}
      aria-hidden={alt ? undefined : "true"}
    >
      <img
        className="shiori-asset-img"
        src={src}
        alt={alt}
        draggable={false}
        onError={() => {
          const fallbackSrc = SHIORI_ASSET_MAP[FALLBACK_VARIANT];
          if (src !== fallbackSrc) {
            setSrc(fallbackSrc);
          } else {
            setIsHidden(true);
          }
        }}
      />
    </span>
  );
}

export function ShioriCharacter({
  variant = "default",
  size = "sm",
  className,
  alt = "",
}: {
  variant?: ShioriVariant;
  size?: ShioriSize;
  className?: string;
  alt?: string;
}) {
  return <ShioriImage variant={variant} size={size} className={className} alt={alt} />;
}

// ShioriMark -- the compact inline "brand mark" form for a slot that used
// to hold a plain generic bookmark glyph (e.g. the selected-word panel's
// title, a section heading). Same artwork as ShioriCharacter, always
// rendered at "sm" -- the calling screen's own CSS (e.g.
// .token-sheet-bookmark-icon, .shared-deck-title-mark) shrinks the box
// further where a spot needs it even smaller.
export function ShioriMark({
  variant = "default",
  className,
}: {
  variant?: ShioriVariant;
  className?: string;
}) {
  return (
    <ShioriImage
      variant={variant}
      size="sm"
      className={`shiori-mark${className ? ` ${className}` : ""}`}
    />
  );
}

// ShioriStamp -- the "moment just completed" mark: a small Shiori image
// plus an optional short label, read as a postmark stamped in a notebook
// rather than a second illustration next to the real one. Without a label
// it's just the bare character (inline next to a message line); with one
// it picks up the dashed-pill "postmark" chrome. Always renders at "sm" --
// a stamp is a small aside, never a second big character next to the
// real one.
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
      <ShioriImage variant={variant} size="sm" className="shiori-stamp-character" />
      {label ? <span className="shiori-stamp-label">{label}</span> : null}
    </span>
  );
}

// ShioriGuideCard -- a slim horizontal "Shiori says one quiet line" card
// (image left, one short message right). Distinct from AppEmptyState's
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
