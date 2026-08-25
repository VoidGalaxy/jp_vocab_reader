"use client";

import { useEffect, useState } from "react";
import { BookIcon, CloseIcon, MenuIcon } from "./icons";

export type NavAction = {
  key: string;
  label: string;
  // Preferred label for the desktop toolbar, which has to fit all tabs
  // plus brand/account/feedback in one row -- falls back to `label` when a
  // tab has no shorter form. The mobile/tablet drawer always uses the full
  // `label`, since it has vertical room to spare.
  shortLabel?: string;
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

// Phase 113 -- replaces the old two-piece chrome (a persistent left
// "library rail" sidebar + a separate slim topbar, plus a fixed 7-icon
// bottom tab bar on mobile) with ONE navigation surface: a single toolbar
// row, matching the mockup's rounded toolbar sitting on top of the
// desk/notebook scene rather than an admin sidebar bolted to its edge.
//
// >=1024px ("true desktop", the same tier the rest of the desk-scene
// redesign already gates on -- see globals.css) renders every tab as a
// text link directly in that row. Below that tier, seven full-label tabs
// no longer fit one row, so they move into a slide-in drawer opened by a
// small hamburger button -- the mockup's mobile boards show no persistent
// bottom tab bar at all, just a minimal top strip, so the old fixed
// bottom nav this replaces is gone rather than restyled. Same `navItems`
// (built from the existing tabs/activeTab/handleTabChange state in
// page.tsx) drives both presentations, so there is exactly one source of
// truth for "what page am I on" regardless of which one is visible.
//
// Phase 172 -- every tab now owns a full-bleed V2 photographed scene (see
// globals.css's Phase 172 block), so the old `minimalChrome` prop (Phase
// 118, a Home-only translucent toolbar skin layered on top of a heavier
// default) is gone: that lighter look -- plus a further-quieted active-tab
// indicator -- is just what `.app-toolbar` always looks like now, for
// every tab, not a conditional skin.
export function AppShell({
  navItems,
  accountSlot,
  feedbackSlot,
  children,
}: AppShellProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    if (!isDrawerOpen) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsDrawerOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isDrawerOpen]);

  function handleDrawerNavClick(item: NavAction) {
    item.onClick();
    setIsDrawerOpen(false);
  }

  return (
    <div className="app-shell">
      <header className="app-toolbar">
        <button
          type="button"
          className="app-toolbar-menu-button"
          aria-label="메뉴 열기"
          aria-haspopup="menu"
          aria-expanded={isDrawerOpen}
          onClick={() => setIsDrawerOpen(true)}
        >
          <MenuIcon />
        </button>

        <nav className="app-toolbar-nav" aria-label="일본어 단어장 주요 메뉴">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={
                item.isActive
                  ? "app-toolbar-link app-toolbar-link-active"
                  : "app-toolbar-link"
              }
              aria-current={item.isActive ? "page" : undefined}
              onClick={item.onClick}
            >
              {item.isActive ? (
                <span className="app-toolbar-pin" aria-hidden="true" />
              ) : null}
              <item.icon className="app-toolbar-link-icon" />
              <span>{item.shortLabel ?? item.label}</span>
            </button>
          ))}
        </nav>

        <div className="app-toolbar-end">
          {feedbackSlot}
          {accountSlot}
        </div>
      </header>

      {isDrawerOpen ? (
        <div
          className="app-nav-drawer-overlay"
          onClick={() => setIsDrawerOpen(false)}
        >
          <div
            className="app-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="일본어 단어장 주요 메뉴"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="app-nav-drawer-header">
              <span className="app-nav-drawer-brand">
                <BookIcon className="app-nav-drawer-brand-icon" />
                책갈피
              </span>
              <button
                type="button"
                className="app-nav-drawer-close"
                aria-label="메뉴 닫기"
                onClick={() => setIsDrawerOpen(false)}
              >
                <CloseIcon />
              </button>
            </div>
            <nav className="app-nav-drawer-list">
              {navItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={
                    item.isActive
                      ? "app-nav-drawer-link app-nav-drawer-link-active"
                      : "app-nav-drawer-link"
                  }
                  aria-current={item.isActive ? "page" : undefined}
                  onClick={() => handleDrawerNavClick(item)}
                >
                  <item.icon className="app-nav-drawer-link-icon" />
                  <span>{item.label}</span>
                </button>
              ))}
            </nav>
            <div
              className="app-nav-drawer-footer"
              onClick={() => setIsDrawerOpen(false)}
            >
              {feedbackSlot}
            </div>
          </div>
        </div>
      ) : null}

      <div className="app-shell-content">{children}</div>
    </div>
  );
}
