"use client";

import { BookIcon } from "./icons";

export type NavAction = {
  key: string;
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
  onClick: () => void;
  isActive?: boolean;
};

type AppShellProps = {
  navItems: NavAction[];
  accountSlot: React.ReactNode;
  feedbackSlot: React.ReactNode;
  children: React.ReactNode;
};

// Desktop: a slim "library rail" (icon + tiny label, book-spine width) next
// to the main content column -- V3 replaces the old wide sidebar (216px,
// full text labels, its own repeated app-name block) with something that
// reads as a shelf edge, not an admin-panel menu. Every nav item is a flat,
// always-visible list here -- no "더보기" flyout layer, so there is exactly
// one place to look for any screen.
// Mobile: the rail is hidden (CSS) and the fixed bottom tab bar takes over
// instead -- both read from the same `navItems` the caller built from the
// existing tabs/activeTab/handleTabChange state, so there is exactly one
// source of truth for "what page am I on" regardless of which nav is
// visible.
export function AppShell({
  navItems,
  accountSlot,
  feedbackSlot,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="library-rail" aria-label="일본어 단어장 주요 메뉴">
        <span className="library-rail-brand" aria-hidden="true">
          <span className="library-rail-brand-icon">
            <BookIcon />
          </span>
          <span className="library-rail-brand-name">책갈피</span>
        </span>
        <nav className="library-rail-nav">
          {navItems.map((item) => (
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
        {navItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={
              item.isActive
                ? "app-bottom-nav-item app-bottom-nav-item-active"
                : "app-bottom-nav-item"
            }
            aria-current={item.isActive ? "page" : undefined}
            onClick={item.onClick}
          >
            <item.icon className="app-bottom-nav-icon" />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
