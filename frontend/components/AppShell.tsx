"use client";

import { useEffect, useRef, useState } from "react";
import { BookIcon, MoreIcon } from "./icons";

export type NavAction = {
  key: string;
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
  onClick: () => void;
  isActive?: boolean;
};

export type NavGroup = {
  label: string;
  items: NavAction[];
};

type AppShellProps = {
  groups: NavGroup[];
  mobilePrimaryItems: NavAction[];
  mobileMoreItems: NavAction[];
  accountSlot: React.ReactNode;
  feedbackSlot: React.ReactNode;
  children: React.ReactNode;
};

// Desktop: a slim "library rail" (icon + tiny label, book-spine width) next
// to the main content column -- V3 replaces the old wide sidebar (216px,
// full text labels, its own repeated app-name block) with something that
// reads as a shelf edge, not an admin-panel menu. Only the primary 5 nav
// items ever show on the rail itself; everything in later `groups` entries
// (빠른 분류/기록/피드백) collapses behind one "더보기" flyout instead of
// eating rail height with a whole second labeled section.
// Mobile: the rail is hidden (CSS) and the fixed bottom tab bar takes over
// instead -- both still read from the same NavAction data the caller built
// from the existing tabs/activeTab/handleTabChange state, so there is
// exactly one source of truth for "what page am I on" regardless of which
// nav is visible.
export function AppShell({
  groups,
  mobilePrimaryItems,
  mobileMoreItems,
  accountSlot,
  feedbackSlot,
  children,
}: AppShellProps) {
  const [isMoreOpen, setIsMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement | null>(null);
  const [isRailMoreOpen, setIsRailMoreOpen] = useState(false);
  const railMoreRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isMoreOpen) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (!moreRef.current?.contains(event.target as Node)) {
        setIsMoreOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMoreOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMoreOpen]);

  useEffect(() => {
    if (!isRailMoreOpen) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (!railMoreRef.current?.contains(event.target as Node)) {
        setIsRailMoreOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsRailMoreOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isRailMoreOpen]);

  const isMoreActive = mobileMoreItems.some((item) => item.isActive);
  // The rail's "더보기" flyout has room to spare (unlike the narrow rail
  // buttons above), so it keeps the full desktop labels (groups[1..])
  // instead of the bottom-tab bar's short mobileLabel set.
  const secondaryItems = groups.slice(1).flatMap((group) => group.items);
  const isRailMoreActive = secondaryItems.some((item) => item.isActive);

  return (
    <div className="app-shell">
      <aside className="library-rail" aria-label="일본어 단어장 주요 메뉴">
        <span className="library-rail-brand" aria-hidden="true">
          <BookIcon />
        </span>
        <nav className="library-rail-nav">
          {/* Rail buttons reuse the same short mobileLabel set the bottom
              tab bar already uses (책상/읽기/복습/노트/덱) -- the rail is
              too narrow for full labels like "어휘 노트" without wrapping
              or truncating. */}
          {mobilePrimaryItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={
                item.isActive
                  ? "library-rail-link library-rail-link-active"
                  : "library-rail-link"
              }
              aria-current={item.isActive ? "page" : undefined}
              onClick={item.onClick}
            >
              <item.icon className="library-rail-icon" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        {secondaryItems.length > 0 ? (
          <div className="library-rail-more-wrap" ref={railMoreRef}>
            {isRailMoreOpen ? (
              <div className="library-rail-more-sheet" role="menu">
                {secondaryItems.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitem"
                    className={
                      item.isActive
                        ? "library-rail-more-item library-rail-more-item-active"
                        : "library-rail-more-item"
                    }
                    onClick={() => {
                      setIsRailMoreOpen(false);
                      item.onClick();
                    }}
                  >
                    <item.icon className="button-icon" />
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
            <button
              type="button"
              className={
                isRailMoreActive
                  ? "library-rail-link library-rail-link-active"
                  : "library-rail-link"
              }
              aria-haspopup="menu"
              aria-expanded={isRailMoreOpen}
              onClick={() => setIsRailMoreOpen((open) => !open)}
            >
              <MoreIcon className="library-rail-icon" />
              <span>더보기</span>
            </button>
          </div>
        ) : null}
      </aside>

      <div className="app-shell-content">
        <header className="app-topbar">
          <div className="app-topbar-end">
            {feedbackSlot}
            {accountSlot}
          </div>
        </header>
        {children}
      </div>

      <nav className="app-bottom-nav" aria-label="주요 메뉴">
        {mobilePrimaryItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={
              item.isActive
                ? "app-bottom-nav-item app-bottom-nav-item-active"
                : "app-bottom-nav-item"
            }
            aria-current={item.isActive ? "page" : undefined}
            onClick={() => {
              setIsMoreOpen(false);
              item.onClick();
            }}
          >
            <item.icon className="app-bottom-nav-icon" />
            <span>{item.label}</span>
          </button>
        ))}
        {mobileMoreItems.length > 0 ? (
          <div className="app-bottom-nav-more-wrap" ref={moreRef}>
            {isMoreOpen ? (
              <div className="app-bottom-nav-more-sheet" role="menu">
                {mobileMoreItems.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitem"
                    className={
                      item.isActive
                        ? "app-bottom-nav-more-item app-bottom-nav-more-item-active"
                        : "app-bottom-nav-more-item"
                    }
                    onClick={() => {
                      setIsMoreOpen(false);
                      item.onClick();
                    }}
                  >
                    <item.icon className="button-icon" />
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
            <button
              type="button"
              className={
                isMoreActive
                  ? "app-bottom-nav-item app-bottom-nav-item-active"
                  : "app-bottom-nav-item"
              }
              aria-haspopup="menu"
              aria-expanded={isMoreOpen}
              onClick={() => setIsMoreOpen((open) => !open)}
            >
              <MoreIcon className="app-bottom-nav-icon" />
              <span>더보기</span>
            </button>
          </div>
        ) : null}
      </nav>
    </div>
  );
}
