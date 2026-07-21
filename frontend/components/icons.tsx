"use client";

// Small hand-written stroke icons (feather-style, ~20x20), used instead of
// pulling in an icon library the project doesn't already depend on. Each
// icon inherits color from its parent via currentColor/stroke="currentColor"
// so it follows button/text theming automatically. Purely decorative next
// to existing text labels, so no aria-label is added here -- callers that
// use an icon alone (no visible label) are responsible for their own
// aria-label on the interactive element.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function baseProps(props: IconProps): IconProps {
  return {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <polyline points="9 6 15 12 9 18" />
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5.5 9.5V19a1 1 0 0 0 1 1H9a1 1 0 0 0 1-1v-4h4v4a1 1 0 0 0 1 1h2.5a1 1 0 0 0 1-1V9.5" />
    </svg>
  );
}

// Plain X -- used where "닫기" needs to read as a quiet corner affordance
// (small icon-only button) instead of a full text pill competing with the
// panel's actual content, e.g. the reading word panel's close control.
export function CloseIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

export function CardsIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <rect x="3" y="7" width="13" height="13" rx="2" />
      <path d="M7.5 7V5a2 2 0 0 1 2-2H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2" />
    </svg>
  );
}

export function FolderIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
    </svg>
  );
}

// A small index-card box with one card peeking above the rim -- the
// "어휘 노트" nav item/section's own icon, distinct from the generic
// FolderIcon still used elsewhere for the plain "save into a folder"
// action (홈 flow strip, 저장 바구니 등).
export function CardFileIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M4 11h16v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8z" />
      <path d="M8.5 11V6.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1V11" />
      <path d="M4 11h16" />
    </svg>
  );
}

// Classic ribbon bookmark (rounded-rect body, V-notch bottom) -- same
// silhouette language as Shiori's own body shape. Used for the "다시"
// review rating (책갈피를 되돌려 놓는다 -- put the bookmark back for later)
// so the four rating buttons read as four different actions, not four
// same-shape buttons in different colors.
export function BookmarkIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M6 3h12a1 1 0 0 1 1 1v16l-7-4-7 4V4a1 1 0 0 1 1-1z" />
    </svg>
  );
}

// A short pencil stroke -- the "어려움" review rating (연필로 메모해두는
// 느낌 -- jotting a note to come back to this one soon).
export function PencilIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function ShareIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="M8.2 10.7 15.8 6.3M8.2 13.3l7.6 4.4" />
    </svg>
  );
}

// A shelf of uneven book spines -- the "덱 책장" (deck bookshelf) screen's
// own icon, distinct from the generic share/nodes glyph ShareIcon was
// previously overloaded to also represent. Used for the bookshelf nav
// item/empty states/"go to shelf" buttons; ShareIcon stays reserved for
// actual share actions (어휘 노트 공유하기 등).
export function BookshelfIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3 20h18" />
      <rect x="4.5" y="7" width="3" height="13" rx="0.6" />
      <rect x="9" y="4" width="3" height="16" rx="0.6" />
      <rect x="13.5" y="9" width="3" height="11" rx="0.6" />
      <rect x="18" y="6" width="2.5" height="14" rx="0.6" />
    </svg>
  );
}

export function RotateIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M3 12a9 9 0 1 1 2.64 6.36" />
      <polyline points="3 21 3 15 9 15" />
    </svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function ZapIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 2 4 5v6c0 5 3.4 9 8 11 4.6-2 8-6 8-11V5z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

export function SparkleIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />
    </svg>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-3.9 3.6-7 8-7s8 3.1 8 7" />
    </svg>
  );
}

export function InboxIcon(props: IconProps) {
  return (
    <svg {...baseProps(props)}>
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}
