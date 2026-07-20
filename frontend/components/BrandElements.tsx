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

// The brand character: a small "bookmark companion" that reuses the same
// ribbon-notch shape as BrandReadingFlowIllustration's bookmark tab (one
// consistent bookmark motif, not two unrelated shapes) with a plain paper
// "face plate" and a two-dot-and-one-line expression on top. Deliberately
// primitive (polygon + rect + circles + one path) instead of a detailed
// illustration -- a small recurring companion, not artwork that competes
// with the screen's actual content. Mood only changes the mouth curve and,
// for the two "positive" moods, adds one tiny sparkle -- keeps every
// variant reading as the same character instead of drifting per screen.
export type CompanionMood =
  | "welcome"
  | "reading"
  | "empty"
  | "review"
  | "done"
  | "feedback"
  | "error";

const companionMouthPaths: Record<CompanionMood, string> = {
  welcome: "M23 44q5 6 10 0",
  reading: "M25 45q4 3 8 0",
  empty: "M24 46h10",
  review: "M23 45q5 5 10 0",
  done: "M21 43q7 8 14 0",
  feedback: "M25 44q4 4 8 0",
  error: "M24 47q5 -3 10 0",
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
  const showSpark = mood === "welcome" || mood === "done";
  return (
    <span
      className={`study-companion study-companion-${size}${className ? ` ${className}` : ""}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 64 88" className="study-companion-svg">
        <polygon
          className="study-companion-body"
          points="4,2 60,2 60,84 32,64 4,84"
        />
        <rect
          className="study-companion-face"
          x="12"
          y="14"
          width="40"
          height="34"
          rx="12"
        />
        <circle className="study-companion-eye" cx="26" cy="32" r="2.6" />
        <circle className="study-companion-eye" cx="38" cy="32" r="2.6" />
        <path className="study-companion-mouth" d={companionMouthPaths[mood]} />
        {showSpark ? (
          <path
            className="study-companion-spark"
            d="M52 6 L54 11 L59 12 L54 13 L52 18 L50 13 L45 12 L50 11 Z"
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
