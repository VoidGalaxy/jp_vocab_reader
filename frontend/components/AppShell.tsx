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
  children: React.ReactNode;
};

// Desktop: a left sidebar (grouped nav) next to the main content column.
// Mobile: the sidebar is simply not rendered in that layout slot (CSS hides
// it below the breakpoint) and a fixed bottom tab bar takes over instead --
// both read from the same NavAction data the caller built from the existing
// tabs/activeTab/handleTabChange state, so there is exactly one source of
// truth for "what page am I on" regardless of which nav is visible.
export function AppShell({
  groups,
  mobilePrimaryItems,
  mobileMoreItems,
  children,
}: AppShellProps) {
  const [isMoreOpen, setIsMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement | null>(null);

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

  const isMoreActive = mobileMoreItems.some((item) => item.isActive);

  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label="주요 메뉴">
        <div className="app-sidebar-brand">
          <span className="app-sidebar-brand-icon" aria-hidden="true">
            <BookIcon />
          </span>
          <div className="app-sidebar-brand-text">
            <strong>일본어 단어장</strong>
            <span>조용한 서재의 학습 책상</span>
          </div>
        </div>
        {groups.map((group) => (
          <div className="app-sidebar-group" key={group.label}>
            <span className="app-sidebar-group-label">{group.label}</span>
            {group.items.map((item) => (
              <button
                key={item.key}
                type="button"
                className={
                  item.isActive
                    ? "app-sidebar-link app-sidebar-link-active"
                    : "app-sidebar-link"
                }
                aria-current={item.isActive ? "page" : undefined}
                onClick={item.onClick}
              >
                <item.icon className="app-sidebar-icon" />
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <div className="app-shell-content">{children}</div>

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
