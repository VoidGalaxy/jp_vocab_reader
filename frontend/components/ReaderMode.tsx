"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TokenStatus, TokenWithStatus } from "./types";
import { StudyCompanion } from "./BrandElements";
import { TokenChip } from "./TokenChip";
import { TokenDetailSheet } from "./TokenDetailSheet";
import { buildReaderLayout, getNavigableTokenIndexes } from "./readerLayout";
import { getTokenGroupKey } from "./coverageUtils";

// Reading-progress percentage is derived from how far the reader has
// scrolled through the .reader-text container relative to the viewport,
// not from selected-token position -- most reading happens without
// clicking every word, so scroll position is the more meaningful signal.
// 0 = container top just entered the viewport top, 1 = container bottom
// has reached the viewport bottom. Deliberately approximate (see task
// notes): the goal is a sense of "how far in", not a precise metric.
function computeScrollProgress(container: HTMLElement | null): number {
  if (!container || typeof window === "undefined") {
    return 0;
  }
  const rect = container.getBoundingClientRect();
  const viewportHeight = window.innerHeight || 1;
  const total = Math.max(rect.height - viewportHeight, 1);
  const scrolled = Math.min(Math.max(-rect.top, 0), total);
  return scrolled / total;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

type ReaderModeProps = {
  originalText: string;
  tokens: TokenWithStatus[];
  onStatusChange: (index: number, status: TokenStatus) => void;
  initialSelectedTokenKey?: string | null;
  onSelectedTokenKeyChange?: (key: string | null) => void;
  // Scroll-through-container fraction (0..1) restored from the last saved
  // reading session, if any. Read once at mount (see bookmarkScrollFractionRef
  // below) -- later prop updates (this same value gets echoed back up via
  // onScrollProgressChange as the user scrolls) are intentionally ignored so
  // the "마지막 위치로 이동" bookmark keeps pointing at where the user left
  // off last time, not at wherever they've scrolled to just now.
  initialScrollFraction?: number | null;
  onScrollProgressChange?: (fraction: number) => void;
  // Imperative "select this token" channel for triggers outside the reader
  // itself (currently: the word-list panel). requestId must increment on
  // every request, including repeat clicks on the same tokenIndex, so the
  // effect below can tell "new click" apart from "unrelated re-render with
  // the same prop value" -- a plain tokenIndex-only prop couldn't do that.
  externalSelectRequest?: { tokenIndex: number; requestId: number } | null;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (token: TokenWithStatus) => void;
  // Word Basket (Save Tray) wiring -- the selection Set itself lives in
  // ReadingTab (shared with the word-list panel), so the inspector only
  // needs yes/no + a toggle for whichever token is currently active.
  isTokenInBasket: (token: TokenWithStatus) => boolean;
  canAddToBasket: (token: TokenWithStatus) => boolean;
  onToggleBasket: (token: TokenWithStatus) => void;
};

export function ReaderMode({
  originalText,
  tokens,
  onStatusChange,
  initialSelectedTokenKey = null,
  onSelectedTokenKeyChange,
  initialScrollFraction = null,
  onScrollProgressChange,
  externalSelectRequest = null,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
  isTokenInBasket,
  canAddToBasket,
  onToggleBasket,
}: ReaderModeProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // Which literal rendered occurrence was clicked, when known -- a repeated
  // word (e.g. 闇 appearing 40 times in a long text) collapses to one
  // tokenIndex after dedup, so tokenIndex alone can't tell "the 3rd 闇" apart
  // from "the 1st 闇". null means "no specific occurrence" (prev/next nav,
  // the word-list panel, or a restored selection), which intentionally
  // falls back to the word's first occurrence.
  const [activeSegmentKey, setActiveSegmentKey] = useState<string | null>(
    null,
  );
  const [focusMode, setFocusMode] = useState(false);
  const [showJlptTags, setShowJlptTags] = useState(true);
  // Guards against re-applying a restored selection every time tokens
  // change (e.g. after a status save) -- only ever resolved once, right
  // after a restore, then the user's own clicks take over.
  const [hasAppliedInitialSelection, setHasAppliedInitialSelection] =
    useState(false);
  // Guards the one-time scroll-to-last-position restore the same way
  // hasAppliedInitialSelection guards the token restore above.
  const [hasAppliedInitialScroll, setHasAppliedInitialScroll] =
    useState(false);
  // Live 0..1 scroll-through-container fraction, recomputed as the user
  // scrolls -- drives the progress bar/percent display.
  const [scrollProgress, setScrollProgress] = useState(0);
  const readerTextRef = useRef<HTMLDivElement | null>(null);
  const scrollProgressThrottleRef = useRef<number | null>(null);
  // Frozen at mount: the "last read position" bookmark from the restored
  // session, kept separate from the live scrollProgress state above (which
  // this same value seeds in the parent and would otherwise immediately
  // drift to "wherever the user is right now" the moment they scroll).
  const bookmarkScrollFractionRef = useRef<number | null>(
    initialScrollFraction,
  );
  // Same reasoning, same bug class: initialSelectedTokenKey and
  // onSelectedTokenKeyChange are two ends of one live-updating piece of
  // parent state (the parent just echoes back whatever the user last
  // clicked), not a one-shot "restore this" value. Freezing it at mount
  // keeps the restore effect below from misfiring on the user's very first
  // in-session click (which otherwise looks identical to "a session was
  // restored with this key" the moment that click's key change round-trips
  // back down as a new initialSelectedTokenKey) and stomping the segment
  // key that click just set.
  const initialSelectedTokenKeyRef = useRef(initialSelectedTokenKey);
  // Tracks the last externalSelectRequest.requestId actually applied, so a
  // repeat click on the same word (same tokenIndex, new requestId) still
  // re-triggers the select+scroll, while an unrelated re-render that just
  // echoes the same request object back doesn't reapply it forever.
  const lastHandledExternalRequestIdRef = useRef<number | null>(null);

  const scrollToFraction = useCallback(
    (fraction: number, behavior: ScrollBehavior) => {
      const container = readerTextRef.current;
      if (!container || typeof window === "undefined") {
        return;
      }
      const rect = container.getBoundingClientRect();
      const viewportHeight = window.innerHeight || 1;
      const total = Math.max(rect.height - viewportHeight, 1);
      const containerTopAbsolute = window.scrollY + rect.top;
      const targetScrollY = Math.max(
        containerTopAbsolute + fraction * total,
        0,
      );
      window.scrollTo({ top: targetScrollY, behavior });
    },
    [],
  );

  const layout = useMemo(
    () => buildReaderLayout(originalText, tokens),
    [originalText, tokens],
  );

  // Previous/next order follows tokens[] directly (already first-occurrence
  // text order -- see getNavigableTokenIndexes), not the rendered layout.
  const navigableIndexes = useMemo(
    () => getNavigableTokenIndexes(tokens),
    [tokens],
  );

  useEffect(() => {
    if (
      hasAppliedInitialSelection ||
      !initialSelectedTokenKeyRef.current ||
      tokens.length === 0
    ) {
      return;
    }
    const matchIndex = tokens.findIndex(
      (token) => getTokenGroupKey(token) === initialSelectedTokenKeyRef.current,
    );
    if (matchIndex !== -1) {
      setActiveIndex(matchIndex);
      setActiveSegmentKey(null);
    }
    setHasAppliedInitialSelection(true);
  }, [hasAppliedInitialSelection, tokens]);

  // Handles an external "jump to this word" request (the word-list panel).
  // Inlines the same select+notify steps selectToken does below rather than
  // calling it directly, since that function is declared after the early
  // tokens.length===0 return and hooks can't depend on post-return bindings.
  useEffect(() => {
    if (
      !externalSelectRequest ||
      lastHandledExternalRequestIdRef.current === externalSelectRequest.requestId
    ) {
      return;
    }
    lastHandledExternalRequestIdRef.current = externalSelectRequest.requestId;
    const { tokenIndex } = externalSelectRequest;
    if (tokenIndex < 0 || tokenIndex >= tokens.length) {
      return;
    }
    setActiveIndex(tokenIndex);
    setActiveSegmentKey(null);
    onSelectedTokenKeyChange?.(getTokenGroupKey(tokens[tokenIndex]));
  }, [externalSelectRequest, tokens, onSelectedTokenKeyChange]);

  // Restores scroll position on mount when there's no token bookmark to
  // restore to instead (the token-restore effect above already scrolls the
  // selected word into view via the activeIndex effect below, which is more
  // precise -- this is only the fallback for "was scroll-reading without
  // selecting a word"). Runs after render so the container has real layout
  // to measure -- a short setTimeout rather than requestAnimationFrame,
  // since rAF isn't guaranteed to be serviced promptly in every context
  // (see the scroll-tracking effect below for the same reasoning).
  useEffect(() => {
    if (
      hasAppliedInitialScroll ||
      initialScrollFraction === null ||
      initialScrollFraction === undefined ||
      tokens.length === 0
    ) {
      return;
    }
    if (initialSelectedTokenKey) {
      const matchExists = tokens.some(
        (token) => getTokenGroupKey(token) === initialSelectedTokenKey,
      );
      if (matchExists) {
        setHasAppliedInitialScroll(true);
        return;
      }
    }
    const timeoutId = window.setTimeout(() => {
      scrollToFraction(initialScrollFraction, "auto");
    }, 50);
    setHasAppliedInitialScroll(true);
    return () => window.clearTimeout(timeoutId);
  }, [
    hasAppliedInitialScroll,
    initialScrollFraction,
    initialSelectedTokenKey,
    tokens,
    scrollToFraction,
  ]);

  // Tracks reading progress as the user scrolls. Throttled with a plain
  // setTimeout rather than requestAnimationFrame -- rAF callbacks are tied
  // to the compositor's paint loop and can silently stall (backgrounded/
  // inactive tabs, some headless/low-power contexts), which would leave the
  // progress bar stuck. A ~50ms timer is imperceptible for a position
  // indicator and fires reliably regardless of paint state.
  useEffect(() => {
    function handleScroll() {
      if (scrollProgressThrottleRef.current !== null) {
        return;
      }
      scrollProgressThrottleRef.current = window.setTimeout(() => {
        scrollProgressThrottleRef.current = null;
        setScrollProgress(computeScrollProgress(readerTextRef.current));
      }, 50) as unknown as number;
    }
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll);
    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
      if (scrollProgressThrottleRef.current !== null) {
        window.clearTimeout(scrollProgressThrottleRef.current);
      }
    };
  }, [layout]);

  // Bubbles the live scroll fraction up to the parent (for localStorage
  // persistence) on a trailing debounce, decoupled from the throttled local
  // updates above so scrolling never writes to localStorage dozens of times
  // per second.
  useEffect(() => {
    if (!onScrollProgressChange) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      onScrollProgressChange(scrollProgress);
    }, 400);
    return () => window.clearTimeout(timeoutId);
  }, [scrollProgress, onScrollProgressChange]);

  // Keeps the selected word visible in the source text as prev/next moves
  // it around -- best-effort only, so a missing DOM match (e.g. the active
  // token fell into the "unmatched" fallback row) is silently skipped.
  // Prefers the exact clicked occurrence (activeSegmentKey) when known;
  // otherwise falls back to the word's first occurrence by tokenIndex --
  // without this split, clicking e.g. the 40th occurrence of a repeated
  // word would scroll back up to the 1st one instead of staying put, since
  // querying by tokenIndex alone always finds the first DOM match.
  useEffect(() => {
    if (activeIndex === null || !readerTextRef.current) {
      return;
    }
    const selector = activeSegmentKey
      ? `[data-segment-key="${activeSegmentKey}"]`
      : `[data-token-index="${activeIndex}"]`;
    const target = readerTextRef.current.querySelector(selector);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeIndex, activeSegmentKey]);

  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goToNext();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToPrev();
      } else if (event.key === "Escape") {
        closeDetail();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, navigableIndexes]);

  if (tokens.length === 0) {
    return null;
  }

  // segmentKey is the specific rendered occurrence that was clicked, if
  // any -- omitted (null) for prev/next nav, which has no single "clicked
  // element" and intentionally lands on the word's first occurrence.
  function selectToken(index: number, segmentKey: string | null = null) {
    setActiveIndex(index);
    setActiveSegmentKey(segmentKey);
    onSelectedTokenKeyChange?.(getTokenGroupKey(tokens[index]));
  }

  function closeDetail() {
    setActiveIndex(null);
    setActiveSegmentKey(null);
    onSelectedTokenKeyChange?.(null);
  }

  const navPosition = activeIndex !== null ? navigableIndexes.indexOf(activeIndex) : -1;
  const canGoPrev = navPosition > 0;
  const canGoNext = navPosition !== -1 && navPosition < navigableIndexes.length - 1;

  function goToPrev() {
    if (navPosition > 0) {
      selectToken(navigableIndexes[navPosition - 1]);
    }
  }

  function goToNext() {
    if (navPosition !== -1 && navPosition < navigableIndexes.length - 1) {
      selectToken(navigableIndexes[navPosition + 1]);
    }
  }

  // "다음 모르는 단어" -- same forward-only walk as goToNext, but skips
  // ahead to the next `unknown`-status word instead of the immediate
  // neighbor. Search starts right after the current position (or from the
  // very start when nothing is selected yet), never wraps.
  function findNextUnknownPosition(): number {
    const startPos = activeIndex !== null ? navPosition : -1;
    for (let i = startPos + 1; i < navigableIndexes.length; i += 1) {
      if (tokens[navigableIndexes[i]].status === "unknown") {
        return i;
      }
    }
    return -1;
  }

  function goToNextUnknown() {
    const nextPos = findNextUnknownPosition();
    if (nextPos !== -1) {
      selectToken(navigableIndexes[nextPos]);
    }
  }

  // Re-selects the same word with no specific occurrence -- selectToken's
  // segmentKey=null default already falls back to the word's first
  // occurrence (see the scroll-into-view effect above), so this is enough
  // to jump back to it from any later occurrence.
  function goToFirstOccurrence() {
    if (activeIndex !== null) {
      selectToken(activeIndex);
    }
  }

  function scrollToTop() {
    readerTextRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const hasBookmarkScrollFraction =
    bookmarkScrollFractionRef.current !== null &&
    bookmarkScrollFractionRef.current !== undefined;
  // Label (and target) depend on what's actually available to jump back
  // to: a currently-selected word wins over the frozen scroll bookmark
  // (it's the more precise target), and the button disappears entirely
  // when neither exists.
  const bookmarkButtonLabel =
    activeIndex !== null
      ? "선택 단어로 이동"
      : hasBookmarkScrollFraction
        ? "마지막 위치로 이동"
        : null;

  function scrollToBookmark() {
    if (activeIndex !== null) {
      const selector = activeSegmentKey
        ? `[data-segment-key="${activeSegmentKey}"]`
        : `[data-token-index="${activeIndex}"]`;
      const target = readerTextRef.current?.querySelector(selector);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (hasBookmarkScrollFraction) {
      scrollToFraction(bookmarkScrollFractionRef.current as number, "smooth");
    }
  }

  const progressPercent = Math.round(scrollProgress * 100);
  const activeToken = activeIndex !== null ? tokens[activeIndex] : null;
  const hasNextUnknown = findNextUnknownPosition() !== -1;
  const isAtFirstOccurrence = activeSegmentKey === null;

  return (
    <div className="reader-mode hero-card">
      <div className="reader-mode-header-row">
        <div>
          <h3 className="reader-mode-title">읽기 모드</h3>
          <p className="reader-mode-hint">모르는 단어를 눌러보세요.</p>
        </div>
        <div className="reader-mode-toggles">
          <label className="checkbox-field reading-focus-toggle">
            <input
              type="checkbox"
              checked={focusMode}
              onChange={(event) => setFocusMode(event.target.checked)}
            />
            모르는/헷갈리는 단어만 강조
          </label>
          <label className="checkbox-field reading-jlpt-toggle">
            <input
              type="checkbox"
              checked={showJlptTags}
              onChange={(event) => setShowJlptTags(event.target.checked)}
            />
            JLPT 태그 표시
          </label>
        </div>
      </div>
      <div className="reader-progress-row">
        <div className="reader-progress-info">
          <span className="reader-progress-percent">
            읽기 진행률 {progressPercent}%
          </span>
          {navPosition !== -1 ? (
            <span className="reader-progress-token-count">
              {navPosition + 1} / {navigableIndexes.length} 단어 확인 중
            </span>
          ) : null}
        </div>
        <div
          className="reader-progress-bar"
          role="progressbar"
          aria-label="읽기 진행률"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progressPercent}
        >
          <div
            className="reader-progress-bar-fill"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <div className="reader-progress-actions">
          {bookmarkButtonLabel ? (
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={scrollToBookmark}
            >
              {bookmarkButtonLabel}
            </button>
          ) : null}
          <button
            type="button"
            className="ghost-button compact-button"
            onClick={scrollToTop}
          >
            맨 위로
          </button>
        </div>
      </div>
      <div className="reader-legend">
        <span className="legend-title">단어 상태 색상</span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-known" /> 아는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-uncertain" /> 헷갈리는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-unknown" /> 모르는 단어
        </span>
        <span className="legend-item">
          <span className="legend-swatch token-chip-unclassified" /> 미분류
        </span>
      </div>
      <div className="reader-text" ref={readerTextRef}>
        {layout.lines.map((line, lineIndex) => (
          <p className="reader-line" key={`line-${lineIndex}`}>
            {line.length > 0
              ? line.map((segment) =>
                  segment.type === "token" ? (
                    <TokenChip
                      key={segment.key}
                      token={tokens[segment.tokenIndex]}
                      tokenIndex={segment.tokenIndex}
                      segmentKey={segment.key}
                      isActive={activeIndex === segment.tokenIndex}
                      focusMode={focusMode}
                      showJlptTags={showJlptTags}
                      onSelect={() => selectToken(segment.tokenIndex, segment.key)}
                    />
                  ) : (
                    <span key={segment.key}>{segment.content}</span>
                  ),
                )
              : " "}
          </p>
        ))}
      </div>
      {layout.unmatchedTokenIndexes.length > 0 ? (
        <div className="reader-unmatched-row">
          <span className="reader-unmatched-label">
            원문 위치를 찾지 못한 단어
          </span>
          <div className="reader-unmatched-chips">
            {layout.unmatchedTokenIndexes.map((tokenIndex) => (
              <TokenChip
                key={`unmatched-${tokenIndex}`}
                token={tokens[tokenIndex]}
                tokenIndex={tokenIndex}
                isActive={activeIndex === tokenIndex}
                focusMode={focusMode}
                showJlptTags={showJlptTags}
                onSelect={() => selectToken(tokenIndex)}
              />
            ))}
          </div>
        </div>
      ) : null}
      {activeToken ? (
        <TokenDetailSheet
          token={activeToken}
          onClose={closeDetail}
          onStatusChange={(status) => {
            if (activeIndex !== null) {
              onStatusChange(activeIndex, status);
            }
          }}
          onPrevious={goToPrev}
          onNext={goToNext}
          canGoPrevious={canGoPrev}
          canGoNext={canGoNext}
          onNextUnknown={goToNextUnknown}
          canGoNextUnknown={hasNextUnknown}
          onFirstOccurrence={goToFirstOccurrence}
          canGoFirstOccurrence={!isAtFirstOccurrence}
          positionLabel={
            navPosition !== -1
              ? `${navPosition + 1} / ${navigableIndexes.length}`
              : null
          }
          isInBasket={isTokenInBasket(activeToken)}
          canAddToBasket={canAddToBasket(activeToken)}
          onToggleBasket={() => onToggleBasket(activeToken)}
          meaningEditItemId={meaningEditItemId}
          meaningEditDraft={meaningEditDraft}
          isSavingMeaningEdit={isSavingMeaningEdit}
          meaningEditMessage={meaningEditMessage}
          onStartMeaningEdit={onStartMeaningEdit}
          onMeaningEditDraftChange={onMeaningEditDraftChange}
          onSaveMeaningEdit={onSaveMeaningEdit}
          onCancelMeaningEdit={onCancelMeaningEdit}
          onReportMeaning={onReportMeaning}
        />
      ) : (
        // Desktop-only idle Word Inspector: docked in the same spot
        // TokenDetailSheet occupies once a word is selected (see
        // .token-sheet-overlay-idle in globals.css, hidden below the
        // 641px breakpoint) so the panel reads as "always there", not
        // something that only appears after a click. Mobile intentionally
        // shows nothing here -- the bottom-sheet inspector only appears
        // on demand there, per the reader-workspace mobile spec.
        <div
          className="token-sheet-overlay token-sheet-overlay-idle"
          aria-hidden="true"
        >
          <div className="token-sheet token-sheet-idle">
            <StudyCompanion mood="reading" size="sm" />
            <p className="token-sheet-idle-text">
              원문에서 모르는 단어를 눌러보세요.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
