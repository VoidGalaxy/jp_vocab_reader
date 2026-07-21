"use client";

import type { ReactNode } from "react";
import { BookIcon, FolderIcon, ShareIcon } from "./icons";
import { ShioriCharacter, type ShioriVariant } from "./Shiori";

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
  mood?: ShioriVariant;
  icon?: IconComponent;
  title: string;
  description?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div className={className}>
      {mood ? (
        <ShioriCharacter variant={mood} size="sm" />
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
