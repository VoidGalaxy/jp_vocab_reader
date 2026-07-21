"use client";

import type { ReactNode } from "react";
import { BookIcon, FolderIcon, ShareIcon } from "./icons";

// Small, reusable "brand illustration" pieces shared across the app --
// consolidates decoration that used to be hand-rolled per screen
// (brand-visual-layer) into one place so the same icon-badge/illustration
// language repeats consistently everywhere instead of drifting screen by
// screen. CSS/SVG/existing-icon-library only, no image assets. Every piece
// here is aria-hidden -- purely decorative, never the only carrier of
// information a screen needs.

type IconComponent = (props: { className?: string }) => JSX.Element;

// Tier 1: small inline badge next to a section heading (h2/h3). Used
// sparingly -- only on a handful of key section titles, not every one.
export function BrandSectionBadge({ icon: Icon }: { icon: IconComponent }) {
  return <Icon className="brand-section-badge" aria-hidden="true" />;
}

// Tier 2: standalone icon illustration centered at the top of an empty
// state / guide card. Same visual language everywhere a screen has
// "nothing here yet" to say, so the app's empty states read as one family
// instead of each screen inventing its own.
export function BrandEmptyIllustration({ icon: Icon }: { icon: IconComponent }) {
  return <Icon className="brand-empty-illustration" aria-hidden="true" />;
}

// Home hero's "読む -> 保存 -> 復習" flow illustration -- three slightly
// tilted paper cards, a highlighter swipe on the payoff step, and a
// bookmark ribbon. Extracted from HomeDashboard so the same illustration
// can be reused anywhere the product's core loop needs a visual, not just
// the home hero.
export function BrandReadingFlowIllustration() {
  return (
    <div className="home-hero-illustration">
      <span className="home-hero-bookmark" aria-hidden="true" />
      <div className="home-hero-preview" aria-hidden="true">
        <div className="home-hero-preview-step">
          <span className="home-hero-preview-word">読む</span>
          <span className="home-hero-preview-caption">읽기</span>
        </div>
        <span className="home-hero-preview-arrow">→</span>
        <div className="home-hero-preview-step">
          <span className="home-hero-preview-word">保存</span>
          <span className="home-hero-preview-caption">저장</span>
        </div>
        <span className="home-hero-preview-arrow">→</span>
        <div className="home-hero-preview-step">
          <span className="home-hero-preview-word">復習</span>
          <span className="home-hero-preview-caption">복습</span>
        </div>
      </div>
    </div>
  );
}

// Home hero's "서재 히어로 비주얼" -- a small flat-lay desk scene (open book,
// pencil, memo card, a peeking bookmark ribbon, one word card) built from
// plain shapes/paths in the same warm palette as the rest of the brand
// system. No external image asset. Deliberately a handful of simple flat
// shapes, not a detailed drawing -- reads as "quiet reading desk" at a
// glance rather than competing with the hero's title/CTAs for attention.
export function LibraryHeroIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 180 150"
      className={`library-hero-illustration${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      {/* Open book */}
      <g transform="rotate(-4 76 92)">
        <rect
          className="library-hero-book-cover"
          x="21"
          y="58"
          width="110"
          height="68"
          rx="10"
        />
        <rect
          className="library-hero-book-page"
          x="29"
          y="64"
          width="94"
          height="56"
          rx="6"
        />
        <line
          className="library-hero-spine"
          x1="76"
          y1="64"
          x2="76"
          y2="120"
        />
      </g>

      {/* Bookmark ribbon peeking out from the spine */}
      <path
        className="library-hero-bookmark"
        d="M68 26 H84 A6 6 0 0 1 90 32 V66 L76 57 L62 66 V32 A6 6 0 0 1 68 26 Z"
      />

      {/* Pencil resting diagonally across the book */}
      <g transform="rotate(-27 118 44)">
        <rect
          className="library-hero-pencil-body"
          x="88"
          y="39"
          width="62"
          height="10"
          rx="5"
        />
        <rect
          className="library-hero-pencil-band"
          x="140"
          y="39"
          width="8"
          height="10"
        />
        <polygon
          className="library-hero-pencil-tip"
          points="150,39 160,44 150,49"
        />
      </g>

      {/* Memo card with two lines of "text" */}
      <g transform="rotate(6 128 34)">
        <rect
          className="library-hero-memo"
          x="105"
          y="17"
          width="46"
          height="34"
          rx="6"
        />
        <rect className="library-hero-memo-line" x="113" y="27" width="30" height="3" rx="1.5" />
        <rect className="library-hero-memo-line" x="113" y="35" width="22" height="3" rx="1.5" />
      </g>

      {/* Small saved-word card */}
      <g transform="rotate(-5 34 114)">
        <rect
          className="library-hero-word-chip"
          x="14"
          y="99"
          width="42"
          height="28"
          rx="7"
        />
        <text
          className="library-hero-word-chip-text"
          x="35"
          y="118"
          textAnchor="middle"
        >
          読
        </text>
      </g>
    </svg>
  );
}

// Shiori (시오리) -- the app's bookmark-fairy guide character. Locked
// character system (2026-07-21 brand-direction pass): reads as a bookmark
// first (rounded-top ribbon, V-notch tail), a quiet companion second (two
// eyes + one simple mouth, warm screen-tinted body). Appears at the same
// deliberate spots as before: home hero, reading empty/idle state, save
// success, study quick-start hero, review complete, and other empty
// states -- never as constant decoration on a loaded/busy screen.
//
// Each mood now has its own simple expression (previously only "done" had
// any facial change at all, which read as ambiguous rather than as a
// character) -- still just plain geometric shapes, never a detailed face,
// per the locked design rules: no complex face, no full human body, no
// chibi/anime styling, identical proportions on every screen (this is the
// one component every call site shares, so that's automatic).
//   reading  (환영/힌트)   -- warm open smile, greets/guides the screen.
//   empty    (빈 상태)     -- resting half-closed eyes + flat mouth, calm
//                             rather than sad -- "nothing waiting right now".
//   done     (저장완료/복습응원) -- the widest smile plus the existing
//                             corner sparkle -- a small celebration.
//   feedback (경청)        -- same attentive smile as reading, head tilted
//                             a few degrees to read as "listening in".
export type CompanionMood = "reading" | "empty" | "done" | "feedback";

const companionMouthByMood: Record<CompanionMood, string> = {
  reading: "M26 36 Q32 41 38 36",
  feedback: "M26 36 Q32 41 38 36",
  done: "M25 35.5 Q32 44.5 39 35.5",
  empty: "M28 37.5 H36",
};

export function StudyCompanion({
  mood = "empty",
  size = "sm",
  className,
}: {
  mood?: CompanionMood;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const isResting = mood === "empty";

  return (
    <span
      className={`study-companion study-companion-${size} study-companion-mood-${mood}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 64 88" className="study-companion-svg">
        {/* Rounded-top bookmark ribbon with a V-notch tail -- the same
            silhouette language as .home-hero-bookmark/.brand-deck-cover
            elsewhere in the app, just standalone instead of a page
            accent. */}
        <path
          className="study-companion-body"
          d="M14 2 H50 A12 12 0 0 1 62 14 V84 L32 63 L2 84 V14 A12 12 0 0 1 14 2 Z"
        />
        <rect
          className="study-companion-face"
          x="14"
          y="16"
          width="36"
          height="28"
          rx="10"
        />
        {isResting ? (
          <>
            <line
              className="study-companion-eye-closed"
              x1="23"
              y1="30"
              x2="29"
              y2="30"
            />
            <line
              className="study-companion-eye-closed"
              x1="35"
              y1="30"
              x2="41"
              y2="30"
            />
          </>
        ) : (
          <>
            <circle className="study-companion-eye" cx="26" cy="30" r="2.2" />
            <circle className="study-companion-eye" cx="38" cy="30" r="2.2" />
          </>
        )}
        <path
          className="study-companion-mouth"
          d={companionMouthByMood[mood]}
        />
        {mood === "done" ? (
          <path
            className="study-companion-highlight"
            d="M46 8 L48 12 L52 13 L48 14 L46 18 L44 14 L40 13 L44 12 Z"
          />
        ) : null}
      </svg>
    </span>
  );
}

// Shared "nothing here yet" body -- every empty/no-result state in the app
// (읽기 첫 진입, 오늘 복습 없음, 어휘 노트 비어 있음/검색 없음, 덱 책장 없음,
// 홈 최근 활동 없음, ...) already followed this exact shape by convention
// (companion or icon -> title -> optional 1-line description -> action
// button(s)); this just gives that convention one implementation instead of
// nine hand-rolled copies, so new empty states can't drift from it by
// accident. Deliberately does NOT own the action buttons' markup/wrapper --
// each screen's surrounding CSS (.empty-guide, .reading-empty-guide,
// .study-ready-card, ...) already targets its own direct-child <button>s
// differently, and passing them as children keeps that untouched instead of
// forcing one wrapper div that would fight several existing layouts.
export function AppEmptyState({
  mood,
  icon,
  title,
  description,
  className = "empty-guide",
  children,
}: {
  mood?: CompanionMood;
  icon?: IconComponent;
  title: string;
  description?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div className={className}>
      {mood ? (
        <StudyCompanion mood={mood} />
      ) : icon ? (
        <BrandEmptyIllustration icon={icon} />
      ) : null}
      <p>{title}</p>
      {description ? <p className="muted-text">{description}</p> : null}
      {children}
    </div>
  );
}

export type DeckCoverTone = "recommended" | "mine" | "shared";

const deckCoverLabels: Record<DeckCoverTone, string> = {
  recommended: "추천 어휘",
  mine: "내가 공유함",
  shared: "공유 덱",
};

const deckCoverIcons: Record<DeckCoverTone, IconComponent> = {
  recommended: BookIcon,
  mine: ShareIcon,
  shared: FolderIcon,
};

// Shared-deck card's top "book cover" band. `level` (N5..N1) drives the
// warm cover-tone ramp already established for JLPT badges elsewhere;
// `tone` covers the two non-JLPT cases (내가 공유함 / 공유 덱) and picks the
// icon. One place for the cover visual so every deck card -- recommended
// or not -- reads as the same shelf/book-cover system.
export function BrandDeckCover({
  tone,
  level,
}: {
  tone: DeckCoverTone;
  level?: string | null;
}) {
  const toneClass = level ? `jlpt-level-${level.toLowerCase()}` : `brand-deck-cover-${tone}`;
  const Icon = deckCoverIcons[tone];
  return (
    <div className={`brand-deck-cover ${toneClass}`}>
      <Icon className="brand-deck-cover-icon" />
      <span>{deckCoverLabels[tone]}</span>
    </div>
  );
}
